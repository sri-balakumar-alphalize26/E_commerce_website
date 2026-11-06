"""The home page arranged from the catalogue (models/home_starter.py).

What matters:

* it is built from the shop's own categories, biggest first, and a category
  holding only services (repair charges, gift cards) never becomes a tab;
* it is a normal saved page, switched on, with the page that was live kept -
  so the admin can rearrange it, and switch back;
* rebuilding makes a new page and never touches an arranged one.
"""

from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMart369HomeStarter(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Categ = env['product.public.category']
        Product = env['product.template']
        cls.big = Categ.create({'name': 'STARTER LAPTOP KEYBOARD'})
        cls.small = Categ.create({'name': 'Starter CCTV Camera'})
        cls.services = Categ.create({'name': 'Starter Repairs'})
        for i in range(3):
            Product.create({'name': 'Starter keyboard %d' % i, 'is_published': True,
                            'list_price': 10, 'public_categ_ids': [(6, 0, cls.big.ids)]})
        for i in range(2):
            Product.create({'name': 'Starter camera %d' % i, 'is_published': True,
                            'list_price': 10, 'public_categ_ids': [(6, 0, cls.small.ids)]})
        Product.create({'name': 'Starter repair charge', 'type': 'service',
                        'is_published': True, 'list_price': 10,
                        'public_categ_ids': [(6, 0, cls.services.ids)]})
        cls.Version = env['mart369.home.version']

    def _top(self):
        return [c for c, __ in self.Version._mart369_top_categories(limit=100000)]

    def _build(self, top=None, groups=()):
        # Only this test's categories, so the page's shape is predictable
        # whatever else the database holds.
        top = [(self.big, 3), (self.small, 2)] if top is None else top
        Model = type(self.Version)
        with patch.object(Model, '_mart369_top_categories', lambda self, limit=10: top[:limit]), \
                patch.object(Model, '_mart369_top_groups', lambda self, limit=6: list(groups)[:limit]):
            return self.Version._mart369_build_starter()

    def _tree(self):
        """Three main groups, the products in the categories under them."""
        Categ = self.env['product.public.category']
        Product = self.env['product.template']
        groups = []
        for name, kids in (('Starter Printers & Consumables', ('Starter Toner', 'Starter Ink')),
                           ('Starter CCTV & Networking', ('Starter Cameras',)),
                           ('Starter Tools & Accessories', ('Starter Screwdrivers',))):
            group = Categ.create({'name': name})
            for kid in kids:
                child = Categ.create({'name': kid, 'parent_id': group.id})
                Product.create({'name': '%s item' % kid, 'is_published': True, 'list_price': 3,
                                'public_categ_ids': [(6, 0, child.ids)]})
            groups.append(group)
        return groups

    # ------------------------------------------------------------ the inputs

    def test_biggest_first_and_no_service_categories(self):
        top = self._top()
        self.assertIn(self.big, top)
        self.assertIn(self.small, top)
        self.assertLess(top.index(self.big), top.index(self.small))
        self.assertNotIn(self.services, top, 'only services: never a tab')

    def test_names_read_like_names(self):
        from odoo.addons.mart369_home.models.home_starter import _nice
        self.assertEqual(_nice('LAPTOP KEYBOARD'), 'Laptop Keyboard')
        self.assertEqual(_nice('CCTV CAMERA'), 'CCTV Camera')
        self.assertEqual(_nice('DC JACK'), 'DC Jack')
        self.assertEqual(_nice('McAfee Antivirus'), 'McAfee Antivirus', 'typed on purpose')

    # ------------------------------------------------------------ the page

    def test_a_switched_on_page_from_the_catalogue(self):
        was = self.Version._mart369_live()
        page = self._build()
        self.assertTrue(page.is_current)
        self.assertEqual(self.Version._mart369_live(), page)
        self.assertTrue(was.exists() and not was.is_current, 'the old page is kept, switched off')

        quick = page.mode_ids.filtered(lambda m: m.key == 'quick')
        self.assertEqual(len(page.mode_ids), 2)
        tabs = quick.tab_ids.sorted('sequence')
        self.assertEqual(tabs.mapped('name'), ['My Home', 'Starter Laptop Keyboard',
                                               'Starter CCTV Camera', 'Offers'])
        self.assertEqual(tabs[1].route_view, 'category')
        self.assertTrue(tabs[1].route_param)
        self.assertEqual(quick.banner_ids.mapped('name'),
                         ['Starter Laptop Keyboard', 'Starter CCTV Camera'])
        self.assertIn('3 to choose from', quick.banner_ids[0].note)
        self.assertEqual(quick.tile_ids.mapped('public_categ_id'), self.big | self.small)
        rows = quick.section_ids.sorted('sequence')
        self.assertEqual(rows[0].rule, 'new')
        self.assertEqual(rows.filtered(lambda s: s.source == 'category').mapped('public_categ_id'),
                         self.big | self.small)

    def test_the_page_serves(self):
        page = self._build()
        quick = page.mode_ids.filtered(lambda m: m.key == 'quick')._serialize()
        self.assertIn('Starter Laptop Keyboard', [t['label'] for t in quick['tabs']])
        names = [p['name'] for s in quick['sections'] for p in s.get('items', [])]
        self.assertIn('Starter keyboard 0', names)
        self.assertNotIn('Starter repair charge', names, 'a service is never listed')

    def test_rebuilding_never_touches_an_arranged_page(self):
        first = self._build()
        tab = first.mode_ids[0].tab_ids[1]
        tab.name = 'Keyboards (my words)'
        second = self._build()
        self.assertNotEqual(first, second)
        self.assertEqual(tab.name, 'Keyboards (my words)')
        self.assertTrue(second.is_current)
        self.assertFalse(first.is_current)

    # ------------------------------------------------------ the main groups

    def test_main_groups_count_everything_under_them(self):
        printers, cctv, tools = self._tree()
        ranked = dict(self.Version._mart369_top_groups(limit=100000))
        self.assertEqual(ranked.get(printers), 2, 'toner + ink, counted through the branch')
        self.assertEqual(ranked.get(cctv), 1)
        self.assertEqual(ranked.get(tools), 1)

    def test_main_groups_become_tabs_and_categories_tiles(self):
        printers, cctv, tools = self._tree()
        toner = self.env['product.public.category'].search([('name', '=', 'Starter Toner')])
        page = self._build(top=[(toner, 1), (self.big, 3)],
                           groups=[(printers, 2), (cctv, 1), (tools, 1)])
        quick = page.mode_ids.filtered(lambda m: m.key == 'quick')
        self.assertEqual(quick.tab_ids.sorted('sequence').mapped('name'),
                         ['My Home', 'Starter Printers & Consumables', 'Starter CCTV & Networking',
                          'Starter Tools & Accessories', 'Offers'])
        self.assertEqual(quick.banner_ids.mapped('art_lines'), ['Box', 'Webcam', 'Mouse'],
                         'computer drawings for the groups, not fruit')
        self.assertEqual(quick.tile_ids.mapped('public_categ_id'), toner | self.big)
        rows = quick.section_ids.filtered(lambda s: s.source == 'category')
        self.assertEqual(rows.mapped('public_categ_id'), printers | cctv | tools)
        self.assertTrue(all(rows.mapped('include_child_categs')))
        names = [p['name'] for s in quick._serialize()['sections'] for p in s.get('items', [])]
        self.assertIn('Starter Toner item', names, 'a group row shows what is under it')

    def test_fewer_than_three_groups_keeps_the_categories(self):
        printers, cctv, __ = self._tree()
        page = self.Version.browse()
        Model = type(self.Version)
        top = [(self.big, 3), (self.small, 2)]
        with patch.object(Model, '_mart369_top_categories', lambda self, limit=10: top[:limit]), \
                patch.object(Model, '_mart369_top_groups',
                             lambda self, limit=6: [(printers, 2), (cctv, 1)]):
            page = self.Version._mart369_build_starter()
        tabs = page.mode_ids.filtered(lambda m: m.key == 'quick').tab_ids.mapped('name')
        self.assertIn('Starter Laptop Keyboard', tabs)
        self.assertNotIn('Starter Printers & Consumables', tabs)

    def test_an_empty_catalogue_still_gets_a_page(self):
        Model = type(self.Version)
        with patch.object(Model, '_mart369_top_categories', lambda self, limit=10: []), \
                patch.object(Model, '_mart369_top_groups', lambda self, limit=6: []):
            page = self.Version._mart369_build_starter()
        quick = page.mode_ids.filtered(lambda m: m.key == 'quick')
        self.assertEqual(quick.tab_ids.mapped('name'), ['My Home', 'Offers'])
        self.assertEqual(quick.section_ids.mapped('rule'), ['new'])

    # ------------------------------------------------- the Dubai update step

    def _migrate(self):
        import importlib.util
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'migrations', '19.0.1.5.0', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('mart369_home_m1950', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, '19.0.1.4.0')
        self.env.invalidate_all()

    def _grocery_live(self):
        grocery = self.env.ref('mart369_home.home_version_everyday')
        # Nothing scheduled may outrank it for this test.
        self.Version.search([('id', '!=', grocery.id)]).write(
            {'starts_on': False, 'ends_on': False})
        grocery.write({'is_current': True, 'deleted_at': False})
        # As installed - this database's copy may have been played with.
        self.env.ref('mart369_home.tab_q_grocery').write(
            {'name': 'Groceries', 'active': True, 'deleted_at': False})
        self.assertEqual(self.Version._mart369_live(), grocery)
        return grocery

    def test_update_replaces_an_untouched_grocery_page(self):
        grocery = self._grocery_live()
        self._migrate()
        live = self.Version._mart369_live()
        self.assertNotEqual(live, grocery, 'customers no longer see the grocery page')
        self.assertTrue(grocery.exists(), 'kept, so switching back is one click')
        self.assertIn('Example', grocery.name)
        tabs = live.mode_ids.filtered(lambda m: m.key == 'quick').tab_ids.mapped('name')
        self.assertNotIn('Groceries', tabs)

    def test_update_leaves_a_rearranged_page_alone(self):
        grocery = self._grocery_live()
        self.env.ref('mart369_home.tab_q_grocery').name = 'Our deals'
        self._migrate()
        self.assertEqual(self.Version._mart369_live(), grocery)
