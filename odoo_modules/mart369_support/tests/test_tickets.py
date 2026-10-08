"""Tickets, ownership, and WhatsApp staying quiet when there is nothing to send on."""

import json

from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.mart369_order.tests.common import Mart369OrderFixtures


@tagged('post_install', '-at_install')
class TestMart369Tickets(Mart369OrderFixtures, TransactionCase):

    def test_asking_for_a_person_really_opens_a_ticket(self):
        """The app said "I've noted this" and noted nothing anywhere."""
        ticket = self.env['mart369.ticket']._mart369_open(
            self.partner, 'My order never arrived')
        self.assertTrue(ticket.name.startswith('369S-'))
        self.assertEqual(ticket.state, 'new')
        self.assertEqual(ticket.partner_id, self.partner)

    def test_asking_twice_does_not_make_two_tickets(self):
        Ticket = self.env['mart369.ticket']
        first = Ticket._mart369_open(self.partner, 'First')
        second = Ticket._mart369_open(self.partner, 'Again')
        self.assertEqual(first, second, 'one conversation, not two in the queue')

    def test_a_closed_ticket_does_not_swallow_a_new_question(self):
        Ticket = self.env['mart369.ticket']
        first = Ticket._mart369_open(self.partner, 'First')
        first.mart369_action_done()
        second = Ticket._mart369_open(self.partner, 'Something else')
        self.assertNotEqual(first, second)

    def test_a_ticket_picks_up_the_order_on_its_way(self):
        order = self._place()
        self._pay(order)
        ticket = self.env['mart369.ticket']._mart369_open(self.partner, 'Where is it')
        self.assertEqual(ticket.order_id, order)

    def test_the_conversation_is_kept(self):
        """It used to live in sessionStorage and die with the tab, so an
        operator picking it up knew nothing."""
        ticket = self.env['mart369.ticket']._mart369_open(self.partner, 'Hello')
        ticket._mart369_say('The bag was torn', from_customer=True)
        # A person: the superuser the tests run as is OdooBot, i.e. the bot.
        ticket.with_user(self.env.ref('base.user_admin'))._mart369_say(
            'Sorry about that, sending a replacement', from_customer=False)
        transcript = ticket._mart369_transcript()
        self.assertEqual(len(transcript), 2)
        self.assertEqual(transcript[0]['from'], 'me')
        self.assertEqual(transcript[1]['from'], 'agent')

    def test_answering_stamps_when_and_who(self):
        ticket = self.env['mart369.ticket']._mart369_open(self.partner, 'Hello')
        self.assertFalse(ticket.answered_at)
        ticket._mart369_say('On it', from_customer=False)
        self.assertTrue(ticket.answered_at)
        self.assertEqual(ticket.state, 'open')

    def test_the_customer_talking_does_not_count_as_an_answer(self):
        ticket = self.env['mart369.ticket']._mart369_open(self.partner, 'Hello')
        ticket._mart369_say('Anyone there?', from_customer=True)
        self.assertFalse(ticket.answered_at, 'waiting time keeps counting')

    def test_an_empty_message_is_not_recorded(self):
        ticket = self.env['mart369.ticket']._mart369_open(self.partner, 'Hello')
        before = len(ticket._mart369_transcript())
        ticket._mart369_say('   ', from_customer=True)
        self.assertEqual(len(ticket._mart369_transcript()), before)


