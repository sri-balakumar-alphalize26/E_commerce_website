# -*- coding: utf-8 -*-
"""The guided finder: from "headphone" to one exact product, by tapping.

A customer who names a model gets a price in one step. A customer who types a
generic word does not yet know what they want, and a list of whatever the
keyword search scored highest does not help them. This walks them there in
the private chat, one poll at a time: which kind, which brand, which model,
then a picture and a Yes. Every question is a poll because that is the one
tappable thing this transport renders on WhatsApp Web as well as the phone.

Nothing here talks to the tracker. The finder writes no `wa.auto.reply`
rows; it holds its own state on the enquiry and answers votes itself. Only
when the customer confirms does it hand the enquiry to `_on_confirmed()`,
which is the same door every enquiry goes through today.
"""

import json
import logging
import re

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

NAV_BACK = 'Back'
NAV_OTHER = 'Something else'
NAV_NOT_LISTED = 'Not listed'
NAV_YES = 'Yes'

# Three phrasings per step: the gateway drops an outbound message identical
# to one sent to the same number in the last five minutes, and "Back" asks
# the previous question again.
_QUESTIONS = {
    'type': [
        "Which kind of %(seed)s? (Ref %(ref)s)",
        "What type of %(seed)s are you after? (Ref %(ref)s)",
        "Pick the kind of %(seed)s you need (Ref %(ref)s)",
    ],
    'brand': [
        "Which brand? ✓ = we have it (Ref %(ref)s)",
        "Any preferred brand for the %(type)s? (Ref %(ref)s)",
        "Choose a brand - ✓ means it is in our stock (Ref %(ref)s)",
    ],
    'model': [
        "Which %(brand)s model? ✓ = in our stock (Ref %(ref)s)",
        "Pick the %(brand)s %(type)s you want (Ref %(ref)s)",
        "Here are the %(brand)s options - tap one (Ref %(ref)s)",
    ],
    'confirm': [
        "Confirm *%(model)s*? (Ref %(ref)s)",
        "Shall I go ahead with *%(model)s*? (Ref %(ref)s)",
        "Lock in *%(model)s*? (Ref %(ref)s)",
    ],
}

_NUDGES = [
    "Please tap one of the options above 👆 (Ref %(ref)s)",
    "Just tap an option in the poll above 🙂 (Ref %(ref)s)",
]


