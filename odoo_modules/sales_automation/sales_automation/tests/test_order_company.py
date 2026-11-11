# -*- coding: utf-8 -*-
"""A WhatsApp group's order is raised in the group's company.

One employee session serves every group, and its Order Company was written on
every order - so a Test 2 order for NEW COMPANY landed in My Company (S00003).
Nothing is sent: the group senders are replaced."""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

PHONE = '919800054321'


@tagged('post_install', '-at_install')
class TestOrderCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.home = env.company
        cls.hub = env['res.company'].create({'name': 'Zz SA Hub Company'})
        session = env['whatsapp.session'].create({
            'name': 'SA company test', 'gateway_api_key': 'x',
            'instance_name': 'sa-company-test'})
        employee = env['hr.employee'].create({'name': 'Zz SA Counter'})
        # The session's Order Company is the home company, as on the server.
        cls.desk = env['wa.employee.session'].create({
            'employee_id': employee.id, 'session_id': session.id,
            'phone_number': '919800000001', 'auto_reply_company_id': cls.home.id})
        Group = env['sa.sales.group']
        cls.hub_group = Group.create({
            'name': 'Zz Test 2', 'group_jid': '120363000000000002@g.us',
            'session_id': session.id, 'group_type': 'customer',
            'company_id': cls.hub.id})
        cls.plain_group = Group.create({
            'name': 'Zz Test 1', 'group_jid': '120363000000000003@g.us',
            'session_id': session.id, 'group_type': 'customer',
            'company_id': False})
        cls.product = env['product.template'].create({
            'name': 'Zz SA Glow Gun', 'list_price': 3.0, 'type': 'consu'})
        env['res.partner'].search([('phone', 'ilike', PHONE[-9:])]).write({'phone': False})
        cls.conv = env['wa.conversation'].sudo()._get_or_create(cls.desk, PHONE)
        cls.AutoReply = env['wa.auto.reply'].sudo()

    def _req(self, group, **vals):
        base = {'group_id': group.id, 'requester_phone': PHONE,
                'requester_name': 'sri', 'raw_text': 'glow gun',
                'conversation_id': self.conv.id, 'product_id': self.product.id,
                'state': 'answered'}
        base.update(vals)
        return self.env['sa.group.request'].create(base)

    def _order(self):
        return self.AutoReply._create_sale_order(
            self.desk, self.conv, self.product, 1, False, unit_price=3.0)

    def assertInCompany(self, order, company):
        self.assertTrue(order, "no order was raised")
        self.assertEqual(order.company_id, company)
        self.assertEqual(order.warehouse_id.company_id, company)
        self.assertLessEqual(order.order_line.tax_ids.company_id, company)

    def test_group_company_decides(self):
        self.assertEqual(self._req(self.hub_group)._sa_order_company(), self.hub)

    def test_group_without_company_keeps_the_session_company(self):
        self.assertEqual(self._req(self.plain_group)._sa_order_company(), self.home)

    def test_stock_company_does_not_move_the_order(self):
        """The finder's shelf is where the goods come from, not whose sale it is."""
        req = self._req(self.hub_group, finder_company_id=self.home.id)
        self.assertEqual(req._sa_order_company(), self.hub)

    def test_private_chat_order_after_a_group_quote(self):
        req = self._req(self.hub_group)
        order = self._order()
        self.assertInCompany(order, self.hub)
        self.assertEqual(req.order_id, order)
        self.assertEqual(order.sa_group_request_id, req)

    def test_plain_whatsapp_chat_is_unchanged(self):
        """No group enquiry behind it: the session's Order Company, as before."""
        self.assertInCompany(self._order(), self.home)

    def test_group_order_placed_from_the_group(self):
        req = self._req(self.hub_group, state='awaiting_order_confirm',
                        qty=1, quoted_price=3.0)
        Req = type(self.env['sa.group.request'])
        for name, value in (('_say', True), ('_ask', 'poll'),
                            ('_assess_availability', True),
                            ('_sa_group_details_start', True)):
            p = patch.object(Req, name, autospec=True, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        req._place_order()
        self.assertInCompany(req.order_id, self.hub)
        self.assertEqual(req.state, 'order_created')
        # Nothing after the order inherits the company switch.
        self.assertFalse(req.order_id.env.context.get('sa_order_company_id'))
