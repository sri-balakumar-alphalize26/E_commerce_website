"""A category's logo: set in the catalogue, worn by its pill and its tile.

A main category shows a small mark on its pill in the top bar; a sub-category
fills its tile. Either is one the app draws itself (`mart_icon`, `mart_art`)
or an uploaded picture, which wins.
"""

import importlib.util
import json
import os

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import HttpCase

# The smallest PNG there is: one transparent pixel.
PNG = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwAD'
       'hgGAWjR9awAAAABJRU5ErkJggg==')


@tagged('post_install', '-at_install')
class TestCategoryLogo(HttpCase):

    def setUp(self):
        super().setUp()
        Category = self.env['product.public.category']
        self.main = Category.create({'name': 'Zz Logo Aisle', 'mart_slug': 'zz-logo-aisle'})
        self.sub = Category.create({'name': 'Zz Logo Shelf', 'mart_slug': 'zz-logo-shelf',
                                    'parent_id': self.main.id})
        self.mode = self.env['mart369.home.mode']._get('quick')

    # ------------------------------------------------------------- the writes

    def test_the_consoles_set_and_clear_a_logo(self):
        row = self.main.mart369_admin_write({'mart_icon': 'plug'})
        self.assertEqual(row['icon'], 'plug')
        self.assertEqual(row['image'], '')
        self.assertFalse(row['hasImage'])

        row = self.sub.mart369_admin_write({'mart_art': 'Keyboard',
                                            'mart_logo': 'data:image/png;base64,' + PNG})
        self.assertEqual(row['art'], 'Keyboard')
        self.assertTrue(row['hasImage'])
        self.assertIn('/web/image/product.public.category/%s/mart_logo' % self.sub.id, row['image'])
        self.assertIn('unique=', row['image'], 'a new upload must not hide behind the old one')

        row = self.sub.mart369_admin_write({'mart_logo': False})
        self.assertFalse(row['hasImage'])
        self.assertEqual(row['image'], '')
        self.assertEqual(row['art'], 'Keyboard', 'removing the upload falls back to the drawing')

        # Created with a logo, from the New category button.
        row = self.env['product.public.category'].mart369_admin_create(
            {'name': 'Zz Logo New', 'parent_id': self.main.id, 'mart_art': 'Mouse'})
        self.assertEqual(row['art'], 'Mouse')

    def test_a_logo_has_to_be_a_logo(self):
        with self.assertRaises(UserError):
            self.main.mart369_admin_write({'mart_icon': 'not-an-icon'})
        with self.assertRaises(UserError):
            self.sub.mart369_admin_write({'mart_art': 'Spaceship'})
        with self.assertRaises(UserError):
            self.sub.mart369_admin_write({'mart_logo': 'this is not base64!'})
        with self.assertRaises(UserError):
            # Valid base64, but text rather than a picture.
            self.sub.mart369_admin_write({'mart_logo': 'PHN2Zz48L3N2Zz4='})
        self.assertFalse(self.sub.mart_logo)

    # --------------------------------------------------------------- the shop

    def test_the_shop_is_sent_the_logo_and_can_load_it(self):
        self.main.mart_icon = 'wifi'
        # The website shop's category photo is not the app's logo.
        self.main.image_1920 = PNG
        self.sub.write({'mart_art': 'Router', 'mart_logo': PNG})
        node = self.main._mart369_serialize()
        self.assertEqual(node['icon'], 'wifi')
        self.assertEqual(node['image'], '')
        sub = node['subs'][0]
        self.assertEqual(sub['art'], 'Router')
        self.assertTrue(sub['image'])

        # A shopper who never logged in still sees the picture.
        path = sub['image'][sub['image'].index('/web/image'):]
        res = self.url_open(path)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.headers.get('Content-Type', '').startswith('image/'))

    def test_a_pill_wears_its_category_s_logo(self):
        Tab = self.env['mart369.home.tab']
        pill = Tab.create({'mode_id': self.mode.id, 'name': 'Zz Aisle', 'key': 'zz-logo-aisle',
                           'icon': 'grid', 'route_view': 'category',
                           'route_param': 'zz-logo-aisle'})
        offers = Tab.create({'mode_id': self.mode.id, 'name': 'Zz Offers', 'key': 'zz-logo-offers',
                             'icon': 'ticket', 'route_view': 'offers'})

        self.assertEqual(pill._serialize()['icon'], 'grid', 'no logo yet: the pill keeps its own')
        self.assertFalse(pill._builder_vals()['logo_from'])

        self.main.mart_icon = 'plug'
        self.assertEqual(pill._serialize()['icon'], 'plug')
        self.assertNotIn('image', pill._serialize())
        self.assertEqual(pill._builder_vals()['logo_from'], 'Zz Logo Aisle')

        self.main.mart_logo = PNG
        self.assertIn('image', pill._serialize())
        self.assertEqual(offers._serialize()['icon'], 'ticket', 'a pill opening no category is untouched')
        self.assertNotIn('image', offers._serialize())

        # A pill opening a sub-category's page wears the sub-category's.
        pill.route_param = 'zz-logo-aisle/zz-logo-shelf'
        self.sub.mart_icon = 'cpu'
        self.assertEqual(pill._serialize()['icon'], 'cpu')

        tabs = {t['key']: t for t in json.loads(self.url_open('/369mart/home/quick').content)['tabs']}
        self.assertEqual(tabs['zz-logo-aisle']['icon'], 'cpu', 'the app is sent the category logo')

    def test_a_tile_wears_its_category_s_logo(self):
        Tile = self.env['mart369.home.tile']
        tile = Tile.create({'mode_id': self.mode.id, 'name': 'Zz Shelf', 'image_source': 'category',
                            'public_categ_id': self.sub.id, 'art': 'Pack', 'badge': 'NEW'})
        own = Tile.create({'mode_id': self.mode.id, 'name': 'Zz Own', 'image_source': 'art',
                           'public_categ_id': self.sub.id, 'art': 'Box'})

        vals = tile._serialize()
        self.assertEqual((vals['art'], vals['image']), ('Pack', ''), 'no logo: its own drawing')
        self.assertNotIn('fill', vals)

        self.sub.mart_art = 'Keyboard'
        vals = tile._serialize()
        self.assertEqual(vals['art'], 'Keyboard')
        self.assertEqual(vals['t'], 'NEW', 'the tile keeps its own text')
        self.assertEqual(tile._builder_vals()['paint_art'], 'Keyboard')

        self.sub.mart_logo = PNG
        tile.invalidate_recordset(['image_path'])
        vals = tile._serialize()
        self.assertTrue(vals['image'])
        self.assertTrue(vals['fill'], 'an uploaded logo fills the whole tile')

        self.assertEqual(own._serialize()['art'], 'Box', 'a tile told to draw its own still does')
        self.assertNotIn('fill', own._serialize())

    # ---------------------------------------------------------- the migration

    def test_the_migration_hands_each_category_the_logo_it_was_shown_with(self):
        spec = importlib.util.spec_from_file_location('mart369_catalog_logo_migration', os.path.join(
            os.path.dirname(__file__), '..', 'migrations', '19.0.1.4.0', 'post-migrate.py'))
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        kept = self.env['product.public.category'].create(
            {'name': 'Zz Logo Kept', 'mart_slug': 'zz-logo-kept', 'mart_icon': 'book'})
        self.env['mart369.home.tab'].create([
            {'mode_id': self.mode.id, 'name': 'Zz A', 'key': 'zz-mig-a', 'icon': 'laptop',
             'route_view': 'category', 'route_param': '/zz-logo-aisle/'},
            {'mode_id': self.mode.id, 'name': 'Zz K', 'key': 'zz-mig-k', 'icon': 'leaf',
             'route_view': 'category', 'route_param': 'zz-logo-kept'},
        ])
        tile = self.env['mart369.home.tile'].create(
            {'mode_id': self.mode.id, 'name': 'Zz M', 'image_source': 'art',
             'public_categ_id': self.sub.id, 'art': 'Webcam'})
        loose = self.env['mart369.home.tile'].create(
            {'mode_id': self.mode.id, 'name': 'Zz L', 'image_source': 'art', 'art': 'Box'})
        self.env.flush_all()

        migration.migrate(self.env.cr, '19.0.1.3.0')
        self.env.invalidate_all()

        self.assertEqual(self.main.mart_icon, 'laptop')
        self.assertEqual(kept.mart_icon, 'book', 'a logo already set is never overwritten')
        self.assertEqual(self.sub.mart_art, 'Webcam')
        self.assertEqual(tile.image_source, 'category')
        self.assertEqual(loose.image_source, 'art', 'a tile with no category keeps its drawing')
