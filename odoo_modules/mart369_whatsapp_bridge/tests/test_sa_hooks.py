"""The senior's sockets, answered: wallet, points, deals, reviews, the menu.

His copy of the stack on this machine is older than those sockets, so the
tests call our answers directly; on DUBAI_TEST his flow calls them.
"""

import importlib.util
import os
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import Mart369BridgeCase

WA = '+919700770011'


@tagged('post_install', '-at_install')
class TestSaHooks(Mart369BridgeCase):

    # ---------------------------------------------------------------- helpers

    def _unpaid(self, phone=WA):
        return self._wa_order(phone=phone, paid=False)

    def _top_up(self, partner, amount):
        card = self.env['loyalty.card'].sudo()._mart369_wallet(partner)
        card._mart369_move(amount, 'add', 'Top up')
        return card

    def _chat(self, partner, phone):
        partner.with_context(mart369_phone_proven=True).write(
            {'phone': phone, 'mart369_phone_verified': True})
        return self.env['sa.group.request'].sudo().create({
            'group_id': self.wa_group.id, 'requester_phone': phone, 'raw_text': 'hi'})

    # ----------------------------------------------------------------- wallet

    def test_wallet_pays_first_and_only_once(self):
        order = self._unpaid()
        card = self._top_up(order.partner_id, 40.0)
        self.assertEqual(order._sa_wallet_apply(), 40.0)
        self.assertEqual(order._sa_wallet_apply(), 0.0, 'a reminder must not take it again')
        self.assertEqual(card._mart369_balance(), 0.0)
        self.assertEqual(order.mart369_wallet_used, 40.0)
        self.assertEqual(order._sa_paid_elsewhere(), 40.0, 'off the rider\'s cash')

    def test_wallet_never_takes_more_than_is_due(self):
        order = self._unpaid(phone='+919700770012')
        card = self._top_up(order.partner_id, 10000.0)
        taken = order._sa_wallet_apply()
        self.assertEqual(taken, order.amount_total)
        self.assertEqual(card._mart369_balance(), 10000.0 - order.amount_total)

    def test_a_cancel_gives_the_wallet_part_back(self):
        order = self._unpaid(phone='+919700770013')
        card = self._top_up(order.partner_id, 30.0)
        order._sa_wallet_apply()
        order._action_cancel()
        self.assertEqual(card._mart369_balance(), 30.0)

    def _post_invoice(self, order):
        invoice = order._create_invoices()
        invoice.action_post()
        return invoice

    def test_the_bill_shows_the_wallet_part_paid(self):
        order = self._unpaid(phone='+919700770014')
        self._top_up(order.partner_id, 40.0)
        order._sa_wallet_apply()
        self.assertEqual(order._sa_paid_elsewhere(), 40.0, 'before the bill: off the rider\'s cash')
        invoice = self._post_invoice(order)
        payment = order.mart369_wa_wallet_payment_id
        self.assertTrue(payment, 'booked when the bill was posted')
        self.assertEqual(payment.amount, 40.0)
        self.assertAlmostEqual(invoice.amount_residual, invoice.amount_total - 40.0, places=2)
        self.assertEqual(order._sa_paid_elsewhere(), 0.0,
                         'the bill carries it now - never taken off twice')
        self.assertFalse(order._mart369_wa_book_wallet(invoice), 'booked once')
        self.assertEqual(order._mart369_wa_paid(), 40.0, 'counted once, not twice')

    def test_no_wallet_no_booking(self):
        order = self._unpaid(phone='+919700770015')
        self._post_invoice(order)
        self.assertFalse(order.mart369_wa_wallet_payment_id)

    def test_website_orders_are_left_to_the_website(self):
        order = self._web_order()
        self.assertEqual(order._sa_wallet_apply(), 0.0)
        self.assertEqual(order._sa_paid_elsewhere(), 0.0)

    # ----------------------------------------------------------------- points

    def _points_on(self):
        if 'mart369_points_spent' not in self.env['sale.order']._fields:
            self.skipTest('mart369_loyalty is not installed')
        self.env['pos.loyalty.card.settings'].sudo().get_settings().write({'enable_loyalty': True})
        Rule = self.env['pos.loyalty.rule'].sudo()
        rule = Rule.get_active_rule() or Rule.create({'name': 'Test rule'})
        rule.write({'is_active': True, 'spend_amount': 100.0, 'points_earned': 10.0,
                    'min_redeem_points': 100.0, 'points_per_currency': 10.0,
                    'max_redeem_percent': 100.0})
        self.env['mart369.config'].sudo()._get().write(
            {'loyalty_enabled': True, 'loyalty_redeem': True})

    def _points(self, partner, points):
        Card = self.env['pos.loyalty.card'].sudo()
        Card.search([('phone', '=', partner.phone)]).filtered(
            lambda c: c.partner_id != partner)._hard_unlink()
        card = Card._mart369_card_for(partner, create=True)
        card._mart369_write(points, 'earned', 'At the store')
        return card

    def test_points_are_offered_and_taken_once(self):
        self._points_on()
        order = self._unpaid(phone='+919700770021')
        card = self._points(order.partner_id, 500)
        total = order.amount_total
        offer = order._sa_points_offer()
        self.assertTrue(offer)
        self.assertEqual(offer['value'], min(50.0, total))
        given = order._sa_points_apply()
        self.assertEqual(given, offer['value'])
        self.assertAlmostEqual(order.amount_total, total - given, places=2)
        self.assertEqual(len(order.order_line.filtered(lambda l: l.mart369_kind == 'points')), 1)
        self.assertEqual(order._sa_points_apply(), 0.0, 'USE POINTS twice takes them once')
        self.assertIsNone(order._sa_points_offer())
        self.assertLess(card.total_points, 500)

    def test_no_points_no_offer(self):
        self._points_on()
        order = self._unpaid(phone='+919700770022')
        self.assertIsNone(order._sa_points_offer())
        self.assertEqual(order._sa_points_apply(), 0.0)

    def test_a_cancel_gives_the_points_back(self):
        self._points_on()
        order = self._unpaid(phone='+919700770023')
        card = self._points(order.partner_id, 500)
        order._sa_points_apply()
        order._action_cancel()
        self.assertEqual(card.total_points, 500)

    # ------------------------------------------------------------ deal floor

    def test_a_live_deal_is_the_bargain_floor(self):
        template = self.quick_product
        request = self.env['sa.group.request'].sudo().create({
            'group_id': self.wa_group.id, 'requester_phone': WA, 'raw_text': template.name,
            'product_id': template.id})
        self.assertIsNone(request._sa_live_deal_price())
        deal = self.env['mart369.deal'].sudo().create({
            'name': 'Test 10 off', 'kind': 'percent', 'value': 10,
            'product_ids': [(6, 0, template.ids)]})
        self.assertAlmostEqual(request._sa_live_deal_price(), template.list_price * 0.9, places=2)
        deal.ends_on = fields.Datetime.now() - timedelta(days=1)
        self.assertIsNone(request._sa_live_deal_price())

    # ---------------------------------------------------------------- review

    def test_review_link_only_after_delivery(self):
        order = self._web_order()
        self.assertEqual(order._sa_review_link(), '')
        order.sudo().write({'mart369_state': 'delivered'})
        link = order._sa_review_link()
        self.assertIn(order.mart369_ref, link)

    # ------------------------------------------------------------------ menu

    def test_the_menu_lists_website_orders(self):
        order = self._web_order()
        request = self._chat(self.partner, '+919700770031')
        rows = request._sa_customer_orders()
        row = next(r for r in rows if r['key'] == 'web:%d' % order.id)
        self.assertEqual(row['ref'], order.mart369_ref)
        self.assertTrue(row['can_cancel'])
        self.assertIn(order.mart369_ref, request._sa_order_card(row['key']))
        self.assertIn(order.mart369_ref, request._sa_track_text(row['key']))

    def test_cancel_from_the_menu(self):
        order = self._web_order()
        request = self._chat(self.partner, '+919700770032')
        text = request._sa_cancel_order('web:%d' % order.id)
        self.assertIn('cancelled', text)
        self.assertEqual(order.mart369_state, 'cancelled')

    def test_someone_elses_order_is_not_shown(self):
        order = self._web_order()
        stranger = self.env['res.partner'].sudo().create({'name': 'Stranger'})
        request = self._chat(stranger, '+919700770033')
        self.assertIn('no longer available', request._sa_order_card('web:%d' % order.id))
        self.assertFalse([r for r in request._sa_customer_orders()
                          if r['key'] == 'web:%d' % order.id])

    def test_talk_to_a_person_opens_a_ticket(self):
        request = self._chat(self.partner, '+919700770034')
        text = request._sa_hand_to_person('my parcel is late')
        ticket = self.env['mart369.ticket'].sudo().search(
            [('partner_id', '=', self.partner.id)], limit=1)
        self.assertTrue(ticket)
        self.assertIn(ticket.name, text)

    def test_wallet_and_points_text(self):
        request = self._chat(self.partner, '+919700770035')
        self._top_up(self.partner, 25.0)
        self.assertIn('25.00', request._sa_wallet_text())

    def test_a_product_name_is_not_a_question(self):
        request = self._chat(self.partner, '+919700770036')
        self.assertIsNone(request._sa_help_answer('Redmi Note 13 back cover'))

    # ----------------------------------------------------------------- label

    def test_a_copy_is_named_the_customers_way(self):
        Partner = self.env['res.partner']
        work = Partner.sudo().create({'name': 'X', 'mart369_label': 'Work'})
        old = Partner.sudo().create({'name': 'Y', 'mart369_label': 'WhatsApp'})
        self.assertEqual(Partner._mart369_label_for(work), 'Work')
        self.assertEqual(Partner._mart369_label_for(old), 'Home')

    def test_old_whatsapp_copies_are_renamed(self):
        address = self.partner._mart369_add_address({
            'name': 'x', 'street': '9 Copy Street', 'zip': '624009', 'mart369_label': 'WhatsApp'})
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'migrations', '19.0.1.3.4', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('bridge_1_3_4', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, '19.0.1.3.3')
        address.invalidate_recordset()
        self.assertEqual(address.mart369_label, 'Home')
