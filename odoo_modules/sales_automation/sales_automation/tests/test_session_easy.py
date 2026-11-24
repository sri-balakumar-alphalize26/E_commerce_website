# -*- coding: utf-8 -*-
"""The easier WhatsApp and employee session screens (23 Nov 2026). The panel is a
fake; nothing is sent."""
from datetime import timedelta
from unittest.mock import patch

from requests.exceptions import ConnectionError

from odoo import fields
from odoo.exceptions import AccessError, RedirectWarning, UserError, ValidationError
from odoo.tests import Form, new_test_user, tagged

from .test_connect_number import ConnectCase, setup_key

UNKNOWN = 'this key is not registered in the WhatsApp panel (reset, or not complete): copy it again there'
WRONG = 'wrong key: it is the key of database testing, but this is here. Open here in the WhatsApp panel and copy the key there'


class EasyCase(ConnectCase):

    def setUp(self):
        super().setUp()
        self.said, self.sent, self.refuse, self.unreachable = [], [], {}, False
        real = self.env.registry['whatsapp.session']._gateway_call
        box = self

        def gateway(rec, method, path, payload=None, **kw):
            key = rec.sudo().gateway_api_key
            if box.unreachable:
                raise UserError('Cannot reach the gateway at x.\nHTTPConnectionPool') from ConnectionError('x')
            if key in box.refuse:
                raise UserError('The gateway refused the request (HTTP 403).\n' + box.refuse[key])
            if path == '/v1/self':
                box.said.append((rec.id, payload['do']))
                return {'ok': True}
            if path.startswith('/message/sendText/'):
                box.sent.append(payload['number'])
                return {'key': {'id': 'x'}}
            return real(rec, method, path, payload, **kw)
        p = patch.object(self.env.registry['whatsapp.session'], '_gateway_call', gateway)
        p.start()
        self.addCleanup(p.stop)
        self.Session = self.env['whatsapp.session']

    def _save(self, vals, session=None):
        return (session or self.Session).web_save(vals, {'id': {}, 'name': {}, 'status': {}})

    def _message(self, session, hours, phone='971501111111'):
        m = self.env['whatsapp.message'].create({
            'session_id': session.id, 'phone': phone, 'message': 'x', 'direction': 'outgoing', 'status': 'pending'})
        self.env.flush_all()
        self.env.cr.execute('UPDATE whatsapp_message SET create_date = %s WHERE id = %s',
                            [fields.Datetime.now() - timedelta(hours=hours), m.id])
        m.invalidate_recordset()
        return m


