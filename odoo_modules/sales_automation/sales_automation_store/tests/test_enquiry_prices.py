# -*- coding: utf-8 -*-
"""Every vendor's price on the Enquiries screen (23 Nov 2026)."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.sales_automation.tests.test_only_listed import ListedCase
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestEnquiryPrices(ListedCase):

    def setUp(self):
        super().setUp()
        self.env['sa.ai.settings'].sudo().get_settings().write({
            'sourcing_window_minutes': 10, 'margin_percent': 20.0, 'price_approval_enabled': True,
            'price_approval_tolerance_percent': 0.0})
        self.alpha, self.kumar = self.env['res.partner'].create([
            {'name': 'Zz Alpha', 'phone': '+971500003101'}, {'name': 'Zz Kumar', 'phone': '+971500003102'}])
        self.req = self._req('zzboard q77660', product_id=self.product.id, state='sourcing',
                             sourcing_vendor_ids=[(6, 0, (self.alpha | self.kumar).ids)],
                             sourcing_deadline=fields.Datetime.now() + timedelta(minutes=9))

    def _price(self, partner, price, **vals):
        return self.env['sa.vendor.quote'].create(dict({
            'request_id': self.req.id, 'partner_id': partner.id, 'price': price, 'matched_by': 'direct',
            'currency_id': self.req.currency_id.id or self.env.company.currency_id.id}, **vals))

    def _row(self, key='tracking'):
        rows = [r for r in self.env['sa.group.request'].sa_enquiry_queue()[key] if r['id'] == self.req.id]
        return rows[0] if rows else None

    def test_the_first_answer_is_there_at_once(self):
        self.assertEqual(self._row()['prices'], [])
        told = []
        with patch.object(self.env.registry['sa.group.request'], '_sa_enquiry_notify', lambda rec: told.append(rec.ids)):
            self._price(self.alpha, 20.0)
        self.assertIn(self.req.ids, told, 'the screen is told')
        row = self._row()
        self.assertEqual([(p['vendor'], p['price'], p['sell']) for p in row['prices']], [('Zz Alpha', 20.0, 24.0)])
        self.assertEqual((row['asked'], row['waiting_on']), (2, ['Zz Kumar']))
        self.assertEqual(self.req.state, 'sourcing', 'the customer is not told before the window ends')

    def test_both_and_which_is_lowest(self):
        with patch.object(self.env.registry['sa.group.request'], '_sa_close_if_all_answered', lambda rec: None):
            self._price(self.kumar, 22.0)
            self._price(self.alpha, 20.0)
        self.assertEqual([(p['vendor'], p['price'], p['lowest']) for p in self._row()['prices']],
                         [('Zz Alpha', 20.0, True), ('Zz Kumar', 22.0, False)])
        vendors = {v['name']: v for v in self.env['sa.group.request'].sa_enquiry_detail(self.req.id)['vendors']}
        self.assertEqual((vendors['Zz Alpha']['lowest'], vendors['Zz Kumar']['lowest']), (True, False))
        self.assertEqual((vendors['Zz Alpha']['price'], vendors['Zz Kumar']['price']), (20.0, 22.0))

    def test_the_same_price_twice_and_a_newer_one(self):
        with patch.object(self.env.registry['sa.group.request'], '_sa_close_if_all_answered', lambda rec: None):
            self._price(self.alpha, 25.0)
            self._price(self.alpha, 22.0)
            self._price(self.kumar, 22.0)
        self.assertEqual([(p['vendor'], p['price'], p['lowest']) for p in self._row()['prices']],
                         [('Zz Alpha', 22.0, True), ('Zz Kumar', 22.0, True)])

    def test_both_while_the_counter_chooses(self):
        """What was seen on 23 Nov: one price of two on the card to approve."""
        with patch.object(self.env.registry['sa.group.request'], '_sa_close_if_all_answered', lambda rec: None):
            self._price(self.alpha, 20.0)
            self._price(self.kumar, 22.0)
        self.req.write({'sa_price_choice_pending': True, 'sa_price_page': 1999.0, 'sa_price_vendor': 24.0, 'vendor_price': 20.0,
                        'sourcing_deadline': False})
        row = self._row('stalled')
        self.assertTrue(row['choice'])
        self.assertEqual([p['vendor'] for p in row['prices']], ['Zz Alpha', 'Zz Kumar'])
        self.assertIsNone(self._row('tracking'), 'not in two tabs at once')

    def test_a_corrected_price(self):
        quote = self._price(self.alpha, 20.0)
        told = []
        with patch.object(self.env.registry['sa.group.request'], '_sa_enquiry_notify', lambda rec: told.append(rec.ids)):
            quote.price = 18.0
        self.assertTrue(told)
        self.assertEqual(self._row()['prices'][0]['price'], 18.0)
