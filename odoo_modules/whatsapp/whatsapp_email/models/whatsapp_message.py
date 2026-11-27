import logging
import re

from odoo import models, api

_logger = logging.getLogger(__name__)

# Customer replies "1-<orderref>" to approve or "2-<orderref>" to reject a
# sale.order credit override. The sale.order action methods are provided by a
# separate credit-management module; we call them defensively (no-op if absent).
CREDIT_REPLY_RE = re.compile(r'^([12])-([A-Za-z0-9]+)$')


class WhatsAppMessage(models.Model):
    """Extends the shared `whatsapp.message` (owned by `whatsapp_gateway`).

    `whatsapp_gateway` creates one `whatsapp.message` record for every inbound
    WhatsApp message. We hook record creation here — without touching
    `whatsapp_gateway` — to keep the instant credit-approval auto-reply flow
    that used to live on the (now removed) duplicate session model.
    """
    _inherit = 'whatsapp.message'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.direction == 'incoming':
                try:
                    rec._process_credit_reply()
                except Exception as e:
                    _logger.error(
                        "Credit-approval reply hook failed for %s: %s",
                        rec.phone, e, exc_info=True,
                    )
        return records

    def _process_credit_reply(self):
        """Parse this incoming message for a "1-SOxxx" / "2-SOxxx" pattern and
        approve/reject the matched sale.order, then reply over the same session."""
        self.ensure_one()
        body = (self.message or '').strip()
        match = CREDIT_REPLY_RE.match(body)
        if not match:
            return

        action_code, order_name = match.group(1), match.group(2).upper()
        action = 'APPROVE' if action_code == '1' else 'REJECT'
        session = self.session_id
        phone = self.phone

        _logger.info("INSTANT credit reply: %s for %s from %s", action, order_name, phone)

        SaleOrder = self.env.get('sale.order')
        if SaleOrder is None:
            _logger.info("sale.order model unavailable — skipping credit reply")
            return

        order = SaleOrder.sudo().search([('name', '=ilike', order_name)], limit=1)
        if not order:
            _logger.error("Credit reply: order not found: %s", order_name)
            self._safe_reply(session, phone, "Order not found: %s" % order_name)
            return

        current_status = getattr(order, 'credit_approval_status', False)
        if current_status in ('approved', 'rejected'):
            self._safe_reply(
                session, phone,
                "Order *%s* was already %s." % (order_name, current_status),
            )
            return

        currency = order.currency_id.symbol or '$'

        if action == 'APPROVE':
            approve = getattr(order, 'action_approve_credit_override', None)
            if not approve:
                _logger.warning(
                    "sale.order.action_approve_credit_override missing — "
                    "credit reply received but no handler exists"
                )
                return
            order.sudo().action_approve_credit_override()
            self._safe_reply(
                session, phone,
                "*ORDER APPROVED*\n\nOrder *%s* approved!\nCustomer: %s\nAmount: %s %s" % (
                    order.name, order.partner_id.name, currency,
                    "{:,.2f}".format(order.amount_total),
                ),
            )
        else:
            reject = getattr(order, 'action_reject_credit_override', None)
            if not reject:
                _logger.warning("sale.order.action_reject_credit_override missing")
                return
            order.sudo().action_reject_credit_override()
            self._safe_reply(
                session, phone,
                "*ORDER REJECTED*\n\nOrder *%s* rejected.\nCustomer: %s\nAmount: %s %s" % (
                    order.name, order.partner_id.name, currency,
                    "{:,.2f}".format(order.amount_total),
                ),
            )

    @staticmethod
    def _safe_reply(session, phone, text):
        """Send a WhatsApp reply over the shared session, swallowing errors so a
        failed reply never blocks message creation."""
        if not session:
            return
        try:
            session.send_message(phone, text)
        except Exception as e:
            _logger.error("Credit reply send failed to %s: %s", phone, e)
