"""Offer a replacement for an item that ran out; the customer decides
(models/order_substitute.py)."""

import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import Mart369OrderCase, Mart369OrderHttpCase


@tagged('post_install', '-at_install')
class TestReplacementOffer(Mart369OrderCase):

    def setUp(self):
        super().setUp()
        self.apples = self._mart369_product('Test Apples', 30.0)
        self.dearer = self._mart369_product('Test Pears', 45.0).product_variant_id
        self.cheaper = self._mart369_product('Test Plums', 20.0).product_variant_id
        self.Order = self.env['sale.order']

    def _order(self, cash=False):
        order = self._place(items={str(self.quick_product.id): 4, str(self.apples.id): 2})
        if cash:
            self._cash(order)
        else:
            self._pay(order)
        return order

    def _apples(self, order):
        return order.order_line.filtered(lambda l: l.product_id.product_tmpl_id == self.apples)

    def _wallet(self):
        return self.env['loyalty.card'].sudo()._mart369_wallet(self.partner).points

    def _offer(self, order, product):
        self.Order.mart369_admin_offer_substitute(order.mart369_ref, self._apples(order).id, product.id)
        return order.mart369_substitute_ids[:1]

    def test_only_something_the_shop_can_send(self):
        order = self._order()
        line = self._apples(order)
        with self.assertRaises(UserError):
            self.Order.mart369_admin_offer_substitute(order.mart369_ref, line.id, line.product_id.id)
        empty = self.env['product.template'].sudo().create({
            'name': 'Test Empty Shelf', 'list_price': 30.0, 'is_published': True,
            'sale_ok': True, 'type': 'consu', 'is_storable': True}).product_variant_id
        with self.assertRaises(UserError):
            self.Order.mart369_admin_offer_substitute(order.mart369_ref, line.id, empty.id)
        names = [p['name'] for p in self.Order.mart369_admin_substitutes(order.mart369_ref, line.id, 'Test')]
        self.assertIn(self.dearer.display_name, names)
        self.assertNotIn(line.product_id.display_name, names)
        self.assertNotIn(empty.display_name, names)

    def test_accepting_a_dearer_one_costs_the_customer_nothing_extra(self):
        order = self._order()
        before_total = order.amount_total
        offer = self._offer(order, self.dearer)
        self.assertEqual(offer.unit_price, 30.0, 'the customer pays what they ordered')
        with self.assertRaises(UserError):
            order.mart369_action_advance()  # not packed while they choose
        before = self._wallet()

        order._mart369_answer_substitute(offer, True)

        self.assertEqual(offer.state, 'accepted')
        self.assertAlmostEqual(order.amount_total, before_total, places=2, msg='same bill')
        self.assertAlmostEqual(self._wallet(), before, places=2, msg='nothing to refund')
        self.assertEqual(offer.new_line_id.product_id, self.dearer)
        self.assertEqual(self._apples(order).product_uom_qty, 0)
        self.assertIn('Replaced by', self._apples(order).mart369_removed_reason)
        order.mart369_action_advance()
        self.assertEqual(order.mart369_state, 'packed')

    def test_accepting_a_cheaper_one_refunds_the_difference(self):
        order = self._order()
        before = self._wallet()
        offer = self._offer(order, self.cheaper)
        order._mart369_answer_substitute(offer, True)
        self.assertGreater(offer.refund, 0)
        self.assertAlmostEqual(self._wallet(), before + offer.refund, places=2)

    def test_cash_on_delivery_owes_less_for_a_cheaper_one(self):
        order = self._order(cash=True)
        offer = self._offer(order, self.cheaper)
        order._mart369_answer_substitute(offer, True)
        self.assertEqual(offer.refund, 0.0)
        tx = self.env['payment.transaction'].sudo().search(
            [('mart369_order_ref', '=', order.mart369_ref), ('state', '=', 'pending')])
        self.assertAlmostEqual(tx.amount, order.amount_total, places=2)

    def test_declining_refunds_the_item(self):
        order = self._order()
        value = order.currency_id.round(self._apples(order).price_total)
        before = self._wallet()
        offer = self._offer(order, self.dearer)
        order._mart369_answer_substitute(offer, False)
        self.assertEqual(offer.state, 'declined')
        self.assertAlmostEqual(self._wallet(), before + value, places=2)
        with self.assertRaises(UserError):
            order._mart369_answer_substitute(offer, True)

    def test_no_answer_in_time_is_a_refund(self):
        self.env['mart369.config']._get().write({'substitute_quick_minutes': 5})
        order = self._order()
        offer = self._offer(order, self.dearer)
        waited = (offer.deadline - offer.create_date).total_seconds() / 60
        self.assertAlmostEqual(waited, 5, delta=1, msg='the wait follows Settings > Orders')
        offer.deadline = fields.Datetime.now() - timedelta(minutes=1)
        before = self._wallet()
        self.Order._cron_mart369_expire_substitutes()
        self.assertEqual(offer.state, 'expired')
        self.assertGreater(self._wallet(), before)
        if 'mart369.notifications' in self.env:
            notes = self.env['mart369.notifications']._mart369_order_notes(order.partner_id)
            self.assertTrue([n for n in notes if '-sub-' in n['id']], 'the customer is told')

    def test_staff_offer_up_to_three_and_the_customer_picks_one(self):
        order = self._order()
        line = self._apples(order)
        extra = self._mart369_product('Test Figs', 35.0).product_variant_id
        other = self._mart369_product('Test Kiwis', 25.0).product_variant_id
        with self.assertRaises(UserError):
            self.Order.mart369_admin_offer_substitute(
                order.mart369_ref, line.id, [self.dearer.id, self.cheaper.id, extra.id, other.id])
        detail = self.Order.mart369_admin_offer_substitute(
            order.mart369_ref, line.id, [self.dearer.id, self.cheaper.id, extra.id])
        offer = order.mart369_substitute_ids[:1]
        self.assertEqual(len(detail['substitutes'][0]['options']), 3)
        with self.assertRaises(UserError):
            order._mart369_answer_substitute(offer, True)  # which one?
        with self.assertRaises(UserError):
            order._mart369_answer_substitute(offer, True, product=other)  # not offered
        before = self._wallet()
        order._mart369_answer_substitute(offer, True, product=self.cheaper)
        self.assertEqual(offer.state, 'accepted')
        self.assertEqual(offer.new_line_id.product_id, self.cheaper, 'the one they picked')
        self.assertAlmostEqual(self._wallet(), before + offer.refund, places=2)
        self.assertGreater(offer.refund, 0, 'cheaper: the difference comes back')

    def test_the_settings_route_saves_the_waits(self):
        Config = self.env['mart369.config']
        Config.mart369_admin_save('orders', {'substituteQuick': 15, 'substituteExpress': 240})
        self.assertEqual(Config.mart369_admin_settings()['orders'],
                         {'substituteQuick': 15, 'substituteExpress': 240})
        with self.assertRaises(UserError):
            Config.mart369_admin_save('orders', {'substituteQuick': 0})


