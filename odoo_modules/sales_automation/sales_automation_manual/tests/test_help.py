"""One Help per app (Sales Automation, Store, Delivery, Insights): User Manual + How It Works (27 Nov 2026)."""
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

BASE = 'sales_automation_manual/static/help/'
APPS = {
    'sa': 'sales_automation.menu_sa_root',
    'store': 'sales_automation_store.menu_sa_store_root',
    'delivery': 'sales_automation_delivery.menu_sa_delivery_root',
    'insights': 'sales_automation_insights.menu_sa_insights_root',
}
PDFS = ('sales_automation_manual.pdf', 'store_manual.pdf', 'delivery_manual.pdf', 'insights_manual.pdf', 'full_manual.pdf')


def _read(rel):
    with open(file_path(rel), encoding='utf-8') as f:
        return f.read()


@tagged('post_install', '-at_install')
class TestHelp(TransactionCase):

    def test_one_help_per_app(self):
        for app, root_xmlid in APPS.items():
            root = self.env.ref(root_xmlid)
            helps = self.env['ir.ui.menu'].search([('parent_id', '=', root.id), ('name', 'ilike', 'help')])
            self.assertEqual(len(helps), 1, 'one Help in %s' % app)
            self.assertEqual(helps, self.env.ref('sales_automation_manual.menu_sa_help_%s' % app))
            siblings = self.env['ir.ui.menu'].search([('parent_id', '=', root.id)])
            self.assertEqual(siblings.sorted('sequence')[-1:], helps, 'Help is the last item of %s' % app)
            action = helps.action
            self.assertEqual(action._name, 'ir.actions.client')
            self.assertEqual(action.tag, 'sales_automation_manual.help', 'its own pop-up')
            url = action.params['url']
            self.assertTrue(url.startswith('/' + BASE + 'help.html?app=%s&v=' % app), url)

    def test_old_user_manual_menus_gone(self):
        for xmlid in ('menu_sa_manual', 'menu_sa_manual_store', 'menu_sa_manual_delivery', 'menu_sa_manual_insights'):
            self.assertFalse(self.env.ref('sales_automation_manual.' + xmlid, raise_if_not_found=False), xmlid)

    def test_pages(self):
        for page, mode in (('help.html', 'help'), ('manual_pick.html', 'pick'), ('manual.html', 'doc')):
            html = _read(BASE + page)
            self.assertIn('data-theme="light"', html, 'light mode only')
            self.assertIn('data-page="%s"' % mode, html)
            self.assertIn('help.js?v=', html)
        js = _read(BASE + 'help.js')
        for text in ('Open here', 'Open in a new tab', 'window.open(', 'manual_pick.html', "'manual.html'",
                     'full_manual.pdf', 'Full Manual', '?back=', 'User Manual', 'How It Works'):
            self.assertIn(text, js)
        self.assertNotIn('video.html', js, 'the video is reached from the steps')
        self.assertNotIn('Odoo', js + _read(BASE + 'help.html'), 'words never say Odoo')
        # 27 Nov 2026: User Manual asks nothing, it shows its 2 buttons under the cards;
        # only those buttons ask "Open here / new tab" (the ask is wired to a.pick:not(.toggle))
        for text in ('id="row-manual"', 'class="pick toggle"', 'data-row="row-manual"', "a.pick:not(.toggle)",
                     "'&open=manual'", "q.get('open')"):
            self.assertIn(text, js)
        self.assertIn('.toggle', _read(BASE + 'help.css'))
        # How It Works also asks nothing: its 2 buttons (<App> steps | Full Flow steps), Back with the row open
        for text in ('id="row-how"', 'data-row="row-how"', 'Full Flow steps', "'full_flow.html?back='", "'&open=how'"):
            self.assertIn(text, js)

    def test_links_carry_the_version(self):
        for app in APPS:
            url = self.env.ref('sales_automation_manual.menu_sa_help_%s' % app).action.params['url']
            self.assertTrue(url.endswith('&v=4'), url)
        self.assertIn("var V = '4'", _read(BASE + 'help.js'))

    def test_the_files_ship(self):
        for pdf in PDFS:
            self.assertTrue(file_path(BASE + pdf), pdf)       # raises when missing
        for how in ('sa_how', 'store_how', 'delivery_how', 'insights_how'):
            self.assertTrue(file_path('sales_automation_manual/static/src/help/%s.html' % how))
            self.assertTrue(file_path('sales_automation_manual/static/src/help/%s.webm' % how))
        self.assertTrue(file_path('sales_automation_manual/static/src/help/video.html'), 'its own video player')
        for ext in ('html', 'webm'):
            self.assertTrue(file_path('sales_automation_manual/static/src/help/full_flow.%s' % ext), 'Full Flow ' + ext)

    def test_self_contained(self):
        """1.6.0: Help needs nothing from whatsapp_gateway's help files (any gateway version works)."""
        for rel in ('static/src/help_dialog/help_dialog.js', 'static/src/help_dialog/help_dialog.xml',
                    'static/src/help_dialog/help_dialog.scss'):
            self.assertTrue(file_path('sales_automation_manual/' + rel), rel)
        js = _read('sales_automation_manual/static/src/help_dialog/help_dialog.js')
        self.assertIn('registry.category("actions").add("sales_automation_manual.help"', js)
        self.assertIn('"/sales_automation_manual/static/src/help/video.html"', js)
        pages = [BASE + p for p in ('help.html', 'manual_pick.html', 'manual.html', 'help.js')]
        pages += ['sales_automation_manual/static/src/help/%s.html' % g
                  for g in ('sa_how', 'store_how', 'delivery_how', 'insights_how', 'full_flow', 'video')]
        for rel in pages:
            self.assertNotIn('/whatsapp_gateway/', _read(rel), rel)
