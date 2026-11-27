"""Reusable mixin for cross-channel (Email + WhatsApp) send buttons.

Any order/document model can inherit `whatsapp.email.sendable.mixin` to gain
two methods:
  - action_send_via_channels()             → opens the channel/session picker
  - _send_via_channels_with_sessions(...)  → called by the wizard, dispatches

Subclasses set three class-level attributes to customize the message:
  _wa_report_xmlid   (optional QWeb report PDF xmlid; '' = caption-only)
  _wa_doc_emoji      (emoji prefix in WhatsApp caption)
  _wa_doc_label      (label like "Sales Order")

The easy_sales / estimate_sale / easy_purchase / estimate_purchase buttons
live in four small link modules (whatsapp_email_easy_sales, ..._estimate_sale,
..._easy_purchase, ..._estimate_purchase). Each installs itself where both its
module and whatsapp_email are installed, so neither depends on the other.
"""

import logging

from odoo import models, _

_logger = logging.getLogger(__name__)


class WhatsAppEmailSendableMixin(models.AbstractModel):
    _name = 'whatsapp.email.sendable.mixin'
    _description = 'Send via Email/WhatsApp helper mixin'

    # Subclasses override:
    _wa_report_xmlid = ''       # leave blank → caption-only
    _wa_doc_emoji = '📄'
    _wa_doc_label = 'Document'

    def _wa_subject(self):
        return _('%s %s - %s') % (
            self._wa_doc_label,
            getattr(self, 'name', '') or '',
            self.env.company.name,
        )

    def _wa_caption(self):
        symbol = self.currency_id.symbol if getattr(self, 'currency_id', False) else ''
        amount = getattr(self, 'amount_total', 0) or 0
        partner = getattr(self, 'partner_id', False)
        partner_name = partner.name if partner else ''
        return _(
            '%(emoji)s *%(label)s %(name)s*\n'
            '👤 %(partner)s\n'
            '💰 Total: %(symbol)s %(amount)s\n'
            '— %(company)s'
        ) % {
            'emoji': self._wa_doc_emoji,
            'label': self._wa_doc_label,
            'name': getattr(self, 'name', '') or '',
            'partner': partner_name,
            'symbol': symbol,
            'amount': '{:,.2f}'.format(amount),
            'company': self.env.company.name,
        }

    def _send_via_channels_with_sessions(self, send_email, send_whatsapp,
                                         email_session=None, whatsapp_session=None):
        self.ensure_one()
        if getattr(self, 'company_id', False):
            self = self.with_company(self.company_id)   # the document's company sends it
        partner = getattr(self, 'partner_id', False)
        if not partner:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Cannot send'),
                    'message': _('This document has no partner — set one first.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        result = self.env['whatsapp.email.dispatch'].send_record(
            record=self,
            partner=partner,
            report_xmlid=self._wa_report_xmlid or False,
            subject=self._wa_subject(),
            wa_caption=self._wa_caption(),
            send_email=send_email,
            send_whatsapp=send_whatsapp,
            email_session=email_session,
            whatsapp_session=whatsapp_session,
        )
        return self.env['whatsapp.email.dispatch'].send_result_notification(result)

    def action_send_via_channels(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send via Email & WhatsApp'),
            'res_model': 'whatsapp.send.channel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }
