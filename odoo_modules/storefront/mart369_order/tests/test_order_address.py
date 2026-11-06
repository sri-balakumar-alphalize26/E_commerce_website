"""An order's delivery address: kept as placed, changeable only before it leaves.

The promise Flipkart and Amazon make, and 369 Mart now makes too: editing a
saved address never rewrites an order that already went there, and support can
move an order to another of the customer's addresses only while it is still in
the store.
"""

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import Mart369OrderCase


@tagged('post_install', '-at_install')
class TestOrderAddress(Mart369OrderCase):

    def setUp(self):
        super().setUp()
        # Staff only ever act on shoppers: the fixtures' logins become portal.
        portal = self.env.ref('base.group_portal')
        (self.customer | self.other).sudo().write({'group_ids': [(6, 0, [portal.id])]})
        self.Partner = self.env['res.partner']
        self.tn = self.env['res.country.state'].search([
            ('country_id.code', '=', 'IN'), ('name', '=', 'Tamil Nadu')], limit=1)
        self.address.write({'country_id': self.env.ref('base.in').id, 'state_id': self.tn.id,
                            'street2': 'Sandai Road', 'mart369_label': 'Home'})
        self.address._mart369_set_default()
        self.work = self.partner.sudo()._mart369_add_address({
            'name': 'Order Tester', 'mart369_label': 'Work', 'street': '3rd Floor, Tech Park',
            'street2': 'Parrys Corner', 'city': 'Chennai', 'zip': '600001',
            'phone': '+919876543210', 'country_id': self.env.ref('base.in').id,
            'state_id': self.tn.id,
        })

    def _order(self, **overrides):
        order = self._place(**overrides)
        self._pay(order)
        return order

    # --------------------------------------------------- an order keeps its address

    def test_editing_an_address_an_order_went_to_keeps_the_order(self):
        order = self._order()
        result = self.Partner.mart369_admin_edit(self.address.id, {
            'line': '9 New Street', 'landmark': 'Near the temple', 'state_id': self.tn.id})
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['replaced'], 'an address in use is copied, not rewritten')

        self.assertEqual(order.partner_shipping_id, self.address, 'the order still points at the original')
        self.assertEqual(self.address.street, '3 Test Street', 'and the original is untouched')
        self.assertFalse(self.address.active, 'archived, so the customer no longer sees it')

        fresh = self.Partner.browse(result['address']['id'])
        self.assertNotEqual(fresh, self.address)
        self.assertEqual((fresh.street, fresh.mart369_landmark), ('9 New Street', 'Near the temple'))
        self.assertEqual(fresh.name, 'Order Tester', 'no "(copy)" on the name')
        self.assertTrue(fresh.mart369_default, 'the default moved to the copy')
        self.assertEqual(fresh.type, 'delivery')
        self.assertIn(fresh, self.partner.sudo()._mart369_book())
        self.assertNotIn(self.address, self.partner.sudo()._mart369_book())

    def test_an_address_no_order_used_is_edited_in_place(self):
        result = self.Partner.mart369_admin_edit(self.work.id, {'line': '4th Floor, Tech Park'})
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['replaced'])
        self.assertEqual(result['address']['id'], self.work.id)
        self.assertEqual(self.work.street, '4th Floor, Tech Park')

    def test_renaming_the_label_never_copies(self):
        self._order()
        result = self.Partner.mart369_admin_edit(self.address.id, {'label': 'Other'})
        self.assertFalse(result['replaced'])
        self.assertEqual(self.address.mart369_label, 'Other')
        self.assertTrue(self.address.active)

    # ------------------------------------------------ changing an order's address

    def test_an_order_in_the_store_can_move_to_another_address(self):
        order = self._order()
        detail = self.env['sale.order'].mart369_admin_detail(order.mart369_ref)
        self.assertTrue(detail['addressChangeable'])
        self.assertEqual({a['id'] for a in detail['addresses']}, {self.address.id, self.work.id})

        after = self.env['sale.order'].mart369_admin_set_address(order.mart369_ref, self.work.id)
        self.assertEqual(order.partner_shipping_id, self.work)
        self.assertEqual(after['address']['id'], self.work.id)
        self.assertIn('Home', order.message_ids[:1].body)
        self.assertIn('Work', order.message_ids[:1].body)

        # Packed is still in the store.
        self.env['sale.order'].mart369_admin_advance(order.mart369_ref)
        self.env['sale.order'].mart369_admin_set_address(order.mart369_ref, self.address.id)
        self.assertEqual(order.partner_shipping_id, self.address)

    def test_an_order_on_its_way_keeps_its_address(self):
        order = self._order()
        self.env['sale.order'].mart369_admin_advance(order.mart369_ref)  # packed
        self.env['sale.order'].mart369_admin_advance(order.mart369_ref)  # out
        detail = self.env['sale.order'].mart369_admin_detail(order.mart369_ref)
        self.assertFalse(detail['addressChangeable'])
        self.assertEqual(detail['addresses'], [])
        with self.assertRaises(UserError):
            self.env['sale.order'].mart369_admin_set_address(order.mart369_ref, self.work.id)
        self.assertEqual(order.partner_shipping_id, self.address)

    def test_someone_else_s_address_is_refused(self):
        order = self._order()
        theirs = self.other.partner_id.sudo()._mart369_add_address({
            'name': 'Someone Else', 'street': '1 Their Road', 'street2': 'Elsewhere',
            'city': 'Madurai', 'zip': '625001', 'phone': '+919876500000',
        })
        with self.assertRaises(UserError):
            self.env['sale.order'].mart369_admin_set_address(order.mart369_ref, theirs.id)
        self.assertEqual(order.partner_shipping_id, self.address)

    # ------------------------------------------------------------------ fences

    def test_a_shopper_cannot_use_the_staff_methods(self):
        shopper = self.Partner.with_user(self.customer)
        with self.assertRaises(AccessError):
            shopper.mart369_admin_edit(self.address.id, {'line': 'hijacked'})
        with self.assertRaises(AccessError):
            shopper.mart369_admin_make_default(self.work.id)
        self.assertEqual(self.address.street, '3 Test Street')
