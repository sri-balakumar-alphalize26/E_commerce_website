"""What the job tells the order, and what the customer is told once.

**Pull.** Every move a rider or the shop makes lands on the picking's
`sa_delivery_state`. The write hook here is the one place that watches it, so
no matter which of the stack's dozen code paths moved the job - the rider
app, the Store screen, a WhatsApp reply, a cron - the console's order follows.

**One voice per step.** A website customer hears the same journey a WhatsApp
customer does - rider on the way, collected, out for delivery, delivered -
in the stack's own words, on their own number. Each step has exactly one
speaker: the stack's `_sa_notify_customer` for the rider's steps, the
website's updates (whatsapp_notify.py) for placed / packed / cancelled. Every
other stack message to the customer (the shop's "accepted", the cancel
notices) stays silent for a website order, because the website says those.
The console's Settings switches and the customer's opt-in still decide.

**One code, also on WhatsApp.** The stack issues its own six-digit door code
when the rider sets off. The website already issued one when the order was
paid, and the customer's app is showing it. For a website job the stack's
code paths are redirected to the website's code, so whatever the rider types
is checked against the number the customer is looking at - and that same
code is sent on WhatsApp to the customer, and to the address's phone when
someone else is receiving the parcel. Sent even to a customer who turned
updates off: without the code there is no parcel.
"""

import logging
import re

from odoo import _, api, models

from odoo.addons.whatsapp_gateway.models.whatsapp_session import WhatsAppQueued

_logger = logging.getLogger(__name__)

# The rider's steps a website customer hears, and the console switch
# (mart369.config `mart369_wa_on_<switch>`) that turns each one off.
STEP_SWITCH = {
    'accepted': 'shipped',
    'picked': 'shipped',
    'dispatched': 'shipped',
    'out_for_delivery': 'out',
    'delivered': 'delivered',
    'returning': 'cancelled',
}


def _digits(number):
    return re.sub(r'\D', '', number or '')


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

    # ------------------------------------------------------------- the counter

    @api.model
    def sa_store_queue(self, shop_id=None):
        """The counter's queue, each card saying which door it came in by.

        369 Mart › Sales › New Orders (mart369_store_board) shows both doors
        in one list; the Store's own screen ignores the extra key. One
        read for every row, sudo'd like the queue itself - counter staff have
        no rights on sale.order.
        """
        data = super().sa_store_queue(shop_id)
        ids = {row['order_id'] for row in data.get('rows', []) if row.get('order_id')}
        channels = {
            order.id: order.mart369_channel
            for order in self.env['sale.order'].sudo().browse(list(ids))
        }
        for row in data.get('rows', []):
            row['channel'] = channels.get(row.get('order_id')) or 'website'
        return data

    # ------------------------------------------------------- one voice per step

    def _mart369_web_order(self):
        order = self.sale_id
        return order if order and order.mart369_ref else order.browse()

    def _mart369_wa_session(self):
        """The number the shop speaks from: the one picked on the console's
        Settings, else the job's own (order, group, any active)."""
        config = self.env['mart369.config'].sudo()._get()
        session = config.mart369_wa_session_id
        if session and session.active:
            return session
        return self._sa_session()

    def _mart369_send_to(self, number, body, unique=False):
        """One text to one number. Queued counts as sent; never raises."""
        self.ensure_one()
        digits = _digits(number)
        session = self._mart369_wa_session()
        if len(digits) < 8 or not session:
            return False
        # The stack's own dedupe, keyed the stack's way - a step said twice
        # by two code paths within a quarter of an hour is said once.
        if not unique and not self.env['sa.outbox.guard'].sudo().claim(
                'track|%s|%s|%s' % (self.id, digits[-9:], body[:40]), 900):
            return False
        try:
            session.send_message(digits, body)
            return True
        except WhatsAppQueued:
            return True
        except Exception as err:  # noqa: BLE001 - the job matters more
            _logger.warning('bridge: could not tell %s about job %s: %s',
                            digits, self.sa_ref_code, err)
            return False

    def _sa_notify_customer(self, state):
        """A website customer hears the rider's steps too - if they asked to,
        and the console has that step switched on."""
        self.ensure_one()
        order = self._mart369_web_order()
        if not order:
            return super()._sa_notify_customer(state)
        switch = STEP_SWITCH.get(state)
        if not switch:
            return False
        config = self.env['mart369.config'].sudo()._get()
        if not config._mart369_wa_on(switch):
            return False
        if not self.env['mart369.whatsapp']._mart369_wants(order):
            return False
        return super(StockPicking, self.with_context(
            mart369_step=state))._sa_notify_customer(state)

    def _sa_tell_customer(self, body, unique=False):
        """For a website order: only the steps let through above, and to the
        customer's own number - never the address's."""
        self.ensure_one()
        order = self._mart369_web_order()
        if not order:
            return super()._sa_tell_customer(body, unique=unique)
        if not self.env.context.get('mart369_step'):
            return False
        number = self.env['mart369.whatsapp']._mart369_customer_number(order)
        return self._mart369_send_to(number, body, unique=unique)

    # ------------------------------------------------------------- one code

    def _mart369_code_numbers(self, order):
        """The customer's own number, then the address's when it is a
        different phone - compared on the last nine digits, so one number
        written two ways is one number."""
        numbers = []
        for number in (
                self.env['mart369.whatsapp']._mart369_customer_number(order),
                self.partner_id.phone):
            digits = _digits(number)
            if len(digits) >= 8 and digits[-9:] not in [n[-9:] for n in numbers]:
                numbers.append(digits)
        return numbers

    def sa_issue_delivery_otp(self, send=True):
        """A website job never mints a second code - it sends the website's.

        The website issued the code at payment and the customer's app shows
        it; a retry is `_mart369_issue_otp`, which copies the fresh one here.
        The same code goes out on WhatsApp in the stack's words, whatever the
        customer's update preference: it is the key to their parcel.

        `send=False` is the stack's Create OTP wizard with "Do not send": the
        code comes back for the screen and nothing goes out.
        """
        self.ensure_one()
        order = self._mart369_web_order()
        if not order:
            # Passed on only when asked: a stack older than delivery 29.0
            # takes no `send` at all.
            return (super().sa_issue_delivery_otp() if send
                    else super().sa_issue_delivery_otp(send=False))
        code = order.sudo().mart369_otp_code or ''
        self.sudo().sa_last_delivery_code = code or self.sa_last_delivery_code
        if not code:
            return False, _('This order has no delivery code yet.'), code
        if not send:
            return True, _('Code made, not sent.'), code
        body = _("\U0001F4E6 Your order is arriving.\n\n"
                 "Give this code to the rider *after* you have the parcel:\n\n"
                 "*%(code)s*\n\n"
                 "Do not share it before you receive your order.", code=code)
        sent = [number for number in self._mart369_code_numbers(order)
                if self._mart369_send_to(number, body, unique=True)]
        if sent:
            return True, _("The code has been sent to the customer on "
                           "WhatsApp. It is also in their app."), code
        return False, _("Could not send the code on WhatsApp. The customer "
                        "can see it in their app."), code

    def sa_verify_otp(self, kind, code):
        """The rider's typed code is checked against the website's."""
        self.ensure_one()
        order = self.sale_id
        if kind != 'delivery' or not order.mart369_ref:
            return super().sa_verify_otp(kind, code)
        if order.sudo()._mart369_check_otp(code):
            return True, ''
        return False, 'That delivery code is not right.'
