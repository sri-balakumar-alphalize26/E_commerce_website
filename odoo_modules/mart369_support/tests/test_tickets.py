"""Tickets, ownership, and WhatsApp staying quiet when there is nothing to send on."""

import json

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
        ticket._mart369_say('Sorry about that, sending a replacement', from_customer=False)
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

    def test_the_chat_route_answers_in_the_shape_the_panel_reads(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._post('/369mart/support/chat', {'text': 'delivery charges'})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get('text'))
        self.assertTrue(set(payload) <= {'text', 'actions', 'chips', 'agent', 'ok'})
