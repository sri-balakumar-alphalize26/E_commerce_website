# -*- coding: utf-8 -*-
"""Several numbers in one database (23 Nov 2026): connect one from Odoo, the
checks, the offline alert. The panel is a fake; nothing is sent."""
import base64
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

SENDS = ('/message/', '/chat/')


def setup_key(token):
    return 'wa1_' + base64.urlsafe_b64encode(('https://panel.test|' + token).encode()).decode().rstrip('=')


@tagged('post_install', '-at_install')
class ConnectCase(TransactionCase):

    def setUp(self):
        super().setUp()
        env = self.env
        self.env['whatsapp.session'].sudo().search([]).write({'active': False})
        box = self
        # the panel: token -> number
        self.panel = {'tokA': '971500000001'}
        self.state = {'971500000001': 'open'}
        self.may_add, self.calls, self.groups_of, self.invite = 5, [], {}, {}
        self.down = False

        def gateway(rec, method, path, payload=None, timeout=None, extra_headers=None):
            box.calls.append((method, path, rec.id, dict(extra_headers or {})))
            if any(path.startswith(p) for p in SENDS):
                raise AssertionError('nothing may be sent: %s' % path)
            if box.down:
                raise UserError('Cannot reach the gateway')
            number = box.panel.get(rec.sudo().gateway_api_key)
            if not number:
                raise UserError('The gateway refused the request (HTTP 403).\ntoken not registered')
            if path.startswith('/v1/numbers?check='):
                return {'check': box.where.get(path.split('=')[1], 'new'), 'in_use': box.in_use}
            if path == '/v1/numbers' and method == 'GET':
                return {'may_add': box.may_add, 'numbers': [{'authorized_number': n} for n in box.panel.values()] + box.unused,
                        'free': [f for f in box.free if f['authorized_number'] not in box.panel.values()]}
            if path == '/v1/numbers':
                if not box.may_add:
                    raise UserError('The gateway refused the request (HTTP 403).\nadding numbers from Odoo is not allowed')
                if payload['number'] in box.panel.values() and payload['number'] not in box.lost:
                    raise UserError('The gateway refused the request (HTTP 409).\n+%s is already connected' % payload['number'])
                token = 'tok-%s-%s' % (payload['number'], len(box.calls))
                box.panel = {k: v for k, v in box.panel.items() if v != payload['number']}
                box.panel[token] = payload['number']
                box.state.setdefault(payload['number'], 'connecting')
                return {'key': setup_key(token), 'authorized_number': payload['number']}
            if path == '/v1/config':
                return {'instance': 'co-' + number, 'tenant_label': 'Co', 'whatsapp': {'authorized_number': number}, 'email': {}}
            if path == '/v1/qr':
                return {'state': box.state[number], 'qr': 'data:image/png;base64,QR' + number}
            if path.startswith('/instance/connectionState'):
                return {'instance': {'state': box.state[number]}}
            if path.startswith('/group/fetchAllGroups'):
                return [{'id': j, 'subject': n, 'size': 4} for j, n in box.groups_of.get(number, [])]
            if path.startswith('/group/inviteCode'):
                jid = path.split('groupJid=')[1]
                return {'inviteUrl': box.invite.get(jid, '')}
            return {}
        self.unused = []
        self.lost, self.free, self.where, self.in_use = set(), [], {}, False
        p = patch.object(env.registry['whatsapp.session'], '_gateway_call', gateway)
        p.start()
        self.addCleanup(p.stop)
        self.first = env['whatsapp.session'].sudo().create({'name': 'Area 1', 'gateway_api_key': setup_key('tokA')})
        self.first._fetch_panel_config()
        self.first._refresh_state(force=True)
        self.ravi = env['hr.employee'].create({'name': 'Zz Ravi'})
        self.anu = env['hr.employee'].create({'name': 'Zz Anu'})
        env['wa.employee.session'].create({'employee_id': self.ravi.id, 'session_id': self.first.id, 'phone_number': '+971500000001'})
        self.ae, self.india = env.ref('base.ae'), env.ref('base.in')
        self.Connect = env['whatsapp.connect']

    def _add(self, number='501234567', country=None, **vals):
        return self.Connect.add(dict({'country_id': (country or self.ae).id, 'number': number,
                                      'employee_id': self.anu.id, 'company_id': self.env.company.id}, **vals))

    def _session(self, number='971501234567'):
        return self.env['whatsapp.session'].search([('authorized_number', '=', number)])


