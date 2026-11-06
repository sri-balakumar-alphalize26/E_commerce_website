import logging
from odoo import models

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _post_process(self):
        res = super()._post_process()
        for tx in self.filtered(lambda t: t.state == 'done'):
            for so in tx.sale_order_ids:
                sess = so.wa_employee_session_id
                if not sess:
                    continue
                try:
                    if so.state in ('draft', 'sent'):
                        so.action_confirm()
                    inv = so.invoice_ids.filtered(
                        lambda m: m.move_type == 'out_invoice' and m.state != 'cancel')
                    if not inv:
                        inv = so._create_invoices()
                    inv.filtered(lambda m: m.state == 'draft').action_post()
                    pdf, _x = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                        'account.account_invoices', inv.ids)
                    phone = (so.wa_conversation_id.phone if so.wa_conversation_id else '') \
                        or so.partner_id.phone or ''
                    fname = ((inv[:1].name or 'Invoice').replace('/', '_')) + '.pdf'
                    if phone:
                        sess.session_id.send_document(phone, pdf, fname, caption='Invoice (Paid)')
                    so.wa_payment_mode = 'online'
                except Exception as e:
                    _logger.error("WA online finalize failed for SO %s: %s", so.id, e)
        return res
