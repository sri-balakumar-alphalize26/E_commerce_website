"""The figures on the dashboard's cards (24 Nov 2026). Nothing is sent."""
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestDashboardStats(TransactionCase):

    def setUp(self):
        super().setUp()
        self.down = False

        def gateway(rec, *args, **kwargs):
            if self.down:
                raise UserError('Cannot reach the gateway')
            return {'instance': {'state': 'open'}}
        p = patch.object(self.env.registry['whatsapp.session'], '_gateway_call', gateway)
        p.start()
        self.addCleanup(p.stop)
        self.ES = self.env['wa.employee.session']
        self.Log = self.env['wa.communication.log']
        self.one, self.two = self._card('Zz One', '+971500000071'), self._card('Zz Two', '+971500000072')

    def _card(self, name, number):
        session = self.env['whatsapp.session'].sudo().create({'name': name, 'gateway_api_key': 'test ' + number})
        employee = self.env['hr.employee'].create({'name': name})
        return self.ES.create({'employee_id': employee.id, 'session_id': session.id, 'phone_number': number})

    def _message(self, card, direction='incoming', status=None, phone='919811122233', at=None):
        message = self.env['whatsapp.message'].create({
            'session_id': card.session_id.id, 'phone': phone, 'message': 'x %s' % fields.Datetime.now(),
            'direction': direction, 'status': status or ('received' if direction == 'incoming' else 'sent')})
        self.assertEqual(message.employee_session_id, card)
        if at:
            message.flush_recordset()
            self.env.cr.execute('UPDATE whatsapp_message SET create_date = %s WHERE id = %s', [at, message.id])
            self.env.invalidate_all()
        return message

    def _typed(self, card, phone, at=None, direction='outgoing', text='typed', conversation=False):
        return self.Log.create({
            'employee_session_id': card.id, 'phone': phone, 'direction': direction, 'message_text': text,
            'message_date': at or fields.Datetime.now(), 'conversation_id': conversation and conversation.id})

    def _read(self, card, *names):
        self.env.invalidate_all()
        return self.ES.web_search_read([('id', '=', card.id)], {n: {} for n in names})['records'][0]

    def test_each_its_own(self):
        self._message(self.one)
        self._message(self.one, 'outgoing')
        self._message(self.two)
        names = ('total_messages', 'total_sent', 'total_received', 'unique_contacts')
        first, second = self._read(self.one, *names), self._read(self.two, *names)
        self.assertEqual([first[n] for n in names], [2, 1, 1, 1])
        self.assertEqual([second[n] for n in names], [1, 0, 1, 1])

    def test_old_number_keeps_its_own(self):
        self._message(self.one)
        self.one.write({'active': False})
        self.env.invalidate_all()
        row = self.ES.with_context(active_test=False).web_search_read(
            [('id', '=', self.one.id)], {'total_messages': {}})['records'][0]
        self.assertEqual(row['total_messages'], 1)

    def test_not_sent_is_not_sent(self):
        for status in ('pending', 'failed', 'blocked', 'sent', 'read'):
            self._message(self.one, 'outgoing', status)
        self.assertEqual(self._read(self.one, 'total_sent')['total_sent'], 2)

    def test_typed_and_its_contact(self):
        self._message(self.one, phone='919811122233')
        self._typed(self.one, '9811122233')
        self._typed(self.one, '919700000001')
        row = self._read(self.one, 'total_sent', 'unique_contacts', 'today_sent')
        self.assertEqual((row['total_sent'], row['unique_contacts'], row['today_sent']), (2, 2, 2))

    def test_the_day_in_india(self):
        self.env.user.tz = 'Asia/Kolkata'
        card = self.one.with_context(tz='Asia/Kolkata')
        # 20:00 UTC of the 10th is 01:30 of the 11th in India
        with patch.object(fields.Datetime, 'now', lambda *a, **k: datetime(2026, 11, 10, 20, 0)):
            self.assertEqual(card._today_start(), datetime(2026, 11, 10, 18, 30))
        self._typed(self.one, '919811122233', datetime(2026, 11, 10, 19, 0))      # 00:30 on the 11th
        self._typed(self.one, '919811122233', datetime(2026, 11, 10, 18, 0))      # 23:30 on the 10th
        self.assertEqual(self.one._figures(datetime(2026, 11, 10, 18, 30))[self.one.id][0], 1)

    def test_score_follows_the_day(self):
        Score = self.env['wa.quality.score']
        mine = [('employee_session_id', '=', self.one.id)]
        now = fields.Datetime.now()
        self._typed(self.one, '919811122233', now)
        Score._cron_compute_scores()
        first = Score.search(mine)
        self.assertEqual((len(first), first.period_messages), (1, 1))
        for _i in range(6):
            self._typed(self.one, '919811122233', now)
        Score._cron_compute_scores()
        self.assertEqual((len(Score.search(mine)), first.period_messages), (1, 7))
        self.assertTrue(self._read(self.one, 'has_score')['has_score'])

    def test_first_reply_of_a_person(self):
        chat = self.env['wa.conversation']._get_or_create(self.one, '919811122233')
        at = fields.Datetime.now() - timedelta(hours=3)
        asked = self._typed(self.one, chat.phone, at, 'incoming', 'price?', chat)
        bot = self._typed(self.one, chat.phone, at + timedelta(minutes=1), text='bot says', conversation=chat)
        reply = self.env['wa.auto.reply'].create({
            'employee_session_id': self.one.id, 'conversation_id': chat.id, 'trigger_message_id': asked.id,
            'reply_message': 'bot says'})
        reply.flush_recordset()
        self.env.cr.execute('UPDATE wa_auto_reply SET create_date = %s WHERE id = %s', [bot.message_date, reply.id])
        self.assertFalse(self._read(self.one, 'has_replies')['has_replies'])
        self._typed(self.one, chat.phone, at + timedelta(minutes=4), text='10', conversation=chat)
        self._typed(self.one, chat.phone, at + timedelta(minutes=60), text='and?', conversation=chat)
        row = self._read(self.one, 'has_replies', 'avg_response_minutes')
        self.assertTrue(row['has_replies'])
        self.assertAlmostEqual(row['avg_response_minutes'], 4, places=1)

    def _reply(self, card):
        self.env.invalidate_all()
        row = (self.one + self.two)._reply_status()[card.id]
        self.assertEqual(len(row.pop('waits')), row['waiting'])
        return row

    def test_reply_status(self):
        now = fields.Datetime.now().replace(microsecond=0)
        ago = lambda **k: now - timedelta(**k)  # noqa: E731
        self.assertEqual(self._reply(self.one), {'last': False, 'waiting': 0, 'oldest': False})
        self._message(self.one, at=ago(minutes=45))
        self._message(self.one, at=ago(minutes=10))
        self._message(self.one, phone='919822222222', at=ago(minutes=5))
        self._message(self.one, phone='919833333333', at=ago(hours=49))          # too old
        self._message(self.one, phone='120363000000000001@g.us', at=ago(hours=1))   # a group
        self.assertEqual(self._reply(self.one), {'last': False, 'waiting': 2, 'oldest': ago(minutes=45)})
        self.assertEqual(self._reply(self.two)['waiting'], 0, 'each its own')
        self.assertEqual(self.one._reply_status()[self.one.id]['waits'],
                         {'811122233': ago(minutes=45), '822222222': ago(minutes=5)}, 'each customer')
        # not a reply of a person
        self._message(self.one, 'outgoing', at=ago(minutes=4))                  # the system
        for status in ('failed', 'blocked', 'pending'):
            self._message(self.one, 'outgoing', status, at=ago(minutes=4))
        self.assertEqual(self._reply(self.one)['waiting'], 2)
        # typed on the phone: that chat waits no more, and the employee was active
        self._typed(self.one, '919811122233', ago(minutes=3))
        self.assertEqual(self._reply(self.one), {'last': ago(minutes=3), 'waiting': 1, 'oldest': ago(minutes=5)})
        # the customer writes again
        self._message(self.one, at=ago(minutes=2))
        self.assertEqual(self._reply(self.one)['waiting'], 2)

    def test_reply_today(self):
        self.assertEqual(self.one._reply_today(), {})
        chat = self.env['wa.conversation']._get_or_create(self.one, '919811122233')
        at = max(fields.Datetime.now() - timedelta(minutes=30), self.one._today_start())
        self._typed(self.one, chat.phone, at, 'incoming', 'price?', chat)
        self._typed(self.one, chat.phone, at + timedelta(minutes=6), text='10', conversation=chat)
        self._typed(self.one, chat.phone, at + timedelta(minutes=9), text='more', conversation=chat)
        count, average = self.one._reply_today()[self.one.id]
        self.assertEqual((count, round(average)), (1, 6))
        self.assertNotIn(self.two.id, (self.one + self.two)._reply_today())

    def test_reply_status_bot_and_manager(self):
        now = fields.Datetime.now().replace(microsecond=0)
        chat = self.env['wa.conversation']._get_or_create(self.one, '919811122233')
        self._message(self.one, at=now - timedelta(minutes=20))
        bot = self._typed(self.one, '919811122233', now - timedelta(minutes=19), text='bot says', conversation=chat)
        reply = self.env['wa.auto.reply'].create({
            'employee_session_id': self.one.id, 'conversation_id': chat.id, 'reply_message': 'bot says'})
        reply.flush_recordset()
        self.env.cr.execute('UPDATE wa_auto_reply SET create_date = %s WHERE id = %s', [bot.message_date, reply.id])
        self.assertEqual(self._reply(self.one)['waiting'], 1, 'the assistant does not end it')
        self.assertFalse(self._reply(self.one)['last'])
        manager = new_test_user(self.env, 'zz-reply-boss', groups='base.group_user')
        sent = self._message(self.one, 'outgoing', at=now - timedelta(minutes=10))
        self.env.cr.execute('UPDATE whatsapp_message SET create_uid = %s WHERE id = %s', [manager.id, sent.id])
        status = self._reply(self.one)
        self.assertEqual((status['waiting'], status['last']), (0, False), "answered, but not by the employee")
        self.one.employee_id.user_id = manager
        self.assertEqual(self._reply(self.one)['last'], now - timedelta(minutes=10), 'their own login')

    def test_nothing_yet_and_panel_down(self):
        self.down = True
        row = self._read(self.two, 'has_replies', 'has_score', 'total_messages', 'number_pretty')
        self.assertEqual((row['has_replies'], row['has_score'], row['total_messages']), (False, False, 0))
        self.assertTrue(row['number_pretty'].startswith('+971'))
