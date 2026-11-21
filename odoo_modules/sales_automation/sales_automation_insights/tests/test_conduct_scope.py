"""The bad-words filter acts only in the shop's own groups.

The connected number also sits in family, college and job groups. A listed
word there must not be deleted, remarked or warned - only in the groups
linked and ticked under Sales Groups, and in private chats to the shop.
"""
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.sales_automation_insights.controllers import conduct_webhook

WORD = 'zqbadwordtest'


@tagged('post_install', '-at_install')
class TestConductScope(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        settings = env['sa.ai.settings'].sudo().get_settings()
        settings.write({'conduct_enabled': True,
                        'conduct_words': (settings.conduct_words or '') + '\n' + WORD,
                        'conduct_warn': 'off'})
        cls.session = env['whatsapp.session'].sudo().create(
            {'name': 'Conduct Test Session', 'gateway_api_key': 'conduct-test-key'})
        cls.linked = env['sa.sales.group'].sudo().create({
            'name': 'Conduct Shop Group', 'group_jid': 'conduct-shop@g.us',
            'session_id': cls.session.id, 'group_type': 'vendor', 'enabled': True})

    def setUp(self):
        super().setUp()
        Remark = type(self.env['sa.conduct.remark'])
        for name in ('_try_delete', '_try_warn'):
            p = patch.object(Remark, name, lambda self, *a, **kw: True)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(conduct_webhook, 'request', SimpleNamespace(env=self.env))
        p.start()
        self.addCleanup(p.stop)
        self.gate = conduct_webhook.ConductWebhook()

    def _send(self, remote_jid, n):
        data = {'message': {'conversation': 'hello %s there' % WORD}, 'pushName': 'Tester'}
        key = {'id': 'CONDUCT-SCOPE-%d' % n, 'remoteJid': remote_jid,
               'participant': '919800033333@s.whatsapp.net'}
        participant = '919800033333' if remote_jid.endswith('@g.us') else ''
        return self.gate._sa_conduct_gate(self.session, data, key, remote_jid,
                                          data['message']['conversation'], participant, '')

    def _remarks(self, n):
        return self.env['sa.conduct.remark'].sudo().search([('wa_message_id', '=', 'CONDUCT-SCOPE-%d' % n)])

    def test_removed_in_a_linked_group(self):
        self.assertTrue(self._send('conduct-shop@g.us', 1))
        self.assertTrue(self._remarks(1))

    def test_left_alone_in_a_group_that_is_not_ours(self):
        self.assertFalse(self._send('family-chat@g.us', 2))
        self.assertFalse(self._remarks(2))

    def test_left_alone_when_the_group_is_unticked(self):
        self.linked.enabled = False
        self.assertFalse(self._send('conduct-shop@g.us', 3))
        self.assertFalse(self._remarks(3))

    def test_left_alone_in_our_group_on_another_number(self):
        other = self.env['whatsapp.session'].sudo().create(
            {'name': 'Other Number', 'gateway_api_key': 'conduct-other-key'})
        data = {'message': {'conversation': 'hello %s there' % WORD}}
        key = {'id': 'CONDUCT-SCOPE-4', 'remoteJid': 'conduct-shop@g.us'}
        self.assertFalse(self.gate._sa_conduct_gate(other, data, key, 'conduct-shop@g.us',
                                                    data['message']['conversation'], '919800033333', ''))

    def test_private_chat_to_the_shop_still_checked(self):
        self.assertTrue(self._send('919800033333@s.whatsapp.net', 5))
        self.assertTrue(self._remarks(5))
