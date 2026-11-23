# -*- coding: utf-8 -*-
"""The ACCEPT page (23 Nov 2026): back to the group and never to a private
chat; the answer has an address of its own, so Back never shows ACCEPT again."""
from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestBackToGroup(HttpCase):

    def setUp(self):
        super().setUp()
        Request = self.env.registry['sa.group.request']
        Group = self.env.registry['sa.sales.group']
        self.followed = []
        for p in (patch.object(Request, '_sa_confirm_link_decided',
                               lambda rec, link, action: self.followed.append(action) or True),
                  patch.object(Group, '_sa_fetch_invite_url', lambda rec: '')):
            p.start()
            self.addCleanup(p.stop)
        session = self.env['whatsapp.session'].sudo().create({
            'name': 'Back Test Session', 'gateway_api_key': 'back-test-key', 'phone_number': '919811122233'})
        session.status = 'connected'
        p = patch.object(self.env.registry['whatsapp.session'], '_refresh_state', lambda rec, force=False: None)
        p.start()
        self.addCleanup(p.stop)
        self.group = self.env['sa.sales.group'].sudo().create({
            'name': 'Back Test Group', 'group_jid': 'back-test@g.us',
            'session_id': session.id, 'group_type': 'customer'})
        product = self.env['product.template'].sudo().create({'name': 'Zz Back Kettle'})
        request = self.env['sa.group.request'].sudo().create({
            'group_id': self.group.id, 'requester_phone': '+96890000079',
            'raw_text': product.name, 'product_id': product.id})
        self.link = self.env['sa.confirm.link'].sudo().create({'request_id': request.id, 'kind': 'customer'})

    def _post(self, what='accept', follow=False):
        res = self.url_open('/wa/confirm/%s/%s' % (self.link.token, what), data={'x': '1'}, allow_redirects=follow)
        self.env.invalidate_all()
        return res

    def _html(self, query=''):
        return self.url_open('/wa/confirm/%s%s' % (self.link.token, query)).text

    def test_the_answer_is_another_address(self):
        res = self._post()
        self.assertEqual(res.status_code, 303)
        self.assertTrue(res.headers['Location'].endswith('/wa/confirm/%s?done=1' % self.link.token))
        self.assertEqual(self.link.decided, 'accept')
        self.assertFalse(self.followed, 'the price and the messages come after the page')
        self._tasks()
        self.assertEqual(self.followed, ['accept'])

    def _tasks(self):
        for task in self.env['sa.after.task'].search([('request_id', '=', self.link.request_id.id)]):
            task._run()

    def test_a_second_tap_changes_nothing(self):
        self._post()
        res = self._post('reject')
        self.assertIn('done=again', res.headers['Location'])
        self.assertEqual(self.link.decided, 'accept')
        self._tasks()
        self._tasks()
        self.assertEqual(self.followed, ['accept'])
        self.assertIn('already recorded', self._html('?done=again'))

    def test_accept_is_never_offered_again(self):
        self.assertIn('/accept', self._html())
        self._post()
        for query in ('', '?done=1', '?done=again'):
            html = self._html(query)
            self.assertIn('You accepted this product', html)
            self.assertNotIn('/wa/confirm/%s/accept' % self.link.token, html)

    def test_done_in_the_address_of_an_open_link_decides_nothing(self):
        html = self._html('?done=1')
        self.env.invalidate_all()
        self.assertFalse(self.link.decided)
        self.assertIn('/wa/confirm/%s/accept' % self.link.token, html)

    def test_without_an_invite_link_no_private_chat(self):
        self._post()
        html = self._html('?done=1')
        self.assertNotIn('wa.me', html)
        self.assertIn('Go back to the <b>Back Test Group</b> group', html)

    def test_with_an_invite_link_this_tab_opens_the_group(self):
        self.group.invite_url = 'https://chat.whatsapp.com/AbCdEf'
        self._post()
        button = self._html('?done=1').split('class="btn ok back"', 1)[1].split('</a>', 1)[0]
        self.assertIn('href="https://chat.whatsapp.com/AbCdEf"', button)
        self.assertNotIn('_blank', button)
        self.assertIn('Back Test Group', button)
