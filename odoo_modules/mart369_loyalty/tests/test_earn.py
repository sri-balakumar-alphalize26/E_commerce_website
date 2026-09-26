"""When an online order earns, and on what.

The step is the shop's choice (Settings -> Loyalty). Whatever it is, an order
earns once: a replayed webhook or a second press of a button must not pay the
points out twice.
"""

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import Mart369LoyaltyCase


@tagged('post_install', '-at_install')
class TestLoyaltyEarn(Mart369LoyaltyCase):

    def _walk(self, order):
        """Every state the order passes through, with its points after each."""
        seen = [(order.mart369_state, order.mart369_points_earned)]
        while order.mart369_state != 'out':
            order.mart369_action_advance()
            seen.append((order.mart369_state, order.mart369_points_earned))
        order.mart369_action_deliver(order.sudo().mart369_otp_code)
        seen.append((order.mart369_state, order.mart369_points_earned))
        return seen

    def _first_earning_step(self, step, **basket):
        self._earn_on(step)
        order = self._place(**basket)
        self.assertFalse(order.mart369_points_earned, "A draft earned.")
        self._pay(order)
        walk = self._walk(order)
        return next(state for state, points in walk if points), walk[-1][1]

    def test_each_setting_earns_at_its_step_on_quick(self):
        for step, state in (('placed', 'placed'), ('packed', 'packed'),
                            ('out', 'out'), ('delivered', 'delivered')):
            with self.subTest(step=step):
                first, points = self._first_earning_step(step, ref='369M-E-' + step)
                self.assertEqual(first, state)
                # 200 of items, 30 of delivery: delivery earns nothing.
                self.assertEqual(points, 20.0)

    def test_packed_means_shipped_on_express(self):
        """Express orders are shipped, never packed. "Packed" must still mean
        the step after placing, or Express orders would wait for delivery."""
        first, points = self._first_earning_step(
            'packed', ref='369E-E-1', items={str(self.express_product.id): 1}, mode='all')
        self.assertEqual(first, 'shipped')
        self.assertEqual(points, 120.0)

    def test_an_order_earns_once(self):
        order = self._place()
        self._pay(order)
        self._deliver(order)
        self.assertEqual(order.mart369_points_earned, 20.0)
        order._mart369_points_earn()
        order._mart369_set_state('delivered')
        rows = self.env['pos.loyalty.history'].sudo().search(
            [('sale_order_id', '=', order.id), ('type', '=', 'earned')])
        self.assertEqual(len(rows), 1)
        self.assertEqual(self._card().total_points, 20.0)

    def test_after_the_return_window_earns_only_from_the_cron(self):
        self._earn_on('settled')
        order = self._place()
        self._pay(order)
        self._deliver(order)
        self.assertFalse(order.mart369_points_earned)

        self.env['sale.order']._mart369_loyalty_settle_cron()
        self.assertFalse(order.mart369_points_earned, "Earned inside the window.")

        stamp = order.mart369_stamp_ids.filtered(lambda s: s.state == 'delivered')
        stamp.sudo().at = fields.Datetime.now() - timedelta(days=8)
        self.env['sale.order']._mart369_loyalty_settle_cron()
        self.assertEqual(order.mart369_points_earned, 20.0)

    def test_switched_off_earns_nothing(self):
        self.config.loyalty_enabled = False
        order = self._place()
        self._pay(order)
        self._deliver(order)
        self.assertFalse(order.mart369_points_earned)
        self.assertFalse(self._card())
