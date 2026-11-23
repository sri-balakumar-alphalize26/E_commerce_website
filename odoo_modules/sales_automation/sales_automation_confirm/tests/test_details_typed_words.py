# -*- coding: utf-8 -*-
"""Typed words while an order waits at "Please check your details" (Test 2,
22 Nov 2026, Ref R): "tablet" after NEW ORDER and "headphone" on its own were
both answered "Sorry, I didn't understand ...". Owner's rule:

  * hi            -> the menu, as before;
  * a product     -> shown from the catalogue, out of stock too (a tap on an
                     out-of-stock one asks the vendors); the order keeps waiting;
  * anything else -> "Sorry, we couldn't find anything for X - type the correct
                     product name, or hi";
  * YES / NO / CANCEL / 1-3, the name and the address still answer the order;
  * a details question unanswered for 30 minutes catches nothing typed.

Nothing is sent: `_say` and `_ask` are captured.
"""
import itertools
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

GROUP = '120363000000000077@g.us'
PHONE = '919800077788'
_SEQ = itertools.count(1)


@tagged('post_install', '-at_install')
class TestDetailsTypedWords(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.said = []        # (request id, body)
        cls.polls = []       # (request id, body, [titles])
        cls.taken = []       # (request id, text) given to _sa_take_details
        Request = env.registry['sa.group.request']
        Session = env.registry['whatsapp.session']

        def say(self, body, addressed=True):
            cls.said.append((self.id, body))
            return True

        def ask(self, body, buttons):
            cls.said.append((self.id, body))
            cls.polls.append((self.id, body, [b['title'] for b in buttons]))
            return True

        for patcher in (
                patch.object(Request, '_say', say),
                patch.object(Request, '_ask', ask),
                patch.object(Session, 'send_message', lambda self, *a, **kw: True),
                patch.object(Session, '_send_payload', lambda self, *a, **kw: True),
                patch.object(Session, '_gateway_call', lambda self, *a, **kw: {}),
                patch.object(env.registry['sa.outbox.guard'], 'claim',
                             lambda self, key, seconds=60: True)):
            patcher.start()
            cls.addClassCleanup(patcher.stop)

        cls.session = env['whatsapp.session'].create({
            'name': 'SA typed words', 'gateway_api_key': 'x', 'instance_name': 'sa-typed-words'})
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz Typed Words', 'group_jid': GROUP,
            'session_id': cls.session.id, 'group_type': 'customer'})
        # an enabled customer group needs an employee session (as in
        # sales_automation/tests/test_order_company.py)
        employee = env['hr.employee'].create({'name': 'Zz Typed Counter'})
        desk = env['wa.employee.session'].create({
            'employee_id': employee.id, 'session_id': cls.session.id,
            'phone_number': '919800000077', 'auto_reply_company_id': env.company.id})
        cls.group.write({'employee_session_id': desk.id, 'enabled': True})
        Categ = env['product.category']
        cls.laptops = Categ.create({'name': 'Laptop'})
        Prod = env['product.template']
        cls.hp = Prod.create({'name': 'Zz HP Laptop 15', 'list_price': 700.0, 'type': 'consu',
                              'categ_id': cls.laptops.id, 'sale_ok': True})
        oos_vals = {'name': 'Zz Dell Laptop OOS', 'list_price': 900.0, 'type': 'consu',
                    'categ_id': cls.laptops.id, 'sale_ok': True}
        if 'is_storable' in Prod._fields:
            oos_vals['is_storable'] = True                    # tracked, nothing on hand
        if 'allow_out_of_stock_order' in Prod._fields:
            oos_vals['allow_out_of_stock_order'] = False      # the website hides it
        cls.oos = Prod.create(oos_vals)
        cls.tablet = Prod.create({'name': 'Zz Tablet Pro 11', 'list_price': 300.0, 'type': 'consu',
                                  'sale_ok': True})
        cls.headphone = Prod.create({'name': 'Zz Headphone Max', 'list_price': 90.0, 'type': 'consu',
                                     'sale_ok': True})
        if 'is_published' in Prod._fields:        # the shop lists published ones only
            (cls.hp | cls.oos | cls.tablet | cls.headphone).write({'is_published': True})
        cls.hidden = Prod.create({'name': 'Zz Backroom Scanner', 'list_price': 50.0, 'type': 'consu',
                                  'sale_ok': True})
        cls.customer = env['res.partner'].create({
            'name': 'Karthick', 'phone': '+' + PHONE, 'street': '13a, beach road kollam',
            'zip': '691001'})
        cls.order = env['sale.order'].create({
            'partner_id': cls.customer.id,
            'order_line': [(0, 0, {'product_id': cls.hp.product_variant_id.id, 'product_uom_qty': 1})],
        })

    def setUp(self):
        super().setUp()
        del self.said[:], self.polls[:], self.taken[:]
        # Ref R: the order waits at the read-back (address-book version: the
        # address was chosen, the landmark answered)
        self.waiting = self.env['sa.group.request'].create({
            'group_id': self.group.id, 'requester_phone': PHONE, 'requester_name': 'Karthick',
            'raw_text': 'laptop', 'product_id': self.hp.id, 'order_id': self.order.id,
            'state': 'order_created', 'sa_details_pending': True, 'profile_step': 'confirm',
            'sa_note_step': 'done', 'sa_book_done': True,
            'profile_asked_on': fields.Datetime.now() - timedelta(minutes=2),
            'poll_wa_id': 'READBACK-POLL', 'poll_wa_ids': 'READBACK-POLL'})

    # ------------------------------------------------------------ helpers
    def _msg(self, text):
        return self.env['whatsapp.message'].create({
            'session_id': self.session.id, 'phone': GROUP, 'group_jid': GROUP,
            'direction': 'incoming', 'message': text, 'participant_phone': PHONE,
            'wa_message_id': 'ZZTYPED%d' % next(_SEQ)})

    def _send(self, text):
        return self.env['sa.group.request']._on_group_message(self._msg(text))

    def _bodies(self):
        return '\n---\n'.join(b for _i, b in self.said)

    def _record_take(self):
        taken = self.taken

        def take(rec, text):
            taken.append((rec.id, text))
            return True
        return patch.object(self.env.registry['sa.group.request'], '_sa_take_details', take)

    def _assert_still_waiting(self):
        self.waiting.invalidate_recordset()
        self.assertTrue(self.waiting.sa_details_pending)
        self.assertEqual(self.waiting.state, 'order_created')
        self.assertEqual(self.waiting.profile_step, 'confirm')
        self.assertFalse(self.waiting.profile_retry, 'no "Sorry, I didn\'t understand" retry')
        self.assertIn('READBACK-POLL', self.waiting.poll_wa_ids or '',
                      'the YES / NO / CANCEL poll still belongs to the order')
        self.assertNotIn("didn't understand", self._bodies())

    # ------------------------------------------------- the two screenshots
    def test_tablet_after_new_order(self):
        """Screenshot 2: NEW ORDER opened after the read-back, then "tablet"."""
        self.waiting._sa_menu_show('ask')              # "what are you looking for?"
        del self.said[:], self.polls[:]
        self._send('tablet')
        self.assertIn('Found for *tablet*', self._bodies())
        self.assertIn(self.tablet.name, self.polls[-1][2])
        self.waiting.invalidate_recordset()
        self.assertTrue(self.waiting.sa_details_pending)
        self.assertNotIn("didn't understand", self._bodies())

    def test_headphone_on_the_readback(self):
        """Screenshot 1: no menu opened; "headphone" typed at the read-back."""
        self._send('headphone')
        self.assertIn('Found for *headphone*', self._bodies())
        rid, _body, titles = self.polls[-1]
        self.assertIn(self.headphone.name, titles)
        self.assertNotEqual(rid, self.waiting.id, 'posted from the menu row, not the waiting order')
        self._assert_still_waiting()

    def test_laptop_on_the_readback_opens_the_category(self):
        self._send('laptop')
        titles = self.polls[-1][2]
        self.assertIn(self.hp.name, titles)
        self._assert_still_waiting()

    def test_a_second_word_after_the_catalogue_is_searched(self):
        self._send('headphone')
        del self.said[:], self.polls[:]
        self._send('tablet')
        self.assertIn('Found for *tablet*', self._bodies())
        self._assert_still_waiting()

    # ------------------------------------------------------ not found
    def test_a_product_we_do_not_list(self):
        self._send('xylophone')
        self.assertIn("couldn't find anything for *xylophone*", self._bodies())
        self.assertIn('type *hi* to continue', self._bodies())
        self._assert_still_waiting()

    def test_anything_else(self):
        self._send('what time do you close')
        self.assertIn("couldn't find anything for *what time do you close*", self._bodies())
        self._assert_still_waiting()

    def test_not_found_on_the_new_order_screen_keeps_searching(self):
        self.waiting._sa_menu_show('ask')
        del self.said[:], self.polls[:]
        self._send('xylophone')
        self.assertIn("couldn't find anything for *xylophone*", self._bodies())
        self.waiting.invalidate_recordset()
        self.assertTrue(self.waiting.sa_menu_ask_at, 'the next word is still a search')
        del self.said[:]
        self._send('headphone')
        self.assertIn('Found for *headphone*', self._bodies())

    def test_not_published_goes_to_the_ordinary_enquiry(self):
        if 'is_published' not in self.hidden._fields:
            self.skipTest('every product is on the menu without the shop')
        Request = self.env.registry['sa.group.request']
        for screen in (False, True):
            with self.subTest(new_order=screen):
                if screen:
                    self.waiting._sa_menu_show('ask')
                del self.said[:], self.polls[:]
                before = self.env['sa.group.request'].search([], order='id desc', limit=1).id
                started = []
                with patch.object(Request, '_process', lambda rec: started.append(rec.raw_text)):
                    self._send('backroom scanner')
                self.assertEqual(started, ['backroom scanner'], 'the enquiry that asks the vendors')
                self.assertNotIn("couldn't find", self._bodies())
                new = self.env['sa.group.request'].search([('id', '>', before), ('raw_text', '=', 'backroom scanner'),
                                                           ('state', '!=', 'dropped')])
                self.assertEqual(len(new), 1)
                self._assert_still_waiting()

    def test_a_sentence_is_still_not_found(self):
        self._send('backroom scanner please tell me quickly')
        self.assertIn("couldn't find", self._bodies())

    def test_not_found_says_whom_to_contact(self):
        self.env['sa.ai.settings'].get_settings().write({'shop_contact_phone': '+97150000000'})
        self._send('xylophone')
        self.assertIn('contact us on *+97150000000*', self._bodies())

    # ------------------------------------------------- answers still answer
    def test_answers_still_reach_the_order(self):
        words = ['yes', 'NO', 'cancel', '1', '3', 'name', 'address', 'back',
                 '✅ YES, CORRECT', '2 ✏️ NO, CHANGE']
        with self._record_take():
            for w in words:
                self._send(w)
        self.assertEqual([t for _i, t in self.taken], words)
        self.assertTrue(all(i == self.waiting.id for i, _t in self.taken))
        self.assertNotIn("couldn't find", self._bodies())

    def test_the_name_and_address_steps_take_typed_text(self):
        with self._record_take():
            self.waiting.write({'profile_step': 'name'})
            self._send('Sri Bala')
            self.waiting.write({'profile_step': 'address'})
            self._send('12 temple street, kollam')
            self.waiting.write({'profile_step': 'confirm', 'sa_note_step': 'ask'})
            self._send('near the blue gate')
        self.assertEqual([t for _i, t in self.taken],
                         ['Sri Bala', '12 temple street, kollam', 'near the blue gate'])

    def test_hi_opens_the_menu(self):
        with self._record_take():
            self._send('hi')
        self.assertFalse(self.taken)
        self.assertIn('what would you like to do', self._bodies().lower())

    # ------------------------------------------------------ 30 minutes
    def test_after_30_minutes_typed_text_is_not_caught(self):
        Request = self.env['sa.group.request']
        self.waiting.write({'profile_asked_on': fields.Datetime.now() - timedelta(minutes=31)})
        self.assertFalse(Request._sa_details_waiting(self.group, self._msg('yes')))
        self.waiting.write({'profile_asked_on': fields.Datetime.now() - timedelta(minutes=29)})
        self.assertEqual(Request._sa_details_waiting(self.group, self._msg('yes')), self.waiting)

    def test_after_30_minutes_the_poll_still_works(self):
        self.waiting.write({'profile_asked_on': fields.Datetime.now() - timedelta(minutes=45)})
        with self._record_take():
            self.waiting._sa_answer_poll('✅ YES, CORRECT')
        self.assertEqual(self.taken, [(self.waiting.id, 'yes')])

    def test_every_details_question_is_stamped(self):
        """The landmark question and the change menu restart the 30 minutes."""
        old = fields.Datetime.now() - timedelta(minutes=40)
        self.waiting.write({'profile_asked_on': old, 'sa_note_step': False})
        self.waiting._sa_details_ask(self.order)                  # landmark question
        self.assertGreater(self.waiting.profile_asked_on, old)
        self.waiting.write({'profile_asked_on': old, 'sa_details_fix': 'menu'})
        self.waiting._sa_details_ask(self.order)                  # what to change?
        self.assertGreater(self.waiting.profile_asked_on, old)

    # ------------------------------------------------------ out of stock
    def test_out_of_stock_is_listed_without_a_stock_note(self):
        self._send('laptop')
        titles = self.polls[-1][2]
        self.assertIn(self.oos.name, titles)
        self.assertIn(self.hp.name, titles)
        for t in titles:
            self.assertNotIn('stock', t.lower())

    def test_out_of_stock_tap_goes_to_the_vendors(self):
        Request = self.env.registry['sa.group.request']
        with patch.object(Request, '_ask_confirmation', lambda self: True):
            self.waiting._sa_menu_start_enquiry(self.oos)
        req = self.env['sa.group.request'].search(
            [('group_id', '=', self.group.id), ('product_id', '=', self.oos.id)], order='id desc', limit=1)
        self.assertEqual(req.ai_source, 'menu')
        self.assertTrue(req._assess_availability(self.oos), 'sourced from the vendors, not refused')
        self.assertNotEqual(req.stock_status, 'in_stock')
        started = []
        with patch.object(Request, '_start_sourcing', lambda self, vendors: started.append(self.id) or True), \
                patch.object(Request, '_sourcing_vendors', lambda self: self.env['res.partner'].browse([1])), \
                patch.object(Request, '_open_twin', lambda self: self.browse()):
            req.with_context(sa_confirm_accepted=True)._on_confirmed()
        self.assertIn(req.id, started)

    def test_a_typed_enquiry_keeps_the_old_stock_rule(self):
        if 'allow_out_of_stock_order' not in self.env['product.template']._fields:
            self.skipTest('the website out-of-stock switch is not installed')
        req = self.env['sa.group.request'].create({
            'group_id': self.group.id, 'requester_phone': PHONE, 'raw_text': 'dell',
            'product_id': self.oos.id, 'state': 'new'})
        self.assertFalse(req._assess_availability(self.oos))
