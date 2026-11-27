from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    auto_email_sent_at_post = fields.Boolean(default=False, copy=False)
    auto_wa_sent_at_post = fields.Boolean(default=False, copy=False)

    def _post(self, soft=True):
        """Auto-send on posting - hooked here, not on action_post().

        Point of Sale posts its invoice with a direct
        `invoice.sudo().with_company(...)._post()`
        (point_of_sale/models/pos_order.py), and `action_post()` is only a
        wrapper that calls `_post()`. Hooking the wrapper therefore missed every
        POS invoice - which is why the invoice reached the customer by email
        (core sends that itself) and never by WhatsApp. Hooking `_post` covers
        the backend button too, since that route passes through here.
        """
        posted = super()._post(soft=soft)
        for move in posted:
            if move.state != 'posted':
                continue
            if move.move_type not in ('in_invoice', 'out_invoice'):
                continue
            method = ('_auto_send_vendor_bill' if move.move_type == 'in_invoice'
                      else '_auto_send_customer_invoice')
            # After commit, deliberately. Each WhatsApp message carries a
            # 1200 ms pacing delay and the gateway read-timeout is 30 s; neither
            # belongs inside the transaction that records a sale.
            # priority 10: before the payment receipt, which is 20.
            self.env['whatsapp.email.dispatch'].run_after_commit(
                'account.move', move.ids, method, priority=10)
        return posted

    def _auto_send_vendor_bill(self):
        self.ensure_one()
        self = self.with_company(self.company_id)  # the document's company sends it
        config = self.env['whatsapp.email.dispatch'].get_config()
        if not config:
            return
        send_email = bool(config.auto_send_bill_email) and not self.auto_email_sent_at_post
        send_wa = bool(config.auto_send_bill_wa) and not self.auto_wa_sent_at_post
        if not (send_email or send_wa):
            return
        self.env['whatsapp.email.dispatch'].send_record(
            record=self,
            partner=self.partner_id,
            report_xmlid='account.account_invoices',
            subject=_('Vendor Bill %s - %s') % (
                self.name or self.ref or '', self.env.company.name,
            ),
            wa_caption=_('🧾 Vendor Bill %s\nAmount: %s %s') % (
                self.name or self.ref or '',
                self.currency_id.symbol or '',
                '{:,.2f}'.format(self.amount_total or 0),
            ),
            send_email=send_email,
            send_whatsapp=send_wa,
        )
        flags = {}
        if send_email:
            flags['auto_email_sent_at_post'] = True
        if send_wa:
            flags['auto_wa_sent_at_post'] = True
        if flags:
            self.write(flags)

    def _auto_send_customer_invoice(self):
        self.ensure_one()
        self = self.with_company(self.company_id)  # the document's company sends it
        config = self.env['whatsapp.email.dispatch'].get_config()
        if not config:
            return
        send_email = bool(config.auto_send_invoice_email) and not self.auto_email_sent_at_post
        send_wa = bool(config.auto_send_invoice_wa) and not self.auto_wa_sent_at_post
        if not (send_email or send_wa):
            return
        self.env['whatsapp.email.dispatch'].send_record(
            record=self,
            partner=self.partner_id,
            report_xmlid='account.account_invoices',
            subject=_('Invoice %s - %s') % (
                self.name or '', self.env.company.name,
            ),
            wa_caption=_('🧾 Invoice %s\nAmount: %s %s') % (
                self.name or '',
                self.currency_id.symbol or '',
                '{:,.2f}'.format(self.amount_total or 0),
            ),
            send_email=send_email,
            send_whatsapp=send_wa,
        )
        flags = {}
        if send_email:
            flags['auto_email_sent_at_post'] = True
        if send_wa:
            flags['auto_wa_sent_at_post'] = True
        if flags:
            self.write(flags)

    def action_send_via_channels(self):
        """Manual button — picker wizard for invoices."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send WhatsApp & Email'),
            'res_model': 'whatsapp.send.channel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': 'account.move',
                'default_res_id': self.id,
            },
        }

    def _send_via_channels_with_sessions(self, send_email, send_whatsapp,
                                         email_session=None, whatsapp_session=None):
        self.ensure_one()
        self = self.with_company(self.company_id)  # the document's company sends it
        if self.move_type == 'out_invoice':
            subj = _('Invoice %s - %s') % (self.name or '', self.env.company.name)
            cap = _('🧾 Invoice %s\nAmount: %s %s') % (
                self.name or '',
                self.currency_id.symbol or '',
                '{:,.2f}'.format(self.amount_total or 0),
            )
        else:
            subj = _('Vendor Bill %s - %s') % (self.name or self.ref or '', self.env.company.name)
            cap = _('🧾 Vendor Bill %s\nAmount: %s %s') % (
                self.name or self.ref or '',
                self.currency_id.symbol or '',
                '{:,.2f}'.format(self.amount_total or 0),
            )
        result = self.env['whatsapp.email.dispatch'].send_record(
            record=self,
            partner=self.partner_id,
            report_xmlid='account.account_invoices',
            subject=subj,
            wa_caption=cap,
            send_email=send_email,
            send_whatsapp=send_whatsapp,
            email_session=email_session,
            whatsapp_session=whatsapp_session,
        )
        return self.env['whatsapp.email.dispatch'].send_result_notification(result)