@tagged('post_install', '-at_install')
class TestMart369ReplyTags(Mart369OrderFixtures, TransactionCase):
    """A team reply carries the question it answers, like a WhatsApp reply."""

    def setUp(self):
        super().setUp()
        self.ticket = self.env['mart369.ticket']._mart369_open(self.partner, 'Help')
        # A person, not OdooBot: the superuser the tests run as *is* the bot.
        self.staff = self.ticket.with_user(self.env.ref('base.user_admin'))

    def _ask(self, text):
        return self.ticket._mart369_say(text, from_customer=True)

    def _answer(self, text, **kwargs):
        return self.staff._mart369_say(text, from_customer=False, **kwargs)

    def test_replies_are_tagged_to_the_questions_in_order(self):
        first = self._ask('Where is my parcel?')
        second = self._ask('Can I change the address too?')
        self.assertEqual(self._answer('It is out for delivery').mart369_reply_to_id, first)
        self.assertEqual(self._answer('Yes, send it here').mart369_reply_to_id, second)
        self.assertFalse(self._answer('Anything else?').mart369_reply_to_id,
                         'nothing left unanswered, so nothing to tag')

    def test_staff_can_pick_the_question_or_leave_it_untagged(self):
        first = self._ask('Where is my parcel?')
        second = self._ask('Can I change the address too?')
        self.assertFalse(self._answer('One moment', reply_to=False).mart369_reply_to_id)
        self.assertEqual(self._answer('Yes', reply_to=second.id).mart369_reply_to_id, second)
        self.assertEqual(self._answer('Out today').mart369_reply_to_id, first,
                         'the one still unanswered')

    def test_only_this_customers_lines_on_this_ticket_can_be_quoted(self):
        asked = self._ask('Where is my parcel?')
        bot_line = self.ticket._mart369_say('Let me check', from_customer=False, from_bot=True)
        other = self.env['mart369.ticket']._mart369_open(self.other.partner_id, 'Mine')
        theirs = other._mart369_say('Not yours', from_customer=True)
        for wrong in (bot_line.id, theirs.id, 'abc'):
            with self.assertRaises(UserError):
                self._answer('Hello', reply_to=wrong)
        self.assertIn(asked, self.ticket._mart369_unanswered())

    def test_what_the_bot_answered_is_not_tagged_again(self):
        asked = self._ask('delivery charges')
        self.ticket._mart369_say('Free over 499', from_customer=False, from_bot=True,
                                 reply_to=asked)
        self.assertFalse(self._answer('Hi, I am here').mart369_reply_to_id)

    def test_the_transcript_carries_the_quote_on_team_lines_only(self):
        asked = self._ask('delivery charges')
        self.ticket._mart369_say('Free over 499', from_customer=False, from_bot=True,
                                 reply_to=asked)
        waiting = self._ask('Is anyone there?')
        self._answer('Yes, how can I help?')
        rows = self.ticket._mart369_transcript()
        self.assertTrue(all(row.get('id') for row in rows))
        self.assertNotIn('replyTo', rows[1], 'the bot line keeps its quote to itself')
        self.assertEqual(rows[-1]['replyTo'],
                         {'id': waiting.id, 'text': 'Is anyone there?', 'from': 'me'})

    def test_the_quote_is_the_first_line_of_the_question(self):
        """A one-line preview, like WhatsApp; the whole question is a tap away."""
        self._ask('My parcel came torn.\nTwo items are missing and one is broken.')
        self._answer('Sorry - a replacement is on its way')
        self.assertEqual(self.ticket._mart369_transcript()[-1]['replyTo']['text'],
                         'My parcel came torn.')

    def test_a_reply_typed_in_odoo_chatter_is_tagged_too(self):
        asked = self._ask('Where is my parcel?')
        posted = self.staff.message_post(body='Out for delivery', message_type='comment',
                                         subtype_xmlid='mail.mt_comment')
        self.assertEqual(posted.mart369_reply_to_id, asked)

    def test_a_log_note_is_never_tagged(self):
        self._ask('Where is my parcel?')
        note = self.staff.message_post(body='Courier says tomorrow', message_type='comment',
                                       subtype_xmlid='mail.mt_note')
        self.assertFalse(note.mart369_reply_to_id)


@tagged('post_install', '-at_install')
class TestMart369Whatsapp(Mart369OrderFixtures, TransactionCase):

    def test_nothing_is_sent_when_no_gateway_is_installed(self):
        """Soft on purpose: the opt-in is still recorded, so switching a gateway
        on later starts sending to people who already agreed."""
        order = self._place()
        order.sudo().write({'mart369_whatsapp': True})
        sent = self.env['mart369.whatsapp']._mart369_notify(order, 'placed')
        available = self.env['mart369.whatsapp']._mart369_available()
        self.assertEqual(bool(sent), bool(sent and available))
        if not available:
            self.assertFalse(sent)

    def test_a_customer_who_did_not_opt_in_is_never_messaged(self):
        order = self._place()
        order.sudo().write({'mart369_whatsapp': False})
        self.assertFalse(self.env['mart369.whatsapp']._mart369_wants(order))

    def test_turning_whatsapp_off_on_the_account_overrides_the_cart(self):
        """Two consents, both needed."""
        order = self._place()
        order.sudo().write({'mart369_whatsapp': True})
        if 'mart369_notify_whatsapp' in self.partner._fields:
            self.partner.sudo().write({'mart369_notify_whatsapp': False})
            self.assertFalse(self.env['mart369.whatsapp']._mart369_wants(order))

    def test_an_order_with_no_phone_is_not_messaged(self):
        order = self._place()
        order.sudo().write({'mart369_whatsapp': True})
        order.partner_shipping_id.sudo().write({'phone': False})
        order.partner_id.sudo().write({'phone': False})
        self.assertFalse(self.env['mart369.whatsapp']._mart369_wants(order))

    def test_an_order_still_moves_when_a_send_blows_up(self):
        """An outbound message failing is not a reason for the shop to stop."""
        order = self._place()
        self._pay(order)

        def explode(self_model, order_arg, state):
            raise RuntimeError('deliberate')

        self.patch(type(self.env['mart369.whatsapp']), '_mart369_notify', explode)
        order.mart369_action_advance()
        self.assertEqual(order.mart369_state, 'packed')


