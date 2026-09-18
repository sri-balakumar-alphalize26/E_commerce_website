"""Order updates on WhatsApp, if there is a WhatsApp to send them on.

Four places in the app offered WhatsApp and none of them sent anything. The
cart's opt-in was stored on the order and read by nobody (`Checkout.jsx:630`);
the account screen's toggle gated nothing; the only thing that ever reached
WhatsApp was a `wa.me/?text=` share link on the referrals page, which is the
customer's own phone opening their own app.

**Found at runtime, not depended on.** `whatsapp_gateway` is installed on some
of these databases and not others, and it pulls in Point of Sale, which has no
business being installed on a shop's database because the shop wants order
updates. So this asks whether the gateway is there and stays quiet when it is
not - the opt-in is still recorded either way, so switching the gateway on later
starts sending to people who already agreed rather than starting from nobody.
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# What the customer is told, per state. Deliberately short: this is a message on
# somebody's phone, not a page.
MESSAGES = {
    'placed': "Order #%(ref)s is confirmed. %(eta)s Track it: %(link)s",
    'packed': "Order #%(ref)s is packed and waiting for a rider. %(link)s",
    'shipped': "Order #%(ref)s has been shipped. %(link)s",
    'out': "Order #%(ref)s is out for delivery. %(eta)s %(link)s",
    'delivered': "Order #%(ref)s has been delivered. Thank you for shopping with 369 Mart.",
    'cancelled': "Order #%(ref)s was cancelled. Any refund is on its way.",
}

LINK_PARAM = 'mart369_support.track_url'
DEFAULT_LINK = 'https://369mart.in/track/%s'


class Mart369Whatsapp(models.AbstractModel):
    _name = 'mart369.whatsapp'
    _description = '369 Mart WhatsApp Updates'

    @api.model
    def _mart369_available(self):
        """Is there a gateway installed that can actually send?"""
        return 'whatsapp.mixin' in self.env or 'whatsapp.message' in self.env

    @api.model
    def _mart369_wants(self, order):
        """Did this customer ask for updates, and can we reach them?

        Two consents, both needed: the box on the cart for this order, and the
        standing preference on the account screen.
        """
        partner = order.partner_id
        if not order.mart369_whatsapp:
            return False
        if 'mart369_notify_whatsapp' in partner._fields and not partner.mart369_notify_whatsapp:
            return False
        return bool(self._mart369_number(order))

    @api.model
    def _mart369_number(self, order):
        """The phone to send to: the delivery address first, then the account."""
        for candidate in (order.partner_shipping_id, order.partner_id):
            if candidate and candidate.phone:
                return candidate.phone
        return ''

    @api.model
    def _mart369_notify(self, order, state):
        """Send one update, if everything lines up. Never raises."""
        template = MESSAGES.get(state)
        if not template or not self._mart369_wants(order):
            return False
        if not self._mart369_available():
            _logger.info(
                'mart369: no WhatsApp gateway installed, not telling %s about %s',
                order.partner_id.display_name, order.mart369_ref)
            return False

        link = (self.env['ir.config_parameter'].sudo().get_param(LINK_PARAM)
                or DEFAULT_LINK)
        try:
            body = template % {
                'ref': order.mart369_ref or '',
                'eta': order.mart369_eta or '',
                'link': link % (order.mart369_ref or '') if '%s' in link else link,
            }
        except (KeyError, TypeError):
            _logger.warning('mart369: bad WhatsApp wording for %s', state)
            return False

        return self._mart369_send(order, body)

    @api.model
    def _mart369_send(self, order, body):
        """Hand it to whichever gateway is installed.

        Wrapped because an outbound message failing is not a reason for an order
        to stop moving through the shop.
        """
        number = self._mart369_number(order)
        try:
            if 'whatsapp.mixin' in self.env and hasattr(order, 'wa_send_text'):
                order.wa_send_text(phone=number, message=body)
                return True
            if 'whatsapp.message' in self.env:
                self.env['whatsapp.message'].sudo().create({
                    'phone': number,
                    'partner_id': order.partner_id.id,
                    'body': body,
                })
                return True
        except Exception:  # noqa: BLE001 - see the docstring
            _logger.exception('mart369: could not send a WhatsApp update for %s',
                              order.mart369_ref)
        return False
