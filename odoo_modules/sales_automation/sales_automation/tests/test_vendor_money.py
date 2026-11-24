# -*- coding: utf-8 -*-
"""A supplier's price in their own currency (23 Nov 2026): converted with a
current rate, else held for the shop. INR 100 is never OMR 100 (S00018)."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

INDIA = '919812345601'


@tagged('post_install', '-at_install')
class TestVendorMoney(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        for p in (patch.object(env.registry['sa.outbox.guard'], 'claim', lambda self, key, seconds=60: True),
                  patch.object(env.registry['sa.group.request'], '_say', lambda self, body, addressed=True: True)):
            p.start()
            cls.addClassCleanup(p.stop)
        cls.session = env['whatsapp.session'].create({
            'name': 'SA money', 'gateway_api_key': 'x', 'instance_name': 'sa-money'})
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz Money', 'group_jid': '120363000000000077@g.us',
            'session_id': cls.session.id, 'group_type': 'customer'})
        env['sa.ai.settings'].get_settings().vendor_money = 'country'
        cls.company = env.company
        Currency = env['res.currency'].with_context(active_test=False)
        cls.own = cls.company.currency_id
        cls.inr, cls.omr, cls.aed = (Currency.search([('name', '=', n)], limit=1) for n in ('INR', 'OMR', 'AED'))
        (cls.inr | cls.omr | cls.aed).write({'active': True})
        env['res.currency.rate'].search([('currency_id', 'in', (cls.inr | cls.omr | cls.aed).ids)]).unlink()
        cls.vendor = env['res.partner'].create({'name': 'Zz Kochi', 'phone': '+' + INDIA, 'country_id': env.ref('base.in').id})
        cls.product = env['product.template'].create({'name': 'Zz money jack', 'type': 'consu'})

    def _rate(self, currency, rate, days=0):
        return self.env['res.currency.rate'].create({
            'currency_id': currency.id, 'company_id': self.company.id, 'rate': rate,
            'name': fields.Date.today() - timedelta(days=days)})

    def _request(self, currency, **vals):
        return self.env['sa.group.request'].create(dict({
            'group_id': self.group.id, 'requester_phone': '919800099901', 'raw_text': 'jack',
            'product_id': self.product.id, 'state': 'sourcing', 'currency_id': currency.id,
            'sourcing_vendor_ids': [(6, 0, self.vendor.ids)]}, **vals))

    def _answer(self, req, text):
        message = self.env['whatsapp.message'].create({
            'session_id': self.session.id, 'phone': INDIA, 'message': text, 'direction': 'incoming',
            'participant_phone': INDIA, 'wa_message_id': 'MONEY-%s-%s' % (req.id, text)})
        with patch.object(self.env.registry['sa.group.request'], '_company_for', lambda rec, group: self.company):
            return self.env['sa.vendor.quote']._capture_direct(message, req)

    def test_s00018_a_hundred_rupees_is_never_a_hundred_rials(self):
        req = self._request(self.omr)
        self.assertFalse(self._answer(req, '100'))
        self.assertFalse(req.quote_ids)
        held = req._sa_held_of(self.vendor.id)
        self.assertEqual((held['amount'], held['code']), (100.0, 'INR'))
        self.assertEqual(req._sa_held_lines(), ['Zz Kochi: INR 100.00'])
        self.assertNotIn('Zz Kochi', str(req._sa_vendor_lists()), 'not under "no price yet"')
        self.assertIn('OMR', req._sa_held_why())

    def test_held_goes_to_the_desk_when_the_window_closes(self):
        req = self._request(self.omr)
        self._answer(req, '100')
        with patch.object(self.env.registry['sa.group.request'], '_sa_tell_shop_no_price', lambda rec, name: True):
            req._close_sourcing()
        self.assertTrue(req.sa_price_stalled)
        self.assertEqual(req.state, 'sourcing')
        self.assertFalse(req.quoted_price)

    def test_converted_with_current_rates(self):
        self._rate(self.inr, 80.0)
        self._rate(self.omr, 0.4)
        req = self._request(self.omr)
        quote = self._answer(req, '200')
        self.assertAlmostEqual(quote.price, 1.0, places=2)
        self.assertEqual((quote.sa_typed_amount, quote.sa_typed_currency, quote.currency_id), (200.0, 'INR', self.omr))
        self.assertEqual(quote._sa_typed_text(), 'INR 200.00')
        self.assertFalse(req._sa_held())

    def test_one_missing_rate_is_enough_to_hold(self):
        # the enquiry's money has no rate: not the company's own, which needs none
        other = self.aed if self.own == self.omr else self.omr
        self._rate(self.inr, 80.0)
        self.assertFalse(self._answer(self._request(other), '200'))

    def test_a_week_old_is_used_older_is_not(self):
        self._rate(self.inr, 80.0, days=7)
        self.assertTrue(self._answer(self._request(self.own), '200'))
        self.env['res.currency.rate'].search([('currency_id', '=', self.inr.id)]).name = \
            fields.Date.today() - timedelta(days=8)
        self.assertFalse(self._answer(self._request(self.own), '200'))

    def test_a_currency_switched_off_is_held(self):
        self._rate(self.inr, 80.0)
        self.inr.active = False
        self.assertFalse(self._answer(self._request(self.own), '200'))

    def test_the_currency_they_wrote_wins(self):
        quote = self._answer(self._request(self.omr), 'OMR 3')
        self.assertEqual((quote.price, quote.sa_typed_currency), (3.0, 'OMR'))
        self._rate(self.aed, 3.6725)
        quote = self._answer(self._request(self.own), '36.725 aed')
        self.assertAlmostEqual(quote.price, 10.0, places=2)

    def test_same_currency_needs_no_rate(self):
        quote = self._answer(self._request(self.inr), '450')
        self.assertEqual((quote.price, quote.currency_id), (450.0, self.inr))

    def test_a_correction_replaces_what_was_held(self):
        req = self._request(self.omr)
        self._answer(req, '100')
        self.assertTrue(self._answer(req, 'OMR 2'))
        self.assertFalse(req._sa_held())

    def test_a_held_answer_is_not_taken_twice_as_thanks(self):
        req = self._request(self.omr)
        self._answer(req, '100')
        self.assertFalse(self._answer(req, 'ok thanks'))
        self.assertEqual(len(req._sa_held()), 1)

    def test_signs(self):
        read = self.env['sa.vendor.quote']._sa_currency_in
        for text, own, code in (('100', 'INR', 'INR'), ('Rs.100', 'PKR', 'PKR'), ('rs 100', 'AED', 'INR'),
                                ('$20', 'SGD', 'SGD'), ('45\u5143', 'CNY', 'CNY'), ('100/- rs', 'OMR', 'INR'),
                                ('450 dhs', 'INR', 'AED'), ('price 100 all ok', 'INR', 'INR'),
                                ('100 pcs at aed 20', 'INR', 'AED')):
            self.assertEqual(read(text, own), code, text)

    def test_a_late_price_re_arms_a_stalled_enquiry(self):
        req = self._request(self.inr, sa_price_stalled=True)
        req._sa_vendor_price_in(self._answer(req, '450'))
        self.assertTrue(req.sourcing_deadline)