@tagged('post_install', '-at_install')
class TestWhatsAppSessionEasy(EasyCase):

    # ------------------------------------------------------------ a pasted key
    def test_a_good_key_is_ready_at_once(self):
        self.panel['tokH'] = '971508888888'
        self.state['971508888888'] = 'open'
        row = self._save({'name': 'Default', 'gateway_api_key': setup_key('tokH'), 'instance_name': 'nexgenn-main'})[0]
        session = self.Session.browse(row['id'])
        self.assertEqual((session.instance_name, session.status), ('co-971508888888', 'connected'))
        self.assertEqual(row['name'], '+971 50 888 8888', 'named after its number')
        self.assertEqual(row['status'], 'connected', 'the form shows it')

    def test_a_name_somebody_typed_stays(self):
        self.panel['tokH'] = '971508888888'
        self.state['971508888888'] = 'open'
        self.assertEqual(self._save({'name': 'Deira', 'gateway_api_key': setup_key('tokH')})[0]['name'], 'Deira')

    def test_a_refused_key_is_not_kept(self):
        for text, words in ((WRONG, 'wrong key'), (UNKNOWN, 'not registered'),
                            ('database here is switched off in the WhatsApp panel. Press Activate on its page there', 'Activate')):
            self.refuse = {'tokX': text}
            n = self.Session.with_context(active_test=False).search_count([])
            with self.assertRaisesRegex(UserError, words) as caught, self.env.cr.savepoint():
                self._save({'name': 'X', 'gateway_api_key': setup_key('tokX')})
            self.assertNotIn('HTTP', str(caught.exception))
            self.assertNotIn('tokX', str(caught.exception))
            self.assertEqual(self.Session.with_context(active_test=False).search_count([]), n)

    def test_a_refused_key_leaves_the_old_one(self):
        self.refuse = {'tokX': WRONG}
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self._save({'gateway_api_key': setup_key('tokX')}, self.first)
        self.assertEqual(self.first.gateway_api_key, 'tokA')

    def test_another_sessions_key(self):
        with self.assertRaisesRegex(ValidationError, 'already belongs'), self.env.cr.savepoint():
            self._save({'name': 'Copy', 'gateway_api_key': setup_key('tokA')})
        self.panel['tokB'] = '971500000001'
        with self.assertRaisesRegex(UserError, 'Area 1'), self.env.cr.savepoint():
            self._save({'name': 'Twin', 'gateway_api_key': setup_key('tokB')})

    def test_the_panel_is_down(self):
        self.unreachable = True
        row = self._save({'name': 'Later', 'gateway_api_key': setup_key('tokH')})[0]
        self.assertTrue(self.Session.browse(row['id']).exists(), 'kept, checked later')

    def test_without_a_key_nothing_is_asked(self):
        self.calls.clear()
        self._save({'name': 'Area one'}, self.first)
        self.assertFalse([c for c in self.calls if c[1] == '/v1/config'])

    def test_made_by_code_is_as_before(self):
        self.refuse = {'tokX': WRONG}
        self.assertTrue(self.Session.create({'name': 'By code', 'gateway_api_key': setup_key('tokX')}).exists())

    def test_mail_stays_with_the_session_that_has_it(self):
        spec = {'use_email': {}, 'route_odoo_mail': {}, 'name': {}}
        value = self.Session.onchange({}, [], spec)['value']
        self.assertFalse(value.get('use_email') or value.get('route_odoo_mail'))
        self.first.write({'use_email': False, 'route_odoo_mail': False})
        value = self.Session.onchange({}, [], spec)['value']
        self.assertTrue(value.get('use_email') and value.get('route_odoo_mail'), 'the first one gets it')
        self.assertTrue(self.Session.create({'name': 'Code', 'gateway_api_key': 'zz'}).use_email, 'by code as before')

    # ------------------------------------------------------------ the steps
    def test_the_next_step(self):
        self.panel['tokH'] = '971508888888'
        self.state['971508888888'] = 'close'
        session = self.Session.create({'name': 'New', 'gateway_api_key': setup_key('tokH')})
        self.assertEqual(session.setup_next, 'settings')
        session._fetch_panel_config()
        self.assertEqual(session.setup_next, 'phone')
        self.state['971508888888'] = 'open'
        session._refresh_state(force=True)
        self.assertEqual(session.setup_next, 'employee')
        self.env['wa.employee.session'].create({'employee_id': self.anu.id, 'session_id': session.id})
        session.invalidate_recordset()
        self.assertEqual(session.setup_next, 'groups')
        self.assertIn('Zz Anu', session.setup_text)
        self.env['sa.sales.group'].create({'name': 'Zz', 'group_jid': '91@g.us', 'session_id': session.id, 'enabled': True})
        session.invalidate_recordset()
        self.assertFalse(session.setup_next)

    def test_the_answer_reloads_the_form(self):
        for action in (self.first.action_test_connection(), self.first.action_fetch_config()):
            self.assertEqual(action['params']['next']['tag'], 'soft_reload')

    def test_the_screens_open(self):
        for model, views in (('whatsapp.session', ('list', 'form')), ('wa.employee.session', ('list', 'form', 'search')),
                             ('sa.sales.group', ('list', 'form'))):
            self.env[model].get_views([(False, v) for v in views])
        with Form(self.first) as form:
            form.name = 'Area one'
        self.first.web_read({'setup_text': {}, 'setup_next': {}, 'waiting_text': {}, 'waiting_count': {}})
        self.env['wa.employee.session'].web_search_read([('session_id.active', '=', False)], {'link_text': {}, 'session_active': {}})

    # ------------------------------------------------------------ the gear menu
    def test_archive_and_unarchive_tell_the_panel(self):
        group = self.env['sa.sales.group'].create({'name': 'Zz', 'group_jid': '92@g.us', 'session_id': self.first.id, 'enabled': True})
        self.first.action_archive()
        self.assertEqual((self.first.active, group.enabled), (False, False))
        self.first.action_unarchive()
        self.assertEqual((self.first.active, group.enabled), (True, True))
        self.assertEqual(self.said, [(self.first.id, 'off'), (self.first.id, 'on')])

    def test_archive_of_a_session_the_panel_does_not_know(self):
        for text in (UNKNOWN, WRONG):
            session = self.Session.create({'name': 'Bad', 'gateway_api_key': 'tokX%s' % len(text)})
            self.refuse = {session.gateway_api_key: text}
            session.action_archive()
            self.assertFalse(session.active)

    def test_archive_while_the_panel_is_down(self):
        self.unreachable = True
        with self.assertRaisesRegex(UserError, 'Nothing was changed'):
            self.first.action_archive()
        self.assertTrue(self.first.active)

    def test_archive_is_for_the_administrator(self):
        user = new_test_user(self.env, 'zz-easy-user', groups='base.group_user,sales_automation.group_sa_manager,whatsapp_gateway.group_whatsapp_manager')
        for name in ('action_archive', 'action_drop_waiting'):
            with self.assertRaises(AccessError, msg=name):
                getattr(self.first.with_user(user), name)()

    def test_remove_one_the_panel_took_out(self):
        """The panel's own words for it: 'not registered' must stay in them."""
        self.refuse = {self.first.gateway_api_key: UNKNOWN}
        self.first._remove_number()
        self.assertEqual((self.first.active, self.first.removed), (False, True))

    # ------------------------------------------------------------ what waits
    def test_nothing_goes_out_a_day_late(self):
        old, fresh = self._message(self.first, 25, '971501111111'), self._message(self.first, 1, '971502222222')
        self.first._flush_outbox()
        self.assertEqual((old.status, fresh.status), ('failed', 'sent'))
        self.assertEqual(self.sent, ['971502222222'])

    def test_an_old_one_no_longer_holds_up_the_queue(self):
        for i in range(3):
            self._message(self.first, 30 + i)
        self.first._cron_sync_status()
        self.assertFalse(self.first._waiting_messages())
        self.assertFalse(self.sent)

    def test_not_sent_by_hand(self):
        waiting = self._message(self.first, 2) | self._message(self.first, 3)
        self.first.invalidate_recordset()
        self.assertEqual(self.first.waiting_count, 2)
        self.assertIn('2 message(s)', self.first.waiting_text)
        self.first.action_drop_waiting()
        self.assertEqual(set(waiting.mapped('status')), {'failed'})
        self.assertTrue(waiting.exists(), 'nothing is deleted')
        self.assertFalse(self.sent)


