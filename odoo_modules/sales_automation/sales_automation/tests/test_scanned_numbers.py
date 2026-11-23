# -*- coding: utf-8 -*-
"""Numbers that are scanned already, and the country on every phone box (23 Nov 2026)."""
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, new_test_user, tagged
from odoo.tools import mute_logger

from .test_connect_number import ConnectCase, setup_key


@tagged('post_install', '-at_install')
class TestScannedNumbers(ConnectCase):

    def setUp(self):
        super().setUp()
        self.free = [{'label': 'karthick', 'authorized_number': '919876543210', 'state': 'open'},
                     {'label': 'old', 'authorized_number': '971502222222', 'state': 'connecting'}]
        self.state['919876543210'] = 'open'

    def _scanned(self):
        return {r['number']: r for r in self.Connect.start()['scanned']}

    def _spare(self):
        self.panel['tokS'] = '971503333333'
        self.state['971503333333'] = 'open'
        spare = self.env['whatsapp.session'].sudo().create({'name': 'Spare', 'gateway_api_key': setup_key('tokS')})
        spare._fetch_panel_config()
        spare._refresh_state(force=True)
        return spare

    def test_the_list(self):
        rows = self._scanned()
        self.assertEqual(list(rows), ['919876543210', '971502222222'], 'connected first')
        self.assertEqual((rows['919876543210']['pretty'], rows['919876543210']['connected']), ('+91 98765 43210', True))
        self.assertNotIn('971500000001', rows, 'ravi has it')
        spare = self._spare()
        self.assertEqual(self._scanned()['971503333333']['session_id'], spare.id)
        self.assertNotIn('tok', str(self.Connect.start()))

    def test_not_listed_when_adding_is_off_or_full(self):
        spare = self._spare()
        for may in (0, 2):
            self.may_add = may
            self.assertEqual(list(self._scanned()), ['971503333333'], 'what is here stays')
        self.assertTrue(spare)
        self.down = True
        self.assertEqual(list(self._scanned()), ['971503333333'], 'the panel does not answer: the rest still works')

    def test_a_connected_free_number_needs_no_scan(self):
        state = self.Connect.add({'free_number': '919876543210', 'employee_id': self.anu.id, 'company_id': self.env.company.id})
        self.assertTrue(state['connected'])
        self.assertEqual(state['employee'], 'Zz Anu')
        session = self._session('919876543210')
        link = self.env['wa.employee.session'].search([('session_id', '=', session.id)])
        self.assertEqual((link.employee_id, link.phone_number), (self.anu, '+919876543210'))
        self.assertNotIn('919876543210', self._scanned())

    def test_a_free_number_not_linked_is_scanned(self):
        state = self.Connect.add({'free_number': '971502222222', 'employee_id': self.anu.id})
        self.assertFalse(state['connected'])
        self.assertTrue(state['qr'])

    def test_only_a_free_number(self):
        for number in ('971509999999', '971500000001'):
            with self.assertRaisesRegex(UserError, 'no longer free'):
                self.Connect.add({'free_number': number, 'employee_id': self.anu.id})

    def test_a_session_gets_its_employee(self):
        spare = self._spare()
        before = self.env['whatsapp.session'].search_count([])
        state = self.Connect.add({'session_id': spare.id, 'employee_id': self.anu.id})
        self.assertTrue(state['connected'])
        link = self.env['wa.employee.session'].search([('session_id', '=', spare.id)])
        self.assertEqual((link.employee_id, link.phone_number), (self.anu, '+971503333333'))
        self.assertEqual(self.env['whatsapp.session'].search_count([]), before)
        for session in (spare, self.first):
            with self.assertRaisesRegex(UserError, 'given'):
                self.Connect.add({'session_id': session.id, 'employee_id': 0, 'employee_name': 'Zz X'})

    def test_an_employee_with_a_number_is_refused(self):
        spare = self._spare()
        with self.assertRaisesRegex(UserError, 'has a number'):
            self.Connect.add({'session_id': spare.id, 'employee_id': self.ravi.id})

    def test_anothers_chats_are_not_taken_over(self):
        spare = self._spare()
        self.Connect.add({'session_id': spare.id, 'employee_id': self.anu.id})
        self.env['wa.employee.session'].search([('session_id', '=', spare.id)]).active = False
        third = self.env['hr.employee'].create({'name': 'Zz Third'})
        mine = self.env['wa.employee.session'].with_context(active_test=False).search([('session_id', '=', spare.id)])
        self.assertTrue(self.Connect.add({'session_id': spare.id, 'employee_id': third.id})['connected'])
        theirs = self.env['wa.employee.session'].search([('session_id', '=', spare.id)])
        self.assertEqual((theirs.employee_id, mine.employee_id, mine.active), (third, self.anu, False))
        self.assertNotEqual(theirs, mine)

    def test_give_button_and_employee_column(self):
        spare = self._spare()
        self.assertFalse(spare.wa_employee_id)
        self.assertEqual(self.first.wa_employee_id, self.ravi)
        self.assertEqual(spare.action_give_number()['params'], {'give_session_id': spare.id})

    def test_employee_session_form(self):
        spare = self._spare()
        new = self.env['wa.employee.session'].new({'employee_id': self.anu.id})
        self.assertIn(spare, new.free_session_ids._origin | new.free_session_ids)
        self.assertNotIn(self.first, new.free_session_ids._origin)
        with Form(self.env['wa.employee.session']) as form:
            form.employee_id = self.anu
            form.session_id = spare
            self.assertEqual(form.phone_number, '+971503333333')
        self.assertEqual(form.record.phone_number, '+971503333333')
        self.assertEqual(spare.with_context(wa_number_in_name=True).display_name, 'Spare, +971 50 333 3333, Connected')
        self.assertEqual(spare.display_name, 'Spare')

    def test_only_an_administrator(self):
        user = new_test_user(self.env, 'zz-scan', groups='base.group_user,sales_automation.group_sa_manager')
        with self.assertRaises(AccessError):
            self.Connect.with_user(user).add({'free_number': '919876543210', 'employee_id': self.anu.id})
        with self.assertRaises(AccessError):
            self.Connect.with_user(user).start()


