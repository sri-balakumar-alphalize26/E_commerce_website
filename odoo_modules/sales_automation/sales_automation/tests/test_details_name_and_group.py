# -*- coding: utf-8 -*-
"""Two gaps found on the WhatsApp test of 11 Nov 2026 (S00024, group Test 2).

1. NO > NAME > "Sri" renamed the contact only: the order's delivery address
   still said "RaviKavitha", the read-back showed "RaviKavitha (for Sri)" and
   the rider got the old name.
2. An order placed from the group's YES had no WhatsApp Group - only the
   enquiry pointed at the order - so the rider job left from whichever
   session came first and the console card named no group.

Nothing is sent: no message leaves these tests.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDetailsNameAndGroup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        session = env['whatsapp.session'].create({
            'name': 'SA name test', 'gateway_api_key': 'x',
            'instance_name': 'sa-name-test'})
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz Name Test', 'group_jid': '120363000000000099@g.us',
            'session_id': session.id, 'group_type': 'customer'})
        cls.product = env['product.template'].create({
            'name': 'Zz Name Test Laptop', 'list_price': 600.0, 'type': 'consu'})
        cls.customer = env['res.partner'].create({
            'name': 'RaviKavitha', 'phone': '+919800011122'})
        cls.home = env['res.partner'].create({
            'name': 'RaviKavitha', 'parent_id': cls.customer.id, 'type': 'delivery',
            'street': '15, Abc road', 'zip': '624003'})
        cls.mum = env['res.partner'].create({
            'name': 'Lakshmi', 'parent_id': cls.customer.id, 'type': 'delivery',
            'street': '2, Temple street', 'zip': '624001'})
        cls.order = env['sale.order'].create({
            'partner_id': cls.customer.id,
            'partner_shipping_id': cls.home.id,
            'order_line': [(0, 0, {'product_id': cls.product.product_variant_id.id,
                                   'product_uom_qty': 1})],
        })
        cls.request = env['sa.group.request'].create({
            'group_id': cls.group.id, 'requester_phone': '919800011122',
            'requester_name': 'RaviKavitha', 'raw_text': 'laptop',
            'product_id': cls.product.id, 'state': 'answered'})

    # -------------------------------------------------------------- the name

    def test_a_new_name_reaches_the_orders_own_address(self):
        old = self.customer.name
        self.customer.name = 'Sri'
        self.request._sa_rename_own_addresses(self.customer, old)
        self.assertEqual(self.home.name, 'Sri', 'her own address follows her name')
        self.assertEqual(self.order.partner_shipping_id.name, 'Sri')

    def test_an_address_for_somebody_else_keeps_its_name(self):
        old = self.customer.name
        self.customer.name = 'Sri'
        self.request._sa_rename_own_addresses(self.customer, old)
        self.assertEqual(self.mum.name, 'Lakshmi')

    def test_the_name_step_renames_both(self):
        """Through the ladder itself, the way NO > NAME > "Sri" arrives."""
        self.request.write({'order_id': self.order.id, 'profile_step': 'name'})
        self.request._sa_take_profile_answer('Sri', self.order)
        self.assertEqual(self.customer.name, 'Sri')
        self.assertEqual(self.home.name, 'Sri')
        self.assertEqual(self.mum.name, 'Lakshmi')

    def test_the_same_name_again_changes_nothing(self):
        self.request._sa_rename_own_addresses(self.customer, self.customer.name)
        self.assertEqual(self.home.name, 'RaviKavitha')

    # ------------------------------------------------------------- the group

    def test_an_order_placed_from_the_group_knows_its_group(self):
        self.assertFalse(self.order.sa_group_id)
        self.request.order_id = self.order
        self.assertFalse(self.order.sa_group_request_id, 'the chat flow is not switched')
        self.assertEqual(self.order.sa_group_id, self.group)

    def test_the_forward_link_still_decides_when_it_is_there(self):
        other = self.env['sa.sales.group'].create({
            'name': 'Zz Other', 'group_jid': '120363000000000098@g.us',
            'session_id': self.group.session_id.id, 'group_type': 'customer'})
        linked = self.env['sa.group.request'].create({
            'group_id': other.id, 'requester_phone': '919800011122',
            'requester_name': 'RaviKavitha', 'raw_text': 'laptop',
            'product_id': self.product.id, 'state': 'answered'})
        self.request.order_id = self.order
        self.order.sudo().sa_group_request_id = linked
        self.assertEqual(self.order.sa_group_id, other)
