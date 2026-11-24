# -*- coding: utf-8 -*-
"""The details page of a number (24 Nov 2026). The panel is a fake."""
from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import Form, new_test_user, tagged

from .test_connect_number import ConnectCase

VIEW = 'whatsapp_gateway.view_whatsapp_session_form'


@tagged('post_install', '-at_install')
class TestNumberPage(ConnectCase):

    def _arch(self):
        return etree.fromstring(self.env['whatsapp.session'].get_view(self.env.ref(VIEW).id, 'form')['arch'])

    def _group(self, name, enabled, session=None):
        return self.env['sa.sales.group'].with_context(sa_no_invite_fetch=True).create({
            'name': name, 'group_jid': '%s@g.us' % abs(hash(name)), 'session_id': (session or self.first).id,
            'group_type': 'customer', 'enabled': enabled})

    def test_tabs_and_buttons(self):
        arch = self._arch()
        self.assertEqual([p.get('string') for p in arch.xpath('//notebook/page')], ['General', 'Technical'])
        for name in ('action_fetch_config', 'action_sa_sync_groups'):
            self.assertEqual(arch.xpath("//header/button[@name='%s']" % name)[0].get('invisible'), "status != 'connected'")
        self.assertEqual(arch.xpath("//header/button[@name='action_test_connection']")[0].get('invisible'),
                         "status not in ('connected', 'error')")
        self.assertEqual(arch.xpath("//div[@name='sa_groups']")[0].get('invisible'), "status != 'connected'")

    def test_page_opens(self):
        Form(self.first, view=VIEW)
        self.down = True
        Form(self.first, view=VIEW)
        new = Form(self.env['whatsapp.session'], view=VIEW)
        new.name = 'Zz new'
        new.gateway_api_key = 'x'

    def test_only_groups_on(self):
        on, off = self._group('Zz on', True), self._group('Zz off', False)
        self.assertEqual(self.first.sa_group_on_ids, on)
        self.assertEqual(self.first.sa_group_ids, on | off)
        action = self.first.action_sa_groups_on()
        self.assertEqual(self.env['sa.sales.group'].search(action['domain']), on)
        on.action_sa_switch_off()
        self.env.invalidate_all()
        self.assertFalse(self.first.sa_group_on_ids)
        self.assertEqual(self.first.sa_group_ids, on | off, 'nothing is deleted')

    def test_only_managers_switch(self):
        group = self._group('Zz on', True)
        user = new_test_user(self.env, 'zz_sa_user', groups='base.group_user,sales_automation.group_sa_user')
        with self.assertRaises(AccessError):
            group.with_user(user).action_sa_switch_off()
        self.assertTrue(group.enabled)

    def test_mismatch(self):
        self.first.write({'instance_name': 'co-971500000001', 'phone_number': '0500000001'})
        self.assertFalse(self.first.number_mismatch, 'one number in two ways of writing')
        self.first.instance_name = 'admin-917092090133'
        self.assertIn('70920', self.first.number_mismatch)
        self.first.write({'instance_name': 'shop', 'phone_number': False})
        self.assertFalse(self.first.number_mismatch)

    def test_figures_of_the_dashboard(self):
        self.env['whatsapp.message'].create({
            'session_id': self.first.id, 'phone': '919811122233', 'message': 'hello', 'direction': 'incoming',
            'status': 'received'})
        self.env.invalidate_all()
        link = self.env['wa.employee.session'].search([('session_id', '=', self.first.id)])
        self.assertEqual((self.first.wa_employee_id, self.first.wa_chats), (self.ravi, 1))
        self.assertEqual((self.first.wa_today_sent, self.first.wa_today_received, self.first.wa_last_activity),
                         (link.today_sent, link.today_received, link.last_activity))
        self.assertEqual(self.first.action_wa_chats()['context']['active_employee_session_id'], link.id)
