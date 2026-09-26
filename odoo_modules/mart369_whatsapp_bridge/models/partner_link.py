"""One phone number, one customer - whichever door they walk in through.

The WhatsApp flow matched customers on the last nine digits with `like`,
which is how a chat could land on a *delivery address* (the website stores a
phone on each address child) or open a second contact for someone who already
has a store account, a wallet and an order history. Here the number is read
properly - E.164, the way the website stores every phone - and the answer is
always the customer record itself, never one of its address children.

And the doors swing both ways: the chat's CHANGE ADDRESS opens the
*storefront's* address book - tap a saved address and both the website and
the next WhatsApp order deliver there; type a new one and it joins the book
as the default (which keeps its one-delivery-child rule).
"""

import json
import logging

from odoo import _, api, models

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

    # A poll shows this many saved addresses at a time; the rest sit behind
    # MORE, the way the catalogue menu pages its products.
    ADDR_PAGE = 6

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

    def _mart369_addr_menu(self, page=0):
        """The saved addresses as a poll: tap one to deliver there, or type a
        new one. The stack's typing prompt when the customer has no book."""
        self.ensure_one()
        customer, book = self._mart369_book_of()
        if not book:
            return super()._sa_ask_new_address()
        start = page * self.ADDR_PAGE
        rows = book[start:start + self.ADDR_PAGE]
        if page and not rows:
            return self._mart369_addr_menu(0)
        opts, used = [], set()
        for a in rows:
            label = self._mart369_addr_text(a)
            if a.mart369_default:
                label = '✅ ' + label
            opts.append((self._sa_menu_clean(label, used),
                         {'kind': 'mart369_addr', 'target': a.id}))
        if len(book) > start + self.ADDR_PAGE:
            opts.append((_("➡️ MORE"),
                         {'kind': 'menu',
                          'level': 'mart369_addr:%d' % (page + 1)}))
        opts.append((_("✏️ TYPE A NEW ADDRESS"),
                     {'kind': 'mart369_addr_new'}))
        back = ('mart369_addr:%d' % (page - 1) if page > 1 else
                'mart369_addr' if page else 'more')
        opts.append((self.MENU_BACK, {'kind': 'menu', 'level': back}))
        opts.append((self.MENU_MAIN, {'kind': 'menu', 'level': 'main'}))
        level = 'mart369_addr:%d' % page if page else 'mart369_addr'
        menu = {}
        for label, item in opts[:10]:
            item = dict(item)
            item.setdefault('req', self.id)
            item['parent'] = level
            menu[label] = item
        self.sa_menu_json = json.dumps(menu)
        self._ask(_("\U0001F4CD *Delivery address* - tap the one to use, "
                    "or add a new one:"),
                  [{'id': 'sa_menu_%d' % i, 'title': label}
                   for i, label in enumerate(menu)])
        return True

    def _sa_ask_new_address(self):
        """CHANGE ADDRESS opens the book first."""
        return self._mart369_addr_menu(0)

    def _sa_menu_show(self, level):
        if (level or '').startswith('mart369_addr'):
            bits = level.split(':')
            page = int(bits[1]) if len(bits) > 1 and bits[1].isdigit() else 0
            return self._mart369_addr_menu(page)
        return super()._sa_menu_show(level)

    def _sa_menu_tapped(self, item):
        self.ensure_one()
        kind = item.get('kind')
        if kind == 'mart369_addr_new':
            # The stack's own prompt; the typed answer is mirrored into the
            # book by `_sa_address_answer` below.
            return super()._sa_ask_new_address()
        if kind != 'mart369_addr':
            return super()._sa_menu_tapped(item)
        customer, book = self._mart369_book_of()
        target = item.get('target') or 0
        address = book.filtered(lambda a: a.id == target)
        if not address:
            self._say(_("That address is no longer available."))
            return self._sa_nav('more')
        address._mart369_set_default()
        order = self.order_id.sudo() if self.order_id else None
        if order and order.state not in ('done', 'cancel') and not any(
                p.state == 'done' for p in order.picking_ids):
            # A plain write: never the storefront's `_mart369_set_state`.
            order.write({'partner_shipping_id': address.id})
        self._say(_("✅ Delivery address set:\n%(addr)s\n\n"
                    "Your next deliveries go there.",
                    addr=self._mart369_addr_text(address)))
        return self._sa_nav('more')

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

    # ------------------------------------------------------ a typed address

    def _sa_address_answer(self, text):
        """After a confirmed change, the storefront's book gets it too."""
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
        """Add the typed address to the storefront's book as its default.

        Through the website's own helpers, so the book keeps exactly one
        `type='delivery'` child - the rule the storefront's checkout depends
        on. The old addresses stay; the customer can tap back to them.
        """
        customer = partner.commercial_partner_id.sudo()
        values = {'street': draft[:250]}
        pin = (self._sa_find_pincode(draft, partner)
               if self._sa_pincode_wanted(partner) else None)
        if pin:
            values['zip'] = pin
        address = customer._mart369_add_address(dict(
            values,
            name=customer.name,
            phone=customer.phone or self.requester_phone or '',
            mart369_label='WhatsApp',
        ))
        if not address.mart369_default:
            address._mart369_set_default()
        return address
