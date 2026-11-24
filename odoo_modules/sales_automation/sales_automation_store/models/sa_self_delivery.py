# -*- coding: utf-8 -*-
"""Delivered by our own staff, no rider (owner, 24 Nov 2026): the customer gets
the code at once, the staff types it. The rider's way is not touched. And how the
payment of an order stands, in one place for the list and the open order."""
import logging

import psycopg2

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .sa_boards import iso

_logger = logging.getLogger(__name__)

SELF_FROM = ('preparing', 'ready', 'to_assign')


class StockPickingSelf(models.Model):
    _inherit = 'stock.picking'

    sa_self_delivery = fields.Boolean('Delivered by Our Staff', readonly=True, copy=False)
    sa_self_user_id = fields.Many2one('res.users', 'Our Staff', readonly=True, copy=False)
    sa_cash_taken = fields.Float('Cash Received', readonly=True, copy=False, help="Said by the staff; no payment is booked by it.")
    sa_cash_user_id = fields.Many2one('res.users', 'Cash Received By', readonly=True, copy=False)
    sa_cash_on = fields.Datetime('Cash Received On', readonly=True, copy=False)

    # ------------------------------------------------------------ may it start
    def _sa_self_problem(self):
        self.ensure_one()
        if self.sa_delivery_state not in SELF_FROM or self.state in ('done', 'cancel'):
            return _("This order is not waiting to be delivered.")
        if self.sa_delivery_partner_id:
            return _("A rider is on this order already.")
        if self.sa_supply_waiting:
            return _("The goods are not here yet.")
        return ''

    def _sa_self_lock(self):
        self.ensure_one()
        self.flush_recordset()
        self.env.cr.execute('SELECT id FROM stock_picking WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset(['sa_delivery_state', 'sa_delivery_partner_id', 'sa_self_delivery', 'state', 'sa_supply_waiting'])

    def _sa_self_start(self):
        """Packed, out with our staff, and the customer has the code. Not sent:
        nothing of it happened."""
        self.ensure_one()
        self._sa_self_lock()
        if self.sa_self_delivery and self.sa_delivery_state == 'out_for_delivery':
            return True                     # a second tap
        problem = self._sa_self_problem()
        if problem:
            raise UserError(problem)
        if self.state != 'assigned':
            self.action_assign()
        if self.state != 'assigned':
            raise UserError(_("The goods of this order are not in stock."))
        session = self._sa_session()
        if not session:
            raise UserError(_("No WhatsApp session is connected."))
        session._refresh_state()
        if session.status != 'connected':
            raise UserError(_("WhatsApp is not connected, so the code cannot be sent."))
        now = fields.Datetime.now()
        with self.env.cr.savepoint():
            self.write({'sa_self_delivery': True, 'sa_self_user_id': self.env.uid, 'sa_shop_ready_on': self.sa_shop_ready_on or now,
                        'sa_shop_user_id': self.sa_shop_user_id.id or self.env.uid, 'sa_packed_unpaid_on': False,
                        'sa_code_resends': 0, 'sa_code_sent_on': False})
            self.with_context(sa_quiet=True).sa_set_state('out_for_delivery')
            self.write({'sa_arrived_customer_on': now})
            ok, message, _code = self.sa_issue_delivery_otp()
            if not ok:
                raise UserError(message)
        self.message_post(body=_("Delivered by our own staff: %s. The code was sent to the customer.", self.env.user.name))
        self._sa_store_notify()
        return True

    def sa_issue_delivery_otp(self, send=True):
        if not self.sa_self_delivery:
            return super().sa_issue_delivery_otp(send=send)
        self.ensure_one()
        Otp = self.env['sa.delivery.otp'].sudo()
        code = Otp._issue(self, 'delivery')
        ok = not send or self._sa_tell_customer(_(
            "\U0001F4E6 Your order *#%(ref)s* is ready.\n\nGive this code to our staff *after* you have the parcel:\n\n*%(code)s*\n\n"
            "Do not share it before you receive your order.", ref=self.sa_ref_code or self.name, code=code), unique=True)
        if send:
            self.sudo().write({'sa_code_sent_on': fields.Datetime.now()})
        if send and ok:
            Otp.search([('picking_id', '=', self.id), ('kind', '=', 'delivery'), ('active', '=', True)], limit=1).sent_to = (
                self.partner_id.phone or '').strip()
        return bool(ok), _("A code has been sent to the customer.") if ok else _("The code could not be sent to the customer. Nothing was changed."), code

    def _sa_self_finish(self, code, cash):
        """'' when delivered, else what to tell. A wrong try counts, so it is
        told and not raised."""
        self.ensure_one()
        self._sa_self_lock()
        if not self.sa_self_delivery or self.sa_delivery_state != 'out_for_delivery':
            raise UserError(_("This order is not out with our staff."))
        due = self._sa_self_due()
        if due > 0.005 and not cash:
            return _("Not paid yet: tick that the cash was received.")
        ok, message = self.sa_verify_otp('delivery', (code or '').strip())
        if not ok:
            return message or _("Wrong code.")
        if due > 0.005:
            self.write({'sa_cash_taken': due, 'sa_cash_user_id': self.env.uid, 'sa_cash_on': fields.Datetime.now()})
            self.message_post(body=_("%(who)s received %(sum).2f %(cur)s in cash. No payment was booked by this.", who=self.env.user.name, sum=due,
                                     cur=(self.sa_currency_id or self.company_id.currency_id).name or ''))
        self.sa_set_state('delivered')
        self.message_post(body=_("Delivered by our staff - customer code verified by %s.", self.env.user.name))
        self._sa_store_notify()
        return ''

    def _sa_self_due(self):
        """What is really still to be taken: 0 when paid online, also before the
        invoice is made; the rest when a part is paid."""
        self.ensure_one()
        job = self.sudo()
        if job._sa_payment_status()['key'] in ('paid', 'cash'):
            return 0.0
        order = job.sale_id
        if order.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted'):
            return job.sa_amount_due() or 0.0
        got = sum(order.transaction_ids.filtered(lambda t: t.state == 'done').mapped('amount'))
        return max(0.0, (order.amount_total or 0.0) - got) if order else (job.sa_amount_due() or 0.0)

    def _sa_self_back(self):
        self.ensure_one()
        self._sa_self_lock()
        if not self.sa_self_delivery or self.sa_delivery_state != 'out_for_delivery':
            return True
        self._sa_void_codes()
        self.write({'sa_delivery_state': 'ready', 'sa_self_delivery': False, 'sa_self_user_id': False, 'sa_arrived_customer_on': False})
        self.message_post(body=_("Not delivered: back to packed by %s. The code no longer works.", self.env.user.name))
        self._sa_store_notify()
        return True

    @api.model
    def sa_store_act(self, job_id, action, reason='', company_id=None, **kwargs):
        if action not in ('self_start', 'self_code', 'self_resend', 'self_back'):
            return super().sa_store_act(job_id, action, reason=reason, company_id=company_id, **kwargs)
        job = self.sudo().browse(int(job_id))
        if not job.exists():
            raise UserError(_("That order is no longer there."))
        told = ''
        if action == 'self_start':
            job._sa_self_start()
        elif action == 'self_code':
            told = job._sa_self_finish(kwargs.get('code'), bool(kwargs.get('cash')))
        elif action == 'self_resend':
            if not job.sa_self_delivery:
                raise UserError(_("This order is not out with our staff."))
            res = job.sa_resend_customer_code()
            told = res['message']
        else:
            job._sa_self_back()
        data = self.sa_store_queue(job.sa_shop_id.id)
        data['self_told'] = told
        return data

    def _sa_carrier_name(self):
        return _("our staff") if self.sa_self_delivery else super()._sa_carrier_name()

    # ------------------------------------------------------------ the payment
    def _sa_payment_status(self):
        """{key, colour, words, note}: one answer for the list and the order."""
        self.ensure_one()
        job = self.sudo()
        order = job.sale_id
        currency = job.sa_currency_id or job.company_id.currency_id
        total, due = order.amount_total or 0.0, job.sa_amount_due() or 0.0
        txs = order.transaction_ids.sorted('id')

        def cash(tx):
            return 'custom_mode' in tx.provider_id._fields and tx.provider_id.custom_mode == 'cash_on_delivery'
        done = txs.filtered(lambda t: t.state == 'done')
        got = sum(done.mapped('amount'))
        money = lambda amount: '%.2f %s' % (amount, currency.name or '')  # noqa: E731
        posted = order.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
        # sa_is_paid is true for a part payment too: the amount decides. Without
        # an online payment it means paid elsewhere (the shop's wallet).
        if (posted and (due <= 0.005 or job.sa_is_paid)) or total <= 0.005 or got >= total - 0.005 or (not posted and not done and job.sa_is_paid):
            last = done[-1:]
            return {'key': 'paid', 'colour': 'good', 'words': _("Paid"), 'amount': money(total), 'how': last.payment_method_id.name or last.provider_id.name or '',
                    'at': iso(last.last_state_change)}
        if job.sa_cash_taken:
            return {'key': 'cash', 'colour': 'good', 'words': _("Cash received"), 'amount': money(job.sa_cash_taken),
                    'how': _("by %s, not booked yet", job.sa_cash_user_id.name or ''), 'at': iso(job.sa_cash_on)}
        part = got if got > 0.005 else (total - due if posted and 0.005 < due < total - 0.005 else 0.0)
        if part > 0.005:
            return {'key': 'part', 'colour': 'warn', 'words': _("Part paid"), 'amount': _("%(a).2f of %(b)s", a=part, b=money(total)), 'how': '', 'at': ''}
        waiting = txs.filtered(lambda t: t.state in ('pending', 'authorized'))
        if waiting.filtered(lambda t: not cash(t)):
            return {'key': 'checking', 'colour': 'warn', 'words': _("Payment being checked"), 'amount': money(due or total), 'how': '', 'at': ''}
        if txs.filtered(lambda t: cash(t) and t.state in ('draft', 'pending', 'authorized')):
            return {'key': 'cod', 'colour': '', 'words': _("Cash on delivery"), 'amount': money(due or total), 'how': '', 'at': ''}
        if txs[-1:].state == 'error':
            return {'key': 'failed', 'colour': 'bad', 'words': _("Payment failed"), 'amount': money(due or total), 'how': '', 'at': ''}
        request = order._sa_group_enquiry() if order else False
        sent = request.sa_pay_link_sent_on if request else False
        return {'key': 'pending', 'colour': 'warn', 'words': _("Payment pending"), 'amount': money(due or total),
                'how': _("link sent") if sent else _("link not sent"), 'at': iso(sent)}

    def _sa_board_extra(self):
        out = super()._sa_board_extra()
        job = self.sudo()
        out.update(payment=self._sa_payment_status(), self_delivery=job.sa_self_delivery, self_by=job.sa_self_user_id.name or '',
                   self_can=not job._sa_self_problem(), self_due=job._sa_self_due())
        return out

    @api.model
    def _sa_done_today(self, shop_id=None):
        rows = super()._sa_done_today(shop_id)
        for row in rows:
            job = self.sudo().browse(row['id'])
            row['payment'] = job._sa_payment_status()
            if job.sa_self_delivery:
                row['rider'] = _("Our staff: %s", job.sa_self_user_id.name or '')
        return rows

    @api.depends('sa_self_delivery')
    def _compute_sa_stage_text(self):
        super()._compute_sa_stage_text()
        for job in self:
            if job.sa_supply_waiting:
                continue
            if job.sa_self_delivery and job.sa_delivery_state == 'out_for_delivery':
                job.sa_stage_text = _("Out with our staff (%s) - next: type the customer's code", job.sa_self_user_id.name or '')
            elif job.sa_delivery_state == 'awaiting_shop':
                job.sa_stage_text = _("New order - next: press Accept")
            elif job.sa_delivery_state == 'preparing':
                job.sa_stage_text = _("Next: pack it, then press Packed or Deliver ourselves")
