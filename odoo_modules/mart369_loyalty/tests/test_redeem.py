"""Spending points at checkout.

The bill decides what may be spent and the order carries exactly that, so the
order and the bill agree to the paisa - the check mart369_order already makes.
The points are held the moment the order is written, so they cannot go on a
second basket, and given back if that order never gets paid for.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import Mart369LoyaltyCase


@tagged('post_install', '-at_install')
class TestLoyaltyRedeem(Mart369LoyaltyCase):

    def test_the_bill_prices_the_points(self):
        self._give(500)
        bill = self._bill()
        self.assertEqual(bill['total'], 230.0)
        self.assertEqual(bill['points']['usable'], 500.0)
        self.assertEqual(bill['points']['usableValue'], 50.0)
        self.assertFalse(bill['points']['applied'])

        bill = self._bill(use_points=True)
        self.assertTrue(bill['points']['applied'])
        self.assertEqual(bill['points']['off'], 50.0)
        self.assertEqual(bill['total'], 180.0)

    def test_the_rule_limits_what_can_be_spent(self):
        self._give(50)
        self.assertEqual(self._bill(use_points=True)['points']['reason'], 'min')

        self._give(950)
        self.rule.max_redeem_percent = 10.0
        points = self._bill(use_points=True)['points']
        # 10% of 230 is 23 rupees, which is 230 points.
        self.assertEqual(points['usable'], 230.0)
        self.assertEqual(points['off'], 23.0)

    def test_a_guest_gets_no_points_block(self):
        bill = self.env['mart369.cart'].sudo()._mart369_bill({str(self.quick_product.id): 4})
        self.assertIsNone(bill['points'])

    def test_placing_holds_the_points_and_the_order_matches_the_bill(self):
        card = self._give(500)
        order = self._place(usePoints=True)
        self.assertEqual(order.amount_total, 180.0)
        self.assertEqual(order.mart369_points_spent, 500.0)
        self.assertEqual(card.total_points, 0.0)
        line = order.order_line.filtered(lambda l: l.mart369_kind == 'points')
        self.assertEqual(line.price_total, -50.0)
        snap = order._mart369_bill_snapshot()
        items = order._mart369_item_lines()
        self.assertAlmostEqual(snap['items'], sum(items.mapped('price_subtotal')), places=2,
                               msg="The points line was counted as an item.")
        self.assertEqual(snap['pointsOff'], 50.0)

    def test_placing_again_does_not_hold_twice(self):
        """Going back to change the slot rewrites the same draft."""
        card = self._give(500)
        self._place(usePoints=True)
        order = self._place(usePoints=True)
        rows = order._mart369_points_hold_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(card.total_points, 0.0)

        order = self._place(usePoints=False)
        self.assertFalse(order._mart369_points_hold_rows())
        self.assertEqual(card.total_points, 500.0)
        self.assertEqual(order.amount_total, 230.0)

    def test_once_a_day_like_the_counter(self):
        self._give(1000)
        order = self._place(usePoints=True)
        # An unpaid draft is not a spend yet.
        self.assertEqual(self._bill(use_points=True)['points']['reason'], '')
        self._pay(order)
        other = self._bill(use_points=True)['points']
        self.assertEqual(other['reason'], 'today')
        self.assertFalse(other['off'])

    def test_an_unpaid_basket_gives_its_points_back(self):
        card = self._give(500)
        order = self._place(usePoints=True)
        self.env.cr.execute("UPDATE sale_order SET write_date = %s WHERE id = %s",
                            (fields.Datetime.now() - timedelta(hours=25), order.id))
        order.invalidate_recordset(['write_date'])
        self.env['sale.order']._mart369_loyalty_release_cron()
        self.assertEqual(card.total_points, 500.0)

        # Paid for after all: the points are taken again, not given free.
        self._pay(order)
        self.assertEqual(order.mart369_state, 'placed')
        self.assertEqual(card.total_points, 0.0)
        self.assertEqual(len(order._mart369_points_hold_rows()), 1)

    def test_points_spent_elsewhere_in_between_are_refused(self):
        card = self._give(500)
        order = self._place(usePoints=True)
        order._mart369_points_hold_rows().unlink()
        card._mart369_write(450, 'redeemed', 'At the store')
        with self.assertRaises(UserError):
            order._mart369_points_hold()

    def test_redeeming_switched_off(self):
        self._give(500)
        self.config.loyalty_redeem = False
        points = self._bill(use_points=True)['points']
        self.assertEqual(points['reason'], 'off')
        self.assertEqual(points['balance'], 500.0)
        self.assertFalse(points['off'])
