# -*- coding: utf-8 -*-
"""WA Tracker: the chats of two numbers, or of two people, are never one chat
and nothing of an old one is lost (23 Nov 2026)."""
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from .test_connect_number import ConnectCase

CUSTOMER = '919811122233'


class HistoryCase(ConnectCase):

    def setUp(self):
        super().setUp()
        self._add()
        self.second = self._session()
        self.state['971501234567'] = 'open'
        self.second._refresh_state(force=True)
        self.ES = self.env['wa.employee.session']
        self.All = self.ES.with_context(active_test=False)
        self.Conv, self.Log = self.env['wa.conversation'], self.env['wa.communication.log']
        self.link = self.ES.search([('session_id', '=', self.second.id)])

    def _in(self, text, session=None, phone=CUSTOMER, **ctx):
        return self.env['whatsapp.message'].with_context(**ctx).create({
            'session_id': (session or self.second).id, 'phone': phone, 'message': text, 'direction': 'incoming', 'status': 'received'})

    def _texts(self, link):
        return self.Log.search([('employee_session_id', '=', link.id)], order='id').mapped('message_text')

    def _remove(self, session):
        real = self.env.registry['whatsapp.session']._gateway_call

        def gateway(rec, method, path, payload=None, **kw):
            return {'ok': True} if path == '/v1/self' else real(rec, method, path, payload, **kw)
        with patch.object(self.env.registry['whatsapp.session'], '_gateway_call', gateway):
            session._remove_number()
        self.panel = {k: v for k, v in self.panel.items() if v != session.authorized_number}

    def _panel_number(self, session, number):
        """The panel gives this key another number."""
        self.panel[session.gateway_api_key] = number
        self.state[number] = 'open'
        session._fetch_panel_config()


