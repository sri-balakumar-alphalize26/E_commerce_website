# -*- coding: utf-8 -*-
"""Stock arrived for a group order that was never paid: confirm, pay, then
invoice and delivery date - all in the group, the customer mentioned.

An out-of-stock enquiry becomes an order without payment (the group path
refuses to take money for goods the shop does not have). When the goods are
bought in and reserved, the customer is asked in the group to confirm; YES
posts the pay link there; a completed payment posts the paid invoice PDF and
the delivery date there too, and the private copies that the tracker and the
email bridge would send are held back for these orders.
"""
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SaAiSettingsPayRemind(models.Model):
    _inherit = 'sa.ai.settings'

    pay_remind_minutes = fields.Integer(
        'Remind unpaid orders after (minutes)', default=60,
        help="A customer who got a pay link and has not paid is reminded in "
             "the group after this long, and again after the same interval, "
             "up to the count below. 0 switches reminders off.")
    pay_remind_max = fields.Integer('Reminders at most', default=2)


class SaGroupRequestStockConfirm(models.Model):
    _inherit = 'sa.group.request'

    sa_stock_confirm_on = fields.Datetime('Stock Confirm Asked On', copy=False)
    sa_stock_confirmed = fields.Boolean('Confirmed After Stock', copy=False)
    sa_pay_link_sent_on = fields.Datetime('Pay Link Sent On', copy=False)
    sa_paid_told_on = fields.Datetime('Paid Invoice Sent On', copy=False)
    sa_paid_on = fields.Datetime('Paid On', copy=False)
    sa_pay_reminded_on = fields.Datetime('Last Pay Reminder', copy=False)
    sa_pay_remind_count = fields.Integer('Pay Reminders Sent', default=0, copy=False)

    def _sa_order_is_paid(self, order):
        return bool(order.invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
            and m.payment_state in ('paid', 'in_payment')))

    @api.model
    def _cron_pay_remind(self):
        """Unpaid after a pay link: remind in the group, link again, and say
        delivery goes out as soon as it is paid. Stops after the cap."""
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        minutes = int(settings.pay_remind_minutes or 0)
        cap = int(settings.pay_remind_max or 0)
        if minutes <= 0 or cap <= 0:
            return True
        now = fields.Datetime.now()
        from datetime import timedelta
        due = now - timedelta(minutes=minutes)
        rows = self.sudo().search([
            ('sa_pay_link_sent_on', '!=', False), ('sa_pay_link_sent_on', '<=', due),
            ('sa_paid_told_on', '=', False), ('order_id', '!=', False),
            ('order_id.state', 'not in', ('cancel',)),
            ('sa_pay_remind_count', '<', cap),
            '|', ('sa_pay_reminded_on', '=', False), ('sa_pay_reminded_on', '<=', due)])
        AR = self.env['wa.auto.reply'].sudo()
        for req in rows:
            order = req.order_id
            if req._sa_order_is_paid(order) or not req.group_id or not req.group_id.group_jid:
                continue
            try:
                pay = AR._online_pay_msg(order, 'card')
                # Numbered, so the group sender's duplicate guard never reads
                # reminder two as a repeat of reminder one.
                req._say(_("⏰ Reminder %(n)s of %(cap)s: your order *#%(ref)s* "
                           "(%(total)s %(cur)s) is still waiting for payment.\n\n%(pay)s\n\n"
                           "Pay once and delivery goes out quickly. \U0001F69A",
                           n=req.sa_pay_remind_count + 1, cap=cap,
                           ref=req.ref_code or order.name, total=('%.2f' % order.amount_total),
                           cur=order.currency_id.symbol or '', pay=pay))
                req.write({'sa_pay_reminded_on': now,
                           'sa_pay_remind_count': req.sa_pay_remind_count + 1})
            except Exception as err:  # noqa: BLE001 - next run
                _logger.warning("Pay reminder for %s failed: %s", order.name, err)
        return True

    # ------------------------------------------------------------------
    def _sa_order_summary(self, order):
        lines = order.order_line.filtered(lambda l: not l.display_type)
        first = lines[:1]
        products = lines.filtered('product_id')
        return {
            # A cart order names every item, not only the first.
            'product': (', '.join(products.mapped('product_id.display_name')) if len(products) > 1
                        else first.product_id.display_name if first else (self.product_id.display_name or '')),
            'qty': sum(lines.mapped('product_uom_qty')) or 0.0,
            'price': first.price_unit if first else (self.agreed_price or self.quoted_price or 0.0),
            'total': order.amount_total,
            'cur': order.currency_id.symbol or order.currency_id.name or '',
        }

    def _sa_ask_stock_confirm(self, job=None, repeat=False):
        """Ask in the group: the goods are here, do you still want them?"""
        self.ensure_one()
        order = self.order_id
        if not order or not self.group_id or not self.group_id.group_jid:
            return False
        s = self._sa_order_summary(order)
        if len(order.order_line.filtered(lambda l: not l.display_type and l.product_id)) > 1:
            # A cart order: every line, then the total.
            body = _("✅ *Good news* - the items for your order *#%(ref)s* are now in stock.\n\n"
                     "%(lines)s\n*Total: %(cur)s %(total).2f*\n\n"
                     "Shall we go ahead? Confirm your order.",
                     ref=self.ref_code or order.name, lines=self._sa_order_lines_text(order),
                     cur=s['cur'], total=s['total'])
        else:
            body = _("✅ *Good news* - *%(product)s* for your order *#%(ref)s* is now in stock.\n\n"
                     "%(qty)s x %(price).2f = *%(cur)s %(total).2f*\n\n"
                     "Shall we go ahead? Confirm your order.",
                     product=s['product'], ref=self.ref_code or order.name,
                     qty=('%g' % s['qty']), price=s['price'], cur=s['cur'], total=s['total'])
        if repeat:
            body = _("Please tap CONFIRM or CANCEL for order *#%(ref)s*.",
                     ref=self.ref_code or order.name)
        sent = self._ask(body, [{'id': 'sa_yes', 'title': _('CONFIRM')},
                                {'id': 'sa_no', 'title': _('CANCEL')}])
        self.write({'state': 'awaiting_order_confirm',
                    'sa_stock_confirm_on': fields.Datetime.now(),
                    'sa_stock_confirmed': False})
        _logger.info("Stock confirm: asked %s in %s for order %s (sent=%s)",
                     self.requester_phone, self.group_id.name, order.name, sent)
        return True

    @api.model
    def _sa_prepare_for_payment(self, order):
        """The portal page behind the pay link must ask for money, not a
        signature: a signed quotation confirms itself with nothing paid."""
        vals = {}
        # Both: the customer pays, then signs the confirmation on the same
        # page. Odoo would confirm on payment alone; see
        # PaymentTransactionGroup._check_amount_and_confirm_order.
        if 'require_signature' in order._fields and not order.require_signature:
            vals['require_signature'] = True
        if 'require_payment' in order._fields and not order.require_payment:
            vals['require_payment'] = True
        if 'prepayment_percent' in order._fields and (order.prepayment_percent or 0) < 1.0:
            vals['prepayment_percent'] = 1.0
        if vals:
            order.sudo().write(vals)
        return order

    def _sa_send_group_pay_link(self):
        """YES after stock: the pay link, in the group."""
        self.ensure_one()
        order = self.order_id
        if not order:
            return self._place_order()
        if order.state in ('draft', 'sent'):
            self._sa_prepare_for_payment(order)
        # A confirmed order cannot pay from its portal page; the any-state link
        # (sa_group_oos) copes with both.
        pay = (self._sa_pay_link_any_state(order) if hasattr(self, '_sa_pay_link_any_state')
               else self.env['wa.auto.reply'].sudo()._online_pay_msg(order, 'card'))
        body = _("✅ Order *#%(ref)s* confirmed - thank you.\n\n%(pay)s\n\n"
                 "Once the payment is done, your invoice and the delivery date "
                 "will be posted here.", ref=self.ref_code or order.name, pay=pay)
        self._say(body)
        self.write({'state': 'order_created', 'sa_stock_confirmed': True,
                    'sa_pay_link_sent_on': fields.Datetime.now()})
        return True

    def _sa_stock_declined(self):
        """NO after stock: the deal is off, the order and its job with it."""
        self.ensure_one()
        self.write({'sa_stock_confirmed': False})
        return self._sa_cancel_deal()

    def _sa_group_paid(self, order):
        """Payment landed. If the confirmation still needs the customer's
        signature, ask for it here, on the same link; the signature confirms
        the order and `_sa_group_confirmed` finishes the job. Otherwise
        confirm now and finish at once."""
        self.ensure_one()
        if self.sa_paid_told_on:
            return False
        order = order.sudo()
        if 'auto_wa_sent_at_confirm' in order._fields:
            order.write({'auto_wa_sent_at_confirm': True})     # no private SO PDF
        if not self.sa_paid_on:
            self.write({'sa_paid_on': fields.Datetime.now()})
        if order.state in ('draft', 'sent') and order._has_to_be_signed():
            link = self.env['wa.auto.reply'].sudo()._sa_public_link(
                '/my/orders/%s?access_token=%s' % (order.id, order._portal_ensure_token()))
            self._say(_("✅ Payment received for order *#%(ref)s* - thank you!\n\n"
                        "One last step: please sign your order confirmation here:\n%(link)s\n\n"
                        "Your invoice and the delivery date follow the moment it is signed.",
                        ref=self.ref_code or order.name, link=link))
            return True
        if order.state in ('draft', 'sent'):
            order.action_confirm()
        return self._sa_group_confirmed(order)

    def _sa_group_confirmed(self, order):
        """Confirmed and paid: invoice, post, and the paid invoice PDF plus the
        delivery date go to the group. Once."""
        self.ensure_one()
        if self.sa_paid_told_on:
            return False
        order = order.sudo()
        if 'auto_wa_sent_at_confirm' in order._fields and not order.auto_wa_sent_at_confirm:
            order.write({'auto_wa_sent_at_confirm': True})
        self._sa_after_part('invoice', lambda: self._sa_paid_invoice(order))
        first = order.invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state != 'cancel').sorted('id')[:1]
        if self.env.context.get('sa_after_task'):
            self._sa_after_part('invoice_pdf', lambda: self._sa_must_send(
                lambda: self._sa_paid_send_invoice(first)), sends=True)
        else:
            try:
                self._sa_paid_send_invoice(first)
            except Exception as err:  # noqa: BLE001 - the words still go out
                _logger.warning("Stock confirm: invoice PDF not sent for %s: %s", order.name, err)
        job = order.picking_ids.filtered(
            lambda p: p.state != 'cancel' and getattr(p, 'sa_delivery_state', 'none') not in ('none', False, 'cancelled')
        ).sorted('id')[:1]
        if job and hasattr(job, 'sa_refresh_cod'):
            try:
                job.sa_refresh_cod()                 # paid now: nothing to collect
            except Exception as err:  # noqa: BLE001
                _logger.warning("Stock confirm: COD refresh for %s failed: %s", job.name, err)
        settings = self.env['sa.delivery.settings'].sudo().get_settings() \
            if 'sa.delivery.settings' in self.env else None
        tell_date = bool(settings and getattr(settings, 'promise_customer', True)) if settings else True
        when = ''
        if job and job.sa_promised_on and tell_date:
            labels = dict(job._fields['sa_delivery_kind']._description_selection(self.env)) \
                if 'sa_delivery_kind' in job._fields else {}
            kind = labels.get(job.sa_delivery_kind, '') if 'sa_delivery_kind' in job._fields else ''
            local = fields.Datetime.context_timestamp(self, job.sa_promised_on)
            when = _("\n\U0001F69A *Delivery:* %(kind)s%(date)s.",
                     kind=(kind + ', ') if kind else '',
                     date=local.strftime('%a %d %b, by %I:%M %p').lstrip('0'))
        if job or self._sa_flow_end() == 'delivery':
            body = _("✅ Payment received for order *#%(ref)s* - thank you!\n"
                     "Invoice %(inv)s is above.%(when)s\n\nWe will message here when "
                     "your order is packed and the rider is on the way.",
                     ref=self.ref_code or order.name, inv=first.name or '', when=when)
        else:
            body = _("✅ Payment received for order *#%(ref)s* - thank you!\n"
                     "Invoice %(inv)s is above.\n\nYour order is complete. We will "
                     "contact you about the handover.",
                     ref=self.ref_code or order.name, inv=first.name or '')
        # signed and paid: now the order is placed (owner, 23 Nov 2026)
        done = _("✅ Done! Your order *%(order)s* is placed.\n\n%(lines)s\n*Total: %(cur)s %(total).2f*",
                 order=order.name, lines=self._sa_order_lines_text(order),
                 cur=order.currency_id.symbol or '', total=order.amount_total)
        text = '%s\n\n%s' % (done, body)
        if self.env.context.get('sa_after_task'):
            self._sa_after_part('words', lambda: self._sa_must_send(
                lambda: self._say(self._sa_after_again(text))), sends=True)
        else:
            self._say(text)
        self.write({'sa_paid_told_on': fields.Datetime.now()})
        return True

    def _sa_paid_invoice(self, order):
        """The invoice of a paid order: made once, posted, the payment matched."""
        self.ensure_one()
        inv = order.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice'
                                         and m.state != 'cancel')
        if not inv:
            inv = order._create_invoices()
        if 'auto_wa_sent_at_post' in inv._fields:
            inv.write({'auto_wa_sent_at_post': True})          # no private invoice PDF
        inv.filtered(lambda m: m.state == 'draft').with_context(wa_skip_autosend=True).action_post()
        # The money arrived before the invoice existed, so the payment sits
        # unmatched. Match it now, before the PDF is made - otherwise the
        # document the customer gets still says the full amount is due.
        first = inv.sorted('id')[:1]
        try:
            with self.env.cr.savepoint():
                for tx in order.transaction_ids.filtered(lambda t: t.state == 'done'):
                    if first not in tx.invoice_ids:
                        tx.sudo().write({'invoice_ids': [(4, first.id)]})
                    pay = tx.payment_id
                    if pay and pay.move_id:
                        for line in pay.move_id.line_ids.filtered(
                                lambda l: l.account_id.account_type == 'asset_receivable'
                                and not l.reconciled):
                            if first.state == 'posted' and first.amount_residual:
                                first.js_assign_outstanding_line(line.id)
                first.invalidate_recordset(['payment_state', 'amount_residual'])
        except Exception as err:  # noqa: BLE001 - an unmatched payment is a bookkeeping job, not a lost message
            _logger.warning("Stock confirm: could not match the payment to %s: %s", first.name, err)
        return first

    def _sa_paid_send_invoice(self, first):
        """The invoice PDF: privately when allowed, the group otherwise."""
        self.ensure_one()
        paid_word = _("PAID") if first.payment_state in ('paid', 'in_payment') else _("payment received")
        session = self.group_id.session_id
        pdf, _x = self.env['ir.actions.report'].sudo()._render_qweb_pdf('account.account_invoices', first.ids)
        fname = ((first.name or 'Invoice').replace('/', '_')) + '.pdf'
        caption = _("\U0001F9FE Invoice %(name)s - %(paid)s. Thank you!",
                    name=first.name or '', paid=paid_word)
        return self._sa_send_doc(
            lambda to: session.send_document(to, pdf, fname, caption=caption),
            note=_("\U0001F9FE Invoice %s sent to your *private chat* \U0001F512") % (first.name or ''))


