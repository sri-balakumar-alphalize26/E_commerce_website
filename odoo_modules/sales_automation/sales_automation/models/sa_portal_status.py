# -*- coding: utf-8 -*-
"""What the customer's order page (/my/orders/<id>) prints in its status card
(owner, 8 Oct 2026): where the order is, how much is still due, PAY NOW even on
a confirmed order (Odoo hides its own Pay once the order is confirmed), the
delivery words the WhatsApp messages use, the tracking link and the invoice.
Read-only, sudo: the page is opened by the customer, not by staff."""
from odoo import _, models

from .sa_self_service import IN_FLIGHT, STATUS_WORDS

INTERNAL_NOTE_START = 'order created via whatsapp'


class SaleOrderPortalStatus(models.Model):
    _inherit = 'sale.order'

    def _sa_portal_note_is_internal(self):
        """The note our WhatsApp flow writes (employee, phone) is for staff."""
        self.ensure_one()
        from odoo.tools import html2plaintext
        text = html2plaintext(self.sudo().note or '').strip().lower()
        return text.startswith(INTERNAL_NOTE_START)

    def _sa_money_text(self, amount):
        """The amount with the currency's OFFICIAL decimals (AED 2, OMR 3),
        whatever its rounding is set to: DUBAI_TEST's AED rounds to 0.001,
        which printed "2,600.000 AED" on the customer's page."""
        self.ensure_one()
        cur = self.currency_id
        try:
            from babel.numbers import get_currency_precision
            digits = get_currency_precision(cur.name)
        except Exception:  # noqa: BLE001
            digits = cur.decimal_places
        number = '{:,.{d}f}'.format(amount or 0.0, d=digits)
        symbol = cur.symbol or cur.name or ''
        return '%s %s' % (number, symbol) if cur.position == 'after' else '%s %s' % (symbol, number)

    def _sa_portal_status(self):
        self.ensure_one()
        o = self.sudo()
        Req = self.env['sa.group.request'].sudo()
        paid = Req._sa_order_is_paid(o)
        due = max((o.amount_total or 0.0) - (o._sa_paid_elsewhere() or 0.0), 0.0)
        if paid:
            due = 0.0
        jobs = o.picking_ids.filtered(lambda p: p.state != 'cancel' and p.picking_type_id.code == 'outgoing')
        job = jobs.sorted('id', reverse=True)[:1]
        dstate = job.sa_delivery_state if job and 'sa_delivery_state' in job._fields else False
        delivered = dstate == 'delivered'
        if o.state == 'cancel':
            icon, label, tone = '❌', _("Cancelled"), 'off'
        elif o.state in ('draft', 'sent') and o._has_to_be_signed():
            icon, label, tone = '✍️', _("Waiting for your signature"), 'wait'
        elif delivered and (paid or due <= 0.005):
            icon, label, tone = '✅', _("Delivered"), 'ok'
        elif paid or due <= 0.005:
            icon, label, tone = '✅', _("Paid"), 'ok'
        elif o.state in ('draft', 'sent'):
            icon, label, tone = '⏳', _("Not confirmed yet · Payment pending"), 'wait'
        else:
            icon, label, tone = '⏳', _("Confirmed · Payment pending"), 'wait'
        pay_url = ''
        if tone == 'wait' and due > 0.005 and not o._has_to_be_signed():
            try:
                pay_url = Req._sa_pay_url(o) or ''
            except Exception:  # noqa: BLE001 - the page must still show
                pay_url = ''
        delivery = _(STATUS_WORDS[dstate]) if dstate in STATUS_WORDS and o.state != 'cancel' else ''
        track_url = ''
        if dstate in IN_FLIGHT and 'sa_track_url' in job._fields:
            track_url = job.sa_track_url or ''
        invoices = o.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
        invoice_url = invoices[:1].get_portal_url() if invoices and (paid or delivered) else ''
        shown = due if tone == 'wait' else (o.amount_total or 0.0)
        return {
            'icon': icon, 'label': label, 'tone': tone, 'amount_text': self._sa_money_text(shown),
            'due': due, 'total': o.amount_total, 'currency': o.currency_id,
            'pay_url': pay_url if pay_url.startswith('http') or pay_url.startswith('/') else '',
            'delivery': delivery, 'track_url': track_url, 'invoice_url': invoice_url,
        }
