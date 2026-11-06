"""Is this group message a product enquiry, and what is being asked for?

A sales group is mostly not sales. Greetings, thanks, forwarded links, delivery
chasers and small talk all arrive on the same webhook as "need 10 chargers",
and answering any of them would make the number look like a bot to every member
at once.

Two gates, cheapest first:

1. `_looks_worth_asking` throws out what obviously is not an enquiry - one-word
   messages, bare emoji, bare links - without spending an API call.
2. The AI is asked for a strict JSON verdict plus the term to search on.

If the AI is off, unconfigured or unreachable, `classify` still answers. It
falls back to the tracker's own keyword search: whatever the catalog matches is
treated as the enquiry. The feature degrades; it never stalls, and it never
raises into the webhook.
"""

import base64
import io as _io
import json
import logging
import re
import time

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

_PROMPT = """You classify messages posted in a WhatsApp group used by a trading company.

Answer with ONLY a JSON object and nothing else:
{"is_product": true or false, "search_term": "<short product name in English>", "quantity": <integer or null>, "confidence": <0.0 to 1.0>}

Set is_product to true ONLY when the message asks about buying, pricing or the
availability of a physical product. Set it to false for greetings, thanks,
small talk, forwarded news, links, payment or delivery status questions, and
complaints about an existing order.

search_term must be the product itself, without words like "need", "want",
"price", "do you have". Translate it to English if the message is not.
Correct obvious misspellings to the name the manufacturer uses - "Samsng
Galxy S23" is "Samsung Galaxy S23" - and keep is_product true when the
wording is a recognisable attempt at a real product.

Message:
<<<%s>>>"""

NL = chr(10)

# Messages that cannot be an enquiry, checked before paying for a call.
_URL_ONLY = re.compile(r'^\s*https?://\S+\s*$', re.IGNORECASE)
_HAS_LETTER_OR_DIGIT = re.compile(r'[A-Za-z0-9؀-ۿऀ-ॿഀ-ൿ]')


# Words that make a message a request for goods even when the catalog has
# never heard of the item. Only consulted when the AI could not answer, so a
# rough list beats no list: the alternative is silence on every product we do
# not already stock, which is the one case sourcing exists for.
_PART_WORDS = frozenset("""
screen glass backglass lcd display touch digitizer panel folder combo
battery charger adapter cable cord wire plug socket pin dock hub otg
case cover housing frame back door lens camera speaker mic buzzer ringer
board motherboard ic flex connector strip ribbon jack antenna vibrator
earphone earphones headphone headphones headset earbuds airpods airpod
powerbank protector tempered film holder stand mount tray sim button
keyboard mouse ram ssd hdd smps cabinet monitor printer toner cartridge
charging port jack module sensor fingerprint touchpad hinge palmrest
""".split())

# A brand plus a model-shaped token is the other way in - "Samsung s24 ultra"
# is plainly a product even with no parts word attached.
_BRAND_WORDS = frozenset("""
samsung apple iphone ipad ipod macbook airpods redmi xiaomi mi poco oppo
vivo realme oneplus nothing iqoo nokia moto motorola infinix tecno itel
lava micromax honor huawei asus acer hp dell lenovo msi sony lg google
pixel jbl boat noise blackberry panasonic philips tcl toshiba
logitech anker belkin sandisk kingston seagate transcend corsair razer
microsoft surface amazon gopro canon epson brother tplink tp-link dlink
netgear zebronics ambrane portronics syska mivi hikvision
""".split())

_MODEL_TOKEN = re.compile(r'\b[a-z]{0,3}\d{1,4}[a-z]{0,3}\b')

# Short pleasantries that would otherwise sail through on length alone.
_CHATTER_WORDS = frozenset("""
hi hello hey ok okay okey yes yeah yep no nope thanks thank welcome
please sorry bye good morning evening night afternoon sir madam bro
""".split())