@tagged('post_install', '-at_install')
class TestReplacementAnswerRoute(Mart369OrderHttpCase):

    def test_only_the_customer_answers_for_their_own_order(self):
        apples = self._mart369_product('Test Apples', 30.0)
        pears = self._mart369_product('Test Pears', 45.0).product_variant_id
        order = self._place(items={str(self.quick_product.id): 4, str(apples.id): 2})
        self._pay(order)
        line = order.order_line.filtered(lambda l: l.product_id.product_tmpl_id == apples)
        self.env['sale.order'].mart369_admin_offer_substitute(order.mart369_ref, line.id, pears.id)
        offer = order.mart369_substitute_ids[:1]
        url = '/369mart/orders/%s/substitute/%d' % (order.mart369_ref, offer.id)
        body = json.dumps({'accept': True})
        headers = {'Content-Type': 'application/json'}

        self.other.sudo().password = 'other_pw_369'
        self.authenticate(self.other.login, 'other_pw_369')
        self.assertEqual(self.url_open(url, data=body, headers=headers).status_code, 404)
        self.assertEqual(offer.state, 'offered', 'another customer cannot answer')

        self.customer.sudo().password = 'customer_pw_369'
        self.authenticate(self.customer.login, 'customer_pw_369')
        res = self.url_open(url, data=body, headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['order']['substitutes'][0]['state'], 'accepted')