class SaleOrderGroupEnquiry(models.Model):
    _inherit = 'sale.order'

    def _sa_group_enquiry(self):
        """The group enquiry this order came from. The forward link is not
        always written (3 of 75 orders lack it); the enquiry's own `order_id`
        always is."""
        self.ensure_one()
        if self.sa_group_request_id:
            return self.sa_group_request_id
        return self.env['sa.group.request'].sudo().search(
            [('order_id', '=', self.id)], order='id desc', limit=1)

    # The "confirmed after payment -> invoice + delivery date in the group"
    # hook lives in sales_automation_store (stock_picking_group_chat.py): it
    # must run AFTER the delivery module has raised and promised the job,
    # and that module loads after this one.


class PaymentTransactionGroup(models.Model):
    _inherit = 'payment.transaction'

    def _check_amount_and_confirm_order(self):
        """A paid group order that still needs the customer's signature is
        NOT confirmed by the payment - the signature does that, on the same
        page. Everything else keeps Odoo's behaviour."""
        def held(tx):
            so = tx.sale_order_ids
            return (len(so) == 1 and so.require_signature and not so.signature
                    and so._sa_group_enquiry() and so._sa_group_enquiry().group_id)
        rest = self.filtered(lambda t: not held(t))
        if rest:
            return super(PaymentTransactionGroup, rest)._check_amount_and_confirm_order()
        return self.env['sale.order']

    def _post_process(self):
        """For group-born orders the tracker's private 'Invoice (Paid)' send is
        held back (it skips orders with no employee session) and the group is
        told instead."""
        done = self.filtered(lambda t: t.state == 'done')
        group_orders = done.mapped('sale_order_ids').filtered(
            lambda so: so._sa_group_enquiry() and so._sa_group_enquiry().group_id)
        saved = {so.id: so.wa_employee_session_id.id for so in group_orders}
        if group_orders:
            group_orders.sudo().write({'wa_employee_session_id': False})
        try:
            res = super()._post_process()
        finally:
            for so in group_orders:
                if saved.get(so.id):
                    so.sudo().write({'wa_employee_session_id': saved[so.id]})
        for so in group_orders:
            try:
                so._sa_group_enquiry().sudo()._sa_group_paid(so)
            except Exception as err:  # noqa: BLE001 - never break a payment
                _logger.error("Stock confirm: group paid message failed for %s: %s", so.name, err)
        return res
