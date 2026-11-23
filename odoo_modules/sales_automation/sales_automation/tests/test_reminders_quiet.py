# -*- coding: utf-8 -*-
"""Sign / pay reminders only after a long silence, one at a time, never from
the outbox; SIGN only after the details, PAY only after SIGN (23 Nov 2026).
Nothing is sent: captured."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

GROUP = '120363000000000033@g.us'
PHONE = '919800066677'
SIGN = 'https://shop.test/my/orders/7?access_token=abc'


@tagged('post_install', '-at_install')
class TestRemindersQuiet(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.said, cls.asked, cls.fail = [], [], []
        Request, Session = env.registry['sa.group.request'], env.registry['whatsapp.session']

        def say(self, body, addressed=True):
            if cls.fail:
                # what the gateway does when it cannot send: a waiting row
                self.env['whatsapp.message'].sudo().create({
                    'session_id': self.group_id.session_id.id, 'phone': GROUP, 'message': body,
                    'direction': 'outgoing', 'status': 'pending'})
                return False
            cls.said.append((self.id, body))
            return True
        for p in (patch.object(Request, '_say', say),
                  patch.object(Request, '_ask', lambda self, body, buttons: cls.asked.append(
                      (body, [b['title'] for b in buttons])) or True),
                  patch.object(Request, '_sa_portal_link', lambda self, order: SIGN),
                  patch.object(Request, '_sa_pay_link_any_state', lambda self, order: 'https://shop.test/pay'),
                  patch.object(Session, '_refresh_state', lambda self, force=False: None)):
            p.start()
            cls.addClassCleanup(p.stop)
        env['sa.group.request'].search([('order_id', '!=', False)]).write({'sa_pay_remind_count': 99})
        env['sa.ai.settings'].get_settings().write({'pay_remind_minutes': 60, 'pay_remind_max': 2})
        cls.session = env['whatsapp.session'].sudo().create({
            'name': 'SA quiet', 'gateway_api_key': 'x', 'instance_name': 'sa-quiet'})
        cls.session.status = 'connected'
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz Quiet', 'group_jid': GROUP, 'session_id': cls.session.id, 'group_type': 'customer'})
        cls.product = env['product.product'].create({'name': 'Zz Quiet Mouse', 'list_price': 5.0})
        cls.customer = env['res.partner'].create({'name': 'Sri', 'phone': '+' + PHONE})

    def setUp(self):
        super().setUp()
        for box in (self.said, self.asked, self.fail):
            box.clear()

    def _order(self, **vals):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id, 'require_signature': True, 'require_payment': False,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 1})]})
        base = {'group_id': self.group.id, 'requester_phone': PHONE, 'requester_name': 'Sri',
                'raw_text': 'mouse', 'state': 'order_created', 'order_id': order.id,
                'sa_sign_link_sent_on': fields.Datetime.now() - timedelta(minutes=90)}
        base.update(vals)
        return self.env['sa.group.request'].create(base)

    def _incoming(self, minutes):
        msg = self.env['whatsapp.message'].sudo().create({
            'session_id': self.session.id, 'phone': GROUP, 'group_jid': GROUP, 'direction': 'incoming',
            'message': 'laptop', 'participant_phone': PHONE})
        self.env.flush_all()
        self.env.cr.execute("UPDATE whatsapp_message SET create_date = %s WHERE id = %s",
                            [fields.Datetime.now() - timedelta(minutes=minutes), msg.id])
        self.env.invalidate_all()

    def _run(self):
        self.env['sa.group.request']._cron_pay_remind()

    # ------------------------------------------------------- reminders
    def test_nothing_while_they_are_chatting(self):
        req = self._order()
        self._incoming(5)
        self._run()
        self.assertFalse(self.said)
        self.assertEqual(req.sa_pay_remind_count, 0)

    def test_one_after_a_long_silence(self):
        req = self._order()
        self._incoming(61)
        self._run()
        self.assertEqual(len(self.said), 1)
        self.assertIn('Reminder 1 of 2', self.said[0][1])
        self.assertIn('signature', self.said[0][1])
        self._run()
        self.assertEqual(len(self.said), 1, 'the second only an hour later')
        self.assertEqual(req.sa_pay_remind_count, 1)

    def test_two_waiting_orders_are_reminded_one_at_a_time(self):
        first, second = self._order(), self._order()
        self._run()
        self.assertEqual([i for i, _b in self.said], [first.id])
        self._run()
        self.assertEqual(len(self.said), 1)
        first.sa_pay_reminded_on = fields.Datetime.now() - timedelta(minutes=61)
        first.sa_pay_remind_count = 2
        self._run()
        self.assertEqual([i for i, _b in self.said], [first.id, second.id])

    def test_not_connected_waits_for_a_later_run(self):
        req = self._order()
        self.session.status = 'disconnected'
        self._run()
        self.assertFalse(self.said)
        self.session.status = 'connected'
        self._run()
        self.assertEqual(len(self.said), 1)
        self.assertEqual(req.sa_pay_remind_count, 1)

    def test_a_refused_send_leaves_nothing_in_the_outbox(self):
        req = self._order()
        self.fail.append(True)
        self._run()
        self.assertEqual(req.sa_pay_remind_count, 0)
        self.assertFalse(self.env['whatsapp.message'].sudo().search([
            ('session_id', '=', self.session.id), ('status', '=', 'pending')]))
        self.fail.clear()
        self._run()
        self.assertEqual(req.sa_pay_remind_count, 1)

    def test_unsigned_is_asked_to_sign_even_with_a_pay_link_out(self):
        self._order(sa_pay_link_sent_on=fields.Datetime.now() - timedelta(minutes=90))
        self._run()
        self.assertIn('signature', self.said[0][1])
        self.assertNotIn('payment', self.said[0][1])

    def test_signed_and_unpaid_is_asked_to_pay(self):
        req = self._order(sa_pay_link_sent_on=fields.Datetime.now() - timedelta(minutes=90))
        req.order_id.require_signature = False
        self._run()
        self.assertIn('waiting for payment', self.said[0][1])

    def test_no_reminder_at_the_details(self):
        self._order(sa_details_pending=True)
        self._run()
        self.assertFalse(self.said)

    # ------------------------------------------------ details > sign > pay
    def test_no_sign_and_no_pay_before_the_details(self):
        req = self._order(sa_details_pending=True, profile_step='confirm', sa_note_step='done',
                          sa_book_done=True, sa_sign_link_sent_on=False)
        row = [r for r in req._sa_customer_orders() if r['key'] == 'req:%d' % req.id][0]
        self.assertFalse(row['can_pay'])
        self.assertFalse(row['needs_sign'])
        self.assertIn('details', row['status'].lower())
        self.assertFalse([k for k, r in req._sa_menu_items() if r == req])
        for kind in ('pay', 'sign'):
            self.said.clear()
            self.asked.clear()
            req._sa_menu_tapped({'kind': kind, 'target': req.id, 'parent': 'orders'})
            self.assertFalse([b for _i, b in self.said if 'http' in b], 'no link yet')
            self.assertTrue([a for a in self.asked if 'check your details' in a[0]], self.asked)

    def test_an_old_pay_tap_on_an_unsigned_order_is_the_sign_link(self):
        req = self._order()
        req._sa_menu_tapped({'kind': 'pay', 'target': req.id, 'parent': 'orders'})
        self.assertIn('sign here', self.said[0][1])

    def test_an_order_without_a_sign_step_still_pays(self):
        req = self._order(sa_sign_link_sent_on=False)
        req.order_id.require_signature = False
        row = [r for r in req._sa_customer_orders() if r['key'] == 'req:%d' % req.id][0]
        self.assertTrue(row['can_pay'])
