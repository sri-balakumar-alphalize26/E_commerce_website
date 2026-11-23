# -*- coding: utf-8 -*-
"""A WhatsApp order is in its company's currency (23 Nov 2026), whatever the
company's price list or the server user's company says. Nothing is sent."""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

PHONE = '919800054399'


@tagged('post_install', '-at_install')
class TestOrderCurrency(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Currency = env['res.currency'].with_context(active_test=False)
        cls.aed, cls.omr = (Currency.search([('name', '=', n)], limit=1) for n in ('AED', 'OMR'))
        (cls.aed | cls.omr).write({'active': True})
        cls.home = env.company
        cls.shop = env['res.company'].create({'name': 'Zz Currency Shop', 'currency_id': cls.aed.id})
        env['product.pricelist'].search([('company_id', '=', cls.shop.id)]).write({'active': False})
        cls.wrong = env['product.pricelist'].create({
            'name': 'Zz wrong', 'currency_id': cls.omr.id, 'company_id': cls.shop.id, 'sequence': 0})
        session = env['whatsapp.session'].create({
            'name': 'SA currency', 'gateway_api_key': 'x', 'instance_name': 'sa-currency'})
        employee = env['hr.employee'].create({'name': 'Zz SA Currency Counter'})
        cls.desk = env['wa.employee.session'].create({
            'employee_id': employee.id, 'session_id': session.id,
            'phone_number': '919800000099', 'auto_reply_company_id': cls.home.id})
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz Currency', 'group_jid': '120363000000000044@g.us',
            'session_id': session.id, 'group_type': 'customer', 'company_id': cls.shop.id})
        cls.product = env['product.template'].create({'name': 'Zz Currency Jack', 'list_price': 3.0, 'type': 'consu'})
        env['res.partner'].search([('phone', 'ilike', PHONE[-9:])]).write({'phone': False})
        cls.conv = env['wa.conversation'].sudo()._get_or_create(cls.desk, PHONE)

    def _req(self, **vals):
        return self.env['sa.group.request'].create(dict({
            'group_id': self.group.id, 'requester_phone': PHONE, 'requester_name': 'sri', 'raw_text': 'jack',
            'conversation_id': self.conv.id, 'product_id': self.product.id, 'state': 'answered'}, **vals))

    def _place(self, req):
        Req = type(self.env['sa.group.request'])
        for name, value in (('_say', True), ('_ask', 'poll'), ('_assess_availability', True),
                            ('_sa_group_details_start', True)):
            p = patch.object(Req, name, autospec=True, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        req._place_order()
        return req.order_id

    def _using_the_wrong_list(self):
        return patch.object(self.env.registry['res.partner'], '_compute_product_pricelist',
                            lambda rec: [p.update({'property_product_pricelist': self.wrong.id}) for p in rec] and None)

    def test_an_enquiry_without_a_currency_takes_the_companys(self):
        self.assertNotEqual(self.home.currency_id, self.aed)
        self.assertEqual(self._req().currency_id, self.aed)

    def test_the_group_order_ignores_a_list_in_another_currency(self):
        req = self._req(state='awaiting_order_confirm', qty=2, quoted_price=3.0)
        with self._using_the_wrong_list():
            order = self._place(req)
        self.assertEqual(order.company_id, self.shop)
        self.assertEqual(order.currency_id, self.aed)
        self.assertFalse(order.pricelist_id)
        self.assertEqual((order.order_line.price_unit, order.order_line.currency_id), (3.0, self.aed))
        self.assertEqual(order.currency_id, req.currency_id)

    def test_a_list_in_the_companys_currency_is_kept(self):
        right = self.env['product.pricelist'].create({
            'name': 'Zz right', 'currency_id': self.aed.id, 'company_id': self.shop.id})
        req = self._req(state='awaiting_order_confirm', qty=1, quoted_price=3.0)
        with patch.object(type(self), 'wrong', right), self._using_the_wrong_list():
            order = self._place(req)
        self.assertEqual((order.pricelist_id, order.currency_id), (right, self.aed))

    def test_other_orders_keep_their_list(self):
        partner = self.env['res.partner'].create({'name': 'Zz desk customer'})
        with self._using_the_wrong_list():
            order = self.env['sale.order'].create({'partner_id': partner.id, 'company_id': self.shop.id})
            self.assertEqual(order.pricelist_id, self.wrong)
        self.assertEqual(order.currency_id, self.omr)

    def test_the_shelfs_price_only_in_the_same_currency(self):
        req = self._req(finder_company_id=self.home.id)
        self.assertEqual(req._sa_priced(self.product).env.company, self.shop)
        same = self.env['res.company'].create({'name': 'Zz same money', 'currency_id': self.aed.id})
        req.finder_company_id = same
        self.assertEqual(req._sa_priced(self.product).env.company, same)

    def test_a_vendors_price_is_turned_into_the_order_currency(self):
        req = self._req(state='sourcing')
        self.assertIsNone(req._sa_price_in_own(100.0, 'OMR'), 'no rate: held, never 1:1')
        self.assertEqual(req._sa_price_in_own(100.0, 'AED'), 100.0)

    def test_vendors_are_asked_in_the_order_companys_currency(self):
        req = self._req(state='sourcing')
        vendor = self.env['res.partner'].create({
            'name': 'Zz Kochi', 'phone': '+919812345602', 'country_id': self.env.ref('base.in').id})
        self.assertEqual(req._sa_vendor_currency(vendor.phone, vendor), 'AED')
        self.assertEqual(req._sa_partner_currency(vendor, vendor.phone, self.shop), 'AED')
        # one they write themselves still counts: no rate, held
        self.assertEqual(self.env['sa.vendor.quote']._sa_currency_in('INR 100', 'AED'), 'INR')
        self.assertIsNone(req._sa_price_in_own(100.0, 'INR'))
        self.env['sa.ai.settings'].get_settings().vendor_money = 'country'
        self.assertEqual(req._sa_vendor_currency(vendor.phone, vendor), 'INR')