@tagged('post_install', '-at_install')
class TestPhoneBox(ConnectCase):

    def test_split(self):
        self.env.company.country_id = self.ae
        split = self.Connect.phone_split(['+971501234567', '971501234567', '+91 98765 43210', '919876543210', '96891234567'])
        self.assertEqual(split['+971501234567'], {'country': self.ae.id, 'national': '501234567', 'pretty': '+971 50 123 4567'})
        self.assertEqual(split['971501234567']['national'], '501234567')
        self.assertEqual((split['+91 98765 43210']['country'], split['+91 98765 43210']['national']), (self.india.id, '9876543210'))
        self.assertEqual(split['919876543210']['country'], self.india.id)
        self.assertEqual(split['96891234567']['country'], self.env.ref('base.om').id)

    def test_what_is_not_one_number_stays_plain(self):
        self.env.company.country_id = self.india
        for value in ('', 'shop', '+971501234567 / +971502222222', '050 123 4567', '9876543210', '12', '+1', '+97150', 'a@b.c',
                      '120363000000000001@g.us', '120363000000000001'):
            self.assertFalse(self.Connect.phone_split([value])[value].get('country'), value)

    def test_check(self):
        self.assertTrue(self.Connect.phone_check(self.ae.id, '501234567')['ok'])
        self.assertFalse(self.Connect.phone_check(self.ae.id, '42345678')['ok'], 'a landline is no WhatsApp number')
        self.assertTrue(self.Connect.phone_check(self.ae.id, '42345678', True)['ok'], 'but a contact may have one')
        self.assertFalse(self.Connect.phone_check(self.ae.id, '111111111', True)['ok'])

    def test_rule_keeps_its_lengths(self):
        rule = self.Connect._rule(self.ae)
        self.assertEqual((rule['min'], rule['max']), (9, 9))
        self.assertLessEqual(rule['amin'], 8)

    @mute_logger('odoo.http')
    def test_employees_only(self):
        portal = new_test_user(self.env, 'zz-portal', groups='base.group_portal')
        user = new_test_user(self.env, 'zz-user', groups='base.group_user')
        for call in (lambda c: c.phone_countries(), lambda c: c.phone_split(['1']), lambda c: c.phone_check(self.ae.id, '1')):
            call(self.Connect.with_user(user))
            with self.assertRaises(AccessError):
                call(self.Connect.with_user(portal))

    def test_every_changed_form_opens(self):
        for model, kinds in (('whatsapp.optout', ('list', 'form')), ('whatsapp.config', ('form',)), ('whatsapp.owner.number', ('list',)),
                             ('whatsapp.send.message.wizard', ('form',)), ('whatsapp.session', ('list', 'form')),
                             ('wa.employee.session', ('list', 'form')), ('res.partner', ('form',)),
                             ('sa.delivery.partner', ('list', 'form')), ('sa.delivery.shop', ('form',))):
            views = self.env[model].get_views([(False, k) for k in kinds])['views']
            if model in ('res.partner', 'whatsapp.optout', 'sa.delivery.partner', 'wa.employee.session', 'whatsapp.send.message.wizard'):
                self.assertIn('wa_phone', views['form']['arch'], model)
            if model == 'res.partner':
                self.assertEqual(views['form']['arch'].count('widget="wa_phone"'), 2, 'the contact and its people')

    def test_saved_values_still_find_the_customer(self):
        partner = self.env['res.partner'].create({'name': 'Zz P', 'phone': '+919800012345'})
        for value in ('919800012345', '+919800012345', '9800012345'):
            self.assertIn(partner, self.env['res.partner']._sa_phone_matches(value))

    def test_shopkeeper_numbers_are_checked(self):
        settings = self.env['sa.ai.settings'].search([], limit=1) or self.env['sa.ai.settings'].create({})
        settings.takeover_numbers = '919876543210\n+968 7712 3456\n# note\n\n'
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            settings.takeover_numbers = 'call ravi'
