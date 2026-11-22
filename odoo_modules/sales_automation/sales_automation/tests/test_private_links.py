# -*- coding: utf-8 -*-
"""Personal links and PDFs go to the customer's private chat (21 Nov 2026,
models/sa_private_links.py): the group gets a short note instead. Hidden
number, refused message or the setting off: the group, as before.

Nothing is sent: the gateway is mocked.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

GROUP = '120363000000000066@g.us'
PHONE = '919800033344'
PAY = 'https://shop.test/scoped_app/wa-link?db=x&to=%2Fwa%2Fpay%2F7%3Fmethod%3Dcard'
SIGN = 'https://shop.test/scoped_app/wa-link?db=x&to=%2Fmy%2Forders%2F7%3Faccess_token%3Dabc'
TRACK = 'https://shop.test/scoped_app/wa-link?db=x&to=%2Fwa%2Ftrack%2F9%3Ftoken%3Dabc'


@tagged('post_install', '-at_install')
class TestPrivateLinks(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.sent, cls.docs, cls.polls = [], [], []
        cls.refuse = set()       # numbers whose messages "fail"
        Session = env.registry['whatsapp.session']

        def send_message(self, phone, message):
            if phone in cls.refuse:
                return False
            cls.sent.append((phone, message))
            return True

        def mentioning(self, phone, message, mention=''):
            cls.sent.append((phone, message))
            return True

        def send_document(self, phone, data, filename, caption='', **kw):
            if phone in cls.refuse:
                return False
            cls.docs.append((phone, filename, caption))
            return True

        def payload(self, action, data, *a, **kw):
            cls.polls.append((action, data))
            return True

        for patcher in (
                patch.object(Session, 'send_message', send_message),
                patch.object(Session, 'sa_send_text_mentioning', mentioning),
                patch.object(Session, 'send_document', send_document),
                patch.object(Session, '_send_payload', payload),
                patch.object(Session, '_gateway_call', lambda self, *a, **kw: {}),
                patch.object(env.registry['sa.outbox.guard'], 'claim',
                             lambda self, key, seconds=60: True)):
            patcher.start()
            cls.addClassCleanup(patcher.stop)

        session = env['whatsapp.session'].sudo().create({
            'name': 'SA private links test', 'gateway_api_key': 'x',
            'instance_name': 'sa-private-links-test'})
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz Private Links', 'group_jid': GROUP,
            'session_id': session.id, 'group_type': 'customer'})
        cls.product = env['product.template'].create({
            'name': 'Zz Private Links Laptop', 'list_price': 600.0, 'type': 'consu'})
        cls.customer = env['res.partner'].create({'name': 'Sri', 'phone': '+' + PHONE})
        env['ir.config_parameter'].sudo().set_param('sa.shop_url', 'https://shop.test/shop')

    def setUp(self):
        super().setUp()
        self.sent.clear()
        self.docs.clear()
        self.polls.clear()
        self.refuse.clear()
        # Customer Links as shipped: every personal link private, the shop link in the group
        self.settings = self.env['sa.ai.settings'].get_settings()
        self.settings.write(dict({'link_%s' % k: 'private' for k in (
            'confirm', 'address', 'sign', 'pay', 'track', 'map', 'review', 'web', 'docs')},
            link_shop='group', link_group_note=True, link_reply_hours=6))
        self.order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {'product_id': self.product.product_variant_id.id,
                                   'product_uom_qty': 1})],
        })
        self.request = self.env['sa.group.request'].create({
            'group_id': self.group.id, 'requester_phone': PHONE, 'requester_name': 'Sri',
            'raw_text': 'laptop', 'product_id': self.product.id, 'ref_code': 'P7',
            'state': 'order_created', 'order_id': self.order.id})

    def _to(self, who):
        return [t for to, t in self.sent if to == who]

    # ------------------------------------------------------------------ texts
    def test_a_pay_link_goes_privately_and_the_group_gets_a_note(self):
        self.request._say("Total 600\n\n\U0001F4B3 Pay here: %s" % PAY)
        private = self._to(PHONE)
        self.assertEqual(len(private), 1)
        self.assertIn(PAY, private[0])
        self.assertIn('answer in the group', private[0])
        group = self._to(GROUP)
        self.assertTrue(any('payment link' in t and 'private chat' in t for t in group), group)
        self.assertFalse(any('http' in t for t in group), 'no link in the group')
        self.assertFalse(any('600' in t for t in group), 'nor the amount')

    def test_sign_and_tracking_get_their_own_notes(self):
        self.request._say("✍️ Sign here: %s" % SIGN)
        self.request._say("Follow it live: %s" % TRACK)
        group = '\n'.join(self._to(GROUP))
        self.assertIn('link to sign', group)
        self.assertIn('tracking link', group)
        self.assertEqual(len(self._to(PHONE)), 2)

    def test_the_points_poll_stays_in_the_group(self):
        body = "\U0001F4B3 Pay here: %s\n\nTap %s to use them." % (PAY, self.request.POINTS_MARK)
        self.request._say(body)
        self.assertEqual(len(self._to(PHONE)), 1)
        self.assertTrue(self.polls, 'the USE POINTS poll still goes out')
        self.assertFalse([d for a, d in self.polls if PHONE in str(d.get('number', ''))],
                         'not to the private chat')

    def test_a_hidden_number_keeps_the_link_in_the_group(self):
        self.request.write({'requester_is_lid': True, 'requester_lid': '55@lid'})
        self.request._say("Pay here: %s" % PAY)
        self.assertFalse(self._to(PHONE))
        self.assertTrue(any(PAY in t for t in self._to(GROUP)))

    def test_payment_set_to_group_stays_in_the_group_marked(self):
        self.settings.link_pay = 'group'
        self.request._say("Pay here: %s" % PAY)
        self.assertFalse(self._to(PHONE))
        group = [t for t in self._to(GROUP) if PAY in t]
        self.assertTrue(group)
        self.assertIn('Only for Sri', group[0])

    def test_a_refused_private_message_falls_back_to_the_group(self):
        self.refuse.add(PHONE)
        self.request._say("Pay here: %s" % PAY)
        self.assertTrue(any(PAY in t for t in self._to(GROUP)))

    def test_the_shop_link_stays_in_the_group(self):
        self.request._say("\U0001F6D2 Shop online: https://shop.test/shop")
        self.assertFalse(self._to(PHONE))
        self.assertTrue(any('https://shop.test/shop' in t for t in self._to(GROUP)))

    def test_text_without_a_link_stays_in_the_group(self):
        self.request._say("Your order is packed.")
        self.assertFalse(self._to(PHONE))
        self.assertTrue(self._to(GROUP))

    # ------------------------------------------------------------------ PDFs
    def test_the_order_pdf_goes_privately(self):
        self.request._sa_send_order_pdf(self.order)
        self.assertEqual([d[0] for d in self.docs], [PHONE])
        self.assertTrue(any('private chat' in t for t in self._to(GROUP)))

    def test_with_a_hidden_number_the_order_pdf_goes_to_the_group(self):
        self.request.write({'requester_is_lid': True, 'requester_lid': '55@lid'})
        self.request._sa_send_order_pdf(self.order)
        self.assertEqual([d[0] for d in self.docs], [GROUP])

    def test_a_refused_pdf_falls_back_to_the_group(self):
        self.refuse.add(PHONE)
        where = self.request._sa_send_doc(
            lambda to: self.group.session_id.send_document(to, b'%PDF', 'x.pdf'))
        self.assertEqual(where, 'group')
        self.assertEqual([d[0] for d in self.docs], [GROUP])

    # ------------------------------------------------------------- back button
    def test_back_to_the_group_uses_the_invite_link(self):
        self.assertTrue(self.group._sa_back_url().startswith('https://wa.me/'))
        self.group.invite_url = 'https://chat.whatsapp.com/AbCdEf'
        self.assertEqual(self.group._sa_back_url(), 'https://chat.whatsapp.com/AbCdEf')
        self.group.invite_url = 'https://evil.example/x'
        self.assertTrue(self.group._sa_back_url().startswith('https://wa.me/'))

    # ------------------------------------------- answers typed in the private chat
    def test_a_private_send_points_later_private_messages_to_the_group(self):
        self.request._say("Pay here: %s" % PAY)
        self.assertTrue(self.request.sa_private_sent_on)
        Request = self.env['sa.group.request']
        found = Request._sa_private_reply_request(PHONE, self.group.session_id)
        self.assertEqual(found, self.request)
        self.sent.clear()
        self.assertTrue(found._sa_private_redirect_reply(PHONE))
        reply = self._to(PHONE)
        self.assertEqual(len(reply), 1)
        self.assertIn('answer in the group', reply[0])
        self.assertIn(self.group.name, reply[0])

    def test_the_group_invite_link_is_in_the_answer(self):
        self.group.invite_url = 'https://chat.whatsapp.com/ZzInvite'
        self.request._say("Pay here: %s" % PAY)
        self.sent.clear()
        self.request._sa_private_redirect_reply(PHONE)
        self.assertIn('https://chat.whatsapp.com/ZzInvite', self._to(PHONE)[0])

    def test_nothing_sent_privately_means_the_salesbot_answers(self):
        Request = self.env['sa.group.request']
        self.assertFalse(Request._sa_private_reply_request(PHONE, self.group.session_id))
        self.request._say("Pay here: %s" % PAY)
        self.assertFalse(Request._sa_private_reply_request('919811111111', self.group.session_id),
                         'another number')

    def test_after_six_hours_the_salesbot_answers_again(self):
        from datetime import timedelta
        from odoo import fields
        self.request._say("Pay here: %s" % PAY)
        self.request.sa_private_sent_on = fields.Datetime.now() - timedelta(hours=7)
        self.assertFalse(self.env['sa.group.request']._sa_private_reply_request(
            PHONE, self.group.session_id))

    def test_a_pdf_sent_privately_also_counts(self):
        self.request._sa_send_order_pdf(self.order)
        self.assertTrue(self.request.sa_private_sent_on)

    def test_a_review_link_gets_its_own_note(self):
        review = 'https://shop.test/scoped_app/wa-link?db=x&to=%2Fwa%2Freview%2F7%3Faccess_token%3Dabc'
        self.request._say("⭐ How was it? Rate your products: %s" % review)
        self.assertTrue(any(review in t for t in self._to(PHONE)))
        self.assertTrue(any('rate your products' in t and 'private chat' in t for t in self._to(GROUP)))

    # ------------------------------------------------ easy set-up (21 Nov 2026)
    def test_the_address_form_is_on_by_default(self):
        fresh = self.env['sa.ai.settings'].new({})
        self.assertTrue(fresh.address_link_enabled)

    def test_get_invite_link_saves_the_link(self):
        Session = self.env.registry['whatsapp.session']
        self.group.session_id.instance_name = 'sa-private-links-test'
        with patch.object(Session, '_gateway_call', lambda s, *a, **kw: {'inviteCode': 'AbC'}):
            action = self.group.action_sa_get_invite_link()
        self.assertEqual(self.group.invite_url, 'https://chat.whatsapp.com/AbC')
        self.assertFalse(self.group.invite_error)
        self.assertTrue(self.group.invite_checked_on)
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(self.group._sa_back_url(), 'https://chat.whatsapp.com/AbC')
        self.assertIn('opens this group', self.group.invite_hint)

    def test_get_invite_link_says_why_when_not_admin(self):
        from odoo.exceptions import UserError
        Session = self.env.registry['whatsapp.session']
        self.group.session_id.instance_name = 'sa-private-links-test'

        def refuse(s, *a, **kw):
            raise UserError('not-admin')
        with patch.object(Session, '_gateway_call', refuse):
            action = self.group.action_sa_get_invite_link()
        self.assertFalse(self.group.invite_url)
        self.assertIn('admin', self.group.invite_error)
        self.assertIn('not-admin', self.group.invite_error)
        self.assertEqual(action['params']['type'], 'warning')
        self.assertTrue(self.group._sa_back_url().startswith('https://wa.me/'))
        self.assertIn('Get invite link', self.group.invite_hint)

    def test_the_group_screen_loads(self):
        views = self.env['sa.sales.group'].get_views([(False, 'form'), (False, 'list')])
        self.assertIn('action_sa_get_invite_link', views['views']['form']['arch'])

    # ------------------------------------- Customer Links, one row each (21 Nov)
    def test_each_link_follows_its_own_row(self):
        self.settings.link_track = 'group'
        self.request._say("Follow it live: %s" % TRACK)
        self.request._say("Pay here: %s" % PAY)
        self.assertTrue(any(TRACK in t for t in self._to(GROUP)), 'tracking: group')
        self.assertTrue(any(PAY in t for t in self._to(PHONE)), 'payment: private')

    def test_pdfs_set_to_group(self):
        self.settings.link_docs = 'group'
        self.request._sa_send_order_pdf(self.order)
        self.assertEqual([d[0] for d in self.docs], [GROUP])

    def test_no_group_note_when_switched_off(self):
        self.settings.link_group_note = False
        self.request._say("Pay here: %s" % PAY)
        self.assertTrue(self._to(PHONE))
        self.assertFalse([t for t in self._to(GROUP) if 'private chat' in t])

    def test_the_shop_link_can_go_privately(self):
        self.settings.link_shop = 'private'
        self.request._say("\U0001F6D2 Shop online: https://shop.test/shop")
        self.assertTrue(any('https://shop.test/shop' in t for t in self._to(PHONE)))
        self.assertTrue(any('shop link' in t for t in self._to(GROUP)))

    def test_the_kinds_are_told_apart(self):
        kind = self.request._sa_link_kind_of
        self.assertEqual(kind(PAY), 'pay')
        self.assertEqual(kind(SIGN), 'sign')
        self.assertEqual(kind(TRACK), 'track')
        self.assertEqual(kind('https://shop.test/scoped_app/wa-link?db=x&to=%2Fmy%2Forders%2F7%3Fpayment_amount%3D5'), 'pay')
        self.assertEqual(kind('https://shop.test/scoped_app/c?db=x&t=abc'), 'confirm')
        self.assertEqual(kind('https://shop.test/scoped_app/wa-link?db=x&to=%2Fwa%2Faddress%2Fabc'), 'address')
        self.assertEqual(kind('https://shop.test/scoped_app/wa-link?db=x&to=%2Fwa%2Freview%2F7'), 'review')
        self.assertEqual(kind('https://maps.google.com/?q=1,2'), 'map')
        self.assertEqual(kind('https://shop.test/track/369M-1'), 'web')
        self.assertEqual(kind('https://shop.test/shop'), 'shop')

    def test_reply_window_zero_turns_the_answer_off(self):
        self.request._say("Pay here: %s" % PAY)
        self.settings.link_reply_hours = 0
        self.assertFalse(self.env['sa.group.request']._sa_private_reply_request(
            PHONE, self.group.session_id))

    def test_the_storefront_console_reads_and_saves_the_rows(self):
        if 'mart369.config' not in self.env:
            self.skipTest('no 369 Mart console here')
        Config = self.env['mart369.config']
        links = Config._mart369_wa_links()
        self.assertEqual(len(links['rows']), 10)
        self.assertEqual({r['key']: r['to'] for r in links['rows']}['pay'], 'private')
        Config._mart369_admin_save_group('whatsapp', {'links': {'to': {'pay': 'group'}, 'replyHours': 3}})
        self.assertEqual(self.settings.link_pay, 'group')
        self.assertEqual(self.settings.link_reply_hours, 3)
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            Config._mart369_admin_save_group('whatsapp', {'links': {'to': {'pay': 'nowhere'}}})
