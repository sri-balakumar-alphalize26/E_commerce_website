"""The Customers screens' "ordered 2 d ago": when a customer last placed an
order (mart369_auth/models/customer_admin.py, _mart369_admin_last_placed).

Placed, not confirmed - and never an unpaid or cancelled one.
"""

from odoo.tests import tagged

from .common import Mart369OrderCase


@tagged('post_install', '-at_install')
class TestCustomerLastPlaced(Mart369OrderCase):

    def _row(self):
        return self.customer.sudo()._mart369_admin_row()

    def test_only_a_placed_order_counts(self):
        self.assertIsNone(self._row()['lastPlaced'], 'no orders yet')

        order = self._place()
        if order.mart369_state == 'draft':
            self.assertIsNone(self._row()['lastPlaced'], 'waiting for payment is not ordered')
            self._pay(order)
        self.assertNotIn(order.mart369_state, ('draft', 'cancelled'))
        self.assertTrue(order.mart369_placed_at)
        self.assertEqual(self._row()['lastPlaced'],
                         int(order.mart369_placed_at.timestamp() * 1000))

    def test_a_cancelled_order_does_not_count(self):
        order = self._place()
        if order.mart369_state == 'draft':
            self._pay(order)
        order.sudo().write({'mart369_state': 'cancelled'})
        self.assertIsNone(self._row()['lastPlaced'])
