"""A basket from several hubs: one order per hub, one checkout.

Priya's bananas come Quick from the Ruwi hub (the shop's own company); the
cable belongs to Sohar Hub, another company. Her one basket becomes two
orders - each in its own company, at its own delivery fee, sharing the coupon
by what each is worth - and one cash-on-delivery payment becomes one per hub.
Online payment is refused for such a basket for now. A basket from one hub,
or a shop with one company, is one order exactly as before.
"""

import json

from odoo.tests import tagged

from .common import Mart369OrderFixtures, Mart369OrderHttpCase

RUWI = (23.5880, 58.3829)
NEAR = (23.6000, 58.4000)
SOHAR = (24.3470, 56.7090)


class SplitFixtures(Mart369OrderFixtures):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        env['stock.warehouse'].sudo().search([]).write({'mart369_quick': False})
        env['mart369.hub.rule'].sudo().search([]).unlink()

        cls.main = env.company
        cls.sohar = env['res.company'].sudo().create({
            'name': 'Zz Sohar Hub', 'currency_id': cls.main.currency_id.id})
        Branch = env['stock.warehouse'].sudo()
        cls.ruwi_wh = Branch.search([('company_id', '=', cls.main.id)], limit=1)
        cls.sohar_wh = Branch.search([('company_id', '=', cls.sohar.id)], limit=1)
        cls.ruwi_wh.write({'mart369_quick': True, 'mart369_quick_km': 5.0,
                           'mart369_lat': RUWI[0], 'mart369_lng': RUWI[1]})
        cls.sohar_wh.write({'mart369_lat': SOHAR[0], 'mart369_lng': SOHAR[1],
                            'mart369_own_fees': True, 'mart369_express_fee': 10.0,
                            'mart369_free_above': 1000.0})

        cls.pinned = env['res.partner'].sudo().create({
            'name': 'Order Tester', 'parent_id': cls.partner.id, 'type': 'other',
            'street': '1 Near Street', 'city': 'Muscat', 'zip': '112',
            'phone': '+968 9123 4567',
            'partner_latitude': NEAR[0], 'partner_longitude': NEAR[1],
        })
        cls.cable = env['product.template'].sudo().create({
            'name': 'Zz Sohar Cable', 'list_price': 20.0, 'is_published': True,
            'sale_ok': True, 'type': 'consu', 'company_id': cls.sohar.id,
        })
        cls.coupon = env['mart369.coupon'].sudo().create({
            'code': 'ZZSPLIT10', 'title': 'Ten off', 'kind': 'flat', 'value': 10.0})

        # A delivery method that takes cash, usable by every company.
        fee_product = env['product.product'].sudo().create(
            {'name': 'Zz Split Delivery', 'type': 'service', 'list_price': 0.0})
        env['delivery.carrier'].sudo().create({
            'name': 'Zz Split Cash Carrier', 'delivery_type': 'fixed', 'fixed_price': 0.0,
            'allow_cash_on_delivery': True, 'product_id': fee_product.id,
            'company_id': False, 'sequence': 1,
        })

        # Cash on delivery, switched on in the shop's company and in the hub's.
        cod = env.ref('delivery.payment_provider_cod').sudo()
        cls._mart369_enable(cod)
        env['payment.provider'].sudo()._mart369_ensure_hub_providers(cls.sohar)
        for provider in env['payment.provider'].sudo().with_context(active_test=False).search([
                ('company_id', '=', cls.sohar.id), ('code', '=', 'custom'),
                ('custom_mode', 'in', ('cash_on_delivery', 'mart369_wallet'))]):
            cls._mart369_enable(provider)

    def _split_basket(self, **overrides):
        return self._basket(**dict({
            'ref': '369M-SPLIT1',
            'items': {str(self.quick_product.id): 4, str(self.cable.id): 1},
            'address_id': self.pinned.id,
        }, **overrides))

    def _place_split(self, **overrides):
        return self.env['sale.order']._mart369_place(self.partner, self._split_basket(**overrides))


