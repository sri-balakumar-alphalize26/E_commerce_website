"""The hub split, where the senior's Quick / Express module runs too.

Priya's basket has bananas from the Ruwi hub and a cable from Sohar Hub. On
a database with his module, the basket used to stay one order: his stack
switched the split off and charged his one shared fee. Now the hub rules win
on the website: two orders, one per hub, each at its hub's own fee - the
fee the customer was shown - and his "add the fee" never changes it after.

WhatsApp is untouched: each hub is its own group there, and a group's order
still gets his fee line.

Skipped on a database without `sales_automation_quick_express`.
"""

from odoo.tests import TransactionCase, tagged

from odoo.addons.mart369_order.tests.test_split_orders import SplitFixtures

from ..models.qe_link import hubs_on, qe_on
from .common import Mart369BridgeFixtures


@tagged('post_install', '-at_install')
class TestHubSplitQe(SplitFixtures, Mart369BridgeFixtures, TransactionCase):

    def setUp(self):
        super().setUp()
        if not qe_on(self.env):
            self.skipTest("the senior's Quick / Express module is not installed here")
        env = self.env
        # His two rules, at the same numbers as the website's fixtures.
        Rule = env['sa.qe.delivery.rule'].sudo().with_context(active_test=False)
        for mode, values in (('quick', {'fee': 30, 'free_above': 499, 'min_order': 99}),
                             ('express', {'fee': 49, 'free_above': 999, 'min_order': 0})):
            rule = Rule.search([('mode', '=', mode)], limit=1)
            values = dict(values, label=mode.title(), eta='%s promise' % mode, active=True)
            if rule:
                rule.write(values)
            else:
                Rule.create(dict(values, mode=mode))
        env['sa.qe.delivery.slot'].sudo().search([]).write({'active': False})
        # Ruwi charges the shop's fees; Sohar its own (SplitFixtures).
        self.ruwi_wh.sudo().mart369_own_fees = False
        # The hub rules are on: one row, Sohar to Ruwi, next day.
        env['mart369.hub.rule'].sudo().create({
            'from_hub_id': self.sohar_wh.id, 'to_hub_id': self.ruwi_wh.id,
            'days': 1, 'arrives': 'Next day'})
        self.assertTrue(hubs_on(env))
        settings = env['sa.delivery.settings'].sudo().get_settings()
        settings.write({'qe_enabled': True, 'qe_auto_fee': True})

    def _parts(self):
        orders = self._place_split()
        ruwi = orders.filtered(lambda o: o.company_id == self.main)
        return orders, ruwi, orders - ruwi

    # ----------------------------------------------------------- the bill

    def test_the_bill_still_comes_in_two_parts_at_each_hubs_fee(self):
        items = self._split_basket()['items']
        bill = self.env['mart369.cart']._mart369_bill(items, address=self.pinned)
        self.assertEqual(len(bill['parts']), 2, 'his module no longer switches the split off')
        by_seller = {p['seller']['id']: p for p in bill['parts']}
        self.assertEqual(by_seller[self.main.id]['fees'], 30.0, 'Quick fee, from Ruwi')
        self.assertEqual(by_seller[self.sohar.id]['fees'], 10.0, "Sohar Hub's own Express fee")
        self.assertEqual(bill['total'], 260.0)

    # ---------------------------------------------------------- placing

    def test_one_order_per_hub_each_at_the_fee_shown(self):
        orders, ruwi, sohar = self._parts()
        self.assertEqual(len(orders), 2)
        self.assertEqual(set(orders.mapped('mart369_group')), {'369M-SPLIT1'})
        self.assertEqual(sohar.warehouse_id, self.sohar_wh)
        self.assertAlmostEqual(ruwi.amount_total, 230.0)
        self.assertAlmostEqual(sohar.amount_total, 30.0)
        for order in orders:
            fee_lines = order.order_line.filtered(lambda l: l.mart369_kind == 'fee')
            self.assertEqual(len(fee_lines), 1)
            self.assertFalse(order.order_line.filtered(lambda l: l.qe_kind == 'fee'),
                             'no second fee line from his rule')
        self.assertEqual(sohar.order_line.filtered(lambda l: l.mart369_kind == 'fee').price_unit,
                         10.0)

    def test_his_stack_never_decides_a_part_again(self):
        __, ruwi, sohar = self._parts()
        self.assertTrue(ruwi.qe_decided and sohar.qe_decided)
        self.assertEqual(ruwi.qe_mode, 'quick')
        self.assertEqual(sohar.qe_mode, 'express')
        self.assertEqual(ruwi.qe_shop_id, self.shop, 'a Quick part goes from its hub\'s shop')
        self.assertEqual(sohar.qe_fee, 10.0)
        self.assertFalse(ruwi.qe_blocked or sohar.qe_blocked)

    def test_his_add_the_fee_leaves_the_parts_alone(self):
        # What his confirm runs with "add the fee automatically" on, and his
        # button - without confirming, which on some databases first wants
        # serial numbers picked (product_tracker).
        orders, __, __ = self._parts()
        before = {o.id: o.amount_total for o in orders}
        orders._qe_apply_fee()
        orders.action_qe_apply_fee()
        for order in orders:
            self.assertAlmostEqual(order.amount_total, before[order.id])
            self.assertFalse(order.order_line.filtered(lambda l: l.qe_kind == 'fee'))

    def test_a_one_hub_basket_is_one_order_at_the_websites_fee(self):
        order = self._place(address_id=self.pinned.id, ref='369M-ONEHUBQE')
        self.assertEqual(len(order), 1)
        self.assertFalse(order.mart369_group)
        self.assertAlmostEqual(order.amount_total, 230.0, '4 bananas + the Quick fee')
        self.assertFalse(order.order_line.filtered(lambda l: l.qe_kind == 'fee'))

    # ---------------------------------------------------------- WhatsApp

    def test_a_whatsapp_group_order_still_gets_his_fee(self):
        order = self._wa_order(confirm=False)
        self.assertFalse(order.mart369_ref)
        order._qe_apply_fee()
        self.assertTrue(order.order_line.filtered(lambda l: l.qe_kind == 'fee'),
                        'a group order is his to charge, as before')
