"""One Help in WA Tracker: choices page -> manual (PDF) or video, each with Back (27 Nov 2026)."""
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

HOME = '/whatsapp_employee_tracker/static/help/help.html'


def _read(url):
    with open(file_path(url.lstrip('/')), encoding='utf-8') as f:
        return f.read()


@tagged('post_install', '-at_install')
class TestHelp(TransactionCase):

    def test_one_help_menu_opens_the_choices(self):
        self.assertFalse(self.env.ref('whatsapp_employee_tracker.menu_wa_help_guide', raise_if_not_found=False),
                         'the old User Guide menu is gone')
        root = self.env.ref('whatsapp_employee_tracker.menu_wa_tracker_root')
        helps = self.env['ir.ui.menu'].search([('id', 'child_of', root.id), ('name', 'ilike', 'help')])
        self.assertEqual(helps, self.env.ref('whatsapp_employee_tracker.menu_wa_tracker_help'), 'one Help only')
        action = helps.action
        self.assertEqual(action._name, 'ir.actions.client')
        self.assertEqual(action.tag, 'whatsapp_employee_tracker.help', 'its own pop-up')
        url, _sep, query = action.params['url'].partition('?')
        self.assertEqual(url, HOME)
        self.assertTrue(query.startswith('v='), 'a version in the address, so browsers fetch the new page')

    def test_choices_and_back(self):
        home = _read(HOME)
        self.assertIn('href="manual.html?v=', home)
        # steps first (they have Play and the video link); Back from them returns to the choices
        self.assertIn('/whatsapp_employee_tracker/static/src/help/wa_tracker.html?back=%s' % HOME, home)
        self.assertNotIn('video.html', home, 'the video is reached from the steps, not straight from here')
        # a tap asks: here (in the pop-up) or a new tab
        for text in ('Open here', 'Open in a new tab', 'data-tab="manual.pdf"', "window.open("):
            self.assertIn(text, home)
        manual = _read('/whatsapp_employee_tracker/static/help/manual.html')
        self.assertIn('href="help.html?v=', manual, 'the manual goes back to the choices')
        self.assertIn('src="manual.pdf', manual)
        for page in (home, manual):
            self.assertIn('data-theme="light"', page, 'light mode only')

    def test_the_files_ship(self):
        """A package without the manual, the video or the player fails here, not in front of a user."""
        for url in ('/whatsapp_employee_tracker/static/help/manual.pdf',
                    '/whatsapp_employee_tracker/static/src/help/wa_tracker.html',
                    '/whatsapp_employee_tracker/static/src/help/wa_tracker.webm',
                    '/whatsapp_employee_tracker/static/src/help/video.html'):
            self.assertTrue(file_path(url.lstrip('/')), url)   # raises when the file is missing

    def test_self_contained(self):
        """1.5.14: Help needs nothing from whatsapp_gateway's help files (any gateway version works)."""
        for rel in ('help_dialog.js', 'help_dialog.xml', 'help_dialog.scss'):
            self.assertTrue(file_path('whatsapp_employee_tracker/static/src/help_dialog/' + rel), rel)
        js = _read('/whatsapp_employee_tracker/static/src/help_dialog/help_dialog.js')
        self.assertIn('registry.category("actions").add("whatsapp_employee_tracker.help"', js)
        for url in (HOME, '/whatsapp_employee_tracker/static/help/manual.html',
                    '/whatsapp_employee_tracker/static/src/help/wa_tracker.html',
                    '/whatsapp_employee_tracker/static/src/help/video.html'):
            self.assertNotIn('/whatsapp_gateway/', _read(url), url)
