import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    wa_invoice_sent = fields.Boolean('WA Invoice Sent', copy=False)

    def action_post(self):
        res = super().action_post()
        if self.env.context.get('wa_skip_autosend'):
            return res
        for mv in self.filtered(
                lambda m: m.move_type == 'out_invoice' and not m.wa_invoice_sent):
            try:
                so = mv.invoice_line_ids.sale_line_ids.order_id[:1]
                sess = so.wa_employee_session_id if so else False
                if not sess:
                    continue
                phone = (so.wa_conversation_id.phone if so.wa_conversation_id else '') \
                    or mv.partner_id.phone or ''
                if not phone:
                    continue
                pdf, _x = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                    'account.account_invoices', mv.ids)
                fname = ((mv.name or 'Invoice').replace('/', '_')) + '.pdf'
                sess.session_id.send_document(phone, pdf, fname, caption='Invoice')
                mv.wa_invoice_sent = True
                try:
                    sess.session_id.send_message(
                        phone, "Your invoice is attached. Thank you! \U0001F64F")
                except Exception:
                    pass
            except Exception as e:
                _logger.error("WA invoice autosend move %s: %s", mv.id, e)
        return res
