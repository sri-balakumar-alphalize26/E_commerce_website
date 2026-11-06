# -*- coding: utf-8 -*-
"""A remark: one message that was removed for its language, pinned to the
person who sent it.

The webhook creates these; nobody types them in the normal course of things.
They are what the dashboards show as FLAGGED and what the `conduct` component
of the rating is made of. A manager can also add one by hand, and can delete
a wrong one - the rating recovers on the next recompute, because nothing is
stored but the remark itself.

Matching is whole-word only. "Scunthorpe", "assistant" and "classic" contain
rude substrings and must never hit; a typed "fuuuuck" or "sh1t" must. So a
message word is tried as typed, with leet digits mapped to letters, and with
repeated letters collapsed - against a list that is kept literal.
"""
import base64
import json
import logging
import re
import unicodedata

import requests
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Leet: only applied to the message, never to the list, so "3ars" can sit in
# the list as typed while a plain "ears" in a message stays clean.
_LEET = str.maketrans({'0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's',
                       '7': 't', '@': 'a', '$': 's', '!': 'i'})
# Letters and digits of the scripts the shops actually type in: Latin,
# Arabic, Devanagari (Hindi), Tamil, Malayalam. Everything else is a gap.
_KEEP = re.compile(r'[^a-z0-9؀-ۿऀ-ॿ஀-௿'
                   r'ഀ-ൿ\s]+')


def _norm(text):
    t = unicodedata.normalize('NFKC', str(text or '')).lower()
    return _KEEP.sub(' ', t)


def _tail(value):
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return digits[-9:] if len(digits) >= 9 else digits


def _default_conduct_words():
    """A starting list, one word per line, editable in AI Settings. Local
    slang is the owner's to add; this is the common core in the languages
    the groups use, script and typed-in-English-letters both."""
    return '\n'.join([
        '# One word per line. Lines starting with # are ignored.',
        '# Whole words only: "class" or "assistant" never match.',
        '# --- English',
        'fuck', 'fucker', 'fucking', 'fuk', 'fck', 'motherfucker', 'shit',
        'bullshit', 'bitch', 'bastard', 'asshole', 'arsehole', 'dick',
        'dickhead', 'cunt', 'pussy', 'slut', 'whore', 'wanker', 'prick',
        'moron', 'retard', 'scumbag', 'wtf', 'stfu',
        '# --- Sexual content',
        'sex', 'sexy', 'sexx', 'porn', 'porno', 'xxx', 'nude', 'nudes', 'boobs',
        'horny', 'blowjob', 'handjob', 'orgasm', 'penis', 'vagina', 'condom',
        'kambi', 'kundi', 'mulai', 'chut', 'sexi', 'jins',
        '# --- Toilet talk and drugs',
        'pee', 'piss', 'poop', 'fart', 'crap', 'turd', 'ganja', 'weed', 'drugs', 'smoking',
        'cocaine', 'heroin', 'moothram', 'theetam', 'appi', 'peshab', 'tatti',
        '# --- Hindi (typed in English letters)',
        'chutiya', 'chutiye', 'chutiyа', 'madarchod', 'maderchod', 'behenchod',
        'bhenchod', 'bhosdike', 'bhosdi', 'gandu', 'gaandu', 'gaand', 'harami',
        'kamina', 'kamine', 'randi', 'saala', 'saale', 'lund', 'lawda',
        'chodu', 'bakchod', 'kutta', 'kutte', 'kutti',
        '# --- Hindi (script)',
        'चूतिया', 'मादरचोद', 'भेनचोद', 'भोसड़ी', 'गांडू', 'हरामी', 'रंडी', 'लंड', 'कुत्ते',
        '# --- Malayalam (typed in English letters)',
        'myru', 'myre', 'mairu', 'maire', 'mayir', 'mayiru', 'mayru', 'mayre', 'poori', 'pooru', 'poore', 'kunna',
        'kunne', 'thayoli', 'thayoly', 'nayinte', 'naayinte', 'koothichi',
        'pundachi', 'thendi', 'oombu', 'oomb', 'umbu', 'pottan', 'potti', 'mundam',
        'mundan', 'munda', 'mandan', 'mandi', 'kazhuveri', 'kazhuvery', 'kazhutha',
        'kazhuthe', 'mayuir', 'myrandi', 'poorimon', 'poorimone', 'pundachimon', 'naari',
        '# --- Malayalam (script)',
        'മൈര്', 'മൈരേ', 'പൂറ്', 'പൂറി', 'കുണ്ണ', 'തായോളി', 'നായിന്റെ', 'കൂത്തിച്ചി', 'തെണ്ടി',
        '# --- Tamil (typed in English letters)',
        'punda', 'pundai', 'ommala', 'thevidiya', 'thevdiya', 'baadu',
        'sunni', 'koodhi', 'otha', 'othu', 'oothu', 'kena', 'naaye', 'kazhuthai',
        '# --- Tamil (script)',
        'புண்ட', 'புண்டை', 'ஓம்மாள', 'தேவடியா', 'பாடு', 'சுன்னி', 'கூதி', 'ஓத்தா', 'நாயே',
        '# --- Arabic (script)',
        'كس', 'كسمك', 'كسختك', 'خرا', 'خرة', 'زب', 'زبي', 'شرموطة', 'شرموط', 'عرص',
        'قحبة', 'عاهرة', 'منيوك', 'منيك', 'خول', 'طيز', 'يلعن', 'حقير', 'زبالة',
        '# --- Arabic (typed in English letters)',
        'kos', 'koss', 'kosomak', 'kosommak', 'kosokhtak', 'sharmouta',
        'sharmota', 'sharmoota', '3ars', 'ars', 'khara', 'kharra', 'zeb',
        'zib', 'zebi', 'zobi', 'teez', 'tiz', 'manyak', 'manyouk', 'khawal',
        'kahba', 'qahba', 'ya7mar', 'ya5ara',
    ])


_URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"']+"
    r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|xyz|xxx|tv|to|io|me|co|in|ae|"
    r"info|biz|club|site|online|live|top|vip|cc|ws|pro|sex|porn|cam|link|app)"
    r"(?:/[^\s<>\"']*)?", re.I)

DEFAULT_MEDIA_PROMPT = (
    "You moderate a shop's WhatsApp sales group. Look at this image (it may be "
    "a video's thumbnail). Answer only JSON: {\"sexual\": true or false, "
    "\"reason\": \"a few words\"}. sexual is true for pornography, nudity, "
    "sexual acts, sexually explicit or suggestive content, or adult-site "
    "adverts. Product photos, people in normal clothes, documents and memes "
    "are false.")


def _default_conduct_link_words():
    return '\n'.join([
        '# One fragment per line, matched anywhere in a link address.',
        'porn', 'xxx', 'sex', 'xvideos', 'xnxx', 'xhamster', 'redtube',
        'youporn', 'brazzers', 'onlyfans', 'hentai', 'nsfw', 'camgirl',
        'chaturbate', 'stripchat', 'livejasmin', 'bongacams', 'nude', 'erotic',
        'escort', 'adult', 'hotgirl', 'desixxx', 'mallu', 'masala', 'bluefilm',
        'blue-film', 'sexvideo', 'sex-video', 'fuck', 'boobs', 'milf', 'cam4',
    ])


DEFAULT_TEXT_PROMPT = (
    "You moderate a shop's WhatsApp sales group in India / the Gulf. Members "
    "may write in English, Malayalam, Tamil, Hindi or Arabic, often in Latin "
    "letters. Decide whether this message is abusive, insulting, obscene, "
    "sexual or adult content. Ordinary haggling, complaints and product talk "
    "are NOT abusive. Answer only JSON: {\"abusive\": true or false, "
    "\"confidence\": 0-100, \"reason\": \"a few words\"}.\n\nMessage: %s")


def _default_conduct_doubtful_words():
    return '\n'.join([
        '# Rude only sometimes: not removed on their own, the AI model decides.',
        'hot', 'kiss', 'naked', 'bikini', 'lick', 'suck', 'balls', 'ass',
        'damn', 'hell', 'stupid', 'idiot', 'fool', 'dog', 'pig', 'donkey',
        'shut up', 'loser', 'useless', 'cheat', 'cheater', 'fraud', 'thief',
        'poda', 'podi', 'po', 'sakkitham', 'nayi', 'patti', 'pottan', 'mandan',
        'kalla', 'kallan', 'thief', 'loosu', 'paithiyam', 'pagal', 'gadha',
        'mental', 'waste', 'bekar', 'mookan', 'muttal', 'moodan',
        'kutta', 'ullu', 'kalb', 'himar', 'hmar', 'ghabi', 'gabi', 'tafsh',
        'smoke', 'cigarette', 'beer', 'alcohol', 'drunk', 'wine', 'saniyan', 'sanian',
        'kothi', 'kothiyan', 'venna',
        'whisky', 'vodka', 'bar', 'hangover', 'high',
    ])


