"""WhatsApp sells the storefront's shelf - one category tree, its price."""

import json

from odoo.tests import tagged

from .common import Mart369BridgeCase


@tagged('post_install', '-at_install')
class TestCatalog(Mart369BridgeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Categ = cls.env['product.category'].sudo()
        # The package's own Product Category. Menu order 1 puts it ahead of
        # whatever the live catalogue carries.
        cls.shelf = Categ.create({'name': 'Bridge Drives', 'sa_menu_sequence': 1})
        cls.quick_product.categ_id = cls.shelf
        cls.hidden = cls.env['product.template'].sudo().create({
            'name': 'Backroom Widget',
            'list_price': 99.0,
            'sale_ok': True,
            'is_published': False,
            'type': 'consu',
            'categ_id': cls.shelf.id,
        })
        cls.request = cls.env['sa.group.request'].sudo().create({
            'group_id': cls.wa_group.id,
            'requester_phone': '+919876500009',
            'raw_text': 'anything',
        })

    def _menu(self):
        return json.loads(self.request.sa_menu_json or '{}')

    # ---------------------------------------------------------- the tree

    def test_menu_lists_the_product_categories_in_menu_order(self):
        top = self.env['sa.group.request']._sa_menu_categories()
        self.assertTrue(all(c._name == 'product.category' for c in top))
        self.assertEqual(top[0], self.shelf, 'WhatsApp menu order 1 comes first')

    def test_a_hidden_category_is_skipped(self):
        self.shelf.sa_menu_hide = True
        self.assertNotIn(self.shelf, self.env['sa.group.request']._sa_menu_categories())

    def test_category_without_published_products_is_hidden(self):
        empty = self.env['product.category'].sudo().create(
            {'name': 'Bridge Backroom Only', 'sa_menu_sequence': 2})
        self.hidden.categ_id = empty
        top = self.env['sa.group.request']._sa_menu_categories()
        self.assertNotIn(empty, top)

    def test_menu_lists_published_only(self):
        products, __ = self.env['sa.group.request']._sa_menu_products(self.shelf)
        self.assertIn(self.quick_product, products)
        self.assertNotIn(self.hidden, products)

    def test_menu_levels_walk_category_to_product(self):
        # No sub-categories, so the category falls through to its products.
        self.request._sa_menu_show('categ:%d' % self.shelf.id)
        menu = self._menu()
        self.assertIn(self.quick_product.name, menu)
        self.assertEqual(menu[self.quick_product.name]['kind'], 'prodpick')
        self.assertNotIn(self.hidden.name, menu)

    def test_not_listed_survives_on_every_level(self):
        for level in ('categ', 'categ:%d' % self.shelf.id, 'prod:%d' % self.shelf.id):
            self.request._sa_menu_show(level)
            self.assertTrue([k for k in self._menu() if 'NOT LISTED' in k],
                            'no NOT LISTED on %s' % level)

    def test_tap_opens_an_enquiry_for_the_product(self):
        self.request._sa_menu_show('prod:%d' % self.shelf.id)
        item = self._menu()[self.quick_product.name]
        self.request._sa_menu_tapped(item)
        enquiry = self.env['sa.group.request'].sudo().search(
            [('product_id', '=', self.quick_product.id),
             ('group_id', '=', self.wa_group.id)], order='id desc', limit=1)
        self.assertTrue(enquiry)

    # ------------------------------------------- the website lists the same

    def test_the_website_twin_follows_menu_order_and_hide(self):
        twin = self.shelf.mart_mirror_id
        self.assertEqual(twin.sequence, 1)
        self.assertTrue(twin.mart_in_app)
        self.assertEqual(self.quick_product.public_categ_ids, twin)
        self.shelf.write({'sa_menu_sequence': 5, 'sa_menu_hide': True})
        self.assertEqual(twin.sequence, 5)
        self.assertFalse(twin.mart_in_app)

    def test_hiding_it_on_the_website_hides_it_on_whatsapp(self):
        self.shelf.mart_mirror_id.write({'mart_in_app': False, 'sequence': 7})
        self.assertTrue(self.shelf.sa_menu_hide)
        self.assertEqual(self.shelf.sa_menu_sequence, 7)

    # --------------------------------------------------- search and price

    def test_loose_search_skips_unpublished(self):
        hits = self.env['sa.group.request']._search_products_loose(
            'Backroom Widget')
        self.assertNotIn(self.hidden, hits)
        hits = self.env['sa.group.request']._search_products_loose(
            'Test Bananas')
        self.assertIn(self.quick_product, hits)

    def test_published_price_is_the_website_price(self):
        self.quick_product.wa_retail_price = 999.0
        price = self.env['sa.group.request']._catalog_price(
            self.quick_product, is_existing_contact=False)
        self.assertEqual(price, self.quick_product.list_price)
        # An unpublished product keeps the stack's own rule.
        self.hidden.wa_retail_price = 150.0
        price = self.env['sa.group.request']._catalog_price(
            self.hidden, is_existing_contact=False)
        self.assertEqual(price, 150.0)

    def test_vendor_quote_product_stays_unpublished(self):
        request = self.request
        request.write({'ai_search_term': 'Seagate BarraCuda 4TB',
                       'quoted_price': 40.0})
        product = request._create_product_from_enquiry()
        self.assertTrue(product)
        self.assertFalse(product.is_published)
        self.assertTrue(product.sa_created_from_enquiry)
        # And it is offerable again on WhatsApp without a duplicate.
        hits = self.env['sa.group.request']._search_products_loose(
            'Seagate BarraCuda 4TB')
        self.assertIn(product, hits)
