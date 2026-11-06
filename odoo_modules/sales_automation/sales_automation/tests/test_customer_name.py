# -*- coding: utf-8 -*-
"""Names beside the mention, the first-"hi" name question, and the taps that
replaced typing (quantity, the order's name, points). Nothing is sent: the
two base senders are replaced, so every message is only recorded."""
import json
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.sales_automation.models.sa_group_request import SaGroupRequest

PHONE = '919800012345'


@tagged('post_install', '-at_install')
class TestCustomerName(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        session = cls.env['whatsapp.session'].create({
            'name': 'SA name test', 'gateway_api_key': 'x', 'instance_name': 'sa-name-test'})
        cls.group = cls.env['sa.sales.group'].create({
            'name': 'SA name test group', 'group_jid': '120363000000000001@g.us',
            'session_id': session.id, 'group_type': 'customer'})
        cls.Req = cls.env['sa.group.request']
        cls.Partner = cls.env['res.partner']
        # other contacts on the test number must not take part
        cls.Partner.search([('phone', 'ilike', PHONE[-9:])]).write({'phone': False})

    def setUp(self):
        super().setUp()
        self.said, self.asked = [], []
        p1 = patch.object(SaGroupRequest, '_say', autospec=True,
                          side_effect=lambda rec, body, addressed=True: self.said.append(body) or True)
        p2 = patch.object(SaGroupRequest, '_ask', autospec=True,
                          side_effect=lambda rec, body, buttons: self.asked.append(
                              (body, [b['title'] for b in buttons])) or 'poll')
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def _req(self, **vals):
        base = {'group_id': self.group.id, 'requester_phone': PHONE,
                'requester_name': 'sri bala', 'raw_text': 'hi', 'state': 'dropped'}
        base.update(vals)
        return self.Req.create(base)

    def _menu_labels(self, req):
        return list(json.loads(req.sa_menu_json or '{}'))

    def _tap(self, req, label):
        return req._sa_answer_poll(label)

    # ------------------------------------------------------------ names
    def test_real_name_rules(self):
        P = self.Partner
        self.assertEqual(P.new({'name': 'WhatsApp Customer (+91 98)'})._sa_real_name(), '')
        self.assertEqual(P.new({'name': '+91 98000 12345'})._sa_real_name(), '')
        self.assertEqual(P.new({'name': ''})._sa_real_name(), '')
        self.assertEqual(P.new({'name': 'Sri Bala'})._sa_real_name(), 'Sri Bala')

    def test_mention_carries_the_known_name(self):
        self.Partner.create({'name': 'Sri Bala', 'phone': '+' + PHONE, 'customer_rank': 1})
        line = self._req()._sa_addressed('Body')
        self.assertTrue(line.startswith('@%s - Sri Bala · Ref ' % PHONE), line)

    def test_mention_without_a_name_is_unchanged(self):
        line = self._req(requester_name='')._sa_addressed('Body')
        self.assertTrue(line.startswith('@%s · Ref ' % PHONE), line)

    def test_placeholder_name_is_not_shown(self):
        self.Partner.create({'name': 'WhatsApp Customer (+%s)' % PHONE, 'phone': '+' + PHONE,
                             'customer_rank': 1})
        line = self._req()._sa_addressed('Body')
        self.assertTrue(line.startswith('@%s · Ref ' % PHONE), line)

    def test_website_account_name_wins_over_a_placeholder(self):
        self.Partner.create({'name': 'WhatsApp Customer (+%s)' % PHONE, 'phone': '+' + PHONE,
                             'customer_rank': 1})
        web = self.Partner.create({'name': 'Sri Bala', 'phone': '+' + PHONE})
        self.env['res.users'].create({'login': 'sa.name.web@test', 'partner_id': web.id,
                                      'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        if web not in self.Partner._sa_phone_matches(PHONE):
            # another module (369 Mart's bridge) counts only numbers proven by
            # a sign-in code; a bare test contact is not one
            self.skipTest("phone lookup narrowed by another module")
        self.assertEqual(self._req()._sa_known_name(), 'Sri Bala')

    # ------------------------------------------------------------ first hi
    def test_first_hi_asks_the_name_with_the_whatsapp_name(self):
        req = self._req()
        req._sa_menu_show('main')
        labels = self._menu_labels(req)
        self.assertIn('✅ Sri Bala', labels)
        self.assertEqual(req.sa_name_pending, 'ask')
        self.assertTrue(self.asked and 'What should we call you' in self.asked[-1][0])

    def test_numeric_whatsapp_name_is_not_offered(self):
        req = self._req(requester_name='919800012345')
        req._sa_menu_show('main')
        self.assertFalse([l for l in self._menu_labels(req) if l.startswith('✅')])

    def test_tap_saves_the_name_then_the_menu(self):
        req = self._req()
        req._sa_menu_show('main')
        self._tap(req, '✅ Sri Bala')
        partner = req._sa_ss_customer()
        self.assertEqual(partner.name, 'Sri Bala')
        self.assertFalse(req.sa_name_pending)
        self.assertTrue(any('Thanks Sri' in s for s in self.said))
        self.assertTrue('What would you like to do' in self.asked[-1][0])

    def test_typed_name_after_type_a_different_one(self):
        req = self._req()
        req._sa_menu_show('main')
        self._tap(req, req.NAME_TYPE)
        self.assertEqual(req.sa_name_pending, 'typing')
        msg = self.env['whatsapp.message'].new({'participant_phone': PHONE})
        self.Req._sa_typed_answer_hook(self.group, msg, 'karthik raja')
        self.assertEqual(req._sa_ss_customer().name, 'Karthik Raja')

    def test_skip_is_remembered(self):
        req = self._req()
        req._sa_menu_show('main')
        self._tap(req, req.NAME_SKIP)
        self.asked.clear()
        self._req()._sa_menu_show('main')
        self.assertTrue('What would you like to do' in self.asked[-1][0])

    def test_a_product_typed_instead_is_not_a_name(self):
        self.env['product.template'].create({'name': 'Wireless Mouse', 'sale_ok': True})
        req = self._req()
        req._sa_menu_show('main')
        msg = self.env['whatsapp.message'].new({'participant_phone': PHONE})
        self.Req._sa_typed_answer_hook(self.group, msg, 'mouse')
        self.assertNotEqual(req._sa_ss_customer().name, 'Mouse')
        self.assertFalse(req.sa_name_pending)

    def test_a_real_name_is_never_overwritten(self):
        p = self.Partner.create({'name': 'Sri Bala', 'phone': '+' + PHONE, 'customer_rank': 1})
        req = self._req()
        req._sa_name_save('Someone Else')
        self.assertEqual(p.name, 'Sri Bala')

    # ------------------------------------------------------------ taps
    def test_quantity_is_a_poll(self):
        req = self._req(state='quoted', quoted_price=100.0, agreed_price=100.0)
        req._ask_quantity()
        body, titles = self.asked[-1]
        self.assertEqual(titles[:6], ['1', '2', '3', '4', '5', '6'])
        self.assertEqual(titles[-1], req.QTY_OTHER)
        self.assertEqual(req.state, 'awaiting_qty')

    def test_tapped_quantity_moves_to_the_summary(self):
        req = self._req(state='quoted', quoted_price=100.0, agreed_price=100.0)
        req._ask_quantity()
        req._sa_answer_poll('3')
        self.assertEqual(req.qty, 3)
        self.assertIn('Order summary', self.asked[-1][0])

    def test_other_amount_then_typed(self):
        req = self._req(state='quoted', quoted_price=100.0, agreed_price=100.0)
        req._ask_quantity()
        req._sa_answer_poll(req.QTY_OTHER)
        self.assertTrue(any('Type the number' in s for s in self.said))
        self.assertEqual(req.state, 'awaiting_qty')
        req._on_deal_reply('15')
        self.assertEqual(req.qty, 15)

    def test_change_quantity_is_a_poll(self):
        req = self._req(state='awaiting_order_confirm', quoted_price=100.0, agreed_price=100.0, qty=2)
        req.sa_change_pending = True
        req._sa_change_answer(req.CHANGE_QTY)
        self.assertEqual(self.asked[-1][1][-1], req.QTY_OTHER)
        self.assertEqual(req.qty, 0)

    def test_address_line_shows_the_receiver(self):
        p = self.Partner.create({'name': 'Sri Bala', 'phone': '+' + PHONE, 'street': '12 Green Park',
                                 'customer_rank': 1})
        self.assertIn('Sri Bala, ', p._sa_addr_title())
