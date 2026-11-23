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
        """The amount with the decimals Odoo is set to for this currency (its
        rounding, Accounting > Currencies) - the same as Odoo's own payment
        pages, invoices and PDFs (13 Nov 2026, owner). It used the currency's
        official decimals before, which disagreed with Odoo's pages wherever
        the rounding differs (AED set to 0.001 shows 3 decimals in Odoo)."""
        self.ensure_one()
        cur = self.currency_id
        digits = cur.decimal_places if cur else 2
        number = '{:,.{d}f}'.format(amount or 0.0, d=digits)
        symbol = cur.symbol or cur.name or ''
        return '%s %s' % (number, symbol) if cur.position == 'after' else '%s %s' % (symbol, number)

    def _sa_portal_status(self):
        self.ensure_one()
        o = self.sudo()
        Req = self.env['sa.group.request'].sudo()
        paid = Req._sa_order_is_paid(o)
        # Money taken online counts at once (Odoo's amount_paid: done or
        # authorized transactions), not only when the invoice is paid - a
        # card payment with no invoice yet still showed "Pay" (13 Nov 2026).
        online = o.amount_paid if 'amount_paid' in o._fields else 0.0
        due = max((o.amount_total or 0.0) - (o._sa_paid_elsewhere() or 0.0) - (online or 0.0), 0.0)
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
        # A WhatsApp group order is paid only once its pay link went out
        # (21 Nov 2026): not while the goods are being arranged, and never when
        # the flow ends at the signed order or the invoice.
        enquiry = o._sa_group_enquiry() if hasattr(o, '_sa_group_enquiry') else False
        payable = not enquiry or bool(enquiry.sa_pay_link_sent_on)
        if tone == 'wait' and due > 0.005 and not o._has_to_be_signed() and payable:
            try:
                pay_url = Req._sa_pay_url(o) or ''
            except Exception:  # noqa: BLE001 - the page must still show
                pay_url = ''
        delivery = _(STATUS_WORDS[dstate]) if dstate in STATUS_WORDS and o.state != 'cancel' else ''
        track_url = ''
        if dstate in IN_FLIGHT and 'sa_track_url' in job._fields:
            track_url = job.sa_track_url or ''
        invoices = o.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
        # The PDF itself, not Odoo's invoice page (13 Nov 2026: "Download
        # invoice" opened the old Odoo screen).
        invoice_url = (invoices[:1].get_portal_url(report_type='pdf', download=True)
                       if invoices and (paid or delivered) else '')
        shown = due if tone == 'wait' else (o.amount_total or 0.0)
        return {
            'icon': icon, 'label': label, 'tone': tone, 'amount_text': self._sa_money_text(shown),
            'due': due, 'total': o.amount_total, 'currency': o.currency_id,
            'pay_url': pay_url if pay_url.startswith('http') or pay_url.startswith('/') else '',
            'delivery': delivery, 'track_url': track_url, 'invoice_url': invoice_url,
            'paid': bool(paid or (due <= 0.005 and (o.amount_total or 0.0) > 0)),
            'delivered': delivered,
            'dstate': dstate or '',
            'promised_on': job.sa_promised_on if job and 'sa_promised_on' in job._fields else False,
            'rider': (job.sa_delivery_partner_id.name or '')
            if job and 'sa_delivery_partner_id' in job._fields else '',
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

    # -- delivery slots on the order page (13 Nov 2026) - hooks only here --
    # The slots live in the storefront modules; mart369_whatsapp_bridge fills
    # these in. Without it the page simply shows no slot picker.

    def _sa_portal_slots(self):
        """{'chips': [{key, top, sub, label}], 'chosen': key} for the optional
        slot picker - empty when slots are off, none apply, or the order is
        past choosing (signed, confirmed, paid)."""
        return {'chips': [], 'chosen': ''}

    def _sa_portal_set_slot(self, key):
        """Book slot `key` on this order ('' = no preference). Returns an
        error text for the customer, or '' when done."""
        return _("Delivery slots are not available for this order.")

    def _sa_portal_promise(self, step, status):
        """When the delivery is due, in the words the order already has
        (13 Nov 2026) - first found wins: the slot the customer chose on the
        website or in WhatsApp, the delivery job's promise once it exists
        (the one every WhatsApp update quotes), the due time, the promise
        text. '' when there is none, or when the shop has switched off telling
        customers a date (Delivery Settings > promise_customer)."""
        self.ensure_one()
        o = self.sudo()
        settings = (self.env['sa.delivery.settings'].sudo().get_settings()
                    if 'sa.delivery.settings' in self.env else None)
        if settings and not getattr(settings, 'promise_customer', True):
            return ''
        when = lambda dt: self.env['sa.group.request']._sa_ss_when(dt, o.company_id)  # noqa: E731
        if 'mart369_slot_label' in o._fields and o.mart369_slot_label:
            return o.mart369_slot_label
        if 'qe_slot_id' in o._fields and o.qe_slot_id:
            day = o.qe_slot_day.strftime('%d %b') if 'qe_slot_day' in o._fields and o.qe_slot_day else ''
            return ', '.join(p for p in (day, o.qe_slot_id.name) if p)
        if step == 'done' and status.get('promised_on'):
            return _("By %s", when(status['promised_on']))
        for field in ('qe_due_at', 'mart369_due_at'):
            if field in o._fields and o[field]:
                return _("By %s", when(o[field]))
        if 'mart369_eta' in o._fields and o.mart369_eta:
            return o.mart369_eta
        return ''

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
            # an old pay address opened again (phone's Back) shows Paid, not Pay
            or (payment_amount and o.state != 'cancel' and not st['paid'])))
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
                    # the image server's address, or the picture inline as
                    # before - never downloaded here when it lives there
                    'picture': self.env['sa.picture'].src(line.product_id, 'image_128'),
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
        # The paid card (13 Nov 2026): how it was paid, and where the delivery is.
        promise = self._sa_portal_promise(step, st)
        paid_with, timeline = {}, []
        if step == 'done':
            done_tx = o.transaction_ids.filtered(lambda t: t.state in ('done', 'authorized')).sorted('id')[-1:]
            if done_tx:
                when = done_tx.last_state_change
                paid_with = {
                    'method': done_tx.payment_method_id.name or done_tx.provider_id.name or '',
                    'when': when.strftime('%d %b %Y') if when else '',
                    'ref': done_tx.reference or '',
                }
            dstate = st['dstate']
            on_road = dstate in ('to_assign', 'offered', 'accepted', 'picked', 'dispatched', 'out_for_delivery')
            stage = 2 if delivered else 1 if on_road else 0
            road_note = (_("With %s", st['rider']) if st['rider'] and dstate in ('picked', 'dispatched', 'out_for_delivery')
                         else st['delivery'] if on_road else '')
            for index, (label, note) in enumerate((
                    (_("Packing"), st['delivery'] if stage == 0 else ''),
                    (_("On the way"), road_note),
                    (_("Delivered"), '' if delivered else promise))):
                state = 'done' if index < stage or delivered else ('cur' if index == stage else 'todo')
                timeline.append({'label': label, 'note': note, 'state': state})

        return {
            'paid_with': paid_with, 'timeline': timeline, 'promise': promise,
            'step': step, 'subtitle': subtitle, 'steps': steps, 'status': st,
            'items': items, 'rows': rows, 'total_text': self._sa_money_text(o.amount_total),
            'address': address, 'signed_by': o.signed_by if signed else '',
            'tx_pending': tx_pending,
            'pdf_url': o.get_portal_url(report_type='pdf'),
        }
