"""The figures on the dashboard's cards (24 Nov 2026). Nothing is sent."""
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


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

    def test_nothing_yet_and_panel_down(self):
        self.down = True
        row = self._read(self.two, 'has_replies', 'has_score', 'total_messages', 'number_pretty')
        self.assertEqual((row['has_replies'], row['has_score'], row['total_messages']), (False, False, 0))
        self.assertTrue(row['number_pretty'].startswith('+971'))
