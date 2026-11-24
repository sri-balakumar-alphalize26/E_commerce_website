# -*- coding: utf-8 -*-
"""A number turned off, on, removed; nothing is deleted with it (23 Nov 2026)."""
from unittest.mock import patch

from requests.exceptions import ConnectionError

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .test_connect_number import ConnectCase


@tagged('post_install', '-at_install')
class TestNumberOff(ConnectCase):

    def setUp(self):
        super().setUp()
        self._add()
        self.second = self._session()
        self.state['971501234567'] = 'open'
        self.second._refresh_state(force=True)
        self.link = self.env['wa.employee.session'].search([('session_id', '=', self.second.id)])
        Group = self.env['sa.sales.group']
        self.on = Group.create({'name': 'Zz on', 'group_jid': '61@g.us', 'session_id': self.second.id, 'enabled': True})
        self.off = Group.create({'name': 'Zz off', 'group_jid': '62@g.us', 'session_id': self.second.id})
        self.request = self.env['sa.group.request'].create({
            'group_id': self.on.id, 'requester_phone': '1', 'raw_text': 'x', 'state': 'sourcing',
            'sourcing_deadline': fields.Datetime.now()})
        self.said = []
        real = self.env.registry['whatsapp.session']._gateway_call

        def gateway(rec, method, path, payload=None, **kw):
            if path == '/v1/self':
                self.said.append((rec.id, payload['do']))
                if self.down:
                    raise UserError('Cannot reach the gateway at x.\nHTTPSConnectionPool') from ConnectionError('x')
                if self.refuse:
                    raise UserError('The gateway refused the request (HTTP 403).\n' + self.refuse)
                return {'ok': True}
            return real(rec, method, path, payload, **kw)
        self.refuse = ''
        p = patch.object(self.env.registry['whatsapp.session'], '_gateway_call', gateway)
        p.start()
        self.addCleanup(p.stop)

    def _do(self, do, session=None):
        action = getattr(session or self.second, {'off': 'action_turn_off', 'on': 'action_turn_on', 'remove': 'action_remove_number'}[do])()
        return self.env[action['res_model']].browse(action['res_id']).action_do()

    def test_the_question_says_what_is_open(self):
        action = self.second.action_turn_off()
        wizard = self.env[action['res_model']].browse(action['res_id'])
        self.assertIn('1 group(s) on', wizard.open_text)
        self.assertIn('1 open enquiry', wizard.open_text)
        self.assertEqual(wizard.number, '+971 50 123 4567')
        self.assertTrue(self.second.active, 'asking changes nothing')

    def test_off_and_on(self):
        self._do('off')
        self.assertEqual((self.second.active, self.on.enabled, self.on.sa_paused), (False, False, True))
        self.assertTrue(self.first.active)
        self.assertTrue(self.link.active, 'the employee keeps the number')
        self.assertEqual(self.said, [(self.second.id, 'off')])
        self._do('on')
        self.assertEqual((self.second.active, self.on.enabled, self.on.sa_paused, self.off.enabled), (True, True, False, False))
        self.assertEqual(self.second.status, 'connected')

    def _waiting(self):
        return self.env['whatsapp.message'].create({'session_id': self.second.id, 'phone': '1', 'message': 'x',
                                                    'direction': 'outgoing', 'status': 'pending'})

    def test_a_waiting_message_waits_a_day_at_most(self):
        old, new = self._waiting(), self._waiting()
        self._do('off')
        self.assertEqual((old.status, new.status), ('pending', 'pending'), 'nothing is thrown away by turning off')
        self.env.flush_all()
        self.env.cr.execute("UPDATE whatsapp_message SET create_date = now() - interval '30 hours' WHERE id = %s", [old.id])
        self.env.invalidate_all()
        self._do('on')
        self.assertEqual((old.status, new.status == 'failed'), ('failed', False))

    def test_removed_drops_what_waits(self):
        waiting = self._waiting()
        self._do('remove')
        self.assertEqual(waiting.status, 'failed')

    def test_off_gives_no_offline_alert(self):
        self._do('off')
        self.env['whatsapp.session']._sa_offline_check()
        self.assertFalse(self.second.sa_offline_since)

    def test_on_again_not_where_another_number_took_over(self):
        self._do('off')
        self.env['sa.sales.group'].create({'name': 'Zz on', 'group_jid': '61@g.us', 'session_id': self.first.id, 'enabled': True})
        done = self._do('on')
        self.assertFalse(self.on.enabled)
        self.assertIn('Area 1', done['params']['message'])

    def test_panel_not_reached_changes_nothing(self):
        for do in ('off', 'remove'):
            self.down = True
            with self.assertRaisesRegex(UserError, 'Nothing was changed: the WhatsApp panel cannot be reached'), self.env.cr.savepoint():
                self._do(do)
            self.env.invalidate_all()
            self.assertEqual((self.second.active, self.second.removed, self.on.enabled, self.link.active), (True, False, True, True))

    def test_the_administrators_off_stays(self):
        self._do('off')
        self.refuse = 'the panel administrator turned this number off'
        with self.assertRaisesRegex(UserError, 'administrator'), self.env.cr.savepoint():
            self._do('on')
        self.env.invalidate_all()
        self.assertFalse(self.second.active)

    def test_the_only_number_cannot_be_removed(self):
        self.refuse = 'This is the only number of the database; it cannot be removed.'
        with self.assertRaisesRegex(UserError, 'only number'), self.env.cr.savepoint():
            self._do('remove')
        self.env.invalidate_all()
        self.assertTrue(self.second.active)

    def test_remove_keeps_everything(self):
        self._do('remove')
        self.assertEqual((self.second.active, self.second.removed, self.on.enabled, self.link.active), (False, True, False, False))
        self.assertNotIn('tok', self.second.gateway_api_key)
        self.assertTrue(self.on.exists() and self.request.exists() and self.off.exists())
        employees = {e['id']: e['taken'] for e in self.Connect.start()['employees']}
        self.assertFalse(employees[self.anu.id], 'free for another number')
        self.assertNotIn(self.second, self.env['whatsapp.session'].with_context(active_test=False).search(
            [('removed', '=', False)]))

    def test_off_in_the_panel_already(self):
        self.refuse = 'this WhatsApp number is turned off'
        self._do('off')
        self.assertFalse(self.second.active)

    def test_an_off_number_is_not_asked_about(self):
        self._do('off')
        with patch.object(self.env.registry['whatsapp.session'], '_gateway_call',
                          side_effect=AssertionError('asked')):
            self.second._refresh_state(force=True)
            with self.assertRaises(UserError):
                self.second.send_message('120363000000000009@g.us', 'x')
        self.assertEqual(self.second.status, 'disconnected')

    def test_removed_in_the_panel_already(self):
        self.refuse = 'token not registered'
        self._do('remove')
        self.assertTrue(self.second.removed)

    def test_the_same_number_comes_back_with_its_history(self):
        self._do('remove')
        self.panel = {k: v for k, v in self.panel.items() if v != '971501234567'}
        self._add()
        self.assertEqual(self._session(), self.second)
        self.assertEqual((self.second.active, self.second.removed, self.on.enabled, self.link.active, self.on.session_id),
                         (True, False, False, True, self.second))

    def test_for_another_employee_the_number_comes_back_without_the_chats(self):
        self._do('remove')
        self.panel = {k: v for k, v in self.panel.items() if v != '971501234567'}
        other = self.env['hr.employee'].create({'name': 'Zz Other'})
        self._add(employee_id=other.id)
        self.assertEqual(self._session(), self.second, 'the groups of the number')
        new = self.env['wa.employee.session'].search([('session_id', '=', self.second.id)])
        self.assertEqual(new.employee_id, other)
        self.assertNotEqual(new, self.link)
        self.assertEqual((self.link.active, self.link.employee_id), (False, self.anu))

    def test_an_off_number_is_turned_on_not_added(self):
        self._do('off')
        ask = self._add(employee_id=0, employee_name='Zz X')['ask_on']
        self.assertEqual(ask['owner'], 'Zz Anu')
        self.assertFalse(self.second.active, 'asked first')

    def test_the_freed_employee_takes_another_number(self):
        self._do('remove')
        self._add('502223333')
        self.assertEqual(self._session('971502223333').exists().name, 'Zz Anu')

    def test_never_deleted_with_its_history(self):
        with self.assertRaisesRegex(UserError, 'Turn it off'), self.env.cr.savepoint():
            self.second.unlink()
        empty = self.env['whatsapp.session'].create({'name': 'Empty', 'gateway_api_key': 'zz-empty'})
        empty.unlink()

    def test_only_an_administrator(self):
        user = new_test_user(self.env, 'zz-off-user', groups='base.group_user,sales_automation.group_sa_manager,whatsapp_gateway.group_whatsapp_manager')
        for name in ('action_turn_off', 'action_turn_on', 'action_remove_number'):
            with self.assertRaises(AccessError, msg=name):
                getattr(self.second.with_user(user), name)()

    def test_the_list_opens(self):
        action = self.env.ref('whatsapp_gateway.action_whatsapp_session')
        self.env['whatsapp.session'].get_views([(False, 'list'), (False, 'form')])
        self.assertIn('active_test', action.context)
        self.env['whatsapp.number.off'].get_views([(False, 'form')])
