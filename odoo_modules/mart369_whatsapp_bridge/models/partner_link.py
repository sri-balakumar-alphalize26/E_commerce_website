"""One phone number, one customer - whichever door they walk in through.

The WhatsApp flow matched customers on the last nine digits with `like`,
which is how a chat could land on a *delivery address* (the website stores a
phone on each address child) or open a second contact for someone who already
has a store account, a wallet and an order history. Here the number is read
properly - E.164, the way the website stores every phone - and the answer is
always the customer record itself, never one of its address children.

And the doors swing both ways: a WhatsApp customer changing their address
through the menu changes the address the *storefront* will deliver to, through
the website's own address book (which keeps its one-delivery-child rule).
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

try:
    import phonenumbers
except ImportError:  # pragma: no cover - phone_validation depends on it
    phonenumbers = None


class WaAutoReply(models.Model):
    _inherit = 'wa.auto.reply'

    @api.model
    def _mart369_bridge_partner(self, phone):
        """The store account behind a WhatsApp number, or nothing.

        Exact E.164 match first - that is what the website writes - against
        the number fields, preferring a partner with a login, then a plain
        contact, and always answering with the customer, not a child address.
        """
        digits = ''.join(c for c in (phone or '') if c.isdigit())
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
        found = (with_login or customers)[:1]
        _logger.info('bridge: WhatsApp %s is store customer %s', phone,
                     found.display_name)
        return found

    def _get_or_create_partner(self, conv):
        found = self._mart369_bridge_partner(conv.phone)
        return found or super()._get_or_create_partner(conv)


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

    def _sa_address_answer(self, text):
        """After a confirmed change, the storefront's default moves too."""
        self.ensure_one()
        confirming = self.sa_address_pending == 'confirm'
        draft = self.sa_address_draft or ''
        partner = self._sa_address_partner() if confirming else None
        handled = super()._sa_address_answer(text)
        if not (handled and confirming and partner and draft):
            return handled
        if self.sa_address_pending:
            return handled          # they said "no, type again"
        if (partner.street or '') != draft[:250]:
            return handled          # the save did not go through
        try:
            self._mart369_bridge_mirror_address(partner, draft)
        except Exception:  # noqa: BLE001 - the chat answer already went out
            _logger.exception('bridge: could not mirror the address of %s',
                              partner.display_name)
        return handled

    def _mart369_bridge_mirror_address(self, partner, draft):
        """Write the storefront's default delivery address.

        Through the website's own book: `_mart369_revise` archives-and-copies
        an address an order is using, and keeps exactly one `type='delivery'`
        child - the rule the storefront's checkout depends on.
        """
        customer = partner.commercial_partner_id.sudo()
        values = {'street': draft[:250]}
        pin = (self._sa_find_pincode(draft, partner)
               if self._sa_pincode_wanted(partner) else None)
        if pin:
            values['zip'] = pin
        book = customer._mart369_book()
        default = book.filtered('mart369_default')[:1]
        if default:
            default._mart369_revise(values)
        else:
            customer._mart369_add_address(dict(
                values,
                name=customer.name,
                phone=customer.phone or self.requester_phone or '',
                mart369_label='WhatsApp',
            ))
        return True
