# -*- coding: utf-8 -*-
"""A card for every vendor asked; Choose on the counter (24 Nov 2026)."""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.sales_automation.tests.test_only_listed import ListedCase
from . import test_enquiry_prices


@tagged('post_install', '-at_install')
class TestVendorCards(ListedCase):
    _price = test_enquiry_prices.TestEnquiryPrices._price
    _row = test_enquiry_prices.TestEnquiryPrices._row

    def setUp(self):
        super().setUp()
        self.env['sa.ai.settings'].sudo().get_settings().write({
            'sourcing_window_minutes': 10, 'margin_percent': 20.0, 'price_approval_enabled': False, 'vendor_choice_mode': 'auto'})
        self.alpha, self.kumar = self.env['res.partner'].create([
            {'name': 'Zz Alpha', 'phone': '+971500003101'}, {'name': 'Zz Kumar', 'phone': '+971500003102'}])
        self.req = self._req('zzboard q77660', product_id=self.product.id, state='sourcing',
                             sourcing_deadline=fields.Datetime.now() + timedelta(minutes=9))
        self.more = self.env['res.partner'].create([{'name': 'Zz More %s' % n, 'phone': '+97150000320%s' % n} for n in range(3)])
        self.req.write({'sourcing_vendor_ids': [(6, 0, (self.alpha | self.kumar | self.more).ids)]})

    def test_five_cards_two_without_a_price(self):
        self._price(self.alpha, 20.0)
        self._price(self.kumar, 25.0)
        self._price(self.more[0], 40.0)
        self.req.sa_vendor_no_ids = [(4, self.more[2].id)]
        cards = self._row()['cards']
        self.assertEqual(len(cards), 5)
        self.assertEqual([(c['vendor'], c['price'], c['lowest']) for c in cards[:3]],
                         [('Zz Alpha', 20.0, True), ('Zz Kumar', 25.0, False), ('Zz More 0', 40.0, False)])
        self.assertTrue(all(c['replied_at'] for c in cards[:3]))
        self.assertEqual({(c['vendor'], c['state'], c['price'], c['replied_at']) for c in cards[3:]},
                         {('Zz More 1', 'waiting', None, None), ('Zz More 2', 'no', None, None)})
        self.assertFalse(any(c['can_choose'] for c in cards), 'not before all answered or the time is up')

    def test_one_price_is_not_lowest(self):
        self._price(self.alpha, 20.0)
        self.assertFalse(any(c['lowest'] for c in self._row()['cards']))

    def test_manual_waits_in_needs_you_and_is_chosen(self):
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        settings.write({'vendor_choice_mode': 'manual', 'price_approval_enabled': False})
        self._price(self.alpha, 20.0)
        high = self._price(self.kumar, 25.0)
        self.req.sourcing_deadline = fields.Datetime.now() - timedelta(seconds=5)
        self.req._close_sourcing()
        row = self._row('stalled')
        self.assertTrue(row['pick_vendor'])
        self.assertIsNone(self._row('tracking'), 'not in two tabs at once')
        self.assertEqual([c['can_choose'] for c in row['cards']], [True, True, False, False, False])
        self.assertTrue(self.env['sa.group.request'].sa_alarm_state()['stalled'])
        self.assertIn((self.req.id, 'vendor'), [(w['id'], w['kind']) for w in self.env['sa.notice']._waiting()])
        with self.assertRaises(UserError):
            self.env['sa.group.request'].sa_vendor_choose(self.req.id, 0)
        self.env['sa.group.request'].sa_vendor_choose(self.req.id, high.id)
        self.assertEqual((self.req.state, self.req.best_quote_id), ('quoted', high))
        chosen = [c['vendor'] for c in self._row()['cards'] if c['selected']]
        self.assertEqual(chosen, ['Zz Kumar'])
        self.assertIn('chosen by hand', self._row()['selected_why'])

    def test_the_chat_of_one_vendor_and_this_order_only(self):
        self._price(self.alpha, 20.0)
        order = self.env['sale.order'].create({'partner_id': self.alpha.id, 'order_line': [(0, 0, {
            'product_id': self.product.product_variant_id.id, 'product_uom_qty': 1, 'price_unit': 1.0})]})
        order.action_confirm()
        order.picking_ids.sa_ref_code = 'ZZQ7'
        self.req.order_id = order
        Message = self.env['whatsapp.message']
        base = {'session_id': self.session.id, 'direction': 'outgoing', 'status': 'sent'}
        Message.create([dict(base, phone=self.alpha.phone, message='Order #ZZQ7 please'), dict(base, phone=self.alpha.phone, message='Order #ZZQ8 another'),
                        dict(base, phone='+971511111111', message='Order #ZZQ7 a stranger')])
        detail = self.env['sa.group.request'].sa_enquiry_detail(self.req.id)
        texts = [m['text'] for m in detail['vendor_messages']]
        self.assertIn('Order #ZZQ7 please', texts)
        self.assertNotIn('Order #ZZQ8 another', texts)
        self.assertNotIn('Order #ZZQ7 a stranger', texts)
        card = [c for c in detail['cards'] if c['vendor'] == 'Zz Alpha'][0]
        self.assertEqual(card['phone'], '500003101')

    def test_detail_has_the_cards(self):
        self._price(self.alpha, 20.0)
        self.assertEqual(len(self.env['sa.group.request'].sa_enquiry_detail(self.req.id)['cards']), 5)
