# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

# Shop pin; 0.027 of a degree of latitude is about 3 km, 0.081 about 9 km.
LAT, LNG = 23.6000, 58.5000


@tagged('post_install', '-at_install')
class TestQuickExpress(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Shop = cls.env['sa.delivery.shop']
        cls.Area = cls.env['sa.qe.service.area']
        # other shops and areas in the database must not take part
        cls.Shop.search([]).write({'qe_quick': False})
        # archived areas still hold their pincode; the test makes its own
        cls.Area.with_context(active_test=False).search([]).unlink()

        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.shop = cls.Shop.create({
            'name': 'QE Shop', 'warehouse_id': cls.warehouse.id,
            'latitude': LAT, 'longitude': LNG,
            'qe_quick': True, 'qe_quick_km': 5.0,
        })
        cls.stocked = cls.env['product.product'].create({
            'name': 'QE stocked', 'type': 'consu', 'is_storable': True,
            'tracking': 'none',
            'list_price': 100.0, 'taxes_id': [(6, 0, [])]})
        cls.empty = cls.env['product.product'].create({
            'name': 'QE empty', 'type': 'consu', 'is_storable': True,
            'tracking': 'none',
            'list_price': 100.0, 'taxes_id': [(6, 0, [])]})
        cls.env['stock.quant']._update_available_quantity(
            cls.stocked, cls.warehouse.lot_stock_id, 10.0)

        Partner = cls.env['res.partner']
        cls.near = Partner.create({'name': 'QE near', 'zip': '680001',
                                   'partner_latitude': LAT + 0.027,
                                   'partner_longitude': LNG})
        cls.far = Partner.create({'name': 'QE far', 'zip': '680001',
                                  'partner_latitude': LAT + 0.081,
                                  'partner_longitude': LNG})
        cls.no_pin = Partner.create({'name': 'QE no pin', 'zip': '670123'})

    def _order(self, partner, product=None, qty=1.0):
        product = product or self.stocked
        return self.env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [(0, 0, {'product_id': product.id,
                                   'product_uom_qty': qty})],
        })

    # ---- the decision ----
    def test_in_reach_in_stock_is_quick(self):
        order = self._order(self.near)
        order.action_qe_decide()
        self.assertEqual(order.qe_mode, 'quick')
        self.assertEqual(order.qe_shop_id, self.shop)
        self.assertFalse(order.qe_reason)
        self.assertEqual(order.order_line.qe_mode, 'quick')

    def test_in_reach_no_stock_is_express(self):
        order = self._order(self.near, self.empty)
        order.action_qe_decide()
        self.assertEqual((order.qe_mode, order.qe_reason), ('express', 'stock'))

    def test_out_of_reach_is_express(self):
        order = self._order(self.far)
        order.action_qe_decide()
        self.assertEqual((order.qe_mode, order.qe_reason), ('express', 'far'))

    def test_product_text_is_express(self):
        self.stocked.product_tmpl_id.qe_delivery_text = 'Delivered in 5-7 days'
        order = self._order(self.near)
        order.action_qe_decide()
        self.assertEqual((order.qe_mode, order.qe_reason), ('express', 'product'))

    def test_mixed_order_is_express(self):
        order = self._order(self.near)
        order.write({'order_line': [(0, 0, {'product_id': self.empty.id,
                                            'product_uom_qty': 1.0})]})
        order.action_qe_decide()
        self.assertEqual(order.qe_mode, 'express')
        self.assertEqual(set(order.order_line.mapped('qe_mode')),
                         {'quick', 'express'})

    def test_no_pin_uses_the_area(self):
        self.Area.create({'pincode': '67', 'quick': False})
        self.Area.create({'pincode': '6701', 'quick': True})
        order = self._order(self.no_pin)
        order.action_qe_decide()
        self.assertEqual(order.qe_mode, 'quick', "the longest prefix wins")
        self.Area.search([('pincode', '=', '6701')]).unlink()
        order.action_qe_decide()
        self.assertEqual((order.qe_mode, order.qe_reason), ('express', 'area'))

    def test_no_area_is_quick(self):
        order = self._order(self.no_pin)
        order.action_qe_decide()
        self.assertEqual(order.qe_mode, 'quick')

    def test_no_ready_shop_uses_the_area(self):
        self.shop.qe_quick_km = 0.0
        self.Area.create({'pincode': '68', 'quick': False})
        order = self._order(self.near)
        order.action_qe_decide()
        self.assertEqual((order.qe_mode, order.qe_reason), ('express', 'area'))

    # ---- fee, minimum, slots ----
    def test_fee_and_minimum(self):
        rule = self.env['sa.qe.delivery.rule']._qe_for('quick')
        rule.write({'min_order': 99.0, 'free_above': 499.0, 'fee': 30.0})
        order = self._order(self.near)                      # goods 100
        order.action_qe_apply_fee()
        self.assertEqual(order.qe_fee, 30.0)
        self.assertFalse(order.qe_blocked)
        fee_lines = order.order_line.filtered(lambda l: l.qe_kind == 'fee')
        self.assertEqual(fee_lines.mapped('price_unit'), [30.0])
        order.action_qe_apply_fee()
        self.assertEqual(
            len(order.order_line.filtered(lambda l: l.qe_kind == 'fee')), 1,
            "pressing twice does not charge twice")

        big = self._order(self.near, qty=5.0)               # goods 500
        big.action_qe_apply_fee()
        self.assertEqual(big.qe_fee, 0.0)
        self.assertFalse(big.order_line.filtered(lambda l: l.qe_kind == 'fee'))

        rule.min_order = 150.0
        order.action_qe_decide()
        self.assertTrue(order.qe_blocked)

    def test_slot_capacity(self):
        slot = self.env['sa.qe.delivery.slot'].create({
            'name': 'QE tomorrow', 'mode': 'quick', 'kind': 'window',
            'from_hour': 8.0, 'to_hour': 10.0, 'day_offset': 1, 'capacity': 1})
        first = self._order(self.near)
        first.action_qe_decide()
        first.qe_slot_id = slot
        self.assertTrue(first.qe_slot_day)
        self.assertTrue(first._qe_due())
        second = self._order(self.near)
        second.action_qe_decide()
        with self.assertRaises(ValidationError):
            second.qe_slot_id = slot

    # ---- the hand-off ----
    def test_promise_follows_the_order(self):
        settings = self.env['sa.delivery.settings'].get_settings()
        settings.write({'qe_enabled': True, 'quick_enabled': True,
                        'flow_end': 'delivery'})
        # in stock at the warehouse, so the old rule would say quick...
        order = self._order(self.far)
        order.action_confirm()
        self.assertEqual(order.qe_mode, 'express')
        picking = order.picking_ids[:1]
        self.assertTrue(picking)
        kind, promised = settings._promise_for(picking)
        self.assertEqual(kind, 'express', "...but the customer is out of reach")
        self.assertEqual(promised, order.qe_due_at)

        near = self._order(self.near)
        near.action_confirm()
        kind, _promised = settings._promise_for(near.picking_ids[:1])
        self.assertEqual(kind, 'quick')
        self.assertEqual(near.picking_ids[:1].sa_shop_id, self.shop)

    def test_confirm_keeps_a_decided_order(self):
        settings = self.env['sa.delivery.settings'].get_settings()
        settings.write({'qe_enabled': True})
        # in reach and in stock, so a fresh decision would say quick...
        order = self._order(self.near)
        order.write({'qe_decided': True, 'qe_mode': 'express',
                     'qe_shop_id': False})
        order.action_confirm()
        self.assertEqual(order.qe_mode, 'express',
                         "...but the order was decided when it was placed")

        fresh = self._order(self.near)
        fresh.action_confirm()
        self.assertTrue(fresh.qe_decided)
        self.assertEqual(fresh.qe_mode, 'quick')
