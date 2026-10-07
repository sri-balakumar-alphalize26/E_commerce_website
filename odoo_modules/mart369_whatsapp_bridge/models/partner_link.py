"""One phone number, one customer - whichever door they walk in through.

The WhatsApp flow matched customers on the last nine digits with `like`,
which is how a chat could land on a *delivery address* (the website stores a
phone on each address child) or open a second contact for someone who already
has a store account, a wallet and an order history. Here the number is read
properly - E.164, the way the website stores every phone - and the answer is
always the customer record itself, never one of its address children.

Since the tracker's 1.3.0 every lookup of a WhatsApp number goes through
`res.partner._sa_phone_matches`, and this module's rule - a store account
catches the chat only once it has proven the number - lives in its override
below, rather than in a second copy of the stack's `_get_or_create_partner`.

The chat's CHANGE ADDRESS is the stack's own address book now
(sales_automation, sa_address_book.py): it lists the storefront's addresses,
writes their label, landmark and alternate phone, and keeps the one default
through `_mart369_set_default`. This module no longer draws its own.
"""

import logging

from odoo import _, api, models

_logger = logging.getLogger(__name__)

try:
    import phonenumbers
except ImportError:  # pragma: no cover - phone_validation depends on it
    phonenumbers = None


def _digits(phone):
    return ''.join(c for c in (phone or '') if c.isdigit())


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _sa_phone_matches(self, phone):
        """The stack's lookup, as customers this shop may hand the chat to.

        The stack answers "every contact whose number is this number, oldest
        first". Kept, with three things it cannot know:

        * a store account counts only once it has *proven* the number - one
          typed at signup proves nothing, and would hand the real owner's
          WhatsApp orders and addresses to whoever typed it;
        * the answer is the customer, never one of its address children;
        * a proven account comes before a plain contact with the same number.
        """
        stack = getattr(super(), '_sa_phone_matches', None)
        found = stack(phone) if stack else self._mart369_phone_matches(phone)
        customers = self.browse()
        for partner in found:
            customer = partner.commercial_partner_id
            if customer not in customers:
                customers |= customer
        customers -= customers.filtered(
            lambda c: c.user_ids and not c.mart369_phone_verified)
        proven = customers.filtered('user_ids')
        return proven + (customers - proven)

    @api.model
    def _mart369_phone_matches(self, phone):
        """The stack's own matching, for a tracker older than 1.3.0 that has
        no `_sa_phone_matches` yet: equal digits, or the last ten agree."""
        digits = _digits(phone)
        if len(digits) < 5:
            return self.browse()
        Partner = self.sudo().with_context(active_test=True)
        found = (Partner.search([('phone', 'ilike', digits[-5:])], order='id')
                 | Partner.search([('phone_sanitized', 'ilike', digits[-5:])], order='id'))

        def same(number):
            d = _digits(number)
            return bool(d) and (d == digits or (len(d) >= 7 and len(digits) >= 7
                                                and d[-10:] == digits[-10:]))
        return found.filtered(lambda p: same(p.phone) or same(p.phone_sanitized)).sorted('id')


class WaAutoReply(models.Model):
    _inherit = 'wa.auto.reply'

    @api.model
    def _mart369_bridge_partner(self, phone):
        """The store account behind a WhatsApp number, or nothing.

        Exact E.164 match first - that is what the website writes - against
        the number fields, preferring a partner with a login, then a plain
        contact, and always answering with the customer, not a child address.
        """
        digits = _digits(phone)
        if len(digits) < 8:
            return self.env['res.partner']
        e164 = '+%s' % digits
        if phonenumbers:
            try:
                parsed = phonenumbers.parse(e164)
                if phonenumbers.is_possible_number(parsed):
                    e164 = phonenumbers.format_number(
                        parsed, phonenumbers.PhoneNumberFormat.E164)
            except phonenumbers.NumberParseException:
                pass
        Partner = self.env['res.partner'].sudo()
        matches = Partner.search([
            '|', '|', ('phone', '=', e164),
            ('phone_sanitized', '=', e164),
            ('mart369_alt_phone', '=', e164),
        ]) if 'mart369_alt_phone' in Partner._fields else Partner.search([
            '|', ('phone', '=', e164), ('phone_sanitized', '=', e164),
        ])
        if not matches:
            return Partner.browse()
        customers = matches.mapped('commercial_partner_id')
        with_login = customers.filtered('user_ids')
        # A store account catches the chat only once it has *proven* the
        # number: one typed at signup proves nothing, and would hand the real
        # owner's WhatsApp orders and addresses to whoever typed it.
        proven = with_login.filtered('mart369_phone_verified')
        found = (proven or (customers - with_login))[:1]
        if found:
            _logger.info('bridge: WhatsApp %s is store customer %s', phone,
                         found.display_name)
        return found


class SaGroupRequest(models.Model):
    _inherit = 'sa.group.request'

    def _sa_address_partner(self):
        partner = super()._sa_address_partner()
        if partner and not partner.parent_id:
            return partner
        # The stack's loose search can land on an address child; and with no
        # order yet, the store account is still worth finding.
        found = self.env['wa.auto.reply']._mart369_bridge_partner(
            self.requester_phone)
        if found:
            return found
        return partner.commercial_partner_id if partner else partner

    # ------------------------------------------------------- the address book

    def _mart369_book_of(self):
        """The store customer behind this chat and their address book."""
        partner = self._sa_address_partner()
        if not partner:
            return self.env['res.partner'], self.env['res.partner']
        customer = partner.commercial_partner_id.sudo()
        return customer, customer._mart369_book()

    @staticmethod
    def _mart369_addr_text(address):
        """'Home - 12 New Colony, 4th Street, Dindigul 624001': the address
        the way the app's cards read it, on one line."""
        parts = [address.street, address.street2, address._mart369_city_line()]
        text = ', '.join(p for p in parts if p)
        label = address.mart369_label or 'Home'
        return '%s - %s' % (label, text) if text else label

    def _sa_say_my_details(self):
        """The stack prints one street; a store customer has a book."""
        self.ensure_one()
        customer, book = self._mart369_book_of()
        if not book:
            return super()._sa_say_my_details()
        digits = self.requester_phone or ''
        orders = self.sudo().search([
            ('group_id', '=', self.group_id.id), ('order_id', '!=', False),
            ('requester_phone', 'like',
             digits[-9:] if len(digits) >= 9 else digits)])
        live = orders.filtered(lambda r: r.order_id.state != 'cancel')
        paid = live.filtered(lambda r: r._sa_order_is_paid(r.order_id))
        lines = ['%s %s' % ('✅' if a.mart369_default else '•',
                            self._mart369_addr_text(a)) for a in book]
        self._say(_("\U0001F464 *Your details*\n\nName: %(name)s\n"
                    "Phone: %(phone)s\nAddresses:\n%(addrs)s\n\n"
                    "Paid orders: %(paid)d\n"
                    "Orders waiting for payment: %(open)d\n\n"
                    "To change anything, just tell us here.",
                    name=customer.name or self.requester_name or '-',
                    phone=('+' + digits) if digits else '-',
                    addrs='\n'.join(lines),
                    paid=len(paid), open=len(live) - len(paid)))
        return True
