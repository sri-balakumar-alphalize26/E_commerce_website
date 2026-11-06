"""The Create from my products button, and links that cannot go wrong.

The tests that matter most:

* test_it_does_not_go_live - the button must never change what shoppers see.
* test_a_shop_with_no_sub_categories_still_gets_tiles - the bug this was written
  for: a shop whose categories are all top-level got a page with no tiles.
"""

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.mart369.models.serializers import ICON_CHOICES
from odoo.addons.mart369_home.models.home_starter import _look, _nice


@tagged('post_install', '-at_install')
class TestCreateFromProducts(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Version = self.env['mart369.home.version'].sudo()
        Category = self.env['product.public.category'].sudo()
        self.groups = [Category.create({'name': name}) for name in (
            'zzq-laptop-fan', 'zzq-laptop-speaker', 'zzq-laptop-dc-jack', 'Zzq-Display Cable')]

    def _create(self):
        """Only this test's categories, whatever else the database holds."""
        pairs = [(c, 3) for c in self.groups]
        cls = type(self.Version)
        with patch.object(cls, '_mart369_top_categories', lambda s, limit=10: pairs[:limit]), \
                patch.object(cls, '_mart369_top_groups', lambda s, limit=6: pairs[:limit]):
            return self.Version._mart369_create_from_products()

    def _quick(self, page):
        return page.mode_ids.filtered(lambda m: m.key == 'quick')

    # ------------------------------------------------------------- the button

    def test_it_does_not_go_live(self):
        was = self.Version._mart369_live()
        page = self._create()
        self.assertFalse(page.is_current)
        self.assertEqual(self.Version._mart369_live(), was)
        self.assertTrue(was.is_current or was.starts_on or was.ends_on)

    def test_the_form_button_does_not_go_live_either(self):
        was = self.Version._mart369_live()
        with patch.object(type(self.Version), '_mart369_top_categories',
                          lambda s, limit=10: [(c, 3) for c in self.groups][:limit]):
            self.Version.action_mart369_build_starter()
        self.assertEqual(self.Version._mart369_live(), was)

    def test_with_nothing_published_it_says_so(self):
        count = self.Version.search_count([])
        with patch.object(type(self.Version), '_mart369_top_categories', lambda s, limit=10: []):
            with self.assertRaisesRegex(UserError, 'Publish'):
                self.Version._mart369_create_from_products()
        self.assertEqual(self.Version.search_count([]), count)

    def test_a_shop_with_no_sub_categories_still_gets_tiles(self):
        quick = self._quick(self._create())
        self.assertEqual(len(quick.tile_ids), 4)
        self.assertEqual(set(quick.tile_ids.mapped('public_categ_id').ids), {c.id for c in self.groups})
        self.assertEqual(set(quick.tile_ids.mapped('image_source')), {'art'})

    def test_names_and_drawings_read_like_the_category(self):
        quick = self._quick(self._create())
        self.assertIn('Zzq Laptop Fan', quick.tile_ids.mapped('name'))
        tile = quick.tile_ids.filtered(lambda t: t.name == 'Zzq Laptop Speaker')
        self.assertEqual(tile.art, 'Speaker')
        tab = quick.tab_ids.filtered(lambda t: t.name == 'Zzq Laptop Fan')
        self.assertEqual(tab.icon, 'fan')

    def test_pressing_it_twice_makes_two_pages(self):
        self.assertNotEqual(self._create().name, self._create().name)

    def test_no_best_sellers_row_without_sales(self):
        with patch.object(type(self.Version), '_mart369_has_sales', lambda s: False):
            page = self._create()
        rows = page.mode_ids.mapped('section_ids')
        self.assertFalse(rows.filtered(lambda s: s.rule == 'best'))

    def test_the_tabs_promises_carry_over(self):
        live = self.Version._mart369_live()
        mode = live.mode_ids.filtered(lambda m: m.key == 'quick')
        mode.write({'tagline': 'Parts at your door', 'label': 'Fast'})
        quick = self._quick(self._create())
        self.assertEqual((quick.tagline, quick.label), ('Parts at your door', 'Fast'))

    # ---------------------------------------------------------- names, drawings

    def test_names(self):
        self.assertEqual(_nice('laptop-dc-jack'), 'Laptop DC Jack')
        self.assertEqual(_nice('Laptop-Display Cable'), 'Laptop Display Cable')
        self.assertEqual(_nice('Laptop-hdd-connector'), 'Laptop HDD Connector')
        self.assertEqual(_nice('Wi-Fi Routers'), 'Wi-Fi Routers')
        self.assertEqual(_nice('Tools & Accessories'), 'Tools & Accessories')

    def test_drawings_and_icons_are_not_all_laptops(self):
        self.assertEqual(_look('laptop-fan'), ('Cooler', 'fan'))
        self.assertEqual(_look('laptop-speaker'), ('Speaker', 'speaker'))
        self.assertEqual(_look('Laptop-Display Cable'), ('Cable', 'cable'))
        self.assertEqual(_look('laptop-dc-jack'), ('Adapter', 'connector'))
        self.assertEqual(_look('Laptop-Keyboard'), ('Keyboard', 'keyboard'))
        self.assertEqual(_look('Laptops'), ('Laptop', 'laptop'))

    def test_the_new_icons_can_be_saved(self):
        """They are new choices on an existing field. This runs without a module
        upgrade, so it says whether one is needed."""
        tab = self._quick(self._create()).tab_ids[:1]
        for icon in ('fan', 'speaker', 'cable', 'connector'):
            tab.icon = icon
            self.assertEqual(tab.icon, icon)
            self.assertEqual(tab._serialize()['icon'], icon)


@tagged('post_install', '-at_install')
class TestLinksAreClean(TransactionCase):

    def setUp(self):
        super().setUp()
        Version = self.env['mart369.home.version'].sudo()
        self.mode = Version._mart369_live().mode_ids[:1]

    def test_a_hidden_tab_is_removed(self):
        tile = self.env['mart369.home.tile'].sudo().create({
            'mode_id': self.mode.id, 'key': 'zz-link', 'name': 'Link', 'route': '\tlaptop-keyboard',
        })
        self.assertEqual(tile.route, 'laptop-keyboard')
        tile.route = ' laptop-fan\n'
        self.assertEqual(tile.route, 'laptop-fan')

    def test_banner_and_row_links_too(self):
        banner = self.env['mart369.home.banner'].sudo().create({
            'mode_id': self.mode.id, 'key': 'zz-link', 'href': ' /category/laptop-fan\t',
        })
        self.assertEqual(banner.href, '/category/laptop-fan')
        row = self.env['mart369.home.section'].sudo().create({
            'mode_id': self.mode.id, 'key': 'zz-link', 'name': 'Row', 'view_all_route': '\tlaptop-fan ',
        })
        self.assertEqual(row.view_all_route, 'laptop-fan')

    def test_clearing_a_link_still_works(self):
        banner = self.env['mart369.home.banner'].sudo().create({
            'mode_id': self.mode.id, 'key': 'zz-link', 'href': '/offers',
        })
        banner.href = False
        self.assertFalse(banner.href)

    def test_the_editor_is_sent_the_lists(self):
        vocab = self.env['mart369.home.mode'].sudo()._mart369_link_choices()
        self.assertIn('links', vocab)
        self.assertIn('routes', vocab)
        self.assertIn('fan', [value for value, __ in ICON_CHOICES])

    def test_the_lists_read_like_names(self):
        category = self.env['product.public.category'].sudo().create({'name': 'zzq-laptop-dc-jack'})
        vocab = self.env['mart369.home.mode'].sudo()._mart369_link_choices()
        slug = category.mart_slug
        self.assertIn([slug, 'Zzq Laptop DC Jack'], vocab['routes'])
        self.assertIn(['/category/%s' % slug, 'Zzq Laptop DC Jack'], vocab['links'])
