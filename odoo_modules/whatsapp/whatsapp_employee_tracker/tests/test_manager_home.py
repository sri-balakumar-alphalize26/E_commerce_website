"""The manager's screen: replied or not (25 Nov 2026). Nothing is sent."""
import calendar
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.whatsapp_employee_tracker.models import phone_chats


@tagged('post_install', '-at_install')
class TestManagerHome(TransactionCase):

    def setUp(self):
        super().setUp()
        phone_chats._MEMO.clear()
        self.addCleanup(phone_chats._MEMO.clear)
        self.rows, self.calls = [], []

        def gateway(rec, method, path, payload=None, **kw):
            self.calls.append((rec.id, path, payload))
            if 'findChats' in path:
                return self.rows
            return {'instance': {'state': 'open'}} if 'connectionState' in path else []
        p = patch.object(self.env.registry['whatsapp.session'], '_gateway_call', gateway)
        p.start()
        self.addCleanup(p.stop)
        self.env['wa.employee.session'].search([]).write({'active': False})
        self.sri, self.watch = self._number('Sri', '919000000001'), self._number('Watch', '919000000009')
        employee = self.env['hr.employee'].create({'name': 'Zz Sri'})
        self.card = self.env['wa.employee.session'].create(
            {'employee_id': employee.id, 'session_id': self.sri.id, 'phone_number': '+919000000001'})

    def _number(self, name, phone):
        return self.env['whatsapp.session'].sudo().create({
            'name': name, 'gateway_api_key': 'test ' + phone, 'authorized_number': phone, 'instance_name': 'co-' + phone,
            'status': 'connected', 'company_id': self.env.company.id})

    def _chat(self, jid, mine, minutes=5, **key):
        at = calendar.timegm((fields.Datetime.now() - timedelta(minutes=minutes)).timetuple())
        return {'remoteJid': jid, 'lastMessage': {'key': dict({'id': 'X', 'remoteJid': jid, 'fromMe': mine}, **key),
                                                  'pushName': 'Asker', 'message': {'conversation': 'hello'}, 'messageTimestamp': at}}

    def _home(self, own=('000000001',)):
        phone_chats._MEMO.clear()
        return {c['id']: c for c in self.card._home_chats(set(own))}

    def test_replied_or_not(self):
        self.rows = [self._chat('919811111111@s.whatsapp.net', False), self._chat('919822222222@s.whatsapp.net', True),
                     self._chat('919833333333@s.whatsapp.net', False, minutes=49 * 60),
                     self._chat('1@g.us', False), self._chat('2@g.us', True),
                     self._chat('3@g.us', False, participantAlt='919000000002@s.whatsapp.net')]
        found = self._home(('000000001', '000000002'))
        self.assertEqual({k.split('@')[0]: c['state'] for k, c in found.items()},
                         {'919811111111': 'no', '919822222222': 'yes', '919833333333': 'old', '1': 'no', '2': 'yes', '3': 'yes'})
        self.assertTrue(found['1@g.us']['group'])
        self.assertEqual((found['1@g.us']['last'], found['1@g.us']['tick']), ('X', ''))
        self.rows = [self._chat('5@g.us', False), dict(self._chat('919844444444@s.whatsapp.net', True))]
        self.rows[0].update(pushName='Asker')
        self.rows[0]['lastMessage']['message'] = {}
        self.rows[1]['lastMessage']['status'] = 'PENDING'
        later = self._home()
        self.assertEqual((later['5@g.us']['sender'], later['5@g.us']['preview']), ('', 'Message'), 'its own name is not repeated')
        self.assertEqual(later['919844444444@s.whatsapp.net']['tick'], '', 'no clock for ever')
        self.assertEqual((found['2@g.us']['mine'], found['2@g.us']['unread'], found['1@g.us']['pic']), (True, 0, ''))
        self.assertEqual({c['preview'] for c in found.values()}, {'hello'}, 'the text as it is')
        self.assertEqual(found['1@g.us']['sender'], 'Asker')

    def test_wrong_words(self):
        rule = self.env['wa.keyword.alert.rule'].create(
            {'name': 'Zz', 'keywords': 'zzrude', 'match_type': 'contains', 'category': 'profanity', 'severity': 'high'})
        other = self.env['wa.keyword.alert.rule'].create(
            {'name': 'Zz2', 'keywords': 'salary', 'match_type': 'contains', 'category': 'policy', 'severity': 'high'})
        for used, text, way in ((rule, 'you zzrude', 'outgoing'), (other, 'salary', 'outgoing'), (rule, 'zzrude you', 'incoming')):
            log = self.env['wa.communication.log'].create({
                'employee_session_id': self.card.id, 'phone': '919811111111', 'direction': way, 'message_text': text,
                'message_date': fields.Datetime.now()})
            self.env['wa.keyword.alert.log'].search([('log_entry_id', '=', log.id)]).unlink()
            self.env['wa.keyword.alert.log'].create({
                'employee_session_id': self.card.id, 'log_entry_id': log.id, 'rule_id': used.id, 'matched_keywords': used.keywords,
                'message_text': text, 'message_direction': way, 'phone': '919811111111', 'message_date': fields.Datetime.now()})
        self.rows = [self._chat('919811111111@s.whatsapp.net', True), self._chat('919822222222@s.whatsapp.net', True)]
        found = self._home()
        self.assertEqual(found['919811111111@s.whatsapp.net']['wrong'], {'words': ['zzrude'], 'texts': ['you zzrude']})
        self.assertFalse(found['919822222222@s.whatsapp.net']['wrong'])