@tagged('post_install', '-at_install')
class TestEmployeeSessionEasy(EasyCase):

    def setUp(self):
        super().setUp()
        self.Link = self.env['wa.employee.session']
        self.link = self.Link.search([('session_id', '=', self.first.id)])
        self.spare = self.Session.create({'name': 'Spare', 'gateway_api_key': 'zz-spare', 'authorized_number': '971503333333'})

    def test_the_employee_has_one(self):
        with self.assertRaisesRegex(ValidationError, 'Zz Ravi already has the number'), self.env.cr.savepoint():
            self.Link.create({'employee_id': self.ravi.id, 'session_id': self.spare.id})

    def test_the_session_is_taken(self):
        with self.assertRaisesRegex(ValidationError, 'already belongs to Zz Ravi'), self.env.cr.savepoint():
            self.Link.create({'employee_id': self.anu.id, 'session_id': self.first.id})

    def test_a_session_that_is_off(self):
        self.spare.active = False
        with self.assertRaisesRegex(ValidationError, 'is off'), self.env.cr.savepoint():
            self.Link.create({'employee_id': self.anu.id, 'session_id': self.spare.id})
        with self.assertRaisesRegex(ValidationError, 'is off'), self.env.cr.savepoint():
            self.link.session_id = self.spare

    def test_moving_to_another_session(self):
        self.link.write({'session_id': self.spare.id, 'phone_number': '+971503333333'})
        self.assertEqual(self.link.session_id, self.spare)

    def test_it_says_what_to_do(self):
        self.assertFalse(self.link.link_text)
        self.first.action_archive()
        self.link.invalidate_recordset()
        self.assertIn('is off', self.link.link_text)

    def test_a_whole_number(self):
        loose = self.Session.create({'name': 'Loose', 'gateway_api_key': 'zz-loose'})
        spec = {'phone_number': {}}
        with self.assertRaisesRegex(UserError, 'whole phone number'), self.env.cr.savepoint():
            self.Link.web_save({'employee_id': self.anu.id, 'session_id': loose.id, 'phone_number': '12345'}, spec)
        row = self.Link.web_save({'employee_id': self.anu.id, 'session_id': loose.id, 'phone_number': '+971501234567'}, spec)
        self.assertTrue(row)

    def test_connect_a_number_is_as_before(self):
        self._add()
        self.assertEqual(self.Link.search([('session_id', '=', self._session().id)]).employee_id, self.anu)