@tagged('post_install', '-at_install')
class TestMart369SupportOwnership(Mart369OrderFixtures, HttpCase):
    """A ticket carries a whole conversation, so it is worth its own test."""

    def _post(self, path, body=None):
        response = self.url_open(
            path, data=json.dumps(body or {}),
            headers={'Content-Type': 'application/json'})
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, {}

    def _get(self, path):
        response = self.url_open(path)
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, {}

    def setUp(self):
        super().setUp()
        self.ticket = self.env['mart369.ticket']._mart369_open(
            self.partner, 'My parcel was torn open')
        self.ticket._mart369_say('There was a hole in the bag', from_customer=True)

    def test_another_customer_does_not_see_that_conversation(self):
        self.authenticate('someone.else@369mart.test', 'someone-else-369')
        status, payload = self._get('/369mart/support/ticket')
        self.assertEqual(status, 200)
        self.assertIsNone(payload.get('ticket'), 'not theirs, so not there')

    def test_talking_to_an_agent_appends_to_their_own_ticket_only(self):
        self.authenticate('someone.else@369mart.test', 'someone-else-369')
        status, payload = self._post('/369mart/support/agent/say', {'text': 'hello'})
        self.assertEqual(status, 200)
        self.assertIsInstance(payload.get('reply'), str, 'a bare string, not an object')
        self.assertEqual(len(self.ticket._mart369_transcript()), 1,
                         'the other customer\'s ticket is untouched')

    def test_a_customer_gets_their_own_conversation_back(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._get('/369mart/support/ticket')
        self.assertEqual(status, 200)
        self.assertEqual(payload['ticket']['ref'], self.ticket.name)
        self.assertEqual(len(payload['ticket']['messages']), 1)

    def test_while_waiting_the_bot_still_answers_what_it_knows(self):
        """The chat used to go silent for ten minutes once it was queued."""
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._post('/369mart/support/agent/say', {'text': 'delivery charges'})
        self.assertEqual(status, 200)
        self.assertTrue(payload['bot']['text'])
        self.assertEqual(payload['reply'], payload['bot']['text'], 'the phone app reads `reply`')
        self.ticket.invalidate_recordset()
        unanswered = self.ticket._mart369_unanswered().mapped(lambda m: m.body)
        self.assertFalse([b for b in unanswered if 'delivery charges' in b],
                         'the bot answered it, so the team is not tagged to it')

    def _unanswered_texts(self):
        self.ticket.invalidate_recordset()
        return [m.body for m in self.ticket._mart369_unanswered()]

    def test_every_line_in_the_queue_gets_an_answer_at_once(self):
        """It used to be one line per ten minutes: "hi", then nothing."""
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        for text in ('hi', 'hi', 'can you gift wrap it?', 'thanks'):
            status, payload = self._post('/369mart/support/agent/say', {'text': text})
            self.assertEqual(status, 200)
            self.assertTrue(payload['reply'], 'no answer to %r' % text)
            self.assertEqual(payload['bot']['text'], payload['reply'])

    def test_a_question_the_bot_cannot_settle_stays_in_the_queue(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._post('/369mart/support/agent/say', {'text': 'can you gift wrap it?'})
        self.assertIn('Got it', payload['reply'])
        self.assertTrue([b for b in self._unanswered_texts() if 'gift wrap' in b],
                        'the team reply is tagged to it')

    def test_hi_is_answered_and_not_left_for_the_team_to_quote(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._post('/369mart/support/agent/say', {'text': 'hi'})
        self.assertIn('queue', payload['reply'])
        self.assertFalse([b for b in self._unanswered_texts() if '>hi<' in b])

    def test_once_the_team_has_answered_the_bot_steps_back(self):
        self.ticket.with_user(self.env.ref('base.user_admin'))._mart369_say(
            'Hello, I am looking at it', from_customer=False)
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._post('/369mart/support/agent/say', {'text': 'delivery charges'})
        self.assertEqual(status, 200)
        self.assertNotIn('bot', payload)
        self.assertEqual(payload['reply'], '')

    def test_the_chat_route_answers_in_the_shape_the_panel_reads(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._post('/369mart/support/chat', {'text': 'delivery charges'})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get('text'))
        self.assertTrue(set(payload) <= {'text', 'actions', 'chips', 'agent', 'ok'})