_FOLD = (('ai', 'y'), ('ay', 'y'), ('ei', 'y'), ('ey', 'y'), ('oo', 'u'), ('ee', 'i'),
         ('ou', 'u'), ('th', 't'), ('dh', 'd'), ('bh', 'b'), ('gh', 'g'), ('kh', 'k'),
         ('ph', 'f'), ('ch', 'c'), ('sh', 's'), ('zh', 'l'), ('ck', 'k'), ('q', 'k'),
         ('c', 'k'), ('w', 'v'), ('z', 's'), ('x', 'ks'))


def _skeleton(word):
    """A crude sound-alike key for words typed in English letters: vowel
    spellings folded, aspirates dropped, repeats collapsed, vowels removed
    except a leading one. mayir / mayiru / mairu / myru / myre -> "myr";
    othu / otha -> "ot". Used only to raise doubt, never to remove."""
    w = word
    for a, b in _FOLD:
        w = w.replace(a, b)
    w = re.sub(r'(.)+', r'', w)
    return (w[0] if w else '') + re.sub(r'[aeiou]', '', w[1:])


def _swap1(a, b):
    """True when swapping two adjacent letters turns a into b ("fcuk" ->
    "fuck"). Only swaps: a one-letter substitution would make "price" a
    near miss of "prick" and send every price message to the model."""
    if len(a) != len(b) or a == b:
        return False
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    return (len(diff) == 2 and diff[1] == diff[0] + 1
            and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])


def _default_conduct_safe_words():
    """Ordinary sales-chat words that must never be read as a near miss of a
    listed word (price ~ prick). Extend it whenever the model is asked about
    something obviously innocent."""
    return chr(10).join([
        '# Never doubtful, one per line.',
        'price', 'prices', 'priced', 'pricing', 'rate', 'rates', 'cost', 'costs',
        'more', 'other', 'others', 'order', 'orders', 'need', 'needs', 'want',
        'send', 'sent', 'colour', 'color', 'size', 'sizes', 'stock', 'available',
        'delivery', 'deliver', 'today', 'tomorrow', 'cash', 'pay', 'paid',
        'payment', 'thanks', 'thank', 'please', 'item', 'items', 'number',
        'quantity', 'piece', 'pieces', 'pack', 'packs', 'shirt', 'shirts',
        'pant', 'pants', 'shift', 'shifts', 'class', 'classes', 'classic',
        'assist', 'assistant', 'pass', 'password', 'mass', 'glass', 'grass',
        'brass', 'bass', 'duck', 'dock', 'deck', 'luck', 'truck', 'stuck',
        'sick', 'pick', 'kick', 'tick', 'thick', 'quick', 'stick', 'brick',
        'click', 'trick', 'punch', 'pitch', 'batch', 'match', 'watch', 'catch',
        'switch', 'witch', 'pool', 'tool', 'cool', 'school', 'wool', 'poor',
        'pure', 'pore', 'mary', 'many', 'money', 'shot', 'shop', 'ship', 'shut',
        'hit', 'hot', 'hat', 'cut', 'cup', 'cap', 'car', 'card', 'cart', 'cook',
        'book', 'look', 'hook', 'took',
    ])


def _default_conduct_phrases():
    return '\n'.join([
        '# Exact phrases, one per line.',
        'son of a bitch', 'go to hell', 'ibn el kalb', 'ابن الكلب', 'كس امك',
        'كس اختك', 'teri maa ki', 'teri maa ka', 'ninte amma', 'unga amma',
    ])


