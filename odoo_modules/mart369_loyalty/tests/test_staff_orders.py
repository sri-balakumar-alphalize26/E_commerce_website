"""Orders made in Odoo's Sales earn too.

They have none of the app's steps, so the shop's one setting is read for them
as: "Order placed" is when the order is confirmed; anything later is when its
delivery is done. Either way an order earns once, and an app order - which also
has pickings - never earns a second time through them.
"""

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import Mart369LoyaltyCase


@tagged('post_install', '-at_install')
class TestStaffOrders(Mart369LoyaltyCase):

    def _staff_order(self, qty=4):
        return self.env['sale.order'].sudo().create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.quick_product.product_variant_id.id,
                'product_uom_qty': qty,
                'price_unit': 50.0,
            })],
        })

    def _ship(self, order):
        for picking in order.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.button_validate()
        self.assertTrue(order._mart369_points_delivered_at(), "The delivery did not complete.")

    def _expected(self, order):
        points = self.rule._mart369_points_for(order._mart369_points_base_now())
        self.assertGreater(points, 0)
        return points

    def test_placed_earns_on_confirm_once(self):
        self._earn_on('placed')
        order = self._staff_order()
        self.assertFalse(order.mart369_points_earned, "A quotation earned.")
        order.action_confirm()
        expected = self._expected(order)
        self.assertEqual(order.mart369_points_earned, expected)
        self._ship(order)
        self.assertEqual(order.mart369_points_earned, expected)
        self.assertEqual(self._card().total_points, expected)

    def test_delivered_earns_when_the_delivery_is_done(self):
        for step in ('packed', 'out', 'delivered'):
            with self.subTest(step=step):
                self._earn_on(step)
                order = self._staff_order()
                order.action_confirm()
                self.assertFalse(order.mart369_points_earned)
                self._ship(order)
                self.assertEqual(order.mart369_points_earned, self._expected(order))

    def test_an_app_order_does_not_earn_twice_through_its_pickings(self):
        order = self._place()
        self._pay(order)
        self._deliver(order)
        rows = self.env['pos.loyalty.history'].sudo().search(
            [('sale_order_id', '=', order.id), ('type', '=', 'earned')])
        self.assertEqual(len(rows), 1)

    def test_cancelling_takes_the_points_back(self):
        self._earn_on('placed')
        order = self._staff_order()
        order.action_confirm()
        self.assertTrue(order.mart369_points_earned)
        order.with_context(disable_cancel_warning=True).action_cancel()
        self.assertEqual(order.mart369_points_reversed, order.mart369_points_earned)
        self.assertEqual(self._card().total_points, 0.0)

    def test_a_credit_note_takes_the_points_back(self):
        self._earn_on('placed')
        order = self._staff_order()
        order.action_confirm()
        self._ship(order)
        invoice = order._create_invoices()
        invoice.action_post()
        invoice._reverse_moves([{'ref': 'Returned'}]).action_post()
        self.assertEqual(order.mart369_points_reversed, order.mart369_points_earned)
        self.assertEqual(self._card().total_points, 0.0)

    def test_after_the_return_window_from_the_cron(self):
        self._earn_on('settled')
        order = self._staff_order()
        order.action_confirm()
        self._ship(order)
        self.assertFalse(order.mart369_points_earned)
        self.env['sale.order']._mart369_loyalty_settle_cron()
        self.assertFalse(order.mart369_points_earned, "Earned inside the window.")
        order.picking_ids.write({'date_done': fields.Datetime.now() - timedelta(days=8)})
        self.env['sale.order']._mart369_loyalty_settle_cron()
        self.assertEqual(order.mart369_points_earned, self._expected(order))
