"""Only exact matches on the lists remove a message - no look-alikes, no AI
(owner, 22 Nov 2026). Before, "enoda system eduthuko na shop poren" was
removed as poren~porno and "VAN SALE APK UPDATION" as sale~saala, and every
doubtful message cost a model call."""
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.sales_automation_insights.controllers import conduct_webhook

WORD = 'zqexactbadword'
GROUP = 'conduct-exact@g.us'
PRIVATE = '919800044444@s.whatsapp.net'


def _no_ai(*a, **kw):
    raise AssertionError('the AI must not be asked')


@tagged('post_install', '-at_install')
class TestConductExactOnly(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        settings = env['sa.ai.settings'].sudo().get_settings()
        # the look-alike settings as they were when it went wrong
        settings.write({'conduct_enabled': True, 'conduct_warn': 'off', 'conduct_links': True,
                        'conduct_media': True, 'conduct_doubt_min': 50,
                        'conduct_doubt_action': 'delete_first', 'conduct_model_mode': 'doubt',
                        'conduct_words': '\n'.join(filter(None, [
                            settings.conduct_words or '', WORD, 'porno', 'saala']))})
        cls.session = env['whatsapp.session'].sudo().create(
            {'name': 'Conduct Exact Session', 'gateway_api_key': 'conduct-exact-key'})
        env['sa.sales.group'].sudo().create({
            'name': 'Conduct Exact Group', 'group_jid': GROUP,
            'session_id': cls.session.id, 'group_type': 'vendor', 'enabled': True})

    def setUp(self):
        super().setUp()
        Remark = type(self.env['sa.conduct.remark'])
        for name in ('_try_delete', '_try_warn'):
            p = patch.object(Remark, name, lambda self, *a, **kw: True)
            p.start()
            self.addCleanup(p.stop)
        for name in ('classify_text', 'classify_image', 'picture_of'):
            p = patch.object(Remark, name, _no_ai)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(conduct_webhook, 'request', SimpleNamespace(env=self.env))
        p.start()
        self.addCleanup(p.stop)
        self.gate = conduct_webhook.ConductWebhook()
        self.n = 0

    def _send(self, remote_jid, message):
        self.n += 1
        text = message.get('conversation') or ''
        key = {'id': 'CONDUCT-EXACT-%d' % self.n, 'remoteJid': remote_jid,
               'participant': '919800044444@s.whatsapp.net'}
        participant = '919800044444'
        return self.gate._sa_conduct_gate(self.session, {'message': message, 'pushName': 'T'},
                                          key, remote_jid, text, participant, '')

    def test_owner_examples_are_kept_everywhere(self):
        for jid in (PRIVATE, GROUP):
            for text in ('enoda system eduthuko na shop poren',
                         '*VAN SALE APK UPDATION*\n* The mob num for each users should be shown',
                         'the price is fine, sale today'):
                self.assertFalse(self._send(jid, {'conversation': text}), (jid, text))
        self.assertFalse(self.env['sa.conduct.remark'].sudo().search(
            [('wa_message_id', 'like', 'CONDUCT-EXACT-%')]))

    def test_a_listed_word_is_removed_everywhere(self):
        for jid in (PRIVATE, GROUP):
            self.assertTrue(self._send(jid, {'conversation': 'hello %s there' % WORD}), jid)
        remarks = self.env['sa.conduct.remark'].sudo().search(
            [('wa_message_id', 'like', 'CONDUCT-EXACT-%')])
        self.assertEqual(len(remarks), 2)
        self.assertEqual(set(remarks.mapped('decided_by')), {'local'})

    def test_a_disguised_listed_word_is_still_removed(self):
        self.assertTrue(self._send(PRIVATE, {'conversation': 'pooorno'}))

    def test_a_listed_adult_link_is_removed(self):
        self.assertTrue(self._send(GROUP, {'conversation': 'see https://pornhub.com/x'}))

    def test_a_photo_is_never_shown_to_the_ai(self):
        photo = {'imageMessage': {'mimetype': 'image/jpeg', 'caption': ''}}
        self.assertFalse(self._send(GROUP, photo))
        self.assertFalse(self._send(PRIVATE, photo))

    def test_a_photo_with_a_listed_word_in_its_caption_is_removed(self):
        photo = {'imageMessage': {'mimetype': 'image/jpeg', 'caption': 'look %s' % WORD}}
        self.assertTrue(self._send(GROUP, photo))
