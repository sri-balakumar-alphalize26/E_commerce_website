"""What the job tells the order, and what the customer is told once.

**Pull.** Every move a rider or the shop makes lands on the picking's
`sa_delivery_state`. The write hook here is the one place that watches it, so
no matter which of the stack's dozen code paths moved the job - the rider
app, the Store screen, a WhatsApp reply, a cron - the console's order follows.

**One voice.** The stack messages its customers itself at every step. For a
website order those texts would arrive on top of the website's own updates
(whatsapp_notify.py), worded differently and twice as often. So for a website
order the stack's customer messages are silenced here at their one exit,
`_sa_tell_customer` - the rider's messages are untouched.

**One code.** The stack issues its own six-digit door code when the rider
sets off. The website already issued one when the order was paid, and the
customer's app is showing it. For a website job the stack's code paths are
redirected to the website's code, so whatever the rider types is checked
against the number the customer is actually looking at.
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # ------------------------------------------------------------- the pull

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get('mart369_bridge') == 'push':
            return result
        if 'sa_delivery_state' in vals:
            for picking in self:
                order = picking.sale_id
                if not order:
                    continue
                try:
                    if order.mart369_channel == 'whatsapp':
                        order._mart369_bridge_mirror()
                    elif order.mart369_ref:
                        picking._mart369_bridge_pull(order)
                except Exception:  # noqa: BLE001 - the job matters more
                    _logger.exception('bridge: could not pull %s after %s',
                                      order.name, vals.get('sa_delivery_state'))
        if 'sa_delivery_partner_id' in vals:
            self._mart369_bridge_mirror_rider()
        return result

    def _mart369_bridge_pull(self, order):
        """Bring a website order up to where its parcel really is.

        Forward only: the console's ladder has no way back, and a job being
        re-offered to a second rider is not the order becoming unpacked.
        """
        self.ensure_one()
        stage = self.sa_delivery_state
        if stage in ('cancelled', 'returned', 'failed'):
            if order.mart369_state in ('delivered', 'cancelled'):
                return
            reason = self.sa_cancel_reason or 'Cancelled from the delivery job'
            if order.mart369_state == 'placed':
                order.with_context(mart369_bridge='pull')._mart369_cancel(
                    reason=reason)
            else:
                order.with_context(
                    mart369_bridge='pull')._mart369_return_to_store(reason)
            return
        state = order._mart369_bridge_map(order.mart369_mode or 'quick', self)
        if not state or state == 'cancelled':
            return
        flow = order._mart369_flow()
        if order.mart369_state not in flow or state not in flow:
            return
        if flow.index(state) <= flow.index(order.mart369_state):
            return
        order.with_context(mart369_bridge='pull')._mart369_set_state(state)

    def _mart369_bridge_mirror_rider(self):
        """The job's rider appears on the console card, when they map."""
        for picking in self:
            order = picking.sale_id
            if not order or not (order.mart369_ref
                                 or order.mart369_channel == 'whatsapp'):
                continue
            user = picking.sa_delivery_partner_id.user_id
            if user and user in order._mart369_riders():
                if order.mart369_rider_id != user:
                    order.sudo().mart369_rider_id = user

    # ------------------------------------------------------------ one voice

    def _sa_tell_customer(self, body, unique=False):
        """A website customer hears the website's updates, and only those."""
        self.ensure_one()
        if self.sale_id.mart369_ref:
            return False
        return super()._sa_tell_customer(body, unique=unique)

    # ------------------------------------------------------------- one code

    def sa_issue_delivery_otp(self):
        """A website job never mints a second code.

        The website issued the code at payment and the customer's app shows
        it; a retry is `_mart369_issue_otp`, which copies the fresh one here.
        """
        self.ensure_one()
        order = self.sale_id
        if not order.mart369_ref:
            return super().sa_issue_delivery_otp()
        code = order.sudo().mart369_otp_code or ''
        self.sudo().sa_last_delivery_code = code or self.sa_last_delivery_code
        return bool(code), (
            'The customer already has their delivery code in the app.'), code

    def sa_verify_otp(self, kind, code):
        """The rider's typed code is checked against the website's."""
        self.ensure_one()
        order = self.sale_id
        if kind != 'delivery' or not order.mart369_ref:
            return super().sa_verify_otp(kind, code)
        if order.sudo()._mart369_check_otp(code):
            return True, ''
        return False, 'That delivery code is not right.'
