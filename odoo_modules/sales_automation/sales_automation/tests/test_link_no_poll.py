# -*- coding: utf-8 -*-
"""SIGN / PAY / TRACK send the link and nothing to tap after it (owner, 22 Nov
2026). A track answer with no link yet keeps BACK / MAIN MENU, and the other
menu answers (MY DETAILS ...) keep theirs. Nothing is sent: captured."""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

SIGN = 'https://shop.test/my/orders/7?access_token=abc'
PAY = 'https://shop.test/wa/pay/7'


@tagged('post_install', '-at_install')
class TestLinkNoPoll(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.said, cls.navs, cls.polls = [], [], []
        Request = env.registry['sa.group.request']
        for patcher in (
                patch.object(Request, '_say', lambda self, body, addressed=True: cls.said.append(body) or True),
                patch.object(Request, '_ask', lambda self, body, buttons: cls.polls.append(body) or True),
                patch.object(Request, '_sa_nav', lambda self, level: cls.navs.append(level) or True),
                patch.object(Request, '_sa_portal_link', lambda self, order: SIGN),
                patch.object(Request, '_sa_pay_url', lambda self, order: PAY)):
            patcher.start()
            cls.addClassCleanup(patcher.stop)
        session = env['whatsapp.session'].sudo().create({
            'name': 'SA link no poll', 'gateway_api_key': 'x', 'instance_name': 'sa-link-no-poll'})
        group = env['sa.sales.group'].create({
            'name': 'Zz Link No Poll', 'group_jid': '120363000000000044@g.us',
            'session_id': session.id, 'group_type': 'customer'})
        product = env['product.template'].create({
            'name': 'Zz Link No Poll Laptop', 'list_price': 600.0, 'type': 'consu'})
        customer = env['res.partner'].create({'name': 'Sri', 'phone': '+919800055566'})
        order = env['sale.order'].create({
            'partner_id': customer.id,
            'order_line': [(0, 0, {'product_id': product.product_variant_id.id, 'product_uom_qty': 1})]})
        cls.request = env['sa.group.request'].create({
            'group_id': group.id, 'requester_phone': '919800055566', 'requester_name': 'Sri',
            'raw_text': 'laptop', 'product_id': product.id, 'ref_code': 'L7',
            'state': 'order_created', 'order_id': order.id})

    def setUp(self):
        super().setUp()
        for box in (self.said, self.navs, self.polls):
            box.clear()

    def _link_only(self, url):
        self.assertEqual(len(self.said), 1, self.said)
        self.assertIn(url, self.said[0])
        self.assertIn('Say *hi*', self.said[0])
        self.assertFalse(self.navs, 'no "What next?" after the link')
        self.assertFalse(self.polls)

    def test_sign_pay_and_track_are_the_link_only(self):
        for kind, url in (('sign', SIGN), ('pay', PAY), ('track', SIGN)):
            with self.subTest(kind=kind):
                self.said.clear()
                self.request._sa_menu_tapped({'kind': kind, 'target': self.request.id, 'parent': 'orders'})
                self._link_only(url)

    def test_the_order_screens_track_is_the_link_only(self):
        Request = self.env.registry['sa.group.request']
        with patch.object(Request, '_sa_track_text', lambda self, key: 'Follow it live: https://t.test/9'):
            self.request._sa_menu_tapped({'kind': 'ss_track', 'key': 'x', 'parent': 'orders'})
        self._link_only('https://t.test/9')

    def test_the_main_menus_track_is_the_link_only(self):
        Request = self.env.registry['sa.group.request']
        with patch.object(Request, '_sa_track_text', lambda self, key: 'Follow it live: https://t.test/9'), \
                patch.object(Request, '_sa_customer_orders', lambda self: [{'in_flight': True, 'key': 'x'}]):
            self.request._sa_menu_tapped({'kind': 'ss_track_any', 'parent': 'main'})
        self._link_only('https://t.test/9')

    def test_track_without_a_link_keeps_the_menu(self):
        Request = self.env.registry['sa.group.request']
        with patch.object(Request, '_sa_track_text', lambda self, key: 'It has not left the shop yet'):
            self.request._sa_menu_tapped({'kind': 'ss_track', 'key': 'x', 'parent': 'orders'})
        self.assertEqual(self.said, ['It has not left the shop yet'])
        self.assertEqual(self.navs, ['orders'])

    def test_other_answers_keep_the_menu(self):
        self.request._sa_menu_tapped({'kind': 'details', 'parent': 'more'})
        self.assertEqual(self.navs, ['more'])
