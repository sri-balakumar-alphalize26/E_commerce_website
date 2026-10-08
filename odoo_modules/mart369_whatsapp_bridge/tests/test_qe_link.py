"""Delivery by the senior's rules - where his Quick / Express module runs.

Skipped on a database without `sales_automation_quick_express`; run on the
private copy that matches DUBAI_TEST.
"""

from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.qe_link import qe_on
from .common import Mart369BridgeCase

# The shop's pin; 0.027 of a degree of latitude is about 3 km, 0.081 about 9 km.
LAT, LNG = 23.6000, 58.5000


@tagged('post_install', '-at_install')
class TestQeLink(Mart369BridgeCase):

    def setUp(self):
        super().setUp()
        if not qe_on(self.env):
            self.skipTest("the senior's Quick / Express module is not installed here")
        env = self.env
        # Nothing else in the database takes part.
        env['sa.delivery.shop'].sudo().search([]).write({'qe_quick': False})
        env['sa.qe.service.area'].sudo().search([]).write({'active': False})
        env['sa.qe.delivery.slot'].sudo().search([]).write({'active': False})
        Rule = env['sa.qe.delivery.rule'].sudo().with_context(active_test=False)
        for mode, values in (('quick', {'fee': 30, 'free_above': 499, 'min_order': 99}),
                             ('express', {'fee': 49, 'free_above': 999, 'min_order': 0})):
            rule = Rule.search([('mode', '=', mode)], limit=1)
            values = dict(values, label=mode.title(), eta='%s promise' % mode, active=True)
            if rule:
                rule.write(values)
            else:
                Rule.create(dict(values, mode=mode))
        self.shop.sudo().write({'latitude': LAT, 'longitude': LNG,
                                'qe_quick': True, 'qe_quick_km': 5.0})
        variant = self.quick_product.product_variant_id
        variant.sudo().is_storable = True
        env['stock.quant'].sudo()._update_available_quantity(
            variant, self.shop.warehouse_id.lot_stock_id, 50.0)

    def _pin(self, lat_offset):
        self.address.sudo().write({'partner_latitude': LAT + lat_offset,
                                   'partner_longitude': LNG})

    def _bill(self, items, slot_fee=0.0):
        return self.env['mart369.cart'].sudo()._mart369_bill(
            items, slot_fee=slot_fee, address=self.address)

    def _slot(self, **values):
        return self.env['sa.qe.delivery.slot'].sudo().create(dict({
            'name': 'QE Tomorrow 8 - 10 AM', 'mode': 'quick', 'kind': 'window',
            'from_hour': 8.0, 'to_hour': 10.0, 'day_offset': 1}, **values))

    # ------------------------------------------------------- rules and areas

    def test_the_rules_are_his(self):
        rules = self.env['mart369.delivery.rule']._mart369_rules()
        self.assertEqual(set(rules), {'quick', 'all'})
        self.assertEqual(rules['quick']._mart369_serialize()['fee'], 30.0)
        self.assertEqual(rules['all']._mart369_serialize()['freeAbove'], 999.0)

    def test_a_pincode_is_served_by_his_areas(self):
        Area = self.env['sa.qe.service.area'].sudo()
        Area.create({'pincode': '93', 'quick': True, 'eta': '13 mins'})
        Area.create({'pincode': '9320', 'quick': False, 'express': True, 'eta': '2 days'})
        Check = self.env['mart369.service.area']
        self.assertEqual(Check._mart369_check('932016'),
                         {'ok': True, 'quick': False, 'eta': '2 days'}, 'the longest prefix wins')
        self.assertTrue(Check._mart369_check('939001')['quick'])
        Area.create({'pincode': '94', 'quick': False, 'express': False})
        self.assertFalse(Check._mart369_check('940001')['ok'])

    # ------------------------------------------------- Quick or Express, fees

    def test_in_reach_with_stock_is_quick_from_his_shop(self):
        self._pin(0.027)
        bill = self._bill({str(self.quick_product.id): 2})
        self.assertEqual(set(bill['modes'].values()), {'quick'})
        self.assertEqual(bill['branch'], self.shop.name)

    def test_out_of_reach_is_express(self):
        self._pin(0.081)
        bill = self._bill({str(self.quick_product.id): 2})
        self.assertEqual(set(bill['modes'].values()), {'all'})
        self.assertEqual(bill['movedWhy'], 'far')

    def test_a_product_with_its_own_promise_is_express(self):
        self._pin(0.027)
        bill = self._bill({str(self.express_product.id): 1})
        self.assertEqual(set(bill['modes'].values()), {'all'})
        self.quick_product.sudo().qe_delivery_text = 'Delivered in 5-7 days'
        bill = self._bill({str(self.quick_product.id): 1})
        self.assertEqual(set(bill['modes'].values()), {'all'}, 'his delivery text counts too')

    def test_a_mixed_basket_pays_one_fee_by_his_rule(self):
        self._pin(0.027)
        # The Express item costs 1200; keep the basket under free-above.
        self.env['sa.qe.delivery.rule'].sudo()._qe_for('express').free_above = 5000
        bill = self._bill({str(self.quick_product.id): 2, str(self.express_product.id): 1})
        self.assertEqual(set(bill['modes'].values()), {'quick', 'all'})
        self.assertEqual(bill['fees'], 49.0, 'one Express fee, not 30 + 49')

    def test_quick_fee_free_above_and_minimum(self):
        self._pin(0.027)
        bill = self._bill({str(self.quick_product.id): 4})          # 200
        self.assertEqual(bill['fees'], 30.0)
        self.assertFalse(bill['blocked'])
        bill = self._bill({str(self.quick_product.id): 10})         # 500
        self.assertEqual(bill['fees'], 0.0, 'free above 499')
        bill = self._bill({str(self.quick_product.id): 1})          # 50
        self.assertTrue(bill['blocked'], 'under the Quick minimum')
        bill = self._bill({str(self.quick_product.id): 4}, slot_fee=20.0)
        self.assertEqual(bill['fees'], 50.0, 'his slot fee on top')

    # ------------------------------------------------------------------ slots

    def test_the_checkout_lists_his_open_slots(self):
        open_slot = self._slot()
        closed = self._slot(name='QE Today closed', day_offset=0, from_hour=18.0,
                            to_hour=20.0, order_before=0.01)
        chips = self.env['mart369.delivery.slot']._mart369_slots()
        keys = [chip['key'] for chip in chips['quick']]
        self.assertIn('qe:%d' % open_slot.id, keys)
        self.assertNotIn('qe:%d' % closed.id, keys)

    def test_a_placed_order_carries_his_one_fee_line_and_slot(self):
        slot = self._slot(fee=10.0)
        order = self._place(ref='369M-TESTQE1', slot_key='qe:%d' % slot.id)
        fee_lines = order.order_line.filtered(lambda l: l.qe_kind == 'fee')
        self.assertEqual(len(fee_lines), 1)
        self.assertEqual(fee_lines.mart369_kind, 'fee', 'the website reads it as delivery')
        self.assertEqual(fee_lines.price_unit, 40.0, '30 delivery + 10 slot')
        self.assertFalse(order.order_line.filtered(
            lambda l: l.mart369_kind == 'fee' and not l.qe_kind), 'no second fee line')
        self.assertEqual(order.qe_slot_id, slot)
        self.assertEqual(order.mart369_slot_key, 'qe:%d' % slot.id)
        self.assertEqual(order.mart369_due_at, slot._qe_due(slot._qe_day()))
        self.assertEqual(order._mart369_bill_snapshot()['fees'], 40.0)

    def test_a_full_slot_is_refused(self):
        slot = self._slot(capacity=1)
        self._place(ref='369M-TESTQE2', slot_key='qe:%d' % slot.id)
        with self.assertRaises(UserError):
            self._place(ref='369M-TESTQE3', slot_key='qe:%d' % slot.id)

    # ---------------------------------------------------------- the console

    def test_the_console_lists_his_records(self):
        self._slot()
        data = self.env['mart369.delivery.rule'].mart369_admin_list()
        self.assertEqual({r['mode'] for r in data['rules']}, {'quick', 'all'})
        self.assertTrue(any(s['key'].startswith('qe:') for s in data['slots']))
        row = next(b for b in data['branches'] if b['id'] == self.shop.id)
        self.assertTrue(row['quick'])
        self.assertEqual(row['quickKm'], 5.0)

    def test_the_odoo_desk_keeps_the_website_settings(self):
        """The desk writes what it lists by id, so it never gets his ids."""
        self._slot()
        data = self.env['mart369.delivery.rule'].with_context(
            mart369_desk=True).mart369_admin_list()
        Slot = self.env['mart369.delivery.slot'].sudo().with_context(active_test=False)
        self.assertEqual({s['id'] for s in data['slots']}, set(Slot.search([]).ids))
        self.assertFalse(any(str(s.get('key', '')).startswith('qe:') for s in data['slots']))

    # ---------------------------------------------------------- moving across

    def test_the_website_settings_are_copied_once(self):
        self.env['mart369.service.area'].sudo().create(
            {'pincode': '99999', 'name': 'QE copy', 'quick': True, 'express': True})
        slots_before = self.env['sa.qe.delivery.slot'].sudo().with_context(
            active_test=False).search_count([])
        Rule = self.env['mart369.delivery.rule']
        Rule._mart369_qe_copy_across()
        Rule._mart369_qe_copy_across()
        found = self.env['sa.qe.service.area'].sudo().with_context(
            active_test=False).search([('pincode', '=', '99999')])
        self.assertEqual(len(found), 1)
        Rule._mart369_qe_copy_across()
        self.assertEqual(self.env['sa.qe.delivery.slot'].sudo().with_context(
            active_test=False).search_count([]), slots_before,
            'a slot he already has, by its times, is not copied again')
        self.assertEqual(self.env['sa.qe.delivery.rule']._qe_for('quick').fee, 30.0,
                         'his rule is never written over')
