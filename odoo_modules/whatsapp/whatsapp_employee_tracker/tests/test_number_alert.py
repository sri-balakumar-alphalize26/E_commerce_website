"""The owners are told when a number is down and back (25 Nov 2026). Nothing is sent."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestNumberAlert(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Session = self.env['whatsapp.session'].sudo()
        self.Session.search([]).write({'active': False})
        self.env['whatsapp.owner.number'].search([]).write({'active': False})
        self.state, self.sent, self.refuse = {}, [], set()

        def gateway(rec, method, path, payload=None, **kw):
            if '/message/sendText' in path:
                if rec.id in self.refuse:
                    raise UserError('refused')
                self.sent.append((rec, payload['number'], payload['text']))
                return {'key': {'id': 'ALERT%s' % len(self.sent)}}
            if 'connectionState' in path:
                return {'instance': {'state': self.state.get(rec.id, 'open')}}
            return {}
        p = patch.object(self.env.registry['whatsapp.session'], '_gateway_call', gateway)
        p.start()
        self.addCleanup(p.stop)
        self.sri, self.kar, self.third = (self._number(n, p) for n, p in (
            ('Sri', '919000000001'), ('Karthick', '919000000002'), ('Third', '919000000003')))
        employee = self.env['hr.employee'].create({'name': 'Zz Sri'})
        self.env['wa.employee.session'].create({'employee_id': employee.id, 'session_id': self.sri.id, 'phone_number': '+919000000001'})
        for phone in ('919811111111', '919822222222'):
            self.env['whatsapp.owner.number'].create({'name': 'Owner', 'phone': phone})
        self._round()

    def _number(self, name, phone):
        return self.Session.create({'name': name, 'gateway_api_key': 'test ' + phone, 'authorized_number': phone,
                                    'instance_name': 'co-' + phone, 'status': 'connected', 'company_id': self.env.company.id})

    def _round(self, later=0):
        """The job, so many minutes later."""
        if later:
            for session in self.Session.search([('wa_down_since', '!=', False)]):
                session.wa_down_since -= timedelta(minutes=later)
        self.Session.search([])._refresh_state(force=True)
        self.Session._tell_about_numbers()

    def _down(self, session):
        self.state[session.id] = 'close'
        self._round()               # a moment: connecting
        self._round()

    def test_down_and_back(self):
        self.state[self.sri.id] = 'close'
        self._round()
        self.assertFalse(self.sent, 'a moment is not told')
        self._round()
        self.assertEqual(sorted(p for _s, p, _t in self.sent), ['919000000001', '919811111111', '919822222222'])
        self.assertNotIn(self.sri, [s for s, _p, _t in self.sent], 'another number sends')
        own = [t for _s, p, t in self.sent if p == '919000000001'][0]
        owner = [t for _s, p, t in self.sent if p == '919811111111'][0]
        self.assertIn('Link a device', own)
        self.assertIn(self.env.company.name, own)
        self.assertFalse([t for _s, _p, t in self.sent if 'odoo' in t.lower()])
        self.assertNotIn('Link a device', owner, 'no steps for the owner')
        self.assertIn('Zz Sri', owner)
        self._round(later=30)
        self.assertEqual(len(self.sent), 3, 'once')
        self.sent.clear()
        self.state[self.sri.id] = 'open'
        self._round()
        self.assertEqual(sorted(p for _s, p, _t in self.sent), ['919811111111', '919822222222'], 'only the owners')
        self.assertIn('connected again', self.sent[0][2])
        self.assertIn('Connected: ', self.sent[0][2])
        self.assertRegex(self.sent[0][2], r'Was disconnected: 3\d min, since \d\d ')
        self._round()
        self.assertEqual(len(self.sent), 2)

    def test_the_time_of_the_database(self):
        when = fields.Datetime.to_datetime('2026-11-25 10:10:00')
        self.env.company.partner_id.tz = 'Asia/Kolkata'
        self.assertEqual(self.sri._alert_time(when), '25 Nov 2026, 03:40 PM')
        self.env.company.partner_id.tz = 'Asia/Dubai'
        self.assertEqual(self.sri._alert_time(when), '25 Nov 2026, 02:10 PM')
        self.env.company.partner_id.tz = False
        self.env.ref('base.user_admin').tz = False
        self.env.company.country_id = self.env.ref('base.om')
        self.assertEqual(self.sri._alert_time(when), '25 Nov 2026, 02:10 PM', "the country's")

    def test_nothing_without_an_owner(self):
        self.env['whatsapp.owner.number'].search([]).write({'active': False})
        self._down(self.sri)
        self._round(later=60)
        self.assertFalse(self.sent)

    def test_a_short_drop_is_not_told(self):
        self.state[self.sri.id] = 'close'
        self._round()
        self.state[self.sri.id] = 'open'
        self._round()
        self._round(later=10)
        self.assertFalse(self.sent)

    def test_the_next_one_sends(self):
        self.refuse = {self.kar.id}
        self._down(self.sri)
        self.assertEqual({s for s, _p, _t in self.sent}, {self.third})

    def test_nobody_can_send(self):
        for session in (self.sri, self.kar, self.third):
            self.state[session.id] = 'close'
        self._round()
        self._round()
        self._round(later=6)
        self.assertFalse(self.sent)
        self.assertFalse(self.sri.wa_down_told, 'told when somebody can')
        self.state[self.kar.id] = 'open'
        self._round()
        self._round()
        self.assertIn('919000000001', [p for _s, p, _t in self.sent])

    def test_on_purpose_or_never_connected(self):
        new = self._number('New', '919000000009')
        new.status = 'disconnected'
        self.state[new.id] = 'close'
        self._round()
        self._round(later=10)
        self.assertFalse(self.sent, 'never connected')
        self._down(self.sri)
        self.sri.error_message = 'this WhatsApp number is turned off'
        self.Session._tell_about_numbers()
        self.assertFalse(self.sri.wa_down_since)
        self.third._number_off()
        self.assertFalse(self.third.wa_was_connected)

    def test_every_minute(self):
        self.state[self.sri.id] = 'close'
        self.env['whatsapp.session']._cron_watch_numbers()
        self.assertEqual(len(self.sent), 3, 'in the same minute: looked at twice')
        self.env['whatsapp.session']._cron_watch_numbers()
        self.assertEqual(len(self.sent), 3, 'once')
        self.sent.clear()
        self.state[self.sri.id] = 'open'
        self.env['whatsapp.session']._cron_watch_numbers()
        self.assertEqual(len(self.sent), 2)
        self.env['whatsapp.owner.number'].search([]).write({'active': False})
        self.state[self.sri.id] = 'close'
        self.env['whatsapp.session']._cron_watch_numbers()
        self.assertEqual(len(self.sent), 2, 'nobody to tell')

    def test_trying_is_told_after_a_minute(self):
        self.state[self.sri.id] = 'connecting'
        self._round()
        self._round()
        self.assertFalse(self.sent)
        self._round(later=2)
        self.assertEqual(len(self.sent), 3)

    def test_minutes_of_the_settings(self):
        page = self.env['whatsapp.config'].action_wa_owner_numbers()
        config = self.env['whatsapp.config'].browse(page['res_id'])
        self.assertEqual(len(config.owner_number_ids), 2, 'those typed before are on it')
        config.alert_minutes = 10
        self._down(self.sri)
        self._round(later=8)
        self.assertFalse(self.sent)
        self._round(later=3)
        self.assertEqual(len(self.sent), 3)
        with self.assertRaises(ValidationError):
            config.alert_minutes = -1
        self.assertTrue(config.get_views([(page['views'][0][0], 'form')]))

    def test_what_is_sent(self):
        config = self.env['whatsapp.config'].browse(self.env['whatsapp.config'].action_wa_owner_numbers()['res_id'])
        config.alert_down = False
        self._down(self.sri)
        self.assertEqual([p for _s, p, _t in self.sent], ['919000000001'], 'only the steps')
        self.sent.clear()
        config.alert_up = False
        self.state[self.sri.id] = 'open'
        self._round()
        self.assertFalse(self.sent)
        config.write({'alert_down': True, 'alert_steps': False})
        self._down(self.kar)
        self.assertEqual(sorted(p for _s, p, _t in self.sent), ['919811111111', '919822222222'], 'no steps')

    def test_another_company_does_not_send(self):
        other = self.env['res.company'].create({'name': 'Zz other'})
        (self.kar + self.third).write({'company_id': other.id})
        self.assertFalse(self.sri._alert_senders())

    def test_the_number_is_checked(self):
        with self.assertRaises(ValidationError):
            self.env['whatsapp.owner.number'].create({'name': 'Bad', 'phone': '12'})
        self.assertTrue(self.env['whatsapp.owner.number'].get_views([(self.env.ref(
            'whatsapp_employee_tracker.view_wa_owner_number_list').id, 'list')]))
        self.assertTrue(fields.Datetime.now())