class SaGroupRequestFinder(models.Model):
    _inherit = 'sa.group.request'

    reply_in_dm = fields.Boolean(
        'Answering Privately', readonly=True, copy=False,
        help="Once the finder has moved this enquiry to the customer's own "
             "chat, every later message - the price, the vendor's answer - "
             "goes there too, not back to the group.")
    finder_step = fields.Selection([
        ('type', 'Asking the Kind'),
        ('brand', 'Asking the Brand'),
        ('model', 'Asking the Model'),
        ('model_text', 'Waiting for a Typed Model'),
        ('confirm', 'Waiting for Confirmation'),
        ('done', 'Confirmed'),
    ], string='Finder Step', readonly=True, copy=False)
    finder_seed = fields.Char('Generic Word', readonly=True, copy=False)
    finder_type = fields.Char('Chosen Kind', readonly=True, copy=False)
    finder_type_keywords = fields.Char(
        'Kind Keywords', readonly=True, copy=False,
        help="Words that appear in product names of this kind, used to "
             "filter the catalogue.")
    finder_brand = fields.Char('Chosen Brand', readonly=True, copy=False)
    finder_model = fields.Char('Chosen Model', readonly=True, copy=False)
    finder_kind = fields.Selection([
        ('ours', 'Our Catalogue'),
        ('market', 'Market Model'),
    ], string='Chosen From', readonly=True, copy=False)
    finder_company_id = fields.Many2one(
        'res.company', string='Stock Company', readonly=True, copy=False,
        help="The company whose shelf the chosen product sits on. Price and "
             "stock are read there; the order is still raised in the "
             "group's company and the shop can move the delivery at "
             "Accept.")
    finder_options = fields.Text(
        'Current Options (JSON)', readonly=True, copy=False,
        help="What each label in the last poll stands for, so a vote is "
             "resolved without asking the AI again.")
    finder_asked_on = fields.Datetime('Finder Question Sent', readonly=True,
                                      copy=False)
    finder_variant = fields.Integer('Phrasing Counter', readonly=True,
                                    copy=False)
    finder_locked = fields.Boolean(
        'Choice Locked', readonly=True, copy=False,
        help="Set when the customer confirmed. Later taps on the old polls "
             "are answered once and otherwise ignored.")

    # ------------------------------------------------------------------
    # Where answers go
    # ------------------------------------------------------------------
    def _sa_reply_to(self):
        """Where an answer belongs. Always the group, unless they wrote to us.

        `reply_in_dm` used to send the rest of the enquiry to the customer's
        own chat. The whole conversation now stays in the group, so that
        branch is gone; the field is left in place so old rows still load.

        The `sa_reply_to` context is kept and is not an escape: it is set when
        somebody messages the business number directly, and answering them
        where they wrote is the only civil thing to do.
        """
        self.ensure_one()
        return (self.env.context.get('sa_reply_to')
                or self.group_id.group_jid)

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------
    def _finder_settings(self):
        return self.env['sa.ai.settings'].sudo().get_settings()

    def _finder_eligible(self):
        """A generic word, narrowed down in the group it was asked in.

        The `_sa_dm_target()` gate is gone. It barred every member WhatsApp
        addresses by @lid - people with no reachable number - from the one
        feature that exists to help somebody who only knows "computer parts".
        Now the questions are posted in the group, there is nobody to exclude.
        """
        self.ensure_one()
        settings = self._finder_settings()
        if not getattr(settings, 'finder_enabled', False):
            return False
        if self._sa_specific_enough():
            return False
        return bool(self.group_id.employee_session_id)

    @staticmethod
    def _finder_singular(word):
        word = (word or '').strip().lower()
        if len(word) > 4 and word.endswith('s') and not word.endswith('ss'):
            return word[:-1]
        return word

    def _finder_start(self):
        """Open the finder. False means "nothing to offer, use the old path"."""
        self.ensure_one()
        Classifier = self.env['sa.ai.classifier'].sudo()
        seed = self._finder_singular(Classifier._sa_clean_term(
            self.ai_search_term or self.raw_text))
        if not seed or len(seed) < 3:
            return False

        types = Classifier.suggest_types(seed)
        catalog = self._finder_catalog_products([seed])
        if len(types) < 2 and not catalog:
            return False

        # Nothing moves any more: the narrowing questions are asked in the
        # group, addressed to the person who asked.
        self._ensure_conversation()
        self.write({
            'state': 'finding',
            'finder_seed': seed,
            'finder_type': False,
            'finder_type_keywords': False,
            'finder_brand': False,
            'finder_model': False,
            'finder_kind': False,
            'finder_company_id': False,
            'finder_locked': False,
            'finder_variant': 0,
            'reply_in_dm': False,
        })
        self._say(_(
            "Hi! You asked about *%(seed)s* in *%(group)s* 👇\n"
            "Let me help you find the right one - just tap the options. "
            "_(Ref %(ref)s)_",
            seed=seed, group=self.group_id.name, ref=self.ref_code or self.id))
        _logger.info("Sales Automation: finder opened for enquiry %s (%r)",
                     self.id, seed)
        # The finder now owns this enquiry: state is 'finding' and the
        # options are stored. _finder_ask returns False when the question
        # could not be delivered, and returning that would send the enquiry
        # back down the ordinary path - which ends at a supplier being asked
        # to price a generic word. Log it and keep the enquiry here; the
        # customer can be re-prompted, a vendor cannot be un-asked.
        asked = (self._finder_ask('type', types=types) if len(types) >= 2
                 else self._finder_ask('brand'))
        if not asked:
            _logger.warning(
                "Sales Automation: finder question for enquiry %s could not "
                "be delivered - staying in the finder rather than sourcing "
                "%r from a supplier", self.id, seed)
        return True

    # ------------------------------------------------------------------
    # Our catalogue
    # ------------------------------------------------------------------
    def _finder_keywords(self):
        words = [self.finder_seed or '']
        words += [w.strip() for w in (self.finder_type_keywords or '').split(',')
                  if w.strip()]
        return [w for w in words if w]

    def _finder_catalog_products(self, words, narrow=None):
        """Sale products of THIS group's company whose name carries the seed.

        `narrow` (type keywords) is applied on top when it leaves anything;
        a type nobody named their products after must not hide the whole
        catalogue.
        """
        Product = self.env['product.template'].sudo().with_context(
            active_test=True)
        seed = (words or [''])[0]
        if not seed:
            return Product
        found = Product.search([('sale_ok', '=', True),
                                ('name', 'ilike', seed)], limit=200)
        if not found:
            # "headphone" against "Headphones" is fine with ilike; "earbud"
            # against "Earbuds" too. A seed that matches nothing may still
            # be a spelling the catalogue does not use.
            found = self._search_products_loose(seed)
        # One company's catalogue - the group's. `_match_products` has always
        # done this; the finder did not, so the customer was offered products
        # of businesses this group does not sell for. A product with no
        # company belongs to all of them, which is how most catalogues here
        # are set up.
        company = self._company_for(self.group_id)
        found = found.filtered(
            lambda prod: not prod.company_id or prod.company_id == company)
        if narrow and found:
            # Ordering, not filtering. Product names rarely carry the type
            # word a customer chose - "JBL Tune 510BT Headphones" says nothing
            # about over-ear - so a filter threw out the two products we
            # actually stock and kept a nameless generic one.
            def matches(product):
                name = (product.name or '').lower()
                return any(k.lower() in name for k in narrow)
            found = found.sorted(key=lambda p: (not matches(p), p.name or ''))
        return found

    def _finder_brand_of(self, product):
        brands = self.env['sa.ai.classifier'].sudo()._sa_brand_vocabulary()
        words = [w.strip('.,()-').lower() for w in (product.name or '').split()]
        for w in words:
            if w in brands:
                return w
        return ''

    def _finder_companies_for(self, product):
        """The single company this conversation sells for.

        This used to return **every** company on the database for a product
        that belongs to none, and `_finder_options_model` emits one row per
        (product, company) - so one shared laptop became three poll options,
        each labelled with an internal company name. The customer saw the
        operator's company list and had to choose between three identical
        products.

        An empty recordset for a product belonging to somebody else, so it
        produces no row at all: the catalogue is already filtered, and this
        keeps the guarantee even if some other caller is not.
        """
        company = self._company_for(self.group_id)
        if product.company_id and product.company_id != company:
            return self.env['res.company']
        return company

    def _finder_stock(self, product, company):
        variant = product.product_variant_id or product.product_variant_ids[:1]
        if not variant:
            return 0.0
        field = ('virtual_available' if self.group_id.use_virtual_stock
                 else 'qty_available')
        try:
            return variant.sudo().with_company(company)[field] or 0.0
        except Exception:  # noqa: BLE001 - a stock read must never stop a poll
            return 0.0

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------
    def _finder_max(self):
        return min(10, max(3, getattr(self._finder_settings(),
                                      'finder_max_options', 10) or 10))

    @staticmethod
    def _finder_norm(text):
        return ''.join(c for c in (text or '').lower() if c.isalnum())

    def _finder_options_type(self, types):
        out = []
        for t in types[:self._finder_max()]:
            label = (t.get('label') or '').strip()
            if label:
                out.append((label, {'type': label,
                                    'keywords': t.get('keywords') or []}))
        out.append((NAV_OTHER, {'nav': 'other'}))
        return out

    def _finder_options_brand(self):
        Classifier = self.env['sa.ai.classifier'].sudo()
        narrow = [w for w in self._finder_keywords()[1:]]
        products = self._finder_catalog_products([self.finder_seed], narrow)
        ours = {}
        for product in products:
            brand = self._finder_brand_of(product) or '__other__'
            in_stock = any(self._finder_stock(product, c) > 0
                           for c in self._finder_companies_for(product))
            ours[brand] = ours.get(brand, False) or in_stock
        out = []
        for brand, in_stock in sorted(ours.items(),
                                      key=lambda kv: (kv[0] == '__other__',
                                                      not kv[1], kv[0])):
            shown = _('Other brands') if brand == '__other__' else brand.title()
            label = '%s ✓ %s' % (shown, _('in stock') if in_stock else _('listed'))
            out.append((label, {'brand': brand, 'ours': True}))
        market = Classifier.suggest_brands(self.finder_seed,
                                          self.finder_type or '')
        have = {b.lower() for b in ours}
        for brand in market:
            if len(out) >= self._finder_max():
                break
            if brand.lower() in have:
                continue
            out.append((brand, {'brand': brand.lower(), 'ours': False}))
            have.add(brand.lower())
        out.append((NAV_BACK, {'nav': 'back'}))
        return out

    def _finder_brand_skippable(self):
        """True when the shop's own products for this search name no brand -
        the brand poll would be a single "Other brands" row. Brands are not
        guessed from the internet for it (owner, 22 Nov 2026: brands come
        from the shop's own categories)."""
        self.ensure_one()
        narrow = [w for w in self._finder_keywords()[1:]]
        products = self._finder_catalog_products([self.finder_seed], narrow)
        return bool(products) and not any(self._finder_brand_of(p) for p in products)

    def _finder_options_model(self):
        Classifier = self.env['sa.ai.classifier'].sudo()
        narrow = [w for w in self._finder_keywords()[1:]]
        products = self._finder_catalog_products([self.finder_seed], narrow)
        brand = self.finder_brand or ''
        if brand == '__other__':
            mine = products.filtered(lambda p: not self._finder_brand_of(p))
        else:
            mine = products.filtered(
                lambda p: self._finder_brand_of(p) == brand.lower())
        rows = []
        for product in mine:
            for company in self._finder_companies_for(product):
                qty = self._finder_stock(product, company)
                if qty <= 0 and product.company_id and product.company_id != company:
                    continue
                rows.append((qty, product, company))
        rows.sort(key=lambda r: -r[0])
        out, seen = [], set()
        for qty, product, company in rows[:6]:
            # No company name in the label any more. There is only one
            # company in the list now, so it disambiguated nothing - and it
            # showed a customer what the businesses behind the shop are
            # called.
            # Availability only - the count is the shop's business, not the
            # group's.
            tail = (_('✓ in stock') if qty > 0 else _('· to order'))
            label = '%s %s' % ((product.name or '')[:44], tail)
            out.append((label, {'kind': 'ours', 'product_id': product.id,
                                'company_id': company.id,
                                'name': product.name, 'qty': qty}))
            seen.add(self._finder_norm(product.name))
        if brand and brand != '__other__':
            market = Classifier.suggest_models(self.finder_seed,
                                              self.finder_type or '', brand)
            for name in market:
                if len(out) >= self._finder_max():
                    break
                if self._finder_norm(name) in seen:
                    continue
                seen.add(self._finder_norm(name))
                out.append((name, {'kind': 'market', 'name': name}))
        out.append((NAV_NOT_LISTED, {'nav': 'not_listed'}))
        out.append((NAV_BACK, {'nav': 'back'}))
        return out

    def _finder_options_confirm(self):
        return [(NAV_YES, {'nav': 'yes'}), (NAV_BACK, {'nav': 'back'})]

    @staticmethod
    def _finder_clean_labels(options):
        """Poll labels: no pipes or newlines, ≤60 chars, all different."""
        out, used = [], set()
        for label, payload in options:
            label = re.sub(r'[|\r\n]+', ' ', str(label or '')).strip()[:60]
            if not label:
                continue
            base, n = label, 2
            while label.lower() in used:
                label = '%s (%d)' % (base[:55], n)
                n += 1
            used.add(label.lower())
            out.append((label, payload))
        return out

    # ------------------------------------------------------------------
    # Asking
    # ------------------------------------------------------------------
    def _finder_ask(self, step, types=None):
        self.ensure_one()
        if step == 'type':
            options = self._finder_options_type(types or [])
        elif step == 'brand':
            options = self._finder_options_brand()
        elif step == 'model':
            options = self._finder_options_model()
        else:
            options = self._finder_options_confirm()
        options = self._finder_clean_labels(options)

        real = [o for o in options if 'nav' not in o[1]]
        if step == 'brand' and self._finder_brand_skippable():
            # 22 Nov 2026: none of our products names a brand, so the poll
            # would only say "Other brands ✓ in stock". Show them directly.
            self.write({'finder_brand': '__other__'})
            return self._finder_ask('model')
        if step == 'brand' and not real:
            # Nothing to choose a brand from: let them name the model.
            return self._finder_want_typed()
        if step == 'model' and not real:
            return self._finder_want_typed()
        if len(options) < 2:
            options.append((NAV_BACK, {'nav': 'back'}))
        # Evolution accepts ten poll options and refuses eleven with a bare
        # 400. Navigation stays; the list gives way from the end.
        nav = [o for o in options if 'nav' in o[1]]
        real = [o for o in options if 'nav' not in o[1]]
        options = real[:max(1, 10 - len(nav))] + nav

        words = {
            'seed': self.finder_seed or _('item'),
            'type': (self.finder_type or self.finder_seed or '').lower(),
            'brand': (self.finder_brand or '').title(),
            'model': self.finder_model or '',
            'ref': self.ref_code or self.id,
        }
        question = _QUESTIONS[step][(self.finder_variant or 0) % 3] % words
        self.write({
            'finder_step': step,
            'finder_options': json.dumps(
                {'step': step, 'labels': {l: p for l, p in options}},
                ensure_ascii=False),
            'finder_asked_on': fields.Datetime.now(),
            'finder_variant': (self.finder_variant or 0) + 1,
        })
        return self._ask(question, [{'id': l, 'title': l} for l, _p in options])

    def _finder_want_typed(self):
        self.write({'finder_step': 'model_text',
                    'finder_asked_on': fields.Datetime.now()})
        return self._say(_(
            "Type the exact %(brand)s model name and I'll check it for you. "
            "(Ref %(ref)s)",
            brand=(self.finder_brand or '').title() or self.finder_seed,
            ref=self.ref_code or self.id))

    # ------------------------------------------------------------------
    # Answering
    # ------------------------------------------------------------------
    def _finder_labels(self):
        try:
            return (json.loads(self.finder_options or '{}') or {}).get(
                'labels') or {}
        except ValueError:
            return {}

    def _finder_resolve(self, text):
        labels = self._finder_labels()
        if text in labels:
            return labels[text]
        low = text.lower()
        for label, payload in labels.items():
            if label.lower() == low:
                return payload
        if text.isdigit():
            real = [p for l, p in labels.items() if 'nav' not in p]
            index = int(text) - 1
            if 0 <= index < len(real):
                return real[index]
        return None

    def _finder_answer(self, text):
        """Consume a private message meant for the finder.

        True when it was ours - a vote, a nudge-worthy stray, a typed model
        name. False when the text is a new request that somebody else must
        handle, in which case the caller drops this finder.
        """
        self.ensure_one()
        text = (text or '').strip()
        Classifier = self.env['sa.ai.classifier'].sudo()
        guard = self.env['sa.outbox.guard'].sudo()

        if self.finder_locked:
            if guard.claim('finder_locked_msg|%s' % self.id, 300):
                self._say(_("That one's already confirmed ✅ - send a new "
                            "message if you'd like something else. "
                            "(Ref %(ref)s)", ref=self.ref_code or self.id))
            return True

        if (not self.finder_asked_on
                or self.finder_asked_on < self._sa_still_warm()):
            self._say(_("That list has expired - let's start again 🙂"))
            return bool(self._finder_start())

        if self.finder_step == 'model_text':
            low = text.lower()
            if low == NAV_BACK.lower():
                return self._finder_back()
            if Classifier._looks_like_product_request(text) and len(
                    text.split()) > 4:
                return False
            name = Classifier._sa_clean_term(text) or text
            return self._finder_confirm({'kind': 'market', 'name': name.title()})

        payload = self._finder_resolve(text)
        if payload is None:
            words = [w for w in re.split(r'\s+', text.lower())
                     if w and w not in self._SA_FILLER]
            if len(words) >= 2 or Classifier._looks_like_product_request(text):
                return False
            nudge = _NUDGES[(self.finder_variant or 0) % len(_NUDGES)] % {
                'ref': self.ref_code or self.id}
            self.finder_variant = (self.finder_variant or 0) + 1
            self._say(nudge)
            return True

        nav = payload.get('nav')
        if nav == 'back':
            return self._finder_back()
        if nav == 'other':
            self._say(_("No problem 🙂 - please send me the exact product "
                        "name or model, and I'll check it for you."))
            self.write({'finder_step': 'done'})
            return bool(self._drop('not_confirmed')) or True
        if nav == 'not_listed':
            return self._finder_want_typed()
        if nav == 'yes':
            return self._finder_finish()

        step = self.finder_step
        if step == 'type':
            self.write({'finder_type': payload.get('type') or '',
                        'finder_type_keywords': ','.join(
                            payload.get('keywords') or [])})
            return self._finder_ask('brand')
        if step == 'brand':
            self.write({'finder_brand': payload.get('brand') or ''})
            return self._finder_ask('model')
        if step == 'model':
            return self._finder_confirm(payload)
        return True

    def _finder_back(self):
        self.ensure_one()
        step = self.finder_step
        if step == 'confirm':
            self.write({'finder_model': False, 'finder_kind': False,
                        'finder_company_id': False})
            return self._finder_ask('model')
        if step in ('model', 'model_text') and not self._finder_brand_skippable():
            self.write({'finder_brand': False})
            return self._finder_ask('brand')
        if step in ('brand', 'model', 'model_text'):
            # (the brand step was skipped: back goes where its back would)
            if self.finder_type:
                self.write({'finder_type': False, 'finder_type_keywords': False})
                types = self.env['sa.ai.classifier'].sudo().suggest_types(
                    self.finder_seed)
                if len(types) >= 2:
                    return self._finder_ask('type', types=types)
            self._say(_("No problem 🙂 - please send me the exact product "
                        "name or model, and I'll check it for you."))
            self._drop('not_confirmed')
            return True
        return self._finder_ask('type', types=self.env[
            'sa.ai.classifier'].sudo().suggest_types(self.finder_seed))

    # ------------------------------------------------------------------
    # Picture and confirmation
    # ------------------------------------------------------------------
    def _finder_confirm(self, payload):
        self.ensure_one()
        name = payload.get('name') or ''
        kind = payload.get('kind') or 'market'
        vals = {'finder_model': name, 'finder_kind': kind,
                'finder_company_id': payload.get('company_id') or False}
        product = self.env['product.template']
        if kind == 'ours' and payload.get('product_id'):
            product = self.env['product.template'].sudo().browse(
                int(payload['product_id']))
            if not product.exists():
                product = self.env['product.template']
                vals['finder_kind'] = 'market'
            else:
                vals['candidate_product_ids'] = [(6, 0, [product.id])]
        self.write(vals)
        self._finder_send_picture(product, name)
        return self._finder_ask('confirm')

    def _finder_send_picture(self, product, name):
        """The catalogue photo, or a generated reference picture, once.

        Sent wherever the conversation is - it used to be hard-coded to the
        requester's number, so the photo went to a private chat even after
        everything else had moved to the group.
        """
        phone = self._sa_reply_to()
        session = self.group_id.session_id
        guard = self.env['sa.outbox.guard'].sudo()
        if not guard.claim('finder_img|%s|%s' % (self.id, name.lower()), 300):
            return True
        ref = self.ref_code or self.id
        try:
            if product and product.image_1920:
                company = self.finder_company_id
                qty = self._finder_stock(product, company) if company else 0
                caption = _("📦 *%(name)s* — %(avail)s (Ref %(ref)s)",
                            name=product.name,
                            avail=_("in stock") if qty > 0 else _("to order"), ref=ref)
                # Not through the tracker's helper: it hands the field's
                # base64 bytes straight to the gateway, which encodes bytes
                # again, and the picture never arrives (the queue then sends
                # the log line as text). Decode once here.
                import base64 as _b64
                raw = _b64.b64decode(product.image_1920)
                session.send_image(phone, raw, caption=caption)
                return True
            # no picture of ours: none is drawn or looked up (23 Nov 2026)
            self._say(_("*%(name)s* — I don't have a photo to hand. (Ref %(ref)s)", name=name, ref=ref))
        except Exception as err:  # noqa: BLE001 - a picture is not worth the flow
            _logger.warning("Sales Automation: finder picture for %s failed: %s",
                            self.id, err)
        return True

    # ------------------------------------------------------------------
    # Finish
    # ------------------------------------------------------------------
    def _finder_finish(self):
        """Lock the choice and push it through the ordinary door."""
        self.ensure_one()
        self.write({'finder_locked': True, 'finder_step': 'done'})
        product = self.candidate_product_ids[:1] if self.finder_kind == 'ours' \
            else self.env['product.template']
        # The order is raised in the group's company, and Odoo will not put
        # another company's product on it. A same-name product of ours is
        # used when there is one; otherwise the item is sourced like any
        # other market model - the stock elsewhere is a fulfilment question
        # for the shop's company picker, not a reason to fail the customer.
        company = self._company_for(self.group_id)
        if product and product.company_id and product.company_id != company:
            twin = self.env['product.template'].sudo().search([
                ('name', '=', product.name), ('sale_ok', '=', True),
                '|', ('company_id', '=', company.id),
                ('company_id', '=', False)], limit=1)
            if twin:
                product = twin
            else:
                _logger.info("Sales Automation: finder %s chose %s of %s - "
                             "not sold by %s, sourcing instead", self.id,
                             product.name, product.company_id.name,
                             company.name)
                self.write({'finder_model': product.name})
                product = self.env['product.template']
        if product:
            self.write({'product_id': product.id, 'state': 'awaiting_confirm',
                        'ai_search_term': product.name,
                        'candidate_product_ids': [(5, 0, 0)]})
            _logger.info("Sales Automation: finder %s confirmed %s from %s",
                         self.id, product.name,
                         self.finder_company_id.name or '-')
            return self._on_confirmed()
        name = self.finder_model or self.finder_seed
        self.write({'product_id': False, 'ai_search_term': name,
                    'state': 'awaiting_confirm',
                    'candidate_product_ids': [(5, 0, 0)]})
        _logger.info("Sales Automation: finder %s confirmed market model %r",
                     self.id, name)
        return self._on_confirmed()