@tagged('post_install', '-at_install')
class TestSplitOrders(SplitFixtures, Mart369OrderHttpCase):

    def _post(self, path, body):
        response = self.url_open(path, data=json.dumps(body),
                                 headers={'Content-Type': 'application/json'})
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, {}

    # ----------------------------------------------------------- the bill

    def test_the_bill_comes_in_two_parts_at_each_hubs_fee(self):
        items = self._split_basket()['items']
        bill = self.env['mart369.cart']._mart369_bill(items, address=self.pinned)
        self.assertEqual(len(bill['parts']), 2)
        by_seller = {p['seller']['id']: p for p in bill['parts']}
        # Bananas: 4 x 50 Quick from Ruwi, the shop's Quick fee of 30.
        self.assertEqual(by_seller[self.main.id]['fees'], 30.0)
        # The cable: Sohar Hub's own Express fee of 10.
        self.assertEqual(by_seller[self.sohar.id]['fees'], 10.0)
        self.assertEqual(bill['fees'], 40.0)
        self.assertEqual(bill['total'], 260.0)

    # ---------------------------------------------------------- placing

    def test_one_order_per_hub_in_its_own_company(self):
        orders = self._place_split()
        self.assertEqual(len(orders), 2)
        self.assertEqual(set(orders.mapped('mart369_group')), {'369M-SPLIT1'})
        self.assertEqual(sorted(orders.mapped('mart369_ref')), ['369M-SPLIT1-1', '369M-SPLIT1-2'])
        sohar = orders.filtered(lambda o: o.company_id == self.sohar)
        self.assertEqual(sohar.warehouse_id, self.sohar_wh)
        self.assertEqual(sohar.mart369_mode, 'all')
        self.assertAlmostEqual(sohar.amount_total, 30.0)
        ruwi = orders - sohar
        self.assertEqual(ruwi.company_id, self.main)
        self.assertEqual(ruwi.mart369_mode, 'quick')
        self.assertAlmostEqual(ruwi.amount_total, 230.0)

    def test_the_coupon_is_shared_by_what_each_part_is_worth(self):
        items = self._split_basket()['items']
        bill = self.env['mart369.cart']._mart369_bill(items, coupon='ZZSPLIT10', address=self.pinned)
        orders = self._place_split(coupon='ZZSPLIT10')
        currency = orders[:1].currency_id
        self.assertEqual(currency.compare_amounts(sum(orders.mapped('amount_total')), bill['total']), 0)
        offs = sorted(orders.mapped('mart369_coupon_off'))
        self.assertEqual(currency.compare_amounts(sum(offs), 10.0), 0)
        # 200 of the 220 in goods is Ruwi's: it takes the bigger share.
        ruwi = orders.filtered(lambda o: o.company_id == self.main)
        self.assertGreater(ruwi.mart369_coupon_off, 9.0)

    def test_placing_again_rewrites_the_drafts(self):
        first = self._place_split()
        again = self._place_split()
        self.assertEqual(len(again), 2)
        self.assertFalse(first.exists() - again)
        self.assertEqual(self.env['sale.order'].sudo().search_count(
            [('mart369_group', '=', '369M-SPLIT1')]), 2)

    def test_one_hub_basket_is_one_order_as_before(self):
        order = self._place(address_id=self.pinned.id, ref='369M-ONEHUB')
        self.assertEqual(len(order), 1)
        self.assertEqual(order.mart369_ref, '369M-ONEHUB')
        self.assertFalse(order.mart369_group)

    def test_one_company_shop_never_splits(self):
        # A one-company shop's products are all its own: a Quick and an
        # Express item still make one order, as they always did.
        self.patch(type(self.env['mart369.cart']), '_mart369_sellers_on', lambda self: False)
        order = self._place_split(items={str(self.quick_product.id): 4,
                                         str(self.express_product.id): 1})
        self.assertEqual(len(order), 1)
        self.assertEqual(order.mart369_ref, '369M-SPLIT1')
        self.assertFalse(order.mart369_group)

    # ---------------------------------------------------------- paying

    def test_cash_on_delivery_pays_each_part_to_its_hub(self):
        orders = self._place_split(coupon='ZZSPLIT10')
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, answer = self._post('/369mart/payment/pay',
                                    {'order_ref': '369M-SPLIT1', 'method': 'cod'})
        self.assertEqual(status, 201, answer)
        self.assertEqual(answer['parts'], 2)
        txs = self.env['payment.transaction'].sudo().search(
            [('mart369_order_ref', 'in', orders.mapped('mart369_ref'))])
        self.assertEqual(len(txs), 2)
        for order in orders:
            tx = txs.filtered(lambda t: t.mart369_order_ref == order.mart369_ref)
            self.assertEqual(tx.company_id, order.company_id)
            self.assertAlmostEqual(tx.amount, order.amount_total)
            self.assertEqual(order.mart369_state, 'placed')
        # One checkout, one use of the coupon.
        self.assertEqual(self.coupon.used_count, 1)

    def test_online_payment_is_refused_for_several_hubs(self):
        self._place_split()
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, answer = self._post('/369mart/payment/pay',
                                    {'order_ref': '369M-SPLIT1', 'method': 'upi'})
        self.assertEqual(status, 400)
        self.assertIn('several', answer['error'])
        self.assertFalse(self.env['payment.transaction'].sudo().search_count(
            [('mart369_order_ref', 'like', '369M-SPLIT1')]))

    def test_the_options_offer_only_cash_and_wallet(self):
        self._place_split()
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        response = self.url_open('/369mart/payment/options?amount=260&order_ref=369M-SPLIT1')
        answer = response.json()
        self.assertTrue(answer['onlineOff'])
        self.assertEqual(answer['parts'], 2)
        self.assertNotIn('upi', answer['methods'])
        self.assertIn('cod', answer['methods'])

    def test_the_checkout_number_finds_every_part_once_paid(self):
        self._place_split()
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        self._post('/369mart/payment/pay', {'order_ref': '369M-SPLIT1', 'method': 'cod'})
        answer = self.url_open('/369mart/orders/369M-SPLIT1').json()
        self.assertTrue(answer['ok'])
        self.assertEqual(answer['order']['id'], '369M-SPLIT1')
        self.assertEqual(len(answer['parts']), 2)
        self.assertEqual({p['part'] for p in answer['parts']}, {1, 2})
        self.assertEqual({p['parts'] for p in answer['parts']}, {2})

    def test_someone_else_cannot_pay_or_see_the_checkout(self):
        orders = self._place_split()
        self.authenticate('someone.else@369mart.test', 'someone-else-369')
        self._post('/369mart/payment/pay', {'order_ref': '369M-SPLIT1', 'method': 'cod'})
        # Nothing was paid against Priya's parts, and both are still drafts.
        self.assertFalse(self.env['payment.transaction'].sudo().search_count(
            [('mart369_order_ref', 'in', orders.mapped('mart369_ref'))]))
        self.assertEqual(set(orders.mapped('mart369_state')), {'draft'})
        self.assertEqual(self.url_open('/369mart/orders/369M-SPLIT1').status_code, 404)
