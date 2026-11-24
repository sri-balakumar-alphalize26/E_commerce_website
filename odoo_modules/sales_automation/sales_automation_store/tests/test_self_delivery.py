# -*- coding: utf-8 -*-
"""Delivered by our own staff; how the payment stands; the vendor's time (24 Nov 2026)."""
from datetime import timedelta
from unittest.mock import patch

import pytz

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_supply_choice import ListedCase
from . import test_supply_choice


@tagged('post_install', '-at_install')
class TestSelfDelivery(ListedCase):
    _order = test_supply_choice.TestSupplyChoice._order
    _price = test_supply_choice.TestSupplyChoice._price

    def setUp(self):
        super().setUp()
        self.kumar, self.alpha, self.third, self.fourth = self.env['res.partner'].create(
            [{'name': 'Zz S%s' % n, 'phone': '+97150000410%s' % n} for n in range(4)])
        self.customer = self.env['res.partner'].create({'name': 'Zz buyer', 'phone': '+971500006001'})
        Picking = self.env.registry['stock.picking']
        self.sent, self.refused = [], False
        for p in (patch.object(Picking, '_sa_store_notify', lambda rec, *a, **k: True),
                  patch.object(Picking, '_sa_session', lambda rec: self.session),
                  patch.object(self.env.registry['whatsapp.session'], 'send_message', lambda rec, phone, body: False if self.refused else (self.sent.append((phone, body)) or True))):
            p.start()
            self.addCleanup(p.stop)
        self.req, self.order, self.job = self._order()
        self.env['stock.quant']._update_available_quantity(self.product.product_variant_id, self.job.location_id, 1)
        self.job.write({'sa_delivery_state': 'preparing', 'sa_cod_amount': 24.0})
        self.job.action_assign()

    def _act(self, action, **kw):
        return self.env['stock.picking'].sa_store_act(self.job.id, action, **kw)

    def _code(self):
        return ''.join(ch for ch in self.sent[-1][1].split('parcel:')[1].split('Do not')[0] if ch.isdigit())

    def test_the_code_goes_to_the_customer_only(self):
        self._act('self_start')
        self.assertEqual(([p for p, _b in self.sent], self.job.sa_delivery_state), ([self.customer.phone], 'out_for_delivery'))
        self.assertIn('our staff', self.sent[0][1])
        self._act('self_start')
        self.assertEqual(len(self.sent), 1, 'a second tap sends nothing')

    def test_delivered_with_the_code(self):
        self._act('self_start')
        data = self._act('self_code', code=self._code(), cash=True)
        self.assertFalse(data['self_told'])
        self.assertEqual((self.job.sa_delivery_state, self.job.state), ('delivered', 'done'))
        self.assertEqual((self.job.sa_cash_taken, self.job.sa_cash_user_id), (24.0, self.env.user))
        self.assertFalse(self.order.transaction_ids, 'no payment is booked')
        told = [b for _p, b in self.sent[1:]] + self.said
        self.assertTrue(any('delivered' in b.lower() and 'our staff' in b for b in told), ascii(told))
        self.assertFalse(any('our rider' in b for b in told), ascii(told))
        self.assertEqual(self.job._sa_payment_status()['key'], 'cash')

    def test_unpaid_needs_the_tick(self):
        self._act('self_start')
        data = self._act('self_code', code=self._code())
        self.assertIn('cash', data['self_told'])
        self.assertEqual(self.job.sa_delivery_state, 'out_for_delivery')

    def test_paid_online_before_the_invoice_needs_no_cash(self):
        self._tx('done')
        self.env.invalidate_all()
        self.assertEqual(self.job._sa_board_extra()['self_due'], 0.0)
        self._act('self_start')
        self.assertFalse(self._act('self_code', code=self._code())['self_told'])
        self.assertEqual((self.job.sa_delivery_state, self.job.sa_cash_taken), ('delivered', 0.0))

    def test_a_part_paid_takes_the_rest(self):
        self._tx('done', amount=10.0)
        self.env.invalidate_all()
        self._act('self_start')
        self.assertIn('cash', self._act('self_code', code=self._code())['self_told'])
        self.assertFalse(self._act('self_code', code=self._code(), cash=True)['self_told'])
        self.assertEqual(self.job.sa_cash_taken, 14.0)

    def test_wrong_codes_count(self):
        self._act('self_start')
        code = self._code()
        wrong = '%06d' % ((int(code) + 1) % 1000000)
        for _n in range(5):
            self.assertTrue(self._act('self_code', code=wrong, cash=True)['self_told'])
        self.assertIn('Too many', self._act('self_code', code=code, cash=True)['self_told'])
        self.assertEqual(self.job.sa_delivery_state, 'out_for_delivery')

    def test_an_old_code(self):
        self._act('self_start')
        self.env['sa.delivery.otp'].search([('picking_id', '=', self.job.id)]).expires_on = fields.Datetime.now() - timedelta(minutes=1)
        self.assertIn('expired', self._act('self_code', code=self._code(), cash=True)['self_told'])

    def test_again_and_its_limit(self):
        self._act('self_start')
        self._act('self_resend')
        self.assertEqual(len(self.sent), 1, 'too soon')
        self.job.sa_code_sent_on = fields.Datetime.now() - timedelta(minutes=5)
        first = self._code()
        self._act('self_resend')
        self.assertEqual(len(self.sent), 2)
        self.assertTrue(self._act('self_code', code=first, cash=True)['self_told'], 'the old one no longer works')

    def test_back_to_packed(self):
        self._act('self_start')
        code = self._code()
        self._act('self_back')
        self.assertEqual((self.job.sa_delivery_state, self.job.sa_self_delivery), ('ready', False))
        with self.assertRaises(UserError):
            self._act('self_code', code=code, cash=True)

    def test_not_sent_changes_nothing(self):
        self.refused = True
        with self.assertRaises(UserError):
            self._act('self_start')
        self.assertEqual((self.job.sa_delivery_state, self.job.sa_self_delivery), ('preparing', False))

    def test_where_it_is_not_offered(self):
        self.assertTrue(self.job._sa_board_extra()['self_can'])
        self.job.sa_supply_waiting = True
        self.assertFalse(self.job._sa_board_extra()['self_can'])
        with self.assertRaises(UserError):
            self._act('self_start')
        self.job.sa_supply_waiting = False
        self.job.sa_delivery_partner_id = self.env['sa.delivery.partner'].create({'name': 'Zz rider', 'phone': '+971500006999'})
        self.assertFalse(self.job._sa_board_extra()['self_can'])
        with self.assertRaises(UserError):
            self._act('self_start')

    def test_the_lines(self):
        self.assertIn('pack it', self.job.sa_stage_text)
        self._act('self_start')
        self.assertIn('our staff', self.job.sa_stage_text)

    # -------------------------------------------------------- the payment
    def _tx(self, state, amount=24.0):
        provider = self.env['payment.provider'].search([('code', '!=', 'custom')], limit=1)
        method = self.env['payment.method'].search([], limit=1)
        return self.env['payment.transaction'].create({
            'provider_id': provider.id, 'payment_method_id': method.id, 'reference': 'zz-%s-%s' % (state, self.order.id), 'amount': amount,
            'currency_id': self.order.currency_id.id, 'partner_id': self.customer.id, 'state': state, 'sale_order_ids': [(4, self.order.id)]})

    def _key(self):
        self.env.invalidate_all()
        return self.job._sa_payment_status()['key']

    def test_pending(self):
        status = self.job._sa_payment_status()
        self.assertEqual((status['key'], status['colour'], status['how']), ('pending', 'warn', 'link not sent'))
        self.req.sa_pay_link_sent_on = fields.Datetime.now()
        self.assertEqual(self.job._sa_payment_status()['how'], 'link sent')

    def test_checked_failed_part_and_paid(self):
        tx = self._tx('pending')
        self.assertEqual(self._key(), 'checking')
        tx.state = 'error'
        self.assertEqual(self._key(), 'failed')
        tx.write({'state': 'done', 'amount': 10.0})
        self.assertEqual(self._key(), 'part')
        tx.amount = 24.0
        self.assertEqual(self._key(), 'paid')

    # -------------------------------------------------------- the vendor's time
    def _supply(self, text):
        self.job.write({'sa_delivery_state': 'awaiting_shop'})
        return self._act('supply_set', partner_id=self.kumar.id, cost=20.0, promised_date=text, send=True)

    def test_now_is_the_companys(self):
        now = self.job._sa_supply_now()
        local = pytz.UTC.localize(fields.Datetime.now()).astimezone(self.job._sa_supply_zone())
        self.assertEqual(now['date'], local.strftime('%Y-%m-%d'))

    def test_the_time_is_told(self):
        later = pytz.UTC.localize(fields.Datetime.now() + timedelta(days=1)).astimezone(self.job._sa_supply_zone())
        self._supply(later.strftime('%Y-%m-%d 17:00'))
        self.assertIn('5:00 PM', self.sent[0][1])
        self.assertIn('5:00 PM', self.job._sa_board_extra()['supply_due'])
        timed = self.job.sa_promised_on
        self.job.sa_supply_waiting = False
        self._supply(later.strftime('%Y-%m-%d'))
        self.assertEqual(self.job.sa_promised_on, timed, "the customer's promise is the same")
        self.assertFalse(self.job.sa_supply_due_on)

    def test_not_a_time_that_is_over(self):
        before = pytz.UTC.localize(fields.Datetime.now() - timedelta(hours=1)).astimezone(self.job._sa_supply_zone())
        for text in (before.strftime('%Y-%m-%d %H:%M'), '2026-13-45 10:00', 'tomorrow noon'):
            with self.assertRaises(UserError):
                self._supply(text)
