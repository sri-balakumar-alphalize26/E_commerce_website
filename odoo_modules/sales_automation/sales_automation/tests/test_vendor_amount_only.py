# -*- coding: utf-8 -*-
"""Suppliers are asked for the amount only, in their own currency (owner,
22 Nov 2026: "only amount typeable, highlighted, in their country's currency -
days not needed"). No "#T 500", no "450 3 days". With several price checks
open, a swipe-reply to our message names the enquiry.

Nothing is sent: every send is captured.
"""
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.sales_automation.controllers import group_webhook
from odoo.addons.sales_automation.controllers.group_webhook import WhatsAppWebhookGroups

UAE = '971501234567'
INDIA = '919812345678'


@tagged('post_install', '-at_install')
class TestVendorAmountOnly(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        for patcher in (
                patch.object(env.registry['sa.outbox.guard'], 'claim',
                             lambda self, key, seconds=60: True),
                patch.object(env.registry['sa.group.request'], '_say',
                             lambda self, body, addressed=True: True)):
            patcher.start()
            cls.addClassCleanup(patcher.stop)
        cls.session = env['whatsapp.session'].create({
            'name': 'SA vendor amount', 'gateway_api_key': 'x', 'instance_name': 'sa-vendor-amount'})
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz Vendor Amount', 'group_jid': '120363000000000088@g.us',
            'session_id': cls.session.id, 'group_type': 'customer'})
        env['sa.ai.settings'].get_settings().vendor_money = 'country'
        cls.ae = env.ref('base.ae')
        cls.uae_vendor = env['res.partner'].create({
            'name': 'Zz Dubai Parts', 'phone': '+' + UAE, 'country_id': cls.ae.id})
        cls.india_vendor = env['res.partner'].create({
            'name': 'Zz Kochi Parts', 'phone': '+' + INDIA})          # no country: the +91 decides
        cls.product = env['product.template'].create({
            'name': '3680-5050-acer-laptop-dc-jack', 'list_price': 25.0, 'type': 'consu'})

    def _request(self, vendors, **vals):
        base = {'group_id': self.group.id, 'requester_phone': '919800099911',
                'raw_text': 'dc jack', 'product_id': self.product.id, 'state': 'sourcing',
                'sourcing_vendor_ids': [(6, 0, vendors.ids)]}
        base.update(vals)
        return self.env['sa.group.request'].create(base)

    def _assert_amount_only(self, body, currency):
        self.assertIn('*TYPE YOUR AMOUNT IN %s*' % currency, body)
        low = body.lower()
        for gone in ('days', 'reply *#', 'put its code', 'delivery time', 'change the number'):
            self.assertNotIn(gone, low)

    # ------------------------------------------------------------ currency
    def test_currency_from_the_contacts_country(self):
        Request = self.env['sa.group.request']
        self.assertEqual(Request._sa_partner_currency(self.uae_vendor, UAE), self.ae.currency_id.name)

    def test_currency_from_the_phone_when_no_country(self):
        Request = self.env['sa.group.request']
        inr = self.env.ref('base.in').currency_id.name
        self.assertEqual(Request._sa_partner_currency(self.india_vendor, INDIA), inr)

    def test_currency_falls_back_to_the_shop(self):
        Request = self.env['sa.group.request']
        nobody = self.env['res.partner'].create({'name': 'Zz No Phone'})
        company = self.env.company
        self.assertEqual(Request._sa_partner_currency(nobody, '', company), company.currency_id.name)

    # ------------------------------------------------------------ the messages
    def test_second_message_is_amount_only(self):
        req = self._request(self.uae_vendor)
        sent = []
        fake = SimpleNamespace(send_message=lambda phone, body: sent.append((phone, body)))
        req._sa_ask_vendor_price(fake, UAE)
        self.assertEqual(len(sent), 1)
        body = sent[0][1]
        self.assertIn('what is your best price for *3680-5050-acer-laptop-dc-jack*', body)
        self._assert_amount_only(body, self.ae.currency_id.name)
        self.assertNotIn('#', body)

    def test_first_message_is_amount_only_per_vendor_currency(self):
        Request = self.env.registry['sa.group.request']
        asked = {}

        def has_it(rec, session, phone, name, qty, ask):
            asked[''.join(c for c in phone if c.isdigit())] = ask
            return 'text'
        vendors = self.uae_vendor | self.india_vendor
        req = self._request(vendors, state='new', qty=2)
        with patch.object(Request, '_sa_ask_vendor_has_it', has_it), \
                patch.object(Request, '_sa_ask_vendor_groups', lambda self, *a, **kw: False), \
                patch.object(Request, '_sa_ask_via_wechat', lambda self, *a, **kw: False), \
                patch.object(Request, '_sa_ask_vendor_confirm', lambda self, *a, **kw: False):
            req._start_sourcing(vendors)
        self._assert_amount_only(asked[UAE], self.ae.currency_id.name)
        self._assert_amount_only(asked[INDIA], self.env.ref('base.in').currency_id.name)
        self.assertIn('Quantity: 2', asked[UAE])
        self.assertIn('like *450*', asked[UAE])

    # ------------------------------------------------------------ reading the reply
    def test_the_amount_is_read_however_it_is_typed(self):
        Quote = self.env['sa.vendor.quote']
        for text in ('500', 'AED 500', '500 aed', '₹500', 'INR 500'):
            self.assertEqual(Quote._parse_vendor_price(text), 500.0, text)

    # ------------------------------------------------------------ swipe-reply
    def _capture(self, text, quoted=''):
        message = {'extendedTextMessage': {'text': text}}
        if quoted:
            message['extendedTextMessage']['contextInfo'] = {'stanzaId': quoted}
        payload = {'data': {'key': {'id': 'IN-%s-%s' % (text, quoted), 'fromMe': False},
                            'message': message}}
        Request = self.env.registry['sa.group.request']
        captured, asked_which = [], []
        with patch.object(group_webhook, 'request', SimpleNamespace(env=self.env)), \
                patch.object(Request, '_sa_customer_outranks_vendor', lambda self, d: False), \
                patch.object(Request, '_sa_vendor_confirmed', lambda self, phone: True), \
                patch.object(self.env.registry['sa.vendor.quote'], '_capture_direct',
                             lambda self, message, request: captured.append(request.id) or False), \
                patch.object(WhatsAppWebhookGroups, '_sa_ask_which',
                             lambda self, session, phone, rows: asked_which.append(rows.ids)), \
                patch.object(WhatsAppWebhookGroups, '_sa_revive', staticmethod(lambda hit: None)):
            WhatsAppWebhookGroups()._sa_capture_vendor_reply(self.session, payload, UAE + '@s.whatsapp.net')
        return captured, asked_which

    def test_a_swipe_reply_names_the_price_check(self):
        a = self._request(self.uae_vendor)
        b = self._request(self.uae_vendor, raw_text='hinge')
        self.env['whatsapp.message'].create({
            'session_id': self.session.id, 'phone': UAE, 'direction': 'outgoing',
            'message': 'price check A', 'wa_message_id': 'OUT-A', 'sa_request_id': a.id})
        captured, asked_which = self._capture('200', quoted='OUT-A')
        self.assertEqual(captured, [a.id])
        self.assertFalse(asked_which)
        self.assertTrue(b.exists())

    def test_without_a_swipe_reply_two_open_checks_still_ask_which(self):
        self._request(self.uae_vendor)
        self._request(self.uae_vendor, raw_text='hinge')
        captured, asked_which = self._capture('200')
        self.assertFalse(captured)
        self.assertTrue(asked_which)

    def test_one_open_check_takes_a_bare_amount(self):
        a = self._request(self.uae_vendor)
        captured, asked_which = self._capture('200')
        self.assertEqual(captured, [a.id])
        self.assertFalse(asked_which)