@tagged('post_install', '-at_install')
class TestGroupEmployee(EasyCase):

    def setUp(self):
        super().setUp()
        self.spare = self.Session.create({'name': 'Spare', 'gateway_api_key': 'zz-spare', 'authorized_number': '971503333333'})
        self.group = self.env['sa.sales.group'].create({'name': 'Zz Test 2', 'group_jid': '93@g.us', 'session_id': self.spare.id})

    def test_on_the_screen_with_a_button(self):
        with self.assertRaises(RedirectWarning) as caught:
            self.group.web_save({'enabled': True}, {'enabled': {}})
        text, action, button, context = caught.exception.args
        self.assertIn('no employee is chosen', text)
        self.assertIn('Spare', text)
        self.assertEqual(action, self.env.ref('whatsapp_gateway.action_whatsapp_connect').id)
        self.assertEqual((button, context), ('Choose the employee', {'give_session_id': self.spare.id}))

    def test_by_code_the_plain_refusal(self):
        with self.assertRaisesRegex(ValidationError, 'no employee is chosen'), self.env.cr.savepoint():
            self.group.enabled = True

    def test_the_same_number_elsewhere(self):
        # from before one number could be connected only once
        self.env.flush_all()
        self.env.cr.execute("UPDATE whatsapp_session SET authorized_number = '971500000001' WHERE id = %s", [self.spare.id])
        self.spare.invalidate_recordset()
        with self.assertRaisesRegex(ValidationError, 'already has Zz Ravi'), self.env.cr.savepoint():
            self.group.enabled = True

    def test_with_an_employee_it_goes_on(self):
        self.env['wa.employee.session'].create({'employee_id': self.anu.id, 'session_id': self.spare.id})
        self.group.web_save({'enabled': True}, {'enabled': {}})
        self.assertEqual(self.group.employee_session_id.employee_id, self.anu)

    def test_a_vendor_group_needs_nobody(self):
        self.group.web_save({'enabled': True, 'group_type': 'vendor'}, {'enabled': {}})
        self.assertTrue(self.group.enabled)

    def test_not_an_employee_whose_number_is_off(self):
        link = self.env['wa.employee.session'].search([('session_id', '=', self.first.id)])
        self.group.write({'employee_session_id': link.id, 'enabled': True})      # routed to another, active one
        self.group.enabled = False
        self.first.active = False
        with self.assertRaisesRegex(ValidationError, 'which is off'), self.env.cr.savepoint():
            self.group.write({'employee_session_id': link.id, 'enabled': True})