@tagged('post_install', '-at_install')
class TestConnectNumber(ConnectCase):

    # ------------------------------------------------------------ digits
    def test_digits_by_country(self):
        for code, n in (('AE', 9), ('IN', 10), ('OM', 8), ('SA', 9), ('KW', 8), ('CN', 11)):
            rule = self.Connect._rule(self.env['res.country'].search([('code', '=', code)]))
            self.assertEqual(rule['max'], n, (code, rule))
        rows = self.Connect._countries()
        self.assertGreater(len(rows), 200)
        self.assertTrue(all(r['dial'].isdigit() and 0 < r['min'] <= r['max'] <= 17 for r in rows))

    def test_the_server_checks_too(self):
        number = lambda t, c=None: self.Connect._number(c or self.ae, t)  # noqa: E731
        self.assertEqual(number('501234567'), '971501234567')
        self.assertEqual(number('0501234567'), '971501234567', 'a leading 0')
        self.assertEqual(number('971501234567'), '971501234567', 'the code typed as well')
        self.assertEqual(number('98765 43210', self.india), '919876543210')
        for bad in ('', '50123', '50123456789', 'abc', '50-1234567', '+971501234567', '000000000', '111111111'):
            with self.assertRaises(UserError, msg=bad):
                number(bad)
        with self.assertRaises(UserError):
            self.Connect._number(self.env['res.country'], '501234567')
        self.assertEqual(self.Connect.check_number(self.ae.id, '501234567'), {'ok': True, 'pretty': '+971 50 123 4567'})
        self.assertFalse(self.Connect.check_number(self.ae.id, '5')['ok'])

    # ------------------------------------------------------------ is it there
    def test_look(self):
        look = lambda n='501234567': self.Connect.look(self.ae.id, n)  # noqa: E731
        self.assertEqual((look()['where'], look()['ok']), ('new', True))
        for where, ok in (('free', True), ('here', True), ('off', False), ('elsewhere', False)):
            self.where['971501234567'] = where
            self.assertEqual((look()['where'], look()['ok'], bool(look().get('key'))), (where, ok, False))
        self.where['971501234567'], self.in_use = 'here', True
        self.assertTrue(look()['key'], 'in use, but this Odoo lost it')
        self.assertEqual((look('500000001')['where'], look('500000001')['ok']), ('here', False), 'connected')
        self.assertIn('Area 1', look('500000001')['text'])
        self.assertFalse(look('5')['ok'])
        self.down = True
        self.assertEqual((look()['where'], look()['ok']), ('', True), 'the panel is asked again on Next')
        self.down = False
        self.first.with_context(wa_switch=True).write({'active': False})
        self.assertEqual((look('500000001')['where'], look('500000001')['ok']), ('off', True))
        self.assertFalse([c for c in self.calls if c[0] == 'POST'], 'looking adds nothing')
        self.assertEqual(self.Connect.start()['database'], self.env.cr.dbname)
        user = new_test_user(self.env, 'zz-look', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.Connect.with_user(user).look(self.ae.id, '501234567')

    def _off_with_waiting(self, key):
        """An entry that is off, with messages that wait, some of them new."""
        old = self.env['whatsapp.session'].sudo().create({
            'name': 'Zz old', 'gateway_api_key': key, 'active': False, 'authorized_number': '971501234567', 'phone_number': '971501234567'})
        waiting = self.env['whatsapp.message'].sudo().create([{
            'session_id': old.id, 'phone': '971509990001', 'message': 'm%s' % n, 'direction': 'outgoing', 'status': 'pending'} for n in (1, 2)])
        return old, waiting

    def test_turn_on_here_with_a_new_key(self):
        """Its key is another number's: a new one, the same entry, nothing sent, groups off."""
        old, waiting = self._off_with_waiting(setup_key('tokA'))
        group = self.env['sa.sales.group'].sudo().create({'name': 'Zz old g', 'group_jid': '31@g.us', 'session_id': old.id, 'sa_paused': True})
        ask = self._add()
        self.assertEqual((ask['ask_on']['name'], ask['ask_on']['waiting']), ('Zz old', 2))
        self.assertFalse(old.active, 'asked first')
        self.assertEqual(set(waiting.mapped('status')), {'pending'})
        self._add(turn_on=True)
        self.assertTrue(old.active)
        self.assertEqual(set(waiting.mapped('status')), {'failed'}, 'never sent')
        self.assertFalse(old._key_of_another())
        self.assertFalse(group.enabled)
        self.assertEqual(self._session(), old, 'the same entry, with its history')
        link = self.env['wa.employee.session'].search([('session_id', '=', old.id)])
        self.assertEqual(link.employee_id, self.anu)
        self.assertEqual(self.first.status, 'connected')

    def test_turn_on_here_refused(self):
        old, waiting = self._off_with_waiting(setup_key('tokA'))
        self.where['971501234567'] = 'elsewhere'
        with self.assertRaisesRegex(UserError, 'another database'), self.env.cr.savepoint():
            self._add(turn_on=True)
        self.assertEqual((old.active, set(waiting.mapped('status'))), (False, {'pending'}), 'nothing is changed')
        self.where.clear()
        self.may_add = 0
        with self.assertRaisesRegex(UserError, 'not allowed'), self.env.cr.savepoint():
            self._add(turn_on=True)
        self.assertEqual((old.active, set(waiting.mapped('status'))), (False, {'pending'}))

    def test_turn_on_here_with_its_own_key(self):
        self._add()
        session = self._session()
        waiting = self.env['whatsapp.message'].sudo().create({
            'session_id': session.id, 'phone': '971509990001', 'message': 'm', 'direction': 'outgoing', 'status': 'pending'})
        key = session.gateway_api_key
        session._turn_off()
        self.where['971501234567'] = 'off'
        self.assertEqual(self.Connect.look(self.ae.id, '501234567')['owner'], 'Zz Anu')
        self.assertEqual(self._add(employee_id=0)['ask_on']['owner'], 'Zz Anu')
        self._add(employee_id=0, turn_on=True)
        self.assertEqual((session.active, session.gateway_api_key, waiting.status), (True, key, 'failed'))
        self.assertEqual(self.env['wa.employee.session'].search([('session_id', '=', session.id)]).employee_id, self.anu)

    def test_turn_on_in_the_list_with_anothers_key(self):
        old, waiting = self._off_with_waiting(setup_key('tokA'))
        old._turn_on()
        self.assertTrue(old.active)
        self.assertFalse(old._key_of_another())
        self.assertEqual(set(waiting.mapped('status')), {'failed'})

    def test_added_in_the_panel(self):
        """Added in the panel under this database: Odoo lists it and takes it, no key typed."""
        self.unused = [{'authorized_number': '971501234567', 'label': 'Deira', 'state': 'open', 'in_use': False}]
        self.may_add = 2            # the limit does not count against one that is there already
        rows = self.Connect.start()['scanned']
        self.assertEqual([(r['number'], r['session_id'], r['connected']) for r in rows], [('971501234567', False, True)])
        self.Connect.add({'free_number': '971501234567', 'employee_id': self.anu.id, 'company_id': self.env.company.id})
        self.assertTrue(self._session().gateway_api_key.startswith('tok-971501234567'), 'its own key, fetched')
        self.assertFalse(self.Connect.start()['scanned'], 'it is here now')

    # ------------------------------------------------------------ adding
    def test_start(self):
        data = self.Connect.start()
        self.assertTrue(data['can_add'])
        ravi = [e for e in data['employees'] if e['id'] == self.ravi.id][0]
        self.assertIn('971', ravi['taken'].replace(' ', ''))
        self.assertNotIn('tok', str(data), 'no key goes to the screen')

    def test_add_scan_groups_finish(self):
        state = self._add(label='Deira')
        session = self._session()
        self.assertEqual((session.name, session.instance_name), ('Deira', 'co-971501234567'))
        self.assertFalse(state['connected'])
        self.assertTrue(state['qr'].endswith('971501234567'), 'the QR of its own number')
        self.assertEqual(state['employee'], 'Zz Anu')
        link = self.env['wa.employee.session'].search([('session_id', '=', session.id)])
        self.assertEqual((link.employee_id, link.phone_number), (self.anu, '+971501234567'))
        told = [c for c in self.calls if c[1] == '/v1/config' and c[2] == session.id]
        self.assertIn(session.webhook_secret, told[-1][3]['X-Odoo-Webhook'])
        self.state['971501234567'] = 'open'
        state = self.Connect.state(session.id)
        self.assertTrue(state['connected'])
        self.assertFalse(state['qr'])
        self.groups_of['971501234567'] = [('11@g.us', 'Deira Shops'), ('12@g.us', 'Family'), ('13@g.us', 'Zz shared')]
        self.env['sa.sales.group'].create({'name': 'Zz shared', 'group_jid': '13@g.us', 'session_id': self.first.id,
                                           'enabled': True})
        self.invite['11@g.us'] = 'https://chat.whatsapp.com/AAA'
        rows = {g['name']: g for g in self.Connect.groups(session.id)['groups']}
        self.assertFalse(any(g['enabled'] for g in rows.values()), 'none by itself')
        self.assertEqual(rows['Zz shared']['taken'], 'Area 1')
        done = self.Connect.finish(session.id, [rows['Deira Shops']['id']])
        group = self.env['sa.sales.group'].browse(rows['Deira Shops']['id'])
        self.assertEqual((group.enabled, group.company_id, group.employee_session_id, group.invite_url),
                         (True, self.env.company, link, 'https://chat.whatsapp.com/AAA'))
        self.assertFalse(self.env['sa.sales.group'].browse(rows['Family']['id']).enabled)
        self.assertTrue(all(line['ok'] for line in done['lines']), done)
        self.assertEqual(self.first.name, 'Area 1')
        self.assertEqual(self.first.authorized_number, '971500000001')

    def test_a_new_employee(self):
        self._add(employee_id=0, employee_name='Zz Salim')
        self.assertEqual(self.env['wa.employee.session'].search([('session_id', '=', self._session().id)]).employee_id.name, 'Zz Salim')

    def test_refused(self):
        with self.assertRaisesRegex(UserError, 'has a number already'):
            self._add(employee_id=self.ravi.id)
        with self.assertRaisesRegex(UserError, 'Choose the employee'):
            self._add(employee_id=0)
        with self.assertRaisesRegex(UserError, 'already connected'):
            self._add('500000001')
        self.may_add = 0
        with self.assertRaisesRegex(UserError, 'not allowed'):
            self._add()
        self.assertFalse(self.Connect.start()['can_add'])
        self.assertFalse(self._session(), 'nothing is left behind')

    def test_someone_elses_number(self):
        self.panel['theirs'] = '971501234567'
        with self.assertRaisesRegex(UserError, 'already connected'):
            self._add()

    def test_left_halfway_goes_on(self):
        self._add()
        before = len(self.panel)
        state = self._add()
        self.assertEqual(state['id'], self._session().id)
        self.assertEqual(len(self.panel), before, 'the same number is not asked for again')

    def test_a_lost_answer_gets_a_fresh_key(self):
        self.panel['lostkey'] = '971501234567'
        self.lost.add('971501234567')
        self._add()
        self.assertTrue(self._session())

    def test_wrong_phone_is_said(self):
        self._add()
        self.state['971501234567'] = 'wrong_number'
        state = self.Connect.state(self._session().id)
        self.assertTrue(state['wrong'])
        self.assertFalse(state['connected'])

    def test_panel_down_keeps_the_screen(self):
        self._add()
        self.down = True
        state = self.Connect.state(self._session().id)
        self.assertFalse(state['connected'])
        self.assertTrue(self.Connect.start()['countries'])

    def test_first_number_with_its_key(self):
        self.env['wa.employee.session'].search([]).write({'active': False})
        self.env['whatsapp.session'].search([]).write({'active': False})
        self.assertFalse(self.Connect.start()['has_session'])
        with self.assertRaises(UserError):
            self._add()
        self.panel['tokF'] = '971501234567'
        self.state['971501234567'] = 'connecting'
        self._add(key=setup_key('tokF'))
        self.assertTrue(self._session().use_email)

    def test_the_wrong_key_is_not_kept(self):
        self.panel['tokW'] = '971509999999'
        with self.assertRaisesRegex(UserError, 'belongs to'), self.env.cr.savepoint():
            self._add(key=setup_key('tokW'))
        self.assertFalse(self._session())

    def test_only_an_administrator(self):
        user = new_test_user(self.env, 'zz-wa-user', groups='base.group_user')
        for method, args in (('start', []), ('add', [{}]), ('state', [self.first.id]), ('groups', [self.first.id]),
                             ('finish', [self.first.id, []]), ('check_number', [self.ae.id, '1'])):
            with self.assertRaises(AccessError, msg=method):
                getattr(self.Connect.with_user(user), method)(*args)

    def test_the_styles_compile(self):
        bundle = self.env['ir.qweb']._get_asset_bundle('web.assets_backend', css=True, js=False)
        css = bundle.preprocess_css()
        self.assertFalse(bundle.css_errors, bundle.css_errors)
        self.assertIn('o_wa_connect', css)

    def test_the_screens_open(self):
        for xmlid in ('whatsapp_gateway.action_whatsapp_session', 'sales_automation.action_sa_sales_group'):
            action = self.env.ref(xmlid)
            self.env[action.res_model].get_views([(False, 'list'), (False, 'form')])
        self.assertEqual(self.env.ref('whatsapp_gateway.action_whatsapp_connect').tag, 'whatsapp_gateway.connect')
        self.assertEqual(self.first.action_connect_new()['tag'], 'whatsapp_gateway.connect')
        self.assertEqual(self.first.action_connect_screen()['params'], {'session_id': self.first.id})

    def test_a_session_by_hand_still_works(self):
        self.panel['tokH'] = '971508888888'
        self.state['971508888888'] = 'open'
        session = self.env['whatsapp.session'].create({'name': 'By hand', 'gateway_api_key': setup_key('tokH')})
        session.action_fetch_config()
        self.assertEqual((session.instance_name, session.status), ('co-971508888888', 'connected'))


@tagged('post_install', '-at_install')
class TestNumberChecks(ConnectCase):

    def test_the_same_key_twice(self):
        for key in (setup_key('tokA'), 'tokA'):
            with self.assertRaisesRegex(ValidationError, 'already belongs'), self.env.cr.savepoint():
                self.env['whatsapp.session'].create({'name': 'Copy', 'gateway_api_key': key})
        archived = self.env['whatsapp.session'].create({'name': 'Old', 'gateway_api_key': 'tokA', 'active': False})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            archived.active = True
        self.first.gateway_api_key = setup_key('tokA')      # its own key again

    def test_a_key_that_gives_anothers_number(self):
        self.panel['tokB'] = '971500000001'
        twin = self.env['whatsapp.session'].create({'name': 'Twin', 'gateway_api_key': setup_key('tokB')})
        with self.assertRaisesRegex(UserError, 'Area 1'):
            twin._fetch_panel_config()

    def test_another_number_while_groups_are_on(self):
        self.env['sa.sales.group'].create({'name': 'Zz on', 'group_jid': '21@g.us', 'session_id': self.first.id, 'enabled': True})
        self.panel['tokA'] = '971507777777'
        with self.assertRaisesRegex(UserError, 'groups off'):
            self.first._fetch_panel_config()
        self.env['sa.sales.group'].search([('session_id', '=', self.first.id)]).enabled = False
        self.first._fetch_panel_config()
        self.assertEqual(self.first.authorized_number, '971507777777')

    def test_one_group_one_number(self):
        Group = self.env['sa.sales.group']
        self._add()
        Group.create({'name': 'Zz g', 'group_jid': '31@g.us', 'session_id': self.first.id, 'enabled': True})
        second = Group.create({'name': 'Zz g', 'group_jid': '31@g.us', 'session_id': self._session().id})
        with self.assertRaisesRegex(ValidationError, 'Area 1'), self.env.cr.savepoint():
            second.enabled = True
        Group.search([('session_id', '=', self.first.id)]).enabled = False
        second.enabled = True

    def test_assigned_phone_is_the_sessions(self):
        link = self.env['wa.employee.session'].search([('session_id', '=', self.first.id)])
        with self.assertRaisesRegex(ValidationError, '971500000001'), self.env.cr.savepoint():
            link.phone_number = '+971509999999'
        link.phone_number = '050 000 0001'


@tagged('post_install', '-at_install')
class TestNumberOffline(ConnectCase):

    def setUp(self):
        super().setUp()
        self.boss = new_test_user(self.env, 'zz-sa-boss', groups='base.group_user,sales_automation.group_sa_manager')
        self.user = new_test_user(self.env, 'zz-sa-ravi', groups='base.group_user')
        self.ravi.user_id = self.user
        self.group = self.env['sa.sales.group'].create({
            'name': 'Zz off', 'group_jid': '41@g.us', 'session_id': self.first.id, 'enabled': True})

    def _activities(self):
        return self.first._sa_offline_activities()

    def _check(self, minutes=0):
        if minutes:
            self.first.sa_offline_since = fields.Datetime.now() - timedelta(minutes=minutes)
        self.env['whatsapp.session']._sa_offline_check()

    def test_after_five_minutes_once_and_closed(self):
        self.first.status = 'disconnected'
        self._check()
        self.assertTrue(self.first.sa_offline_since)
        self._check(4)
        self.assertFalse(self._activities())
        self._check(5)
        told = self._activities().user_id
        self.assertIn(self.user, told)
        self.assertIn(self.boss, told)
        n = len(self._activities())
        self._check(9)
        self.assertEqual(len(self._activities()), n, 'once')
        self.first.status = 'connected'
        self._check()
        self.assertFalse(self._activities())
        self.assertFalse(self.first.sa_offline_since)

    def test_not_for_a_number_without_groups(self):
        self.group.enabled = False
        self.first.status = 'disconnected'
        self._check()
        self._check(30)
        self.assertFalse(self._activities())