@tagged('post_install', '-at_install')
class TestChatHistory(HistoryCase):

    def test_new_number_of_the_same_employee(self):
        self._in('one')
        self._remove(self.second)
        self._add('502223333')
        third = self._session('971502223333')
        self._in('two', third)
        new = self.ES.search([('employee_id', '=', self.anu.id)])
        self.assertNotEqual(new, self.link)
        self.assertEqual((self._texts(self.link), self._texts(new)), (['one'], ['two']))
        self.assertEqual((self.link.active, self.link.own_number, new.own_number), (False, '971501234567', '971502223333'))
        chats = self.Conv.search([('phone', '=', CUSTOMER), ('employee_id', '=', self.anu.id)])
        self.assertEqual(len(chats), 2, 'the same customer, two chats')
        self.assertTrue(self.link.until)

    def test_the_old_number_again_goes_on(self):
        self._in('one')
        self._remove(self.second)
        self._add('502223333')
        third = self._session('971502223333')
        self._in('two', third)
        self._remove(third)
        self._add()
        self.assertEqual(self.ES.search([('employee_id', '=', self.anu.id)]), self.link)
        self._in('three')
        self.assertEqual(self._texts(self.link), ['one', 'three'])
        self.assertEqual(self.Conv.search_count([('employee_session_id', '=', self.link.id), ('phone', '=', CUSTOMER)]), 1)

    def test_to_another_employee_it_starts_empty(self):
        self._in('mine')
        self._remove(self.second)
        other = self.env['hr.employee'].create({'name': 'Zz Other'})
        self._add(employee_id=other.id)
        self._in('theirs')
        new = self.ES.search([('employee_id', '=', other.id)])
        self.env['wa.communication.log']._cron_sync_messages()
        self.assertEqual((self._texts(self.link), self._texts(new)), (['mine'], ['theirs']))
        self.assertEqual(self.link.employee_id, self.anu)

    def test_the_panel_changes_the_number(self):
        self._in('one')
        self._panel_number(self.second, '971504444444')
        self.assertEqual(self.second.authorized_number, '971504444444')
        new = self.ES.search([('session_id', '=', self.second.id)])
        self.assertNotEqual(new, self.link)
        self.assertEqual((new.employee_id, new.own_number), (self.anu, '971504444444'))
        self._in('two')
        self._in('late', wa_own_number='971501234567')
        self.assertEqual((self._texts(self.link), self._texts(new)), (['one', 'late'], ['two']), 'one that waited in the panel')
        self._panel_number(self.second, '971501234567')
        self._in('back')
        self.assertEqual(self._texts(self.link), ['one', 'late', 'back'])

    def test_filled_for_the_first_time_is_no_change(self):
        fresh = self.env['whatsapp.session'].create({'name': 'Fresh', 'gateway_api_key': 'zz-fresh'})
        third = self.env['hr.employee'].create({'name': 'Zz Third'})
        link = self.ES.create({'employee_id': third.id, 'session_id': fresh.id, 'phone_number': '+971506666666'})
        self._in('one', fresh)
        fresh.authorized_number = '971506666666'
        self.assertEqual(self.ES.search([('session_id', '=', fresh.id)]), link)
        self._in('two', fresh)
        self.assertEqual(self._texts(link), ['one', 'two'])

    def test_without_chats_only_the_values_change(self):
        n = self.All.search_count([])
        self._panel_number(self.second, '971504444444')
        self.assertEqual(self.All.search_count([]), n)
        self.assertEqual((self.link.own_number, self.link.active), ('971504444444', True))

    def test_settings_go_along(self):
        self.link.write({'auto_reply_max_products': 9, 'notes': 'n'})
        self._in('one')
        self._panel_number(self.second, '971504444444')
        new = self.ES.search([('session_id', '=', self.second.id)])
        self.assertEqual((new.auto_reply_max_products, new.notes), (9, 'n'))

    def test_other_employee(self):
        self._in('one')
        other = self.env['hr.employee'].create({'name': 'Zz Other'})
        action = self.env['wa.employee.handover'].create({'session_id': self.link.id, 'employee_id': other.id}).action_do()
        new = self.ES.browse(action['res_id'])
        self.assertEqual((new.employee_id, new.session_id, new.active, self.link.active), (other, self.second, True, False))
        self._in('two')
        self.assertEqual((self._texts(self.link), self._texts(new)), (['one'], ['two']))
        with self.assertRaisesRegex(UserError, 'has a number'):
            new._go_on_with(employee=self.ravi)

    def test_what_has_chats_is_not_changed_or_deleted(self):
        other = self.env['hr.employee'].create({'name': 'Zz Other'})
        self.link.write({'employee_id': other.id})
        self.link.write({'employee_id': self.anu.id})          # nothing on it yet
        self._in('one')
        for vals in ({'employee_id': other.id}, {'session_id': self.first.id}, {'phone_number': '+971509999999'}):
            with self.assertRaisesRegex(UserError, 'has chats'):
                self.link.write(vals)
        self.link.write({'phone_number': '+971 50 123 4567', 'notes': 'x', 'employee_id': self.anu.id})
        with self.assertRaisesRegex(UserError, 'Archive'):
            self.link.unlink()
        with self.assertRaises(Exception), self.env.cr.savepoint(), mute_logger('odoo.sql_db'):
            self.anu.unlink()
            self.env.flush_all()
        self.assertTrue(self.Log.search([('employee_session_id', '=', self.link.id)]))

    @mute_logger('odoo.sql_db')
    def test_one_at_a_time(self):
        with self.assertRaises(Exception), self.env.cr.savepoint():
            self.ES.create({'employee_id': self.anu.id, 'session_id': self.first.id, 'phone_number': '+971500000001'})
            self.env.flush_all()

    def test_sync_takes_nothing_twice_and_nothing_of_others(self):
        self._in('one')
        self._panel_number(self.second, '971504444444')
        self.env['whatsapp.message'].search([]).write({})
        for _i in range(2):
            self.Log._cron_sync_messages()
        new = self.ES.search([('session_id', '=', self.second.id)])
        self.assertEqual((self._texts(self.link), self._texts(new)), (['one'], []))

    def test_counters_per_number(self):
        self._in('one')
        self._in('two')
        self._panel_number(self.second, '971504444444')
        self._in('three')
        new = self.ES.search([('session_id', '=', self.second.id)])
        (self.link | new)._compute_stats()
        self.assertEqual((self.link.total_messages, new.total_messages), (2, 1))
        self.assertEqual(self.env['whatsapp.message'].search_count(new.action_view_messages()['domain']), 1)

    def test_groups_go_on_with_the_new_one(self):
        group = self.env['sa.sales.group'].create({'name': 'Zz g', 'group_jid': '71@g.us', 'session_id': self.second.id})
        group.employee_session_id = self.link
        self._in('one')
        self._panel_number(self.second, '971504444444')
        new = self.ES.search([('session_id', '=', self.second.id)])
        self.assertEqual(group.employee_session_id, new)
        self.assertEqual(group._sa_ensure_employee_session(), new)

    def test_a_group_does_not_bring_back_the_old_number(self):
        group = self.env['sa.sales.group'].create({'name': 'Zz g', 'group_jid': '71@g.us', 'session_id': self.second.id})
        self._in('one')
        self.link.active = False
        self.second.with_context(x=1).write({'authorized_number': '971504444444'})
        found = group._sa_ensure_employee_session()
        self.assertNotEqual(found, self.link)
        self.assertFalse(self.link.active)

    def test_no_auto_reply_on_an_old_number(self):
        self.link.auto_reply_enabled = True
        self._in('one')
        self._panel_number(self.second, '971504444444')
        with patch.object(self.env.registry['whatsapp.message'], '_schedule_auto_reply') as fire:
            self._in('late', wa_own_number='971501234567')
            fire.assert_not_called()

    def test_our_number_on_every_message(self):
        self.assertEqual(self._in('one').own_number, '971501234567')
        out = self.env['whatsapp.message'].create({'session_id': self.second.id, 'phone': CUSTOMER, 'message': 'x', 'direction': 'outgoing'})
        self.assertEqual((out.own_number, out.employee_session_id), ('971501234567', self.link))
        mail = self.env['whatsapp.message'].create({'session_id': self.second.id, 'phone': 'a@b.c', 'message': 'x',
                                                    'direction': 'outgoing', 'channel': 'email'})
        self.assertFalse(mail.own_number)

    # ------------------------------------------------------------ the old, mixed chats
    def _mixed(self):
        """As it was: one employee session, two numbers."""
        rows = [('a1', '971508888888', CUSTOMER), ('a2', '971508888888', CUSTOMER), ('b1', '971501234567', CUSTOMER),
                ('a3', '971508888888', '919811144455'), ('b2', '971501234567', CUSTOMER)]
        messages = self.env['whatsapp.message']
        for text, number, phone in rows:
            m = self._in(text, phone=phone)
            m.write({'own_number': number})
            messages |= m
        messages.write({'employee_session_id': False})
        return messages

    def test_split(self):
        self._mixed()
        total = self.Log.search_count([('employee_session_id', '=', self.link.id)])
        self.assertEqual(total, 5)
        done = self.ES._split_by_number()
        old = self.All.search([('employee_id', '=', self.anu.id), ('active', '=', False)])
        self.assertEqual((old.own_number, done[self.link.id]), ('971508888888', {'971508888888': 3, '971501234567': 2}))
        self.assertEqual((self._texts(old), self._texts(self.link)), (['a1', 'a2', 'a3'], ['b1', 'b2']))
        chats = {(c.employee_session_id, c.phone): c.total_messages for c in self.Conv.search([('employee_id', '=', self.anu.id)])}
        self.assertEqual(chats, {(old, CUSTOMER): 2, (old, '919811144455'): 1, (self.link, CUSTOMER): 2},
                         'an emptied chat is not left behind')
        self.assertTrue(old.until and old.since)
        before = [(m.id, m.employee_session_id.id) for m in self.env['whatsapp.message'].search([('session_id', '=', self.second.id)])]
        n = self.All.search_count([])
        self.ES._split_by_number()
        self.assertEqual(before, [(m.id, m.employee_session_id.id)
                                  for m in self.env['whatsapp.message'].search([('session_id', '=', self.second.id)])])
        self.assertEqual(self.All.search_count([]), n)
        self.Log._cron_sync_messages()
        self.assertEqual((self._texts(old), self._texts(self.link)), (['a1', 'a2', 'a3'], ['b1', 'b2']))

    def test_split_moves_alerts_and_the_enquirys_chat(self):
        messages = self._mixed()
        log = self.Log.search([('message_id', '=', messages[0].id)])
        rule = self.env['wa.keyword.alert.rule'].search([], limit=1)
        alert = self.env['wa.keyword.alert.log'].create({'employee_session_id': self.link.id, 'log_entry_id': log.id, 'rule_id': rule.id})
        group = self.env['sa.sales.group'].create({'name': 'Zz g', 'group_jid': '72@g.us', 'session_id': self.second.id})
        request = self.env['sa.group.request'].create({
            'group_id': group.id, 'requester_phone': CUSTOMER, 'raw_text': 'x', 'state': 'sourcing',
            'sourcing_deadline': fields.Datetime.now(), 'conversation_id': log.conversation_id.id})
        messages[0].sa_request_id = request.id
        self.ES._split_by_number()
        old = self.All.search([('employee_id', '=', self.anu.id), ('active', '=', False)])
        self.assertEqual((alert.employee_session_id, alert.employee_id), (old, self.anu))
        self.assertEqual(request.conversation_id.employee_session_id, old)

    def test_typed_on_the_phone(self):
        def payload(wa_id, text, jid=CUSTOMER + '@s.whatsapp.net', me=True, **message):
            return {'event': 'messages.upsert', 'data': {'messageTimestamp': 1795487231, 'message': message or {'conversation': text},
                    'key': {'id': wa_id, 'fromMe': me, 'remoteJid': jid}}}
        self.assertFalse(self.Log._typed_values(payload('G', 'x', jid='7@g.us'), 'x'), 'a group')
        self.assertFalse(self.Log._typed_values(payload('I', 'x', me=False), 'x'), 'received')
        self.assertFalse(self.Log._typed_values(payload('R', '', reactionMessage={'text': 'y'}), ''))
        self.assertIn('look', self.Log._typed_values(payload('P', '', imageMessage={'caption': 'look'}), '')[2])
        values = self.Log._typed_values(payload('T1', 'hiloo'), 'hiloo')
        messages = self.env['whatsapp.message'].search_count([])
        log = self.Log._typed_store(self.second.id, '971501234567', values)
        self.assertEqual((log.direction, log.message_text, log.employee_session_id, log.conversation_id.phone),
                         ('outgoing', 'hiloo', self.link, CUSTOMER))
        self.assertEqual(self.env['whatsapp.message'].search_count([]), messages, 'no cap, no bot')
        self.assertEqual(self.link.total_sent, 1)
        self.assertFalse(self.Log._typed_store(self.second.id, '971501234567', values), 'once')
        row = {'session_id': self.second.id, 'phone': CUSTOMER, 'direction': 'outgoing', 'status': 'sent'}
        self.env['whatsapp.message'].create(dict(row, message='by Odoo', wa_message_id='T2'))
        now = fields.Datetime.now()
        self.assertFalse(self.Log._typed_store(self.second.id, '971501234567', ('T2', CUSTOMER, 'by Odoo', now)))
        late = self.Log._typed_store(self.second.id, '971501234567', ('T3', CUSTOMER, 'slow', now))
        self.env['whatsapp.message'].create(dict(row, message='slow', wa_message_id='T3'))
        self.Log._cron_sync_messages()
        self.assertFalse(late.exists(), 'Odoo sent it after all: not twice')
        self.ES._split_by_number()
        self.assertIn('hiloo', self._texts(self.link))

    def test_a_number_without_an_employee(self):
        free = self.env['whatsapp.session'].create({'name': 'Zz free', 'gateway_api_key': 'zz-free', 'authorized_number': '971507777777'})
        ids = [n['id'] for n in self.ES.numbers_without_employee()]
        self.assertIn(free.id, ids)
        self.assertNotIn(self.second.id, ids, 'it has a card')

    def test_one_number_once(self):
        with self.assertRaisesRegex(Exception, 'only once'), self.env.cr.savepoint():
            self.env['whatsapp.session'].create({'name': 'Zz twin', 'gateway_api_key': 'zz-twin', 'authorized_number': '971501234567'})
        off = self.env['whatsapp.session'].create({'name': 'Zz old', 'gateway_api_key': 'zz-old', 'active': False,
                                                   'phone_number': '971509999999', 'authorized_number': '971501234567'})
        self.assertEqual(off.shown_number, '+971 50 999 9999', 'its own phone')
        self.assertEqual(self.second.shown_number, '+971 50 123 4567')
        with self.assertRaisesRegex(UserError, 'only once'):
            off._turn_on()

    def test_the_phones_own_chats(self):
        from odoo.addons.whatsapp_employee_tracker.models import phone_chats
        phone_chats._MEMO.clear()
        self.addCleanup(phone_chats._MEMO.clear)
        jid, lid = CUSTOMER + '@s.whatsapp.net', '55@lid'

        def msg(wid, jid, text, at, me=False, **key):
            return {'key': dict({'id': wid, 'remoteJid': jid, 'fromMe': me}, **key), 'message': {'conversation': text}, 'messageTimestamp': at,
                    'pushName': 'Push', 'MessageUpdate': [{'status': 'READ'}, {'status': 'DELIVERY_ACK'}] if me else []}
        asked = []

        def gateway(rec, method, path, payload=None, **kw):
            asked.append((path.split('/')[2], payload))
            if 'findChats' in path:
                return [{'remoteJid': jid, 'lastMessage': msg('a', jid, 'old', 100), 'unreadCount': 1},
                        {'remoteJid': lid, 'lastMessage': msg('b', lid, 'hi', 300, True, remoteJidAlt=jid), 'unreadCount': 0},
                        {'remoteJid': '9@g.us', 'lastMessage': msg('c', '9@g.us', 'grp', 200)},
                        {'remoteJid': '1@newsletter', 'lastMessage': msg('d', '1@newsletter', 'n', 400)}]
            if 'findContacts' in path:
                return [{'remoteJid': '9@g.us', 'pushName': 'My group'}]
            at = payload['where']['key']['remoteJid']
            rows = {jid: [msg('a', jid, 'old', 100)], lid: [msg('b', lid, 'hi', 300, True)], '9@g.us': [msg('c', '9@g.us', 'grp', 200)]}[at]
            return {'messages': {'pages': 2 if at == jid else 1, 'records': rows}}
        with patch.object(self.env.registry['whatsapp.session'], '_gateway_call', gateway):
            chats = self.link.phone_chats()
            self.assertEqual([(c['id'], c['name'], c['preview']) for c in chats], [(jid, 'Push', 'hi'), ('9@g.us', 'My group', 'grp')])
            one = self.link.phone_messages(jid)
            self.assertEqual([(m['message_text'], m['direction'], m['status']) for m in one['messages']],
                             [('old', 'incoming', 'received'), ('hi', 'outgoing', 'read')])
            self.assertTrue(one['more'])
            self.assertEqual(self.link.phone_messages('9@g.us')['messages'][0]['sender'], 'Push')
            self.assertEqual([a for a, _p in asked].count('findChats'), 1, 'kept for a moment')
            with self.assertRaises(AccessError):
                self.link.phone_messages('77777@s.whatsapp.net')
            user = new_test_user(self.env, 'zz-not-admin', groups='base.group_user')
            with self.assertRaises(AccessError):
                self.link.with_user(user).phone_chats()

    def test_names_and_live_notice(self):
        from odoo.addons.whatsapp_employee_tracker.models import phone_chats
        phone_chats._MEMO.clear()
        self.addCleanup(phone_chats._MEMO.clear)
        jid, lid = CUSTOMER + '@s.whatsapp.net', '77@lid'
        Name = self.env['wa.phone.name']

        def msg(wid, jid, text, at, me=False, push='', **key):
            return {'key': dict({'id': wid, 'remoteJid': jid, 'fromMe': me}, **key), 'message': {'conversation': text},
                    'messageTimestamp': at, 'pushName': push}
        rows = [{'remoteJid': jid, 'lastMessage': msg('a', jid, 'ours', 300, True, 'Our Shop')},
                {'remoteJid': lid, 'lastMessage': msg('b', lid, 'ours too', 200, True, 'Our Shop')}]
        calls = []

        def gateway(rec, method, path, payload=None, **kw):
            calls.append(path)
            if 'findChats' in path:
                return rows
            if 'findContacts' in path:
                return [{'remoteJid': jid, 'pushName': CUSTOMER}]
            return {'messages': {'pages': 1, 'records': [msg('c', payload['where']['key']['remoteJid'], 'hi', 100, push='Ravi')]}}
        told = []
        with patch.object(self.env.registry['whatsapp.session'], '_gateway_call', gateway), \
                patch.object(self.env.registry['res.groups'], '_bus_send', lambda rec, kind, data, **kw: told.append((rec, kind, data))):
            names = {c['id']: c['name'] for c in self.link.phone_chats()}
            self.assertEqual(names, {jid: '+' + CUSTOMER, lid: 'Hidden number'}, 'a number is no name, ours is not theirs')
            Name._look(self.second, jid)
            self.assertEqual(self.link.phone_chats()[0]['name'], 'Ravi', 'what they call themselves')
            Name._teach(self.second.id, {jid: ('', '')})
            self.assertEqual(Name._taught(self.second.id)[jid][0], 'Ravi', 'learnt once, it stays')
            asked = calls.count('/chat/findChats/%s' % self.second.instance_name)
            self.second._phone_new(msg('d', lid, 'secret', 400, push='Meena', remoteJidAlt='9715@s.whatsapp.net'))
            self.assertEqual(told, [(self.env.ref('base.group_system'), 'wa_tracker_new', {'session': self.second.id, 'chat': lid})])
            first = self.link.phone_chats()[0]
            self.assertEqual((first['id'], first['name'], first['preview'], first['unread']), ('9715@s.whatsapp.net', 'Meena', 'secret', 1))
            self.assertEqual(calls.count('/chat/findChats/%s' % self.second.instance_name), asked, 'not asked again')
            del told[:]
            row = {'session_id': self.second.id, 'phone': CUSTOMER, 'direction': 'outgoing', 'message': 'x'}
            waiting = self.env['whatsapp.message'].create(dict(row, status='pending'))
            self.assertFalse(told)
            waiting.status = 'sent'
            self.assertEqual([t[2]['chat'] for t in told], [jid])
            self._in('y')
        self.env.registry.clear_cache()

    def test_unknown_stays_where_it_is(self):
        m = self._in('x')
        m.write({'own_number': False, 'employee_session_id': False})
        self.ES._split_by_number()
        self.assertEqual((m.employee_session_id, self._texts(self.link)), (self.link, ['x']))

    def test_screens(self):
        for model, kinds in (('wa.conversation', ('kanban', 'list', 'form', 'search')), ('wa.communication.log', ('list', 'form', 'search')),
                             ('wa.keyword.alert.log', ('list', 'form')), ('wa.employee.session', ('list', 'form', 'search')),
                             ('wa.employee.handover', ('form',)), ('wa.response.time.stat', ('list',))):
            self.env[model].get_views([(False, k) for k in kinds])
        self._in('one')
        self.assertTrue(self.Conv.search([('employee_session_id.active', '=', True), ('phone', '=', CUSTOMER)]))
        self._panel_number(self.second, '971504444444')
        self.assertTrue(self.Conv.search([('employee_session_id.active', '=', False), ('phone', '=', CUSTOMER)]))
        self.assertEqual(self.link.display_name, 'Zz Anu, +971 50 123 4567')


