# -*- coding: utf-8 -*-
"""The product photo + details link goes to the customer's private chat
(21 Nov 2026, sales_automation/models/sa_private_links.py); the group gets a
note. A hidden number: the group, as before. Nothing is sent: mocked."""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

GROUP = '120363000000000055@g.us'
PHONE = '919800044455'


@tagged('post_install', '-at_install')
class TestConfirmPrivate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.sent, cls.images = [], []
        Session = env.registry['whatsapp.session']
        Request = env.registry['sa.group.request']

        def send_message(self, phone, message):
            cls.sent.append((phone, message))
            return True

        def send_image(self, phone, data, caption=''):
            cls.images.append((phone, caption))
            return True

        for patcher in (
                patch.object(Session, 'send_message', send_message),
                patch.object(Session, 'sa_send_text_mentioning',
                             lambda self, phone, message, mention='': cls.sent.append((phone, message)) or True),
                patch.object(Session, 'send_image', send_image),
                patch.object(Session, '_send_payload', lambda self, *a, **kw: True),
                patch.object(Session, '_gateway_call', lambda self, *a, **kw: {}),
                patch.object(Request, '_sa_confirm_picture', lambda self, fetch=True: (b'jpg', 'local')),
                patch.object(env.registry['sa.outbox.guard'], 'claim',
                             lambda self, key, seconds=60: True)):
            patcher.start()
            cls.addClassCleanup(patcher.stop)

        session = env['whatsapp.session'].sudo().create({
            'name': 'Confirm private test', 'gateway_api_key': 'x'})
        cls.group = env['sa.sales.group'].sudo().create({
            'name': 'Zz Confirm Private', 'group_jid': GROUP,
            'session_id': session.id, 'group_type': 'customer'})
        cls.product = env['product.template'].sudo().create({'name': 'Zz Confirm Private Mouse'})

    def setUp(self):
        super().setUp()
        self.sent.clear()
        self.images.clear()
        self.env['sa.ai.settings'].sudo().get_settings().private_links = True
        self.request = self.env['sa.group.request'].sudo().create({
            'group_id': self.group.id, 'requester_phone': PHONE, 'requester_name': 'Sri',
            'raw_text': 'mouse', 'product_id': self.product.id})

    def test_the_photo_and_link_go_privately(self):
        self.request._sa_confirm_customer_send()
        link = self.request.sa_confirm_link_id
        self.assertEqual([p for p, c in self.images], [PHONE])
        self.assertIn(link.sudo().token, self.images[0][1])
        group = [t for to, t in self.sent if to == GROUP]
        self.assertTrue(any('private chat' in t and 'ACCEPT' in t for t in group), group)
        self.assertFalse(any(link.sudo().token in t for t in group))
        self.assertTrue(link.sent_on)

    def test_a_hidden_number_gets_the_photo_in_the_group(self):
        self.request.write({'requester_is_lid': True, 'requester_lid': '77@lid'})
        self.request._sa_confirm_customer_send()
        self.assertEqual([p for p, c in self.images], [GROUP])
