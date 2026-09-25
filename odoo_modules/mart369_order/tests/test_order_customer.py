"""The customer on an order, and order notes (models/order_customer.py)."""

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import Mart369OrderCase


@tagged('post_install', '-at_install')
class TestOrderCustomer(Mart369OrderCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer.sudo().write({'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])]})
        cls.Order = cls.env['sale.order']
        cls.staff = new_test_user(cls.env, login='zz_order_staff',
                                  groups='base.group_user,website.group_website_designer')

    def _order(self):
        order = self._place(ref='369M-CUST1')
        if order.mart369_state == 'draft':
            self._pay(order)
        return order

    def test_the_row_knows_who_the_customer_is(self):
        order = self._order()
        self.partner.commercial_partner_id.category_id = [(0, 0, {'name': 'Zz Order VIP'})]
        row = order._mart369_admin_row()
        self.assertEqual(row['customer']['userId'], self.customer.id)
        self.assertEqual([t['name'] for t in row['customer']['tags']], ['Zz Order VIP'])
        detail = self.Order.mart369_admin_detail(order.mart369_ref)
        self.assertEqual(detail['customer']['risk']['placed'], 1)
        self.assertIn('notes', detail)

    def test_order_notes_are_signed_and_only_the_author_changes_them(self):
        order = self._order()
        Order = self.Order.with_user(self.staff)
        notes = Order.mart369_admin_add_order_note(order.mart369_ref, 'Called, no answer')
        mine = next(n for n in notes if n['text'] == 'Called, no answer')
        self.assertEqual(mine['author'], self.staff.name)
        self.assertTrue(mine['mine'])
        edited = Order.mart369_admin_edit_order_note(order.mart369_ref, mine['id'], 'Called twice, no answer')
        self.assertIn('Called twice, no answer', [n['text'] for n in edited])
        other = new_test_user(self.env, login='zz_order_staff2',
                              groups='base.group_user,website.group_website_designer')
        with self.assertRaises(AccessError):
            self.Order.with_user(other).mart369_admin_delete_order_note(order.mart369_ref, mine['id'])
        with self.assertRaises(UserError):
            Order.mart369_admin_add_order_note(order.mart369_ref, '   ')
        left = Order.mart369_admin_delete_order_note(order.mart369_ref, mine['id'])
        self.assertNotIn(mine['id'], [n['id'] for n in left])

    def test_a_shopper_cannot_write_order_notes(self):
        order = self._order()
        with self.assertRaises(AccessError):
            self.Order.with_user(self.customer).mart369_admin_add_order_note(order.mart369_ref, 'hi')