@tagged('post_install', '-at_install')
class TestChatPages(HttpCase):

    def _call(self, path, **params):
        return self.make_jsonrpc_request(path, params)

    def test_pages(self):
        session = self.env['whatsapp.session'].create({'name': 'Zz', 'gateway_api_key': 'zz-page', 'authorized_number': '971501234567'})
        employee = self.env['hr.employee'].create({'name': 'Zz Page'})
        ES = self.env['wa.employee.session']
        link = ES.create({'employee_id': employee.id, 'session_id': session.id, 'phone_number': '+971501234567'})
        Message = self.env['whatsapp.message']
        row = {'session_id': session.id, 'phone': CUSTOMER, 'direction': 'incoming', 'status': 'received'}
        Message.create(dict(row, message='one'))
        session.authorized_number = '971504444444'
        new = ES.search([('session_id', '=', session.id)])
        Message.create(dict(row, message='two'))
        new_test_user(self.env, 'zz-page-user', groups='base.group_user', password='zz-page-user')
        new_test_user(self.env, 'zz-page-portal', groups='base.group_portal', password='zz-page-portal')
        self.authenticate('zz-page-user', 'zz-page-user')
        person = [p for p in self._call('/wa_tracker/employee_sessions') if p['id'] == employee.id][0]
        self.assertEqual([(n['id'], n['current'], n['number']) for n in person['numbers']],
                         [(new.id, True, '+971 50 444 4444'), (link.id, False, '+971 50 123 4567')])
        one = self._call('/wa_tracker/conversations', employee_session_id=link.id)
        self.assertEqual([(c['total_messages'], c['own_number'], c['own_current']) for c in one], [(1, '+971 50 123 4567', False)])
        self.assertEqual([m['message_text'] for m in self._call('/wa_tracker/messages', conversation_id=one[0]['id'])], ['one'])
        both = self._call('/wa_tracker/conversations', employee_id=employee.id)
        self.assertEqual({c['employee_session_id'] for c in both}, {link.id, new.id})
        everybody = {c['employee_session_id'] for c in self._call('/wa_tracker/conversations')}
        self.assertIn(new.id, everybody)
        self.assertNotIn(link.id, everybody, 'an old number is not among the present ones')
        self.assertEqual(link.action_open_chats()['context']['active_employee_session_id'], link.id)
        self.authenticate('zz-page-portal', 'zz-page-portal')
        for path, params in (('/wa_tracker/employee_sessions', {}), ('/wa_tracker/conversations', {}),
                             ('/wa_tracker/messages', {'conversation_id': one[0]['id']})):
            with self.assertRaises(Exception, msg=path), mute_logger('odoo.http'):
                self._call(path, **params)
