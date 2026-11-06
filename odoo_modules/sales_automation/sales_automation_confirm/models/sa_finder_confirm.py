# -*- coding: utf-8 -*-
"""The guided finder's last step is the page too.

The finder narrows a generic request down with polls (type → brand → model)
and then asked "Confirm X?" with its own YES / Back poll. Now that step sends
the picture + link instead: ACCEPT on the page finishes the finder exactly as
the old YES did, REJECT goes back to the model list. A model that is not in
the catalogue has no product record, so the picture is looked up by name.
"""
import json
import logging
import re

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


# A part or accessory: the typed model is what it is FOR, not the item itself.
_PART_WORDS = ('battery', 'charger', 'adapter', 'adaptor', 'screen', 'display', 'keyboard', 'cover', 'case',
               'cable', 'strap', 'panel', 'glass', 'protector', 'ink', 'toner', 'cartridge', 'filter', 'belt',
               'motherboard', 'ram', 'ssd', 'hdd', 'fan', 'hinge', 'speaker', 'mic', 'lens', 'remote', 'stand',
               'holder', 'mount', 'bag', 'sleeve', 'pen', 'stylus', 'dock', 'hub')


class SaGroupRequestFinderConfirm(models.Model):
    _inherit = 'sa.group.request'

    sa_finder_for_asked = fields.Datetime('Asked which model the part is for', readonly=True, copy=False)
    sa_finder_for_brand = fields.Char('Typed brand / device while asking', readonly=True, copy=False)

    def _sa_confirm_finder_on(self):
        return bool(self._sa_confirm_settings().confirm_enabled)

    # ------------------------------------------------------------------
    # Parts: keep the asked-for item, ask which device it is for
    # ------------------------------------------------------------------
    def _sa_part_words(self):
        """The part words in what the customer first asked for ('laptop battery' -> ['battery'])."""
        self.ensure_one()
        seed = ' '.join(filter(None, [self.finder_seed or '', self.finder_type or '', self.ai_search_term or ''])).lower()
        return [w for w in _PART_WORDS if re.search(r'\b%s\b' % re.escape(w), seed)]

    def _sa_part_item(self):
        """'laptop battery' - the thing asked for, as typed originally."""
        self.ensure_one()
        return (self.finder_seed or self.ai_search_term or self.raw_text or '').strip()

    def _sa_combine_part_name(self, device, model=''):
        """'dell laptop' + 'Inspiron 15 3520' + 'laptop battery' -> 'Dell Inspiron 15 3520 laptop battery'."""
        self.ensure_one()
        item = self._sa_part_item().lower()
        device = (device or '').strip()
        model = (model or '').strip()
        words = []
        for w in (device + ' ' + model).split():
            lw = w.lower().strip('.,')
            if lw and lw not in item.split() and lw not in [x.lower() for x in words]:
                words.append(w)
        # "laptop" typed again is not a model word when the item already says laptop.
        parts = ' '.join(words).strip()
        name = ('%s %s' % (parts, item)).strip() if parts else item
        # Keep the customer's own casing (ThinkPad, iPhone); title-case only all-lowercase words.
        return ' '.join(x if (any(c.isupper() for c in x) or any(c.isdigit() for c in x)) else x.title() for x in name.split())

    def _finder_answer(self, text):
        """Typed answers for a PART: the model is what it is for. Ask once
        which device model, then confirm '<brand> <model> <part>'."""
        self.ensure_one()
        if self._sa_confirm_finder_on() and self.finder_step == 'model_text' and self._sa_part_words():
            typed = (text or '').strip()
            low = typed.lower()
            if low and low != 'back' and not self.finder_locked:
                if self.sa_finder_for_asked:
                    # The answer to "for which model?"
                    if low in ('skip', 'any', 'no', 'dont know', "don't know", 'not sure'):
                        name = self._sa_combine_part_name(self.sa_finder_for_brand or '')
                    else:
                        name = self._sa_combine_part_name(self.sa_finder_for_brand or '', typed)
                    self.sudo().write({'sa_finder_for_asked': False})
                    return self._finder_confirm({'kind': 'market', 'name': name})
                has_model = any(ch.isdigit() for ch in typed) or len(typed.split()) >= 3
                if not has_model:
                    # "dell laptop": the brand / device, but which model is the part for?
                    self.sudo().write({'sa_finder_for_asked': fields.Datetime.now(), 'sa_finder_for_brand': typed,
                                       'finder_asked_on': fields.Datetime.now()})
                    self._say(_("Got it - a %(item)s for a %(device)s \U0001F44D\n"
                                "Which model is it for? Type the model name or number (for example: Inspiron 15 3520), "
                                "or reply SKIP if you are not sure. (Ref %(ref)s)",
                                item=self._sa_part_item(), device=typed, ref=self.ref_code or self.id))
                    return True
                name = self._sa_combine_part_name(typed)
                return self._finder_confirm({'kind': 'market', 'name': name})
        return self._finder_answer_page(text)

    def _finder_send_picture(self, product, name):
        """The picture goes with the link message; nothing separate here."""
        if self._sa_confirm_finder_on():
            return True
        return super()._finder_send_picture(product, name)

    def _finder_ask(self, step, types=None):
        if step != 'confirm' or not self._sa_confirm_finder_on():
            return super()._finder_ask(step, types=types)
        self.ensure_one()
        self.write({
            'finder_step': 'confirm',
            'finder_options': json.dumps({'step': 'confirm', 'labels': {}}, ensure_ascii=False),
            'finder_asked_on': fields.Datetime.now(),
            'finder_variant': (self.finder_variant or 0) + 1,
        })
        return self._sa_confirm_customer_send()

    def _finder_answer_page(self, text):
        """While the page link is out: a chat YES points at the page, a NO goes back."""
        self.ensure_one()
        link = self.sa_confirm_link_id
        if (self._sa_confirm_finder_on() and self.finder_step == 'confirm' and link and link.sent_on
                and not link.decided and not self.finder_locked):
            low = (text or '').strip().lower()
            if low == 'back' or self._read_yes_no(text) is False:
                return self._finder_back()
            if self._read_yes_no(text) is True:
                if not self.sa_confirm_nudged_on:
                    self.sudo().write({'sa_confirm_nudged_on': fields.Datetime.now()})
                    self._say(_("Please press ACCEPT on the page to confirm \U0001F447\n%(url)s\n\n_Ref %(ref)s_",
                                url=link._url(), ref=self.ref_code or self.id))
                return True
        return super()._finder_answer(text)

    def _finder_back(self):
        # Leaving the confirm step: the old link must not decide anything later.
        link = self.sa_confirm_link_id
        if self.finder_step == 'confirm' and link:
            if not link.decided:
                link.sudo().write({'active': False})
            self.sudo().write({'sa_confirm_link_id': False, 'sa_confirm_nudged_on': False})
        return super()._finder_back()
