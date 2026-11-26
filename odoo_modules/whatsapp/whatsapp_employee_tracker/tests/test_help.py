"""Help (26 Nov 2026): a small window whose button opens manual.pdf."""
import os

from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestHelp(TransactionCase):

    def test_help_opens_the_manual(self):
        user = new_test_user(self.env, login='zz_help_user', groups='base.group_user')
        wizard = self.env['wa.tracker.help'].with_user(user).create({})
        action = wizard.action_open_manual()
        self.assertEqual((action['type'], action['target']), ('ir.actions.act_url', 'new'))
        self.assertTrue(action['url'].endswith('/static/help/manual.pdf'))
        here = os.path.dirname(os.path.dirname(__file__))
        self.assertTrue(os.path.isfile(os.path.join(here, 'static', 'help', 'manual.pdf')))
        self.assertEqual(self.env.ref('whatsapp_employee_tracker.action_wa_tracker_help').target, 'new')
