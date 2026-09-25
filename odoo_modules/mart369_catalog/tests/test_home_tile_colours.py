"""A home tile wears its category's colours (models/home_tile.py)."""

import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged('post_install', '-at_install')
class TestHomeTileColours(HttpCase):

    def setUp(self):
        super().setUp()
        self.mode = self.env['mart369.home.mode']._get('quick')

    # ------------------------------------------------------------ the colours

    def test_a_tile_wears_its_category_s_colours(self):
        """Recolour a category - main or sub - and its home tile follows.
        A tile pointing elsewhere keeps colours of its own."""
        Category = self.env['product.public.category']
        main = Category.create({'name': 'Zz Tile Colours', 'mart_tone': '#fde2e2',
                                'mart_accent': '#9b1c1c'})
        sub = Category.create({'name': 'Zz Tile Colours Sub', 'parent_id': main.id,
                               'mart_tone': '#e2f0fd', 'mart_accent': '#1c4f9b'})
        Tile = self.env['mart369.home.tile']
        linked = Tile.create({'mode_id': self.mode.id, 'name': 'Zz Main', 'image_source': 'art',
                              'public_categ_id': main.id, 'bg': '#f1f4f6', 'color': '#5b6b76'})
        on_sub = Tile.create({'mode_id': self.mode.id, 'name': 'Zz Sub', 'image_source': 'art',
                              'public_categ_id': sub.id})
        loose = Tile.create({'mode_id': self.mode.id, 'name': 'Zz Loose', 'image_source': 'art',
                             'bg': '#fff1e2', 'color': '#b0662a'})

        self.assertEqual((linked._serialize()['bg'], linked._serialize()['color']), ('#fde2e2', '#9b1c1c'))
        self.assertEqual((on_sub._serialize()['bg'], on_sub._serialize()['color']), ('#e2f0fd', '#1c4f9b'))
        self.assertEqual((loose._serialize()['bg'], loose._serialize()['color']), ('#fff1e2', '#b0662a'))
        self.assertEqual(on_sub.colour_from, sub.display_name)
        self.assertFalse(loose.colour_from)

        sub.mart_tone = '#d1fae5'
        self.assertEqual(on_sub._serialize()['bg'], '#d1fae5', 'recolouring the sub-category recolours its tile')

        tiles = {t['key']: t for t in json.loads(self.url_open('/369mart/home/quick').content)['categories']}
        self.assertEqual(tiles[linked.key]['bg'], '#fde2e2', 'the app is sent the category colour')
