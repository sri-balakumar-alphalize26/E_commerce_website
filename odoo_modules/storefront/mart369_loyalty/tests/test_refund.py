"""Giving points back when money goes back.

Earned points follow the money: refund half, lose half the points. Spent points
come back only when the order is cancelled or refunded in full, because a
partial return already refunds the item at its full price.
"""

from odoo.tests import tagged

from .common import Mart369LoyaltyCase


@tagged('post_install', '-at_install')
class TestLoyaltyRefund(Mart369LoyaltyCase):

    def test_a_partial_refund_takes_back_its_share(self):
        self._earn_on('placed')
        order = self._place()
        self._pay(order)
        self.assertEqual(order.mart369_points_earned, 20.0)
        order._mart369_refund_to_wallet(100.0, 'Returned')
        self.assertEqual(order.mart369_points_reversed, 10.0)
        self.assertEqual(self._card().total_points, 10.0)

    def test_cancelling_undoes_everything(self):
        self._earn_on('placed')
        card = self._give(500)
        order = self._place(usePoints=True)
        self._pay(order)
        self.assertEqual(card.total_points, 0.0 + order.mart369_points_earned)
        order._mart369_cancel('Changed my mind')
        self.assertEqual(order.mart369_points_reversed, order.mart369_points_earned)
        self.assertEqual(order.mart369_points_credited, 500.0)
        self.assertEqual(card.total_points, 500.0)

    def test_cash_on_delivery_cancelled_gives_points_back(self):
        """Nothing was paid, so nothing is refunded - the points still come back."""
        card = self._give(500)
        order = self._place(usePoints=True)
        self._cash(order)
        self.assertEqual(order.mart369_state, 'placed')
        order._mart369_cancel('No longer needed')
        self.assertEqual(card.total_points, 500.0)

    def test_taking_back_never_goes_below_zero(self):
        """Points already spent at the counter stay spent."""
        self._earn_on('placed')
        order = self._place()
        self._pay(order)
        card = self._card()
        card._mart369_write(15, 'redeemed', 'At the store')
        order._mart369_cancel('Changed my mind')
        self.assertEqual(card.total_points, 0.0)
        self.assertEqual(order.mart369_points_reversed, 5.0)

    def test_a_partial_refund_keeps_the_spent_points(self):
        self._earn_on('placed')
        card = self._give(500)
        order = self._place(usePoints=True)
        self._pay(order)
        order._mart369_refund_to_wallet(50.0, 'Returned')
        self.assertFalse(order.mart369_points_credited)
        # Everything else refunded: now they come back.
        order._mart369_refund_to_wallet(order._mart369_refundable(), 'Returned')
        self.assertEqual(order.mart369_points_credited, 500.0)
        self.assertEqual(card.total_points, 500.0)
