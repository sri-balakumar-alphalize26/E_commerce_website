# -*- coding: utf-8 -*-
"""Only what the shop has in its own catalogue (owner, 23 Nov 2026).

A product of the database: in stock it is priced, without stock the vendors are
asked. Anything else is answered "sorry, we don't have it" - no vendor, no page,
no product made from it, nothing taken from the internet or drawn by an AI."""
import difflib
import logging
import re

from odoo import _, api, models

_logger = logging.getLogger(__name__)

# said around a product, never part of its name
NOISE = frozenset("""hi hello hey dear sir madam bro pls plz thanks thank ok okay yes no this that these those
there with from by as it its be can could would will may what which how much many when where who show tell
give get buy order ordering looking look find search check new
""".split())


class SaGroupRequestOnlyListed(models.Model):
    _inherit = 'sa.group.request'

    @api.model
    def _sa_squash(self, text):
        return re.sub(r'[\W_]+', '', (text or '').lower())

    def _sa_asked_words(self, term):
        """What must be found, spacing and dashes out: "C-660" is "c660"."""
        words = []
        for word in self._sa_words(term or ''):
            flat = self._sa_squash(word)
            if len(flat) >= 2 and flat not in NOISE and flat not in words:
                words.append(flat)
        return words

    def _sa_listed_ids(self, term, limit=None):
        """Sellable products of this company with EVERY asked word in the name,
        reference or category. No near misses."""
        self.ensure_one()
        words = self._sa_asked_words(term)
        if not words:
            return []
        company = self._company_for(self.group_id) if self.group_id else self.env.company
        self.env['product.template'].flush_model(['name', 'default_code', 'categ_id', 'sale_ok', 'active', 'company_id', 'type'])
        self.env['product.category'].flush_model(['complete_name'])
        flat = ("regexp_replace(lower(concat_ws(' ', (SELECT string_agg(value, ' ') FROM jsonb_each_text(t.name)), "
                "t.default_code, c.complete_name)), '[^[:alnum:]]+', '', 'g')")
        # plural and singular are one word: "keyboards" / "keyboard"
        likes, params = [], []
        for word in words:
            stem = word[:-1] if len(word) > 4 and word.endswith('s') and not word.endswith('ss') else word
            likes.append("%s LIKE %%s" % flat)
            params.append('%' + stem + '%')
        self.env.cr.execute(
            "SELECT t.id FROM product_template t LEFT JOIN product_category c ON c.id = t.categ_id "
            "WHERE t.active AND t.sale_ok AND t.type <> 'service' AND (t.company_id IS NULL OR t.company_id = %s) AND "
            + ' AND '.join(likes) + " ORDER BY t.id" + (" LIMIT %d" % int(limit) if limit else ''), [company.id] + params)
        return [row[0] for row in self.env.cr.fetchall()]

    def _sa_spell_listed(self, term):
        """`term` with a misspelt word put right, when that names something we
        have. A word with a digit - a model number - is never touched."""
        self.ensure_one()
        vocabulary = self._sa_catalog_vocabulary()
        out, changed = [], False
        for word in (term or '').split():
            low = word.lower().strip('.,!?:;()')
            if len(low) >= 4 and low.isalpha() and low not in vocabulary and low not in self._SA_FILLER and low not in NOISE:
                near = difflib.get_close_matches(low, vocabulary, n=1, cutoff=0.8)
                if near:
                    out.append(near[0])
                    changed = True
                    continue
            out.append(word)
        fixed = ' '.join(out)
        return fixed if changed and self._sa_listed_ids(fixed, 1) else ''

    def _sa_need_listed(self):
        """True while this enquiry is about a product of ours. Otherwise the
        customer is told, once, and the enquiry is closed."""
        self.ensure_one()
        product = self.product_id
        company = self._company_for(self.group_id) if self.group_id else self.env.company
        if product and product.exists() and product.active and (not product.company_id or product.company_id == company):
            return True
        name = self.ai_search_term or self.raw_text or ''
        _logger.info("Sales Automation: enquiry %s - %r is no product of ours, nobody is asked", self.id, name[:60])
        if not self._sa_say_not_stocked(name):
            pass
        self._drop('not_stocked')
        return False

    # every door to the vendors
    def _on_confirmed(self):
        if not self._sa_need_listed():
            return True
        return super()._on_confirmed()

    def _park_for_shop(self, vendors):
        if not self._sa_need_listed():
            return True
        return super()._park_for_shop(vendors)

    def _start_sourcing(self, vendors):
        if not self._sa_need_listed():
            return True
        return super()._start_sourcing(vendors)

    def _finder_confirm(self, payload):
        """A model typed after "Not listed" is looked up like any typed
        product; it never gets a page of its own (owner, 23 Nov 2026)."""
        self.ensure_one()
        product = self.env['product.template']
        if payload.get('kind') == 'ours' and payload.get('product_id'):
            product = product.sudo().browse(int(payload['product_id'])).exists()
        if product:
            return super()._finder_confirm(payload)
        return self._sa_offer_listed(payload.get('name') or '')

    def _sa_offer_listed(self, name):
        """What of ours is called that, else sorry."""
        self.ensure_one()
        ids = [i for i in self._sa_listed_ids(name, 20) if i not in self.rejected_product_ids.ids]
        found = self.env['product.template'].browse(ids[:3])
        self.write({'finder_step': 'done', 'ai_search_term': name or self.ai_search_term})
        if len(found) > 1:
            return self._ask_choice(found)
        if found:
            return self._sa_offer_one(found)
        self._sa_say_not_stocked(name)
        self._drop('not_stocked')
        return True

    def _unlisted_vendors(self):
        return self.env['res.partner']

    def _create_product_from_enquiry(self):
        """Never: a product is made by a person, in Products."""
        return self.env['product.template']

    def _reject_match(self):
        """NO to our guess: what else of ours fits, else sorry. Nobody is asked
        about the words that were typed."""
        self.ensure_one()
        refused = self.product_id
        if refused:
            self.rejected_product_ids = [(4, refused.id)]
        self.product_id = False
        ids = [i for i in self._sa_listed_ids(self.ai_search_term or self.raw_text or '', 20)
               if i not in self.rejected_product_ids.ids]
        others = self.env['product.template'].browse(ids[:3])
        if others:
            return self._ask_choice(others) if len(others) > 1 else self._sa_offer_one(others)
        self._say(_("\U0001F614 Sorry, we don't have another *%(term)s* right now.\n\nType another product name, or *hi* for "
                    "the menu.\n\n_Ref %(ref)s_", term=(self.ai_search_term or self.raw_text or _("one"))[:60],
                    ref=self.ref_code or self.id))
        return self._drop('not_confirmed')

    def _sa_offer_one(self, product):
        self.product_id = product.id
        return self._ask_confirmation()


class SaClassifierNoInternet(models.AbstractModel):
    _inherit = 'sa.ai.classifier'

    # The AI reads a sentence. It does not know what the shop sells, and it
    # draws no pictures.
    @api.model
    def suggest_types(self, word):
        return []

    @api.model
    def suggest_brands(self, word, type_label):
        return []

    @api.model
    def suggest_models(self, word, type_label, brand):
        return []

    @api.model
    def _call_gemini_image(self, prompt, timeout=45):
        return b'', ''
