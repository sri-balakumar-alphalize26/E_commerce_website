# -*- coding: utf-8 -*-
"""The customer's name in the group, and the last typed answers made taps.

Owner, 8 Oct 2026: every group message started "@917092090133 · Ref 4C" - a
number nobody reads. The name is usually known already: a 369 Mart website
account sits on the same contact as the WhatsApp number (the shop links them
by phone), and the order ladder asks it. So:

* `_sa_known_name()` - the real name for this sender, never a placeholder
  ("WhatsApp Customer (...)", a phone number), shown after the @mention.
* A first "hi" from somebody with no real name is asked it once, with their
  WhatsApp name offered as one tap. A skip is remembered on the contact.
* "Reply USE POINTS" became a button (owner: "nothing should be typed").
"""

import json
import logging
import re

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

_NOT_A_NAME = re.compile(r'^[\d\s+()\-.]*$')


class ResPartnerSaName(models.Model):
    _inherit = 'res.partner'

    sa_name_asked_on = fields.Datetime(
        'WhatsApp name asked', copy=False,
        help="When the WhatsApp assistant asked this customer their name. "
             "Asked once: a customer who skips is not asked again.")
    # 21 Nov 2026: the name the customer gave (tapped or typed) is not asked
    # again when their first order is placed.
    sa_name_confirmed_on = fields.Datetime(
        'WhatsApp name confirmed', copy=False, readonly=True,
        help="When this customer gave or confirmed their name on WhatsApp.")

    def _sa_real_name(self):
        """The contact's name, or '' when it is a stand-in: empty, the
        tracker's "WhatsApp Customer (...)", or only a phone number."""
        self.ensure_one()
        name = (self.name or '').strip()
        if not name or name.lower().startswith('whatsapp customer') or _NOT_A_NAME.match(name):
            return ''
        return name

    def _sa_receiver_name(self):
        """Who an address is for: its own name, else its customer's."""
        self.ensure_one()
        return self._sa_real_name() or (self.parent_id._sa_real_name() if self.parent_id else '')


