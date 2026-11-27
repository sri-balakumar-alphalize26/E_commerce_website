"""One Help in WhatsApp and Email: choices page -> manual (PDF) or video, each
with Back to the choices (27 Nov 2026, same as WA Tracker 1.5.11: steps first)."""
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

HOME = '/whatsapp_email/static/help/help.html'


def _read(url):
    with open(file_path(url.lstrip('/')), encoding='utf-8') as f:
        return f.read()


@tagged('post_install', '-at_install')
class TestHelpManual(TransactionCase):

    def test_one_help_menu_opens_the_choices(self):
        self.assertNotIn('whatsapp.email.help', self.env, 'the small Odoo Help form is gone')
        root = self.env.ref('whatsapp_email.menu_whatsapp_root')
        helps = self.env['ir.ui.menu'].search([('id', 'child_of', root.id), ('name', 'ilike', 'help')])
        self.assertEqual(helps, self.env.ref('whatsapp_email.menu_send_documents_guide'), 'one Help only')
        action = helps.action
        self.assertEqual(action._name, 'ir.actions.client')
        self.assertEqual(action.tag, 'whatsapp_gateway.help')
        self.assertTrue(action.params['url'].startswith(HOME + '?v='),
                        'a version in the address, or browsers keep the old page for 7 days')

    def test_choices_and_back(self):
        home = _read(HOME)
        self.assertIn('href="manual.html?v=', home)
        self.assertIn('/whatsapp_email/static/src/help/send_documents.html?back=%s' % HOME, home,
                      'How It Works opens the steps first, with Back to the choices')
        self.assertNotIn('video.html', home, 'the video is reached from the steps, not from the choices')
        for word in ('Open here', 'Open in a new tab', 'window.open('):
            self.assertIn(word, home, 'a tap on a card asks where to open it')
        manual = _read('/whatsapp_email/static/help/manual.html')
        self.assertIn('href="help.html?v=', manual, 'the manual goes back to the choices')
        self.assertIn('src="manual.pdf', manual)
        for page in (home, manual):
            self.assertIn('data-theme="light"', page, 'light mode only')

    def test_the_files_ship(self):
        """A package without the manual, the video or the player fails here, not in front of a user."""
        for url in ('/whatsapp_email/static/help/manual.pdf',
                    '/whatsapp_email/static/src/help/send_documents.webm',
                    '/whatsapp_gateway/static/src/help/video.html'):
            self.assertTrue(file_path(url.lstrip('/')), url)