class SaConductRemark(models.Model):
    _name = 'sa.conduct.remark'
    _description = 'Conduct Remark (message removed for language)'
    _order = 'remarked_on desc, id desc'
    _rec_name = 'phone'

    kind = fields.Selection([('customer', 'Customer'), ('vendor', 'Supplier')],
                            required=True, default='customer', index=True)
    source = fields.Selection([('auto', 'Automatic'), ('manual', 'Manual')],
                              required=True, default='auto')
    remarked_on = fields.Datetime('When', required=True, index=True,
                                  default=fields.Datetime.now)
    phone = fields.Char('Phone', help="Digits as WhatsApp reported them.")
    phone_tail = fields.Char('Phone Tail', index=True, compute='_compute_tail',
                             store=True, readonly=False)
    lid = fields.Char('WhatsApp LID', index=True)
    participant_jid = fields.Char('Sender JID', help="Exactly as the payload "
                                  "carried it; what the delete call needs.")
    partner_id = fields.Many2one('res.partner', 'Contact', ondelete='set null')
    entity_id = fields.Many2one('sa.insight.entity', 'Rated Row',
                                ondelete='set null', index=True)
    session_id = fields.Many2one('whatsapp.session', 'Session', ondelete='set null')
    group_jid = fields.Char('Group')
    chat_label = fields.Char('Chat', compute='_compute_chat_label')
    wa_message_id = fields.Char('WhatsApp Message Id')
    message_id = fields.Many2one('whatsapp.message', 'Message Record',
                                 ondelete='set null')
    text = fields.Text('What They Wrote')
    matched_words = fields.Char('Matched')
    hit_type = fields.Selection([('word', 'Bad word'), ('link', 'Adult link'),
                                 ('media', 'Sexual photo/video'), ('doubt', 'Doubtful, model decided'),
                                 ('manual', 'Manual')],
                                'What', default='word', required=True)
    decided_by = fields.Selection([('local', 'Local list'), ('model', 'AI model'),
                                   ('model_down', 'Model unreachable, removed on doubt'),
                                   ('manual', 'Manager')], 'Decided By', default='local')
    confidence = fields.Integer('Confidence %', default=100)
    reason = fields.Char('Model Reason')
    severity = fields.Selection([('normal', 'Normal'), ('high', 'High')],
                                default='normal', required=True)
    deleted = fields.Boolean('Deleted in WhatsApp')
    delete_error = fields.Char('Delete Error')
    warned = fields.Boolean('Sender Warned')
    note = fields.Char('Note', help="For a manual remark: why.")
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company)

    @api.depends('phone')
    def _compute_tail(self):
        for r in self:
            r.phone_tail = _tail(r.phone)

    @api.depends('group_jid', 'kind')
    def _compute_chat_label(self):
        Group = self.env['sa.sales.group'].sudo()
        for r in self:
            if r.group_jid:
                g = Group.search([('group_jid', '=', r.group_jid)], limit=1)
                r.chat_label = g.name if g else r.group_jid.split('@')[0]
            else:
                r.chat_label = 'Private chat'

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------
    @api.model
    def _word_list(self, settings):
        out = set()
        for line in (settings.conduct_words or '').splitlines():
            w = line.strip().lower()
            if w and not w.startswith('#'):
                out.add(_norm(w).strip())
        out.discard('')
        return out

    @api.model
    def _phrase_list(self, settings):
        out = []
        for line in (settings.conduct_phrases or '').splitlines():
            p = line.strip()
            if p and not p.startswith('#'):
                n = ' '.join(_norm(p).split())
                if n:
                    out.append((p, n))
        return out

    @api.model
    def match_words(self, text, settings):
        """The listed words and phrases this text contains, or []."""
        if not text:
            return []
        bad = self._word_list(settings)
        norm = _norm(text)
        hits = []
        seen = set()
        for word in norm.split():
            variants = {word, word.translate(_LEET)}
            for v in list(variants):
                variants.add(re.sub(r'(.)\1{2,}', r'\1\1', v))  # fuuuuck -> fuuck
                variants.add(re.sub(r'(.)\1+', r'\1', v))       # fuuck -> fuck
            for v in variants:
                if v in bad and v not in seen:
                    seen.add(v)
                    hits.append(v)
        collapsed = ' '.join(norm.split())
        for raw, n in self._phrase_list(settings):
            if re.search(r'(?<!\S)%s(?!\S)' % re.escape(n), collapsed) and raw not in seen:
                seen.add(raw)
                hits.append(raw)
        return hits

    @api.model
    def _link_fragments(self, settings):
        out = set()
        for line in (settings.conduct_link_words or '').splitlines():
            w = line.strip().lower()
            if w and not w.startswith('#'):
                out.add(w)
        return out

    @api.model
    def match_links(self, text, settings):
        """Adult links in the text: ['link: pornhub.com', ...] or []."""
        if not text or not settings.conduct_links:
            return []
        frags = self._link_fragments(settings)
        bad = self._word_list(settings)
        hits = []
        for m in _URL_RE.finditer(text):
            url = m.group(0).lower()
            addr = re.sub(r'^(https?://|www\.)', '', url)
            host = addr.split('/')[0]
            tokens = set(re.split(r'[^a-z0-9]+', addr)) - {''}
            if any(f in addr for f in frags) or (tokens & bad):
                label = 'link: %s' % host
                if label not in hits:
                    hits.append(label)
        return hits

    # ------------------------------------------------------------------
    # Doubt: not on the list, but close enough to ask
    # ------------------------------------------------------------------
    @api.model
    def _doubtful_words(self, settings):
        out = set()
        for line in (settings.conduct_doubtful_words or '').splitlines():
            w = line.strip().lower()
            if w and not w.startswith('#'):
                out.add(' '.join(_norm(w).split()))
        out.discard('')
        return out

    @api.model
    def find_doubt(self, text, settings):
        """(score 0-100, [what looked wrong]). 60: a listed word hidden inside
        a longer word ("fuckin", "pornstar"); 55: two letters swapped in a
        listed word ("fcuk"); 50: a doubtful word. 0: nothing."""
        if not text:
            return 0, []
        bad = [w for w in self._word_list(settings) if len(w) >= 4]
        long_bad = bad
        doubtful = self._doubtful_words(settings)
        safe = set()
        for line in (getattr(settings, 'conduct_safe_words', '') or '').splitlines():
            w = line.strip().lower()
            if w and not w.startswith('#'):
                safe.add(w)
        norm = _norm(text)
        collapsed = ' '.join(norm.split())
        score, why = 0, []
        for word in norm.split():
            if word in safe or word.isdigit():
                continue
            variants = {word, word.translate(_LEET), re.sub(r'(.)\1+', r'\1', word)}
            for v in variants:
                if len(v) < 4 or v in safe:
                    continue
                for w in bad:
                    if w != v and w in v:
                        score = max(score, 60)
                        why.append('%s~%s' % (word, w))
                        break
                else:
                    for w in long_bad:
                        if _swap1(v, w):
                            score = max(score, 55)
                            why.append('%s~%s' % (word, w))
                            break
                    else:
                        # Sound-alike (typed Malayalam / Tamil / Hindi): same
                        # skeleton and same first two letters, so "more" is
                        # not a near miss of "myru" but "mayir" is.
                        sk = _skeleton(v)
                        if len(sk) >= 2:
                            for w in long_bad:
                                if w[:2] == v[:2] and _skeleton(w) == sk:
                                    score = max(score, 55)
                                    why.append('%s~%s' % (word, w))
                                    break
        for d in doubtful:
            if re.search(r'(?<!\S)%s(?!\S)' % re.escape(d), collapsed):
                score = max(score, 50)
                why.append(d)
        return score, list(dict.fromkeys(why))

    @api.model
    def _models_to_try(self, settings):
        """Same ladder as the classifier: a 429 on one Gemini model says
        nothing about the next, the free tier meters per model per day."""
        ladder = [settings._effective_model()]
        if settings.provider == 'gemini':
            # The lite models have their own, larger daily quota, and a
            # yes/no moderation question does not need the big one.
            ladder += ['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite',
                       'gemini-flash-lite-latest', 'gemini-3.6-flash']
        out = []
        for m in ladder:
            if m and m not in out:
                out.append(m)
        return out[:4]

    @staticmethod
    def _retryable(err):
        status = getattr(getattr(err, 'response', None), 'status_code', None)
        return status in (404, 429, 500, 502, 503, 504) or status is None

    @api.model
    def classify_text(self, text, settings, hint=''):
        """(abusive, confidence, reason) from the model, or None when it could
        not be asked. Same provider and key as the classifier."""
        key = settings._effective_key() if hasattr(settings, '_effective_key') else ''
        if not key or not text:
            return None
        prompt = (settings.conduct_text_prompt or DEFAULT_TEXT_PROMPT)
        prompt = prompt % text[:800] if '%s' in prompt else prompt + '\n\nMessage: ' + text[:800]
        if hint:
            # What the local check saw. Without it the model reads a misspelt
            # Malayalam obscenity as "a name or gibberish".
            prompt += ('\n\nNote from the local filter: ' + hint + '. If the message is '
                       'that word or another spelling of it, it is abusive.')
        timeout = max(3, getattr(settings, 'conduct_model_timeout', 0) or 6)
        raw = None
        for model in self._models_to_try(settings):
            try:
                if settings.provider == 'gemini':
                    url = ('https://generativelanguage.googleapis.com/v1beta/models/'
                           '%s:generateContent' % model)
                    r = requests.post(url, headers={'Content-Type': 'application/json',
                                                    'x-goog-api-key': key},
                                      json={'contents': [{'parts': [{'text': prompt}]}],
                                            'generationConfig': {'temperature': 0,
                                                                 'responseMimeType': 'application/json'}},
                                      timeout=timeout)
                    r.raise_for_status()
                    cands = r.json().get('candidates') or []
                    parts = (cands[0].get('content') or {}).get('parts') if cands else []
                    raw = ''.join(str(p.get('text') or '') for p in (parts or []))
                else:
                    base = settings._effective_base_url().rstrip('/')
                    r = requests.post(base + '/chat/completions',
                                      headers={'Authorization': 'Bearer %s' % key,
                                               'Content-Type': 'application/json'},
                                      json={'model': model, 'temperature': 0,
                                            'messages': [{'role': 'user', 'content': prompt}]},
                                      timeout=timeout)
                    r.raise_for_status()
                    raw = r.json()['choices'][0]['message']['content']
                break
            except Exception as err:  # noqa: BLE001
                _logger.warning("Conduct: text check on %s failed: %s", model, err)
                if not self._retryable(err):
                    return None
        if raw is None:
            return None
        m = re.search(r'\{.*\}', raw or '', re.S)
        try:
            v = json.loads(m.group(0) if m else raw)
        except (ValueError, TypeError):
            return None
        try:
            conf = int(float(v.get('confidence') or 0))
        except (TypeError, ValueError):
            conf = 0
        return bool(v.get('abusive')), max(0, min(100, conf)), str(v.get('reason') or '')[:120]

    # ------------------------------------------------------------------
    # Pictures
    # ------------------------------------------------------------------
    _MEDIA_NODES = (('imageMessage', 'photo'), ('videoMessage', 'video'),
                    ('stickerMessage', 'sticker'), ('ptvMessage', 'video note'),
                    ('documentWithCaptionMessage', 'file'))
    _MAX_DOWNLOAD = 6 * 1024 * 1024

    @api.model
    def media_node(self, message):
        """(kind, node) for a message that carries a picture worth checking."""
        message = message or {}
        for key, kind in self._MEDIA_NODES:
            node = message.get(key)
            if node is None:
                continue
            if key == 'documentWithCaptionMessage':
                inner = ((node.get('message') or {}).get('imageMessage')
                         or (node.get('message') or {}).get('documentMessage') or {})
                if not str(inner.get('mimetype') or '').startswith('image/'):
                    return '', None
                return 'file', inner
            return kind, (node if isinstance(node, dict) else {})
        return '', None

    @api.model
    def picture_of(self, session, data, kind, node, fetch):
        """(base64, mime) of something the model can look at: the thumbnail
        WhatsApp ships with the message, else the file itself for a photo or
        sticker (videos are judged by their thumbnail only)."""
        thumb = node.get('jpegThumbnail')
        if thumb:
            if isinstance(thumb, dict):          # Buffer-style {type, data}
                try:
                    thumb = base64.b64encode(bytes(thumb.get('data') or [])).decode()
                except Exception:  # noqa: BLE001
                    thumb = ''
            if thumb:
                return str(thumb), 'image/jpeg'
        if kind in ('photo', 'sticker', 'file'):
            try:
                if int(node.get('fileLength') or 0) > self._MAX_DOWNLOAD:
                    return '', ''
            except (TypeError, ValueError):
                pass
            raw = fetch(session, data) or b''
            if raw:
                mime = str(node.get('mimetype') or 'image/jpeg').split(';')[0]
                if kind == 'sticker' and 'webp' not in mime:
                    mime = 'image/webp'
                return base64.b64encode(raw).decode(), mime
        return '', ''

    @api.model
    def classify_image(self, b64, mime, settings):
        """True when the model says sexual, False when not, None when it
        could not be asked. Uses the same provider and key as the classifier."""
        key = settings._effective_key() if hasattr(settings, '_effective_key') else ''
        if not key or not b64:
            return None
        prompt = settings.conduct_media_prompt or DEFAULT_MEDIA_PROMPT
        timeout = max(10, settings.timeout_seconds or 20)
        raw = None
        for model in self._models_to_try(settings):
          try:
            if settings.provider == 'gemini':
                url = ('https://generativelanguage.googleapis.com/v1beta/models/'
                       '%s:generateContent' % model)
                r = requests.post(url, headers={'Content-Type': 'application/json',
                                                'x-goog-api-key': key},
                                  json={'contents': [{'parts': [
                                            {'text': prompt},
                                            {'inline_data': {'mime_type': mime, 'data': b64}}]}],
                                        'generationConfig': {'temperature': 0,
                                                             'responseMimeType': 'application/json'}},
                                  timeout=timeout)
                r.raise_for_status()
                cands = r.json().get('candidates') or []
                parts = (cands[0].get('content') or {}).get('parts') if cands else []
                raw = ''.join(str(p.get('text') or '') for p in (parts or []))
            else:
                base = settings._effective_base_url().rstrip('/')
                r = requests.post(base + '/chat/completions',
                                  headers={'Authorization': 'Bearer %s' % key,
                                           'Content-Type': 'application/json'},
                                  json={'model': model, 'temperature': 0,
                                        'messages': [{'role': 'user', 'content': [
                                            {'type': 'text', 'text': prompt},
                                            {'type': 'image_url', 'image_url': {
                                                'url': 'data:%s;base64,%s' % (mime, b64)}}]}]},
                                  timeout=timeout)
                r.raise_for_status()
                raw = r.json()['choices'][0]['message']['content']
            break
          except Exception as err:  # noqa: BLE001 - the picture is kept, the error logged
            _logger.warning("Conduct: media check on %s failed: %s", model, err)
            if not self._retryable(err):
                return None
        if raw is None:
            return None
        m = re.search(r'\{.*\}', raw or '', re.S)
        try:
            verdict = json.loads(m.group(0) if m else raw)
        except (ValueError, TypeError):
            low = (raw or '').lower()
            return True if '"sexual": true' in low or 'sexual":true' in low else False
        self = self.with_context(sa_conduct_reason=str(verdict.get('reason') or '')[:120])
        return bool(verdict.get('sexual'))

    # ------------------------------------------------------------------
    # Who
    # ------------------------------------------------------------------
    @api.model
    def _kind_for(self, digits, is_group, group_jid=''):
        """Vendor when the number is a supplier we deal with, else customer.
        Inside a group the group's own type decides."""
        if is_group and group_jid:
            g = self.env['sa.sales.group'].sudo().search(
                [('group_jid', '=', group_jid)], limit=1)
            for f in ('group_type', 'kind', 'sa_kind', 'type'):
                if g and f in g._fields and str(g[f] or '') == 'vendor':
                    return 'vendor'
            return 'customer'
        tail = _tail(digits)
        if len(tail) < 8:
            return 'customer'
        Partner = self.env['res.partner'].sudo()
        if Partner.search_count([('supplier_rank', '>', 0), '|',
                                 ('phone', 'like', tail),
                                 ('phone_sanitized', 'like', tail)]):
            return 'vendor'
        cutoff = fields.Datetime.now() - timedelta(days=7)
        if self.env['sa.group.request'].sudo().search_count(
                [('create_date', '>=', cutoff), '|',
                 ('sourcing_vendor_ids.phone', 'like', tail),
                 ('sourcing_vendor_ids.phone_sanitized', 'like', tail)]):
            return 'vendor'
        return 'customer'

    @api.model
    def _partner_for(self, digits, kind='customer'):
        """The partner this number means - in the sense the rating uses.
        Several contacts can share one number (on the test database six
        do), so: for a supplier, the one we asked for a price most recently,
        then any supplier; for a customer, the one whose enquiry it was most
        recently; then anyone with that number."""
        tail = _tail(digits)
        if len(tail) < 8:
            return self.env['res.partner']
        Partner = self.env['res.partner'].sudo()
        by_phone = ['|', ('phone', 'like', tail), ('phone_sanitized', 'like', tail)]
        Req = self.env['sa.group.request'].sudo()
        if kind == 'vendor':
            req = Req.search(['|', ('sourcing_vendor_ids.phone', 'like', tail),
                              ('sourcing_vendor_ids.phone_sanitized', 'like', tail)],
                             order='id desc', limit=1)
            for p in req.sourcing_vendor_ids:
                if _tail(p.phone) == tail:
                    return p
            return (Partner.search([('supplier_rank', '>', 0)] + by_phone, limit=1)
                    or Partner.search(by_phone, limit=1))
        req = Req.search([('requester_partner_id', '!=', False),
                          ('requester_phone', 'like', tail)], order='id desc', limit=1)
        if req.requester_partner_id:
            return req.requester_partner_id
        return (Partner.search([('customer_rank', '>', 0)] + by_phone, limit=1)
                or Partner.search(by_phone, limit=1))

    # ------------------------------------------------------------------
    # Doing
    # ------------------------------------------------------------------
    def _try_delete(self):
        """Ask WhatsApp to delete the message for everyone. Records what
        happened; never raises - the webhook must answer 200."""
        for r in self:
            if not (r.session_id and r.wa_message_id):
                r.write({'deleted': False, 'delete_error': 'no session or message id'})
                continue
            chat = r.group_jid or (('%s@s.whatsapp.net' % r.phone) if r.phone else '')
            if not chat:
                r.write({'delete_error': 'no chat to delete from'})
                continue
            try:
                r.session_id.sa_delete_message(chat, r.wa_message_id,
                                               r.participant_jid or r.phone)
                # A non-admin's delete is accepted and ignored. Say so.
                if r.group_jid:
                    try:
                        is_admin, ours = r.session_id.sa_group_admin_status(r.group_jid)
                    except Exception as err:  # noqa: BLE001 - the lookup is optional
                        _logger.info("Conduct: admin check skipped: %s", err)
                        is_admin, ours = True, ''
                    if not is_admin:
                        r.write({'deleted': False, 'delete_error':
                                 'not deleted: the shop number %s is not an admin of this '
                                 'group. Make it admin in WhatsApp, then press "Delete in '
                                 'WhatsApp again".' % (ours or '')})
                        _logger.warning("Conduct: %s not deleted - shop number is not "
                                        "admin in %s", r.wa_message_id, r.group_jid)
                        continue
                r.write({'deleted': True, 'delete_error': False})
            except UserError as err:
                msg = str(err)
                low = msg.lower()
                if 'not available through the panel' in low or 'http 403' in low:
                    msg = 'panel not updated: delete is not allowed through it yet'
                r.write({'deleted': False, 'delete_error': msg[:250]})
                _logger.warning("Conduct: delete of %s failed: %s", r.wa_message_id, msg)
            except Exception as err:  # noqa: BLE001 - never 500 the webhook
                r.write({'deleted': False, 'delete_error': str(err)[:250]})
                _logger.warning("Conduct: delete of %s failed: %s", r.wa_message_id, err)

    def _try_warn(self, mode, text):
        """A short reminder to the sender, per setting. `mode`: off /
        same / private."""
        for r in self:
            if mode == 'off' or not r.session_id or not text:
                continue
            try:
                if r.group_jid and mode == 'same':
                    digits = ''.join(ch for ch in (r.phone or '') if ch.isdigit())
                    if digits:
                        r.session_id.sa_send_text_mentioning(
                            r.group_jid, '@%s %s' % (digits, text), digits)
                    else:
                        r.session_id.send_message(r.group_jid, text)
                elif r.phone:
                    r.session_id.send_message(r.phone, text)
                else:
                    continue
                r.warned = True
            except Exception as err:  # noqa: BLE001 - a failed warning is not an error
                _logger.info("Conduct: warning to %s not sent: %s", r.phone, err)

    def action_delete_again(self):
        self._try_delete()
        return True

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        rows = super().create(vals_list)
        for r in rows:
            if not r.partner_id and r.phone:
                r.partner_id = self._partner_for(r.phone, r.kind)
        # A manual remark is attached and scored at once; the webhook does the
        # same itself after the delete, so it does not need it here.
        manual = rows.filtered(lambda r: r.source == 'manual')
        if manual:
            Entity = self.env['sa.insight.entity'].sudo()
            for r in manual:
                try:
                    Entity._attach_remark(r)
                except Exception as err:  # noqa: BLE001
                    _logger.warning("Conduct: could not attach remark %s: %s", r.id, err)
        return rows

    def unlink(self):
        entities = self.mapped('entity_id')
        res = super().unlink()
        # The rating recovers straight away, not tonight.
        for e in entities.exists():
            try:
                e._rescore_self()
            except Exception as err:  # noqa: BLE001
                _logger.warning("Conduct: rescore after delete failed: %s", err)
        return res