class SaGroupRequestCustomerName(models.Model):
    _inherit = 'sa.group.request'

    sa_name_pending = fields.Selection(
        [('ask', 'Name asked'), ('typing', 'Typing their name')], copy=False,
        help="The welcome question \"what should we call you?\" is open.")

    NAME_TYPE = '✏️ Type a different name'
    NAME_SKIP = '⏭ Skip'
    POINTS_USE = '💎 USE POINTS'
    POINTS_NO = '💳 PAY FULL AMOUNT'
    # The pay text ends with this when points can be used; `_say` then posts
    # the two buttons under it.
    POINTS_MARK = '*💎 USE POINTS*'

    # ------------------------------------------------------------------
    # Who is this?
    # ------------------------------------------------------------------
    def _sa_known_name(self):
        """The sender's real name, or ''. The customer we already use
        (order, address book, phone owner) first; otherwise any contact on
        this number with a real name - the website account preferred."""
        self.ensure_one()
        try:
            customer = self._sa_ss_customer()
            name = customer._sa_real_name() if customer else ''
            if name or not self.requester_phone or self.requester_is_lid:
                return name
            Partner = self.env['res.partner'].sudo()
            if not hasattr(Partner, '_sa_phone_matches'):
                return ''
            same = Partner._sa_phone_matches(self.requester_phone).filtered(
                lambda p: p.customer_rank > 0 or not p.supplier_rank)
            for p in same.sorted(lambda p: (not p.user_ids, p.id)):
                if p._sa_real_name():
                    return p._sa_real_name()
        except Exception as err:  # noqa: BLE001 - a name is never worth a lost message
            _logger.info("Sales Automation: name lookup for %s failed: %s", self.requester_phone, err)
        return ''

    def _sa_name_partner(self, create=False):
        """The contact to save the name on; a new one for a first-time number."""
        self.ensure_one()
        partner = self._sa_ss_customer()
        if partner or not create or not self.requester_phone or self.requester_is_lid:
            return partner
        Partner = self.env['res.partner'].sudo()
        phone = Partner._sa_phone_e164(self.requester_phone) \
            if hasattr(Partner, '_sa_phone_e164') else self.requester_phone
        return Partner.create({'name': 'WhatsApp Customer (%s)' % phone,
                               'phone': phone, 'customer_rank': 1})

    @staticmethod
    def _sa_tidy_name(name):
        """"sri bala" -> "Sri Bala"; "McDonald" and "O'Brien" are left alone."""
        words = ' '.join((name or '').split())[:80].split(' ')
        return ' '.join(w[:1].upper() + w[1:] for w in words if w)

    # ------------------------------------------------------------------
    # A first "hi": what should we call you?
    # ------------------------------------------------------------------
    def _sa_name_ask(self):
        """Ask the name instead of the menu - once per contact. True when asked."""
        self.ensure_one()
        if self._sa_known_name() or self.requester_is_lid or not self.requester_phone:
            return False
        partner = self._sa_name_partner(create=True)
        if not partner or partner.sa_name_asked_on:
            return False
        partner.sudo().sa_name_asked_on = fields.Datetime.now()
        push = ' '.join((self.requester_name or '').split())
        opts = []
        if push and self._sa_looks_like_name(push) and not _NOT_A_NAME.match(push):
            push = self._sa_tidy_name(push)
            opts.append(('✅ %s' % push[:60], {'kind': 'ss_name_use', 'name': push}))
        opts += [(self.NAME_TYPE, {'kind': 'ss_name_type'}),
                 (self.NAME_SKIP, {'kind': 'ss_name_skip'})]
        self.sa_name_pending = 'ask'
        return self._sa_ss_post('main', _("👋 Welcome! What should we call you?\n\n"
                                          "Tap one, or just type your name 👇"), opts)

    def _sa_name_is_confirmed(self, partner):
        """The customer already gave or confirmed this name on WhatsApp - on
        this contact, or on the contact their number answered the welcome
        with (an order can land on an older contact of the same number)."""
        self.ensure_one()
        partner = partner.sudo() if partner else partner
        if not partner or not partner._sa_real_name():
            return False
        if partner.sa_name_confirmed_on:
            return True
        welcome = self._sa_address_partner()
        welcome = welcome.sudo() if welcome else welcome
        return bool(welcome and welcome != partner and welcome.sa_name_confirmed_on
                    and ' '.join((welcome.name or '').lower().split())
                    == ' '.join((partner.name or '').lower().split()))

    def _sa_profile_first_step(self, partner):
        """Where an order's details start: the check when everything is
        known, the address when only the name is (asked once, at the
        welcome), else the name."""
        self.ensure_one()
        if self._sa_profile_complete(partner):
            return 'confirm'
        if self._sa_name_is_confirmed(partner):
            return 'address'
        return 'name'

    def _sa_name_save(self, name):
        """Save the name the customer gave, thank them, and show the menu."""
        self.ensure_one()
        name = self._sa_tidy_name(name)
        partner = self._sa_name_partner(create=True)
        if partner and not partner._sa_real_name():
            partner.sudo().name = name
        if partner:
            partner.sudo().sa_name_confirmed_on = fields.Datetime.now()
        self.write({'sa_name_pending': False, 'requester_name': name})
        self._say(_("🙏 Thanks %s!") % name.split(' ')[0])
        return self._sa_menu_show('main')

    def _sa_menu_show(self, level):
        if level == 'main' and not self.env.context.get('sa_no_name_ask'):
            try:
                if self._sa_name_ask():
                    return True
            except Exception as err:  # noqa: BLE001 - the menu is shown either way
                _logger.warning("Sales Automation: name question for %s failed: %s",
                                self.requester_phone, err)
        return super()._sa_menu_show(level)

    def _sa_menu_tapped(self, item):
        self.ensure_one()
        kind = item.get('kind')
        if kind == 'ss_name_use':
            return self._sa_name_save(item.get('name') or '')
        if kind == 'ss_name_type':
            self.sa_name_pending = 'typing'
            self._say(_("✏️ Type your name 👇"))
            return True
        if kind == 'ss_name_skip':
            self.sa_name_pending = False
            return self._sa_menu_show('main')
        if kind == 'ss_points':
            return self._sa_use_points()
        if kind == 'ss_points_no':
            self._say(_("👍 OK - pay the full amount with the link above."))
            return True
        return super()._sa_menu_tapped(item)

    def _sa_name_typed_ok(self, text, pending):
        """Is this typed text the name we asked for? After "type a different
        name" any name-shaped text is. Before it, a product name typed instead
        of answering ("Mouse") must stay an enquiry."""
        clean = ' '.join((text or '').split())
        if not clean or len(clean.split()) > 4 or not self._sa_looks_like_name(clean):
            return False
        if self._sa_is_greeting(clean) or self._sa_is_cancel(clean):
            return False
        if pending == 'ask' and self.env['product.template'].sudo().search_count(
                [('name', 'ilike', clean), ('sale_ok', '=', True)], limit=1):
            return False
        return True

    @api.model
    def _sa_typed_answer_hook(self, group, message, text):
        rows = self._sa_ss_sender_rows(group, message, [('sa_name_pending', '!=', False)]) \
            if hasattr(self, '_sa_ss_sender_rows') else self.browse()
        row = rows[:1]
        if row:
            if row._sa_name_typed_ok(text, row.sa_name_pending):
                return row._sa_name_save(text)
            # Something else: the question lapses and the text is read normally.
            rows.write({'sa_name_pending': False})
        return super()._sa_typed_answer_hook(group, message, text)

    # ------------------------------------------------------------------
    # Points: a button, not "reply USE POINTS"
    # ------------------------------------------------------------------
    def _say(self, body, addressed=True):
        res = super()._say(body, addressed=addressed)
        if res and self.POINTS_MARK in (body or '') and self.order_id and self.group_id:
            try:
                menu = {}
                for label, kind in ((self.POINTS_USE, 'ss_points'), (self.POINTS_NO, 'ss_points_no')):
                    menu[label] = {'kind': kind, 'req': self.id, 'parent': 'main'}
                self.sa_menu_json = json.dumps(menu)
                self._ask(_("💎 Use your points on order *#%s*?") % (self.ref_code or self.order_id.name),
                          [{'id': 'sa_pts_%d' % i, 'title': label} for i, label in enumerate(menu)])
            except Exception as err:  # noqa: BLE001 - the pay link already went out
                _logger.warning("Sales Automation: points buttons for %s failed: %s", self.id, err)
        return res
