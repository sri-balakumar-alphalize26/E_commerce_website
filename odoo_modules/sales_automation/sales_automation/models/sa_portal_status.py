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
            'paid': bool(paid or (due <= 0.005 and (o.amount_total or 0.0) > 0)),
            'delivered': delivered,
        }

    # -- the page itself (13 Nov 2026, design A: the storefront checkout look) --

    def _sa_line_kind(self, line):
        """'item', 'fee' (delivery / priority fee) or 'other' (coupon, reward,
        anything negative) - the storefront's, the WhatsApp Quick/Express
        module's and Odoo's own way of marking a delivery line."""
        if line.display_type:
            return ''
        if line._is_delivery():
            return 'fee'
        for field in ('mart369_kind', 'qe_kind'):
            if field in line._fields and line[field] == 'fee':
                return 'fee'
        if 'mart369_kind' in line._fields and line.mart369_kind == 'coupon':
            return 'other'
        if (line.price_total or 0.0) < 0 or getattr(line, 'is_downpayment', False):
            return 'other'
        return 'item'

    @staticmethod
    def _sa_qty_text(qty):
        return ('%d' % qty) if float(qty).is_integer() else ('%g' % qty)

    def _sa_portal_page(self, payment_amount=False):
        """Everything the order page draws, in one place: which step the
        customer is on (sign / pay / pay_link / done / wait / cancel), the
        Sign - Pay - Delivery bar, the items and the bill.

        The sign and pay boxes stay Odoo's own (signature form, payment form),
        shown inline in the page's right-hand card; the rules for which one
        shows are Odoo's own (sale.sale_order_portal_template, #modalaccept),
        copied here so the card's heading matches the box underneath."""
        self.ensure_one()
        o = self.sudo()
        st = self._sa_portal_status()
        has_sign = o._has_to_be_signed()
        sign_inline = bool(has_sign and not payment_amount)
        pay_inline = bool(not sign_inline and (
            (not has_sign and o._has_to_be_paid())
            or (payment_amount and o.state != 'cancel')))
        paid, delivered = st['paid'], st['delivered']
        if o.state == 'cancel':
            step = 'cancel'
        elif sign_inline:
            step = 'sign'
        elif pay_inline:
            step = 'pay'
        elif paid or delivered:
            step = 'done'
        elif st['pay_url']:
            step = 'pay_link'
        else:
            step = 'wait'

        signed = bool(o.signature)
        tx = o.get_portal_last_transaction()
        tx_pending = bool(tx and tx.state in ('pending', 'authorized') and not paid)

        # The step bar: what is done first, then where the customer is, then the rest.
        bar = []
        if o.require_signature or signed:
            bar.append(('sign', _("Sign"), signed))
        if (o.amount_total or 0.0) > 0:
            bar.append(('pay', _("Pay"), paid))
        bar.append(('delivery', _("Delivery"), delivered))
        current = {'sign': 'sign', 'pay': 'pay', 'pay_link': 'pay', 'wait': 'pay',
                   'done': 'delivery'}.get(step)
        if current not in {key for key, _label, _done in bar}:
            current = 'delivery'
        steps = []
        for number, (key, label, done) in enumerate(
                [b for b in bar if b[2]] + [b for b in bar if not b[2]], 1):
            state = 'done' if done else ('cur' if key == current else 'todo')
            steps.append({'n': number, 'label': label, 'state': state})

        items, fees, others = [], 0.0, 0.0
        for line in o.order_line.sorted('sequence'):
            kind = self._sa_line_kind(line)
            if kind == 'fee':
                fees += line.price_total
            elif kind == 'other':
                others += line.price_total
            elif kind == 'item':
                qty = line.product_uom_qty or 0.0
                unit = line.price_total / qty if qty else line.price_unit
                uom = line.product_uom_id.name if 'product_uom_id' in line._fields else ''
                qty_text = self._sa_qty_text(qty)
                if uom and uom.lower() not in ('units', 'unit'):
                    qty_text = '%s %s' % (qty_text, uom)
                name = (line.name or line.product_id.display_name or '').split('\n')[0]
                items.append({
                    'name': name,
                    'qty_text': _("%(qty)s × %(price)s", qty=qty_text, price=self._sa_money_text(unit)),
                    'total_text': self._sa_money_text(line.price_total),
                    'product': line.product_id,
                    'initial': (name[:1] or '?').upper(),
                })
        rows = [{'label': _("Items"), 'amount': self._sa_money_text(
            sum(line.price_total for line in o.order_line if self._sa_line_kind(line) == 'item'))}]
        if fees:
            rows.append({'label': _("Delivery"), 'amount': self._sa_money_text(fees)})
        if others:
            rows.append({'label': _("Savings") if others < 0 else _("Other"),
                         'amount': self._sa_money_text(others)})

        ship = o.partner_shipping_id
        address = ', '.join(p for p in (ship.street, ship.street2, ship.city) if p) if ship else ''
        subtitle = {
            'sign': _("Check your order, then sign to confirm it."),
            'pay': _("Signed. Choose how you want to pay.") if signed
            else _("Choose how you want to pay."),
            'pay_link': _("Your order is confirmed. Pay now to finish."),
            'done': _("Delivered. Thank you for shopping with us.") if delivered
            else _("Thank you! Your order is confirmed."),
            'wait': st['label'],
            'cancel': _("This order was cancelled."),
        }[step]
        return {
            'step': step, 'subtitle': subtitle, 'steps': steps, 'status': st,
            'items': items, 'rows': rows, 'total_text': self._sa_money_text(o.amount_total),
            'address': address, 'signed_by': o.signed_by if signed else '',
            'tx_pending': tx_pending,
            'pdf_url': o.get_portal_url(report_type='pdf'),
        }
