import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    wa_conversation_id = fields.Many2one('wa.conversation', string='WA Conversation')
    wa_employee_session_id = fields.Many2one('wa.employee.session', string='WA Employee Session')
    wa_payment_mode = fields.Selection([
        ('online', 'Online'),
        ('cod', 'Cash on Delivery'),
    ], string='WA Payment Mode')
    wa_payment_claimed = fields.Boolean('WA Payment Claimed', copy=False)

    def _wa_phone(self):
        conv = self.wa_conversation_id
        return (conv.phone if conv else '') or self.partner_id.phone or ''

    def _wa_send_msg(self, text):
        sess = self.wa_employee_session_id
        phone = self._wa_phone()
        if sess and phone and text:
            try:
                sess.session_id.send_message(phone, text)
            except Exception as e:
                _logger.error("WA send_msg SO %s: %s", self.id, e)

    def _wa_send_pdf(self, report_ref, caption):
        sess = self.wa_employee_session_id
        phone = self._wa_phone()
        if not (sess and phone):
            return
        try:
            pdf, _x = self.env['ir.actions.report'].sudo()._render_qweb_pdf(report_ref, self.ids)
            fname = ((self.name or 'Document').replace('/', '_')) + '.pdf'
            sess.session_id.send_document(phone, pdf, fname, caption=caption)
        except Exception as e:
            _logger.error("WA send_pdf SO %s (%s): %s", self.id, report_ref, e)

    def _wa_settle(self, paid=False):
        """Decide: automatic invoice, or agent-verify receipt flow."""
        self.ensure_one()
        sess = self.wa_employee_session_id
        auto = sess.auto_reply_auto_invoice if sess else True
        if auto:
            return self._wa_finalize(paid=paid)
        return self._wa_send_receipt(paid=paid)

    def _wa_finalize(self, paid=False):
        """Automatic: confirm + invoice + post + (register payment) + send invoice PDF."""
        try:
            if self.state in ('draft', 'sent'):
                self.action_confirm()
            inv = self.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state != 'cancel')
            if not inv:
                inv = self._create_invoices()
            inv.filtered(lambda m: m.state == 'draft').with_context(
                wa_skip_autosend=True).action_post()
            if paid:
                reg = self.env['account.payment.register'].sudo().with_context(
                    active_model='account.move', active_ids=inv.ids).create({})
                reg._create_payments()
                self.wa_payment_mode = 'online'
            self._wa_send_pdf('account.account_invoices',
                              'Invoice (Paid)' if paid else 'Invoice')
            self._wa_send_msg(
                "✅ Payment confirmed! Your invoice is attached. Thank you! \U0001F389"
                if paid else
                "✅ Order confirmed (Cash on Delivery). Invoice attached — pay on delivery. \U0001F69A")
            return True
        except Exception as e:
            _logger.error("WA finalize SO %s failed: %s", self.id, e)
            self._wa_send_msg("Your order is saved. Our agent will assist you shortly. \U0001F64F")
            return False

    def _wa_send_receipt(self, paid=False):
        """Agent-verify: confirm SO, send Order Receipt PDF + 'agent will verify' message.
        The invoice is sent later, automatically, when the agent posts it in Odoo."""
        try:
            if self.state in ('draft', 'sent'):
                self.action_confirm()
            self.wa_payment_claimed = paid
            if paid:
                self.wa_payment_mode = 'online'
            self._wa_send_pdf('sale.action_report_saleorder', 'Order Receipt')
            if paid:
                msg = ("✅ Payment received! \U0001F9FE\n\nOur agent will verify your "
                       "payment and confirm your delivery address. Your invoice will be "
                       "sent here shortly. \U0001F64F")
            else:
                msg = ("✅ Order confirmed (Cash on Delivery)! \U0001F69A\n\nOur agent "
                       "will confirm your order and send your invoice here shortly. \U0001F64F")
            self._wa_send_msg(msg)
            return True
        except Exception as e:
            _logger.error("WA receipt SO %s failed: %s", self.id, e)
            self._wa_send_msg("Your order is saved. Our agent will assist you shortly. \U0001F64F")
            return False