class SaAiClassifier(models.AbstractModel):
    _name = 'sa.ai.classifier'
    _description = 'Sales Automation Message Classifier'

    # ----------------------------------------------------------
    # Public
    # ----------------------------------------------------------
    @api.model
    def classify(self, text, settings=None, use_ai=True):
        """Return {'is_product', 'search_term', 'quantity', 'confidence', 'source'}.

        `source` says which gate decided: 'prefilter', the provider name, or
        'catalog' when the AI was skipped or failed and keyword search stood in.
        """
        blank = {
            'is_product': False, 'search_term': '', 'quantity': None,
            'confidence': 0.0, 'source': 'prefilter',
        }
        text = (text or '').strip()
        if not self._looks_worth_asking(text):
            return blank

        if use_ai:
            settings = settings or self.env['sa.ai.settings'].sudo().get_settings()
            if settings.active:
                result = self._classify_with_ai(text, settings)
                if result is not None:
                    return self._sa_normalise(result, text)

        return self._sa_normalise(self._classify_with_catalog(text), text)

    # Padding that surrounds a product name without being part of it.
    # Trimmed from the ends only, so "charger for hp" keeps its middle.
    _SA_TERM_FILLER = frozenset("""
    i we you me my our us do does did can could would will shall u ur
    need needs needed want wants wanted looking searching search get
    give gimme send share provide provides tell show find
    have has had any some the a an is are am was were be
    please pls plz kindly urgent urgently asap now today
    sir madam mam bro bhai dear friend boss hi hello hey hai
    ok okay thanks thank thankyou ty required require requirement
    available availability stock price rate quote quotation cost
    of for from to in on at with and or
    """.split())

    # Kept alongside letters and digits. Everything else - emoji, arrows,
    # stickers, decorative bullets - is stripped.
    _SA_TERM_KEEP = ".-+/&'()"

    @api.model
    def _sa_clean_term(self, text):
        """The product name, without the padding it arrived wrapped in.

        Two jobs. Emoji and decoration come out, because they are not part of
        a product name: a customer wrote "i want lenova laptop charger \U0001F64F"
        and the assistant repeated that back word for word, searched the
        catalog for it, and put it to suppliers as the item being priced.

        Then the courtesy words are trimmed from the ends - "i want", "please",
        "sir". Only from the ends: "charger for hp" would be ruined by
        removing "for" wherever it appears.

        Returns '' when nothing recognisable is left, so the caller can fall
        back to what the customer actually typed rather than to a blank.
        """
        raw = text or ''
        kept = ''.join(ch if (ch.isalnum() or ch.isspace()
                              or ch in self._SA_TERM_KEEP) else ' '
                       for ch in raw)
        words = kept.split()
        while words and words[0].lower().strip(".-+/&'()") in self._SA_TERM_FILLER:
            words.pop(0)
        while words and words[-1].lower().strip(".-+/&'()") in self._SA_TERM_FILLER:
            words.pop()
        return ' '.join(words).strip()

    @api.model
    def _sa_normalise(self, verdict, text):
        """Clean the search term on every path out of `classify`.

        Falls back to the cleaned message, then to the message itself: a term
        is what gets searched, echoed to the customer and sent to a supplier,
        and an empty one is worse than a padded one.
        """
        if not verdict or not verdict.get('is_product'):
            return verdict
        term = (self._sa_clean_term(verdict.get('search_term') or '')
                or self._sa_clean_term(text)
                or (verdict.get('search_term') or text or '').strip())
        if not self._sa_term_is_meaningful(term):
            _logger.info("Sales Automation: %r is not a product name - "
                         "not sourcing it", term[:40])
            return {'is_product': False, 'search_term': '', 'quantity': None,
                    'confidence': 0.0,
                    'source': verdict.get('source') or 'catalog'}
        return dict(verdict, search_term=term)

    @api.model
    def _sa_term_is_meaningful(self, term):
        """Could this be the name of something somebody sells?

        Two refusals, both from the same afternoon of testing.

        *No letters at all.* "6656+" was quoted at 540.00. The catalog's
        keyword search is spacing-blind and matched a product on the digits
        alone; the plausibility rules then threw that product out, which left
        no evidence whatsoever that this was an enquiry - and the code carried
        on and asked suppliers to price "6656+". Nothing is named in digits
        and punctuation.

        *A leaned-on key.* "yyyy" and "yaaaa" have letters and pass every
        other test. Three of the same letter in a row is not a word in any
        language we sell in, and no product name has one - while "oppo" and
        "cable", which doubled letters would have caught, do not.

        Letters only: digits repeat perfectly normally. The first version of
        this rule counted any character, refused "5000mah powerbank" over the
        three zeros, and would have taken every 10000mAh battery and 1000W
        inverter with it.
        """
        import re
        letters = [ch for ch in (term or '') if ch.isalpha()]
        if not letters:
            return False
        if re.search(r'([a-z])\1{2,}', (term or '').lower()):
            return False
        return True

    # ----------------------------------------------------------
    # Gate 1 - free
    # ----------------------------------------------------------
    @api.model
    def _looks_worth_asking(self, text):
        if not text or len(text) < 3:
            return False
        if text == '[voice note]':
            return False
        if _URL_ONLY.match(text):
            return False
        if not _HAS_LETTER_OR_DIGIT.search(text):
            return False  # emoji, punctuation, stickers
        if len(text.split()) < 2:
            # A single word can still be a product name ("chargers"), so this
            # is not a rejection - only long enough words are worth a call.
            return len(text) >= 4
        return True

    # ----------------------------------------------------------
    # Gate 2 - the AI
    # ----------------------------------------------------------
    @api.model
    def _classify_with_ai(self, text, settings):
        """The provider's verdict, or None to fall through to the catalog."""
        key = settings._effective_key()
        if not key:
            _logger.info("Sales Automation: no API key for %s, using catalog "
                         "matching instead.", settings.provider)
            return None

        base_timeout = max(5, settings.timeout_seconds or 20)
        for index, model in enumerate(self._model_ladder(settings)):
            # Stand-ins are slower than the first choice - 3.6-flash measured
            # 22.9s against 3.5-flash's 3.0s - so a timeout tuned for the fast
            # model would fail them all on principle. Not unlimited either:
            # this runs inside the WhatsApp webhook, which is waiting.
            timeout = base_timeout if not index else max(base_timeout, 30)
            try:
                raw = self._provider_call(text, key, settings, model, timeout)
            except Exception as err:  # noqa: BLE001 - a dead API must not eat the message
                _logger.warning("Sales Automation: %s/%s classification failed "
                                "(%s)", settings.provider, model, err)
                if not self._worth_another_model(err):
                    break
                continue

            parsed = self._parse_verdict(raw)
            if parsed is None:
                _logger.warning("Sales Automation: %s/%s returned something "
                                "that was not JSON: %r", settings.provider,
                                model, (raw or '')[:200])
                continue
            parsed['source'] = settings.provider
            if index:
                _logger.info("Sales Automation: %s answered on stand-in model "
                             "%s", settings.provider, model)
            return parsed
        return None

    # ----------------------------------------------------------
    # Free-form JSON and pictures, for the guided finder
    # ----------------------------------------------------------
    @api.model
    def _parse_json_any(self, raw):
        """A dict or list out of whatever the model wrapped it in."""
        text = (raw or '').strip()
        if text.startswith('```'):
            text = re.sub(r'^```[a-zA-Z]*\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
        starts = [i for i in (text.find('{'), text.find('[')) if i >= 0]
        if not starts:
            return None
        start = min(starts)
        end = max(text.rfind('}'), text.rfind(']'))
        if end <= start:
            return None
        try:
            return json.loads(text[start:end + 1])
        except ValueError:
            return None

    @api.model
    def _call_gemini_json(self, prompt, timeout=None):
        """Ask Gemini for JSON with our own prompt. None when it cannot."""
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        if settings.provider != 'gemini' or not settings.active:
            return None
        key = settings._effective_key()
        if not key:
            return None
        base = max(5, settings.timeout_seconds or 20)
        for index, model in enumerate(self._model_ladder(settings)):
            try:
                raw = self._call_gemini(prompt, key, model,
                                        timeout or (base if not index
                                                    else max(base, 30)))
            except Exception as err:  # noqa: BLE001 - the finder degrades
                _logger.warning("Sales Automation: gemini/%s suggestion call "
                                "failed (%s)", model, err)
                if not self._worth_another_model(err):
                    break
                continue
            parsed = self._parse_json_any(raw)
            if parsed is not None:
                return parsed
        return None

    @api.model
    def _call_gemini_image(self, prompt, timeout=45):
        """A JPEG drawn by Gemini, or (b'', '').

        The text call discards `inlineData`; this one keeps it. The picture
        is normalised through Pillow - RGB, at most 1024px, JPEG - so what is
        stored and sent is the same size whatever the model returned.
        """
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        key = settings._effective_key() if settings.provider == 'gemini' else ''
        if not key:
            return b'', ''
        models_to_try = []
        for name in (getattr(settings, 'finder_image_model', '') or
                     'gemini-3.1-flash-image',
                     getattr(settings, 'finder_image_fallback_model', '') or
                     'gemini-2.5-flash-image'):
            if name and name not in models_to_try:
                models_to_try.append(name)
        for model in models_to_try:
            try:
                response = requests.post(
                    'https://generativelanguage.googleapis.com/v1beta/models/'
                    '%s:generateContent' % model,
                    headers={'Content-Type': 'application/json',
                             'x-goog-api-key': key},
                    json={'contents': [{'parts': [{'text': prompt}]}],
                          'generationConfig': {
                              'responseModalities': ['IMAGE', 'TEXT']}},
                    timeout=timeout)
                response.raise_for_status()
                body = response.json()
                parts = ((body.get('candidates') or [{}])[0].get('content')
                         or {}).get('parts') or []
                for part in parts:
                    inline = part.get('inlineData') or part.get('inline_data')
                    if inline and inline.get('data'):
                        raw = base64.b64decode(inline['data'])
                        return self._sa_normalise_picture(raw), 'image/jpeg'
                _logger.info("Sales Automation: %s returned no image part",
                             model)
            except Exception as err:  # noqa: BLE001 - a picture is optional
                _logger.warning("Sales Automation: image from %s failed (%s)",
                                model, err)
        return b'', ''

    @api.model
    def _sa_normalise_picture(self, raw):
        try:
            from PIL import Image
            image = Image.open(_io.BytesIO(raw)).convert('RGB')
            image.thumbnail((1024, 1024))
            out = _io.BytesIO()
            image.save(out, format='JPEG', quality=85, optimize=True)
            return out.getvalue()
        except Exception as err:  # noqa: BLE001 - send what we got
            _logger.info("Sales Automation: picture not normalised (%s)", err)
            return raw

    @api.model
    def _sa_suggest(self, kind, key_parts, prompt, field, shape=str, cap=12):
        """Cached list of suggestions for the finder; [] when nothing."""
        Suggest = self.env['sa.ai.suggestion'].sudo()
        key = Suggest._key(*key_parts)
        cached = Suggest.recall(kind, key)
        if isinstance(cached, list):
            return cached
        parsed = self._call_gemini_json(prompt)
        if parsed is None:
            # Nothing came back - quota, timeout, outage. Not an answer, so
            # not cached: a week of "no brands" would follow one bad minute.
            return []
        items = []
        if isinstance(parsed, dict):
            parsed = parsed.get(field) or []
        if isinstance(parsed, list):
            seen = set()
            for item in parsed:
                if shape is dict:
                    if not isinstance(item, dict):
                        continue
                    label = str(item.get('label') or '').strip()
                    keywords = [str(k).strip().lower() for k in
                                (item.get('keywords') or []) if str(k).strip()]
                    value = {'label': label, 'keywords': keywords[:6]}
                else:
                    label = str(item or '').strip()
                    value = label
                if (not label or len(label) < 2 or len(label) > 60
                        or '|' in label or '\n' in label
                        or label.lower() in seen):
                    continue
                seen.add(label.lower())
                items.append(value)
                if len(items) >= cap:
                    break
        Suggest.store(kind, key, data=items,
                      model_used=self.env['sa.ai.settings'].sudo()
                      .get_settings()._effective_model())
        return items

    @api.model
    def is_quotable(self, term):
        """Could a supplier price this as written? True / False / None.

        None means we could not tell - quota, timeout, outage. The caller
        keeps its old behaviour in that case rather than blocking an enquiry
        on an answer that never came.

        Cached like the other suggestions: the same words come round again and
        again in a sales group, and this verdict does not change week to week.
        """
        term = (term or '').strip()
        if not term:
            return None
        Suggest = self.env['sa.ai.suggestion'].sudo()
        key = Suggest._key('quotable', term.lower())
        cached = Suggest.recall('quotable', key)
        if isinstance(cached, list) and cached:
            return cached[0] == 'specific'

        prompt = (
            'A wholesale shop forwards WhatsApp product enquiries to suppliers '
            'for a price.\nEnquiry: "%s"\n\n'
            'Could a supplier quote a price for this WITHOUT asking anything '
            'back?\n'
            '- A category or generic type ("mobile phone", "computer parts", '
            '"battery", "led tv") is NOT quotable.\n'
            '- A brand plus a category with no model ("hp laptop", "samsung '
            'tv") is NOT quotable.\n'
            '- A concrete model or part, or a spec that pins the item down '
            '("65W charger", "vivo V30 back panel", "iPhone 15 Pro 256GB"), '
            'IS quotable.\n\n'
            'Return JSON only: {"quotable": true|false}' % term[:120])
        parsed = self._call_gemini_json(prompt)
        if not isinstance(parsed, dict) or 'quotable' not in parsed:
            return None
        verdict = bool(parsed.get('quotable'))
        Suggest.store('quotable', key,
                      data=['specific' if verdict else 'generic'],
                      model_used=self.env['sa.ai.settings'].sudo()
                      .get_settings()._effective_model())
        return verdict

    @api.model
    def suggest_types(self, word):
        prompt = (
            'You help an Indian electronics retailer guide a WhatsApp customer '
            'who typed a generic product word.\nProduct word: "%s"\n'
            'Return JSON only: {"types":[{"label":"<2-4 word sub-type a shopper '
            'would recognise>","keywords":["<lowercase words that would appear '
            'in product names of this type>"]}]}\n'
            'Rules: 4 to 8 types, mutually exclusive, most popular first, labels '
            'under 30 characters, no brand names, no prices. If the word is not '
            'a product return {"types":[]}.' % word)
        return self._sa_suggest('types', ('types', word), prompt, 'types',
                                shape=dict, cap=8)

    @api.model
    def suggest_brands(self, word, type_label):
        prompt = (
            'Indian electronics market. Product: "%s %s".\n'
            'Return JSON only: {"brands":["<brand>", ...]} with 6 to 12 brands '
            'actually sold in India for this exact product type, most popular '
            'first, official spelling, no duplicates, no descriptions.'
            % (type_label, word))
        return self._sa_suggest('brands', ('brands', word, type_label), prompt,
                                'brands', cap=12)

    @api.model
    def suggest_models(self, word, type_label, brand):
        prompt = (
            'Indian electronics market, year %s. Brand: "%s". Product type: '
            '"%s %s".\nReturn JSON only: {"models":["<Brand Model-name>", ...]} '
            'listing 5 to 10 current or recent models of this brand and type '
            'sold in India, most popular first, each as the brand followed by '
            'the official model name (e.g. "Sony WH-CH520"), no colours, no '
            'prices, no duplicates.'
            % (time.strftime('%Y'), brand, type_label, word))
        return self._sa_suggest('models', ('models', word, type_label, brand),
                                prompt, 'models', cap=10)

    @api.model
    def _model_ladder(self, settings):
        """Which models to try, in order.

        Gemini's free tier meters per model per day, so a 429 on the first one
        says nothing about the second - and stopping there drops to catalog
        matching, which by definition cannot recognise a product that is not in
        the catalog. That is the exact case sourcing exists for, so it is worth
        one more call before giving up.
        """
        ladder = [settings._effective_model()]
        if settings.provider == 'gemini':
            for alternate in ('gemini-3.6-flash', 'gemini-2.0-flash'):
                if alternate not in ladder:
                    ladder.append(alternate)
        return ladder[:2]

    @api.model
    def _worth_another_model(self, err):
        """True when the failure was about this model, not the request.

        Out of quota, model retired, or the provider overloaded - a different
        model can answer those. A bad key or malformed request will fail
        identically everywhere, and retrying only makes the customer wait.
        """
        response = getattr(err, 'response', None)
        status = getattr(response, 'status_code', None)
        if status in (404, 429, 500, 502, 503, 504):
            return True
        return status is None      # timeouts and connection errors carry none

    @api.model
    def _provider_call(self, text, key, settings, model=None, timeout=None):
        """Ask the configured provider to classify `text`. Raises on failure."""
        prompt = _PROMPT % text[:1000]
        timeout = timeout or max(5, settings.timeout_seconds or 20)
        model = model or settings._effective_model()
        if settings.provider == 'gemini':
            return self._call_gemini(prompt, key, model, timeout)
        # Groq, OpenAI and SinoRouter all speak the OpenAI wire format, so they
        # differ only by URL - which the settings resolve, override included.
        return self._call_openai_compatible(
            settings._effective_base_url(), prompt, key, model, timeout)

    # ----------------------------------------------------------
    # The test button - the one place a failure is shown, not swallowed
    # ----------------------------------------------------------
    @api.model
    def diagnose(self, text, settings):
        """Classify `text` and report exactly what happened, as plain text.

        `classify` deliberately hides every failure: a dead API must never stop
        a group message being handled, so it logs quietly and lets catalog
        matching answer. That is precisely wrong for a test button, where the
        whole point is to see the failure - a bad key, a model name the account
        does not serve, and a 404 on the endpoint are indistinguishable from
        the outside otherwise.
        """
        text = (text or '').strip()
        if not text:
            return 'Type a sample message above, then press Test Classifier.'

        lines = ['Message       : %s' % text]

        if not self._looks_worth_asking(text):
            return NL.join(lines + [
                'Prefilter     : REJECTED - too short, a bare link, or no '
                'letters and digits',
                '',
                'No API call was made, and none would be. In a live group this '
                'message is ignored in silence.',
            ])
        lines.append('Prefilter     : passed')

        if not settings.active:
            lines.append('Provider      : DISABLED - catalog matching only')
            return NL.join(lines + [''] + self._catalog_report(text))

        key = settings._effective_key()
        lines += [
            'Provider      : %s' % settings.provider,
            'Model         : %s' % (settings._effective_model() or '(none set)'),
            'Endpoint      : %s' % (settings._effective_base_url()
                                    or '(Gemini native call)'),
        ]
        if not key:
            return NL.join(lines + [
                'API key       : MISSING - no call made',
                '',
            ] + self._catalog_report(text))
        lines.append('API key       : set (%d chars)' % len(key))

        start = time.time()
        try:
            raw = self._provider_call(text, key, settings)
        except Exception as err:  # noqa: BLE001 - showing the error IS the job
            lines.append('Call          : FAILED after %d ms'
                         % int((time.time() - start) * 1000))
            response = getattr(err, 'response', None)
            if response is not None:
                lines.append('HTTP          : %s' % response.status_code)
                body = (response.text or '').strip()[:600]
                if body:
                    lines.append('Body          : %s' % body)
            lines += ['Error         : %s' % err, '']
            return NL.join(lines + self._catalog_report(text))

        lines.append('Call          : OK in %d ms'
                     % int((time.time() - start) * 1000))

        parsed = self._parse_verdict(raw)
        if parsed is None:
            return NL.join(lines + [
                'Reply         : NOT VALID JSON - the model ignored the format',
                'Raw           : %s' % (raw or '').strip()[:600],
                '',
            ] + self._catalog_report(text))

        lines += [
            '',
            'Verdict       : %s' % ('PRODUCT ENQUIRY' if parsed['is_product']
                                    else 'not a product enquiry'),
            'Confidence    : %.2f' % parsed['confidence'],
            'Search term   : %s' % (parsed['search_term'] or '-'),
            'Quantity      : %s' % (parsed['quantity'] or '-'),
            'Raw           : %s' % (raw or '').strip()[:400],
            '',
        ]
        if parsed['is_product']:
            lines += self._catalog_report(parsed['search_term'] or text,
                                          heading='Would quote')
        else:
            lines.append('The group would see no reply.')
        return NL.join(lines)

    @api.model
    def _catalog_report(self, text, heading='Catalog fallback'):
        """What keyword search finds - the outcome that actually ships."""
        products = self.env['wa.auto.reply'].sudo()._search_products(text, 3)
        if not products:
            return ['%-14s: nothing matched %r' % (heading, text[:60])]
        return ['%-14s: %s' % (heading, ', '.join(p.name for p in products))]

    @api.model
    def _call_gemini(self, prompt, key, model, timeout):
        url = ('https://generativelanguage.googleapis.com/v1beta/models/'
               '%s:generateContent' % model)
        response = requests.post(
            url,
            headers={'Content-Type': 'application/json', 'x-goog-api-key': key},
            json={
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {
                    'temperature': 0,
                    'responseMimeType': 'application/json',
                },
            },
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json()
        candidates = body.get('candidates') or []
        if not candidates:
            return ''
        parts = (candidates[0].get('content') or {}).get('parts') or []
        return ''.join(str(part.get('text') or '') for part in parts)

    @api.model
    def _call_openai_compatible(self, url, prompt, key, model, timeout,
                                json_mode=True):
        """POST one chat completion and return the assistant's text.

        `response_format: json_object` is asked for but not depended on. An
        aggregator fronting many models - SinoRouter, OpenRouter and the like -
        commonly rejects it with a 400 for models that have no JSON mode, so a
        400 is retried once without it. `_parse_verdict` digs the object out of
        prose or a fenced block either way, so nothing is lost by dropping it.
        """
        if not url:
            raise ValueError("no chat-completions URL configured for this provider")
        payload = {
            'model': model,
            'temperature': 0,
            'messages': [{'role': 'user', 'content': prompt}],
        }
        if json_mode:
            payload['response_format'] = {'type': 'json_object'}

        response = requests.post(
            url,
            headers={'Content-Type': 'application/json',
                     'Authorization': 'Bearer %s' % key},
            json=payload,
            timeout=timeout,
        )
        if response.status_code == 400 and json_mode:
            _logger.info("Sales Automation: %s refused JSON mode, retrying "
                         "without it.", url)
            return self._call_openai_compatible(
                url, prompt, key, model, timeout, json_mode=False)

        response.raise_for_status()
        choices = response.json().get('choices') or []
        if not choices:
            return ''
        return str((choices[0].get('message') or {}).get('content') or '')

    @api.model
    def _parse_verdict(self, raw):
        """Pull the JSON object out of whatever the model wrapped it in."""
        if not raw:
            return None
        text = raw.strip()
        if text.startswith('```'):
            text = re.sub(r'^```[a-zA-Z]*\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
        start, end = text.find('{'), text.rfind('}')
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(text[start:end + 1])
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None

        quantity = data.get('quantity')
        try:
            quantity = int(quantity) if quantity not in (None, '', False) else None
        except (TypeError, ValueError):
            quantity = None
        try:
            confidence = float(data.get('confidence') or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        return {
            'is_product': bool(data.get('is_product')),
            'search_term': str(data.get('search_term') or '').strip(),
            'quantity': quantity if (quantity or 0) > 0 else None,
            'confidence': max(0.0, min(1.0, confidence)),
        }

    # ----------------------------------------------------------
    # Fallback - the catalog decides
    # ----------------------------------------------------------
    @api.model
    def _classify_with_catalog(self, text):
        """No AI: if the tracker's keyword search finds products, it is one."""
        products = self.env['wa.auto.reply'].sudo()._search_products(text, 1)
        if not products:
            # Same spacing-blind pass the enquiry itself uses. Without it the
            # fallback calls "Powerbank" chatter and the message is dropped in
            # silence - which is what happens every time the AI is out of quota.
            products = self.env['sa.group.request'].sudo()._search_products_loose(text)
        if products:
            return {
                'is_product': True,
                'search_term': text,
                'quantity': None,
                # Deliberately at the default `min_confidence` of 0.6 rather
                # than 1.0: a keyword hit is weaker evidence than the AI saying
                # yes, and it must not sail past a threshold someone raised on
                # purpose.
                'confidence': 0.6,
                'source': 'catalog',
            }

        # Nothing in the catalog matched, which is not the same as "not a
        # product". "Samsung s24 ultra backglass" is obviously an enquiry and
        # obviously not in stock - and answering it is the whole point of
        # sourcing. With the AI unavailable the only evidence left is the
        # wording, so read that rather than dropping the message in silence.
        if self._looks_like_product_request(text):
            _logger.info("Sales Automation: %r is not in the catalog but reads "
                         "like a product request - sourcing it", text[:60])
            return {
                'is_product': True, 'search_term': text, 'quantity': None,
                'confidence': 0.6, 'source': 'wording',
            }

        return {
            'is_product': False, 'search_term': '', 'quantity': None,
            'confidence': 0.0, 'source': 'catalog',
        }

    @api.model
    def _looks_like_product_request(self, text):
        """Does this read like someone asking for goods?

        Reached only when the AI could not answer and the catalog held nothing.
        Kept narrow on purpose - a wrong yes messages real suppliers - so it
        wants either a parts word, or a brand alongside a model-shaped token.
        """
        lowered = (text or '').lower()
        words = [w.strip('.,!?:;()*_-') for w in lowered.split()]
        words = [w for w in words if w]
        if not 1 < len(words) <= 10:
            return False
        if all(w in _CHATTER_WORDS for w in words):
            return False

        vocabulary = _PART_WORDS | self._category_words()
        if any(word in vocabulary for word in words):
            return True
        has_brand = any(word in _BRAND_WORDS for word in words)
        return has_brand and any(_MODEL_TOKEN.fullmatch(w) for w in words)

    @api.model
    def _sa_brand_vocabulary(self):
        """Words that name a manufacturer."""
        return _BRAND_WORDS

    @api.model
    def _sa_part_vocabulary(self):
        """Words that name a component, for telling two parts of one device
        apart.

        Deliberately not the category names: "iPhone Parts" contributes
        "iphone", and treating that as a part made "iphone 15 pro screen" and
        "Iphone 15 Pro Max Charging Port" look like the same component. Brands
        are excluded for the same reason.
        """
        return _PART_WORDS - _BRAND_WORDS

    @api.model
    def _category_words(self):
        """Words from your own product categories, as extra parts words.

        The categories are named for what you actually sell - "Mobile Parts",
        "iPhone Parts" - so they tune this to the business without anyone
        maintaining a second list.
        """
        found = set()
        for name in self.env['product.category'].sudo().search([]).mapped('name'):
            for word in (name or '').lower().replace('/', ' ').split():
                word = word.strip('.,()&')
                if len(word) > 2 and word not in ('all', 'and', 'the', 'parts',
                                                  'other', 'saleable'):
                    found.add(word)
        return frozenset(found)
