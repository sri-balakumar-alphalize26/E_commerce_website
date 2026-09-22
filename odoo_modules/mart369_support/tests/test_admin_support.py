"""The staff side of support.

Three things are worth pinning here, and none would announce itself.

**Who may look.** These routes have no per-shopper fence - that is the point of
them - so the group check is the only thing between a shopper and every other
customer's name, order number and complaint.

**What the console may write.** Staff move a ticket along and hand it over.
They do not edit what a customer asked, and a request that tries is refused
rather than quietly ignored.

**The wait.** `waiting_minutes` is a stored compute on `opened_at` and
`answered_at`, and neither changes while a ticket sits unanswered - so it is
frozen at nought for exactly the tickets a queue exists to surface. The payload
works the wait out live, and the test below is the one that would catch anybody
"simplifying" it back to the stored field.

Counts are measured as a delta, never against zero: this database already holds
tickets from the other suites.
"""

import json
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.mart369_order.tests.common import Mart369OrderFixtures

HEADERS = {'Content-Type': 'application/json'}
LIST = '/369mart/admin/support'


@tagged('post_install', '-at_install')
class TestSupportAdminModel(Mart369OrderFixtures, TransactionCase):

    def setUp(self):
        super().setUp()
        self.Ticket = self.env['mart369.ticket']
        self.ticket = self.Ticket._mart369_open(self.partner, 'It never arrived')

    # ------------------------------------------------------------- the wait

    def _backdate(self, ticket, **delta):
        """Age a ticket the way the clock does, not the way a write does.

        Writing `opened_at` through the ORM recomputes `waiting_minutes`, which
        is exactly what never happens in life: a ticket is created, nothing
        touches it again, and the stored value sits at nought while the
        customer waits.

        Straight SQL reproduces that, but only after the compute has actually
        been done and written. A freshly created record still has it pending,
        and a pending compute run *after* the backdate would read the new date
        and quietly give the right answer - hiding the very bug this sets up.
        """
        ticket.flush_recordset(['waiting_minutes'])
        self.env.cr.execute(
            "UPDATE mart369_ticket SET opened_at = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(**delta), ticket.id))
        ticket.invalidate_recordset(['opened_at'])

    def test_the_wait_is_worked_out_now_not_read_off_the_stored_field(self):
        """The bug this file exists for.

        A ticket opened two hours ago and never answered has a stored
        `waiting_minutes` of nought, because nothing it depends on has changed
        since it was created. It is the ticket most worth seeing.
        """
        self._backdate(self.ticket, hours=2)

        self.assertEqual(self.ticket.waiting_minutes, 0,
                         'the stored field really is frozen')
        self.assertGreaterEqual(self.ticket._mart369_waited(), 119,
                                'and the payload really does not use it')

        row = self.ticket._mart369_admin_row()
        self.assertGreaterEqual(row['waited'], 119)
        self.assertTrue(row['late'], 'two hours is past the half hour')

    def test_an_answered_ticket_stops_counting(self):
        self._backdate(self.ticket, minutes=40)
        self.ticket._mart369_say('Sorry about that', from_customer=False)
        waited = self.ticket._mart369_waited()
        self.assertGreaterEqual(waited, 39)
        self.assertLess(waited, 60)
        self.assertFalse(self.ticket._mart369_admin_row()['late'],
                         'answered is not late, however long it took')

    def test_the_longest_wait_tile_sees_the_oldest_unanswered_one(self):
        self._backdate(self.ticket, hours=3)
        self.assertGreaterEqual(
            self.Ticket.mart369_admin_counts()['longest'], 179)

    def test_the_board_and_the_desk_agree_about_the_longest_wait(self):
        """The two screens must not answer the same question differently.

        The kanban strip used to read the stored `waiting_minutes`, so it
        reported nought for a ticket nobody had touched since it was created -
        the one most worth surfacing - while the desk beside it had always
        worked the wait out live.
        """
        self._backdate(self.ticket, hours=2)
        self.assertEqual(self.ticket.waiting_minutes, 0,
                         'the stored field is still frozen, as it always was')

        board = self.Ticket.mart369_support_dashboard()
        desk = self.Ticket.mart369_admin_counts()
        self.assertGreaterEqual(board['longest'], 119)
        self.assertEqual(board['longest'], desk['longest'])

    def test_the_average_still_ignores_tickets_nobody_answered(self):
        """Counting the unanswered ones would flatter the number the longer
        they are ignored, which is the opposite of useful."""
        self._backdate(self.ticket, hours=5)
        before = self.Ticket.mart369_support_dashboard()['average']

        answered = self.Ticket._mart369_open(
            self.env.user.partner_id, 'Answered quickly')
        answered._mart369_say('Right away', from_customer=False)

        after = self.Ticket.mart369_support_dashboard()['average']
        self.assertLessEqual(after, before,
                             'a fast answer can only pull the average down')

    # --------------------------------------------------------- the payload

    def test_the_row_carries_what_the_queue_draws(self):
        row = self.ticket._mart369_admin_row()
        self.assertEqual(row['ref'], self.ticket.name)
        self.assertEqual(row['customer'], self.partner.display_name)
        self.assertEqual(row['subject'], 'It never arrived')
        self.assertEqual(row['state'], 'new')
        self.assertEqual(row['stateLabel'], 'Waiting')
        self.assertEqual(row['next'], {'label': 'Take it', 'action': 'take'})

    def test_a_closed_ticket_offers_no_next_step(self):
        self.ticket.mart369_action_done()
        self.assertIsNone(self.ticket._mart369_admin_row()['next'])
        self.assertFalse(self.ticket._mart369_admin_detail()['canReply'],
                         'hidden rather than offered and refused')

    def test_the_staff_shape_does_not_leak_into_the_shopper_one(self):
        """`_mart369_serialize` is the chat panel. Who else is in the queue,
        and who is handling it, are not part of that."""
        shopper = self.ticket._mart369_serialize()
        self.assertNotIn('customer', shopper)
        self.assertNotIn('assignee', shopper)
        self.assertNotIn('waited', shopper)

    def test_an_unknown_reference_is_empty_rather_than_an_error(self):
        self.assertEqual(self.Ticket.mart369_admin_detail('369S-NOPE'), {})
        self.assertEqual(self.Ticket.mart369_admin_detail(None), {})

    # ----------------------------------------------------------- filtering

    def _refs(self, **kwargs):
        return [t['ref'] for t
                in self.Ticket.mart369_admin_list(**kwargs)['tickets']]

    def test_needs_is_open_and_unanswered(self):
        self.assertIn(self.ticket.name, self._refs(tab='needs'))
        self.ticket._mart369_say('On its way', from_customer=False)
        self.assertNotIn(self.ticket.name, self._refs(tab='needs'),
                         'answered, so nobody is waiting on us')

    def test_search_matches_reference_customer_and_subject(self):
        self.assertIn(self.ticket.name, self._refs(tab='all', q=self.ticket.name))
        self.assertIn(self.ticket.name, self._refs(tab='all', q='never arrived'))
        self.assertNotIn(self.ticket.name,
                         self._refs(tab='all', q='nothing is called this'))

    def test_mine_narrows_to_the_signed_in_user(self):
        self.assertNotIn(self.ticket.name, self._refs(tab='all', mine=True))
        self.ticket.mart369_action_take()
        self.assertIn(self.ticket.name, self._refs(tab='all', mine=True))

    def test_the_tiles_count_everything_not_the_filtered_rows(self):
        self.Ticket.create({'partner_id': self.env.user.partner_id.id,
                            'subject': 'Somebody else entirely'})
        wide = self.Ticket.mart369_admin_list(tab='all')
        narrow = self.Ticket.mart369_admin_list(tab='all', q=self.ticket.name)
        self.assertEqual(wide['counts'], narrow['counts'])
        self.assertLess(len(narrow['tickets']), len(wide['tickets']))

    # ------------------------------------------------------------- writing

    def test_replying_claims_the_ticket_and_stamps_it(self):
        self.Ticket.mart369_admin_reply(self.ticket.name, 'We are looking')
        self.assertEqual(self.ticket.state, 'open')
        self.assertTrue(self.ticket.answered_at)
        self.assertEqual(self.ticket.user_id, self.env.user)

    def test_a_second_reply_does_not_move_the_first_answered_stamp(self):
        self.Ticket.mart369_admin_reply(self.ticket.name, 'We are looking')
        first = self.ticket.answered_at
        self.Ticket.mart369_admin_reply(self.ticket.name, 'Still looking')
        self.assertEqual(self.ticket.answered_at, first,
                         'first answered, not last')

    def test_an_empty_reply_is_refused(self):
        with self.assertRaises(Exception):
            self.Ticket.mart369_admin_reply(self.ticket.name, '   ')

    def test_a_closed_ticket_cannot_be_replied_to(self):
        self.ticket.mart369_action_done()
        with self.assertRaises(Exception):
            self.Ticket.mart369_admin_reply(self.ticket.name, 'Hello again')

    def test_waiting_on_the_customer_is_reachable_at_last(self):
        """The fifth state had no button anywhere, so a ticket parked on a
        customer was counted as one nobody had touched."""
        self.Ticket.mart369_admin_advance(self.ticket.name, 'wait')
        self.assertEqual(self.ticket.state, 'waiting')

    def test_an_invented_action_is_refused(self):
        with self.assertRaises(Exception):
            self.Ticket.mart369_admin_advance(self.ticket.name, 'delete')

    def test_a_ticket_can_be_handed_over_and_handed_back(self):
        self.Ticket.mart369_admin_assign(self.ticket.name, self.env.uid)
        self.assertEqual(self.ticket.user_id, self.env.user)
        self.Ticket.mart369_admin_assign(self.ticket.name, None)
        self.assertFalse(self.ticket.user_id, 'clearing it returns it to the pile')


@tagged('post_install', '-at_install')
class TestSupportAdminRoutes(Mart369OrderFixtures, HttpCase):

    def setUp(self):
        super().setUp()
        self.ticket = self.env['mart369.ticket']._mart369_open(
            self.partner, 'Where is my refund')
        self.shopper = self.env['res.users'].sudo().create({
            'name': 'A Shopper',
            'login': 'mart369_support_shopper',
            'password': 'mart369_support_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    def _send(self, method, path, payload=None):
        return self.url_open(
            path, data=json.dumps(payload or {}), headers=HEADERS, method=method)

    def test_a_shopper_is_refused_every_staff_route(self):
        """Refused, not filtered. The queue carries other people's complaints."""
        self.authenticate('mart369_support_shopper', 'mart369_support_shopper')
        ref = self.ticket.name
        self.assertEqual(self.url_open(LIST).status_code, 403)
        self.assertEqual(self.url_open(LIST + '/counts').status_code, 403)
        self.assertEqual(self.url_open(f'{LIST}/{ref}').status_code, 403)
        self.assertEqual(
            self._send('POST', f'{LIST}/{ref}/reply', {'text': 'hi'}).status_code, 403)
        self.assertEqual(
            self._send('PATCH', f'{LIST}/{ref}', {'state': 'done'}).status_code, 403)
        self.assertEqual(self.ticket.state, 'new', 'and nothing moved')

    def test_signed_out_is_sent_to_the_sign_in_page(self):
        """`auth='user'` answers 303 to /web/login rather than 401, and
        url_open follows it - so where the request landed is the proof."""
        response = self.url_open(LIST)
        self.assertIn('/web/login', response.url)
        self.assertNotIn('"ok": true', response.text)

    def test_staff_read_the_queue_and_answer_a_ticket(self):
        self.authenticate('admin', 'admin')
        listed = self.url_open(LIST + '?tab=all').json()
        self.assertTrue(listed['ok'])
        self.assertIn(self.ticket.name, [t['ref'] for t in listed['tickets']])
        self.assertIn('counts', listed)
        self.assertIn('staff', listed)

        replied = self._send('POST', f'{LIST}/{self.ticket.name}/reply',
                             {'text': 'Refund is on its way'})
        self.assertEqual(replied.status_code, 200)
        said = [m['text'] for m in replied.json()['ticket']['messages']]
        self.assertIn('Refund is on its way', said)
        self.assertEqual(self.ticket.state, 'open')

    def test_the_console_cannot_edit_what_the_customer_asked(self):
        """The allow-list is two keys, and anything else is refused rather
        than silently dropped."""
        self.authenticate('admin', 'admin')
        response = self._send('PATCH', f'{LIST}/{self.ticket.name}',
                              {'subject': 'Something else entirely'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'subject')
        self.assertEqual(self.ticket.subject, 'Where is my refund')

    def test_an_empty_reply_says_which_field(self):
        self.authenticate('admin', 'admin')
        response = self._send('POST', f'{LIST}/{self.ticket.name}/reply',
                              {'text': '  '})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'text')

    def test_a_made_up_reference_is_a_404(self):
        self.authenticate('admin', 'admin')
        self.assertEqual(self.url_open(LIST + '/369S-NOPE').status_code, 404)

    def test_counts_is_not_read_as_a_ticket_reference(self):
        """'counts' sits where a reference goes, so route order matters."""
        self.authenticate('admin', 'admin')
        payload = self.url_open(LIST + '/counts').json()
        self.assertTrue(payload['ok'])
        self.assertIn('needs', payload['counts'])
        self.assertNotIn('tickets', payload, 'counts only')
