"""WhatsApp sells the storefront's shelf - its tree, its price."""

import json

from odoo.tests import tagged

from .common import Mart369BridgeCase


@tagged('post_install', '-at_install')
class TestCatalog(Mart369BridgeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Public = cls.env['product.public.category'].sudo()
        # The storefront tree the menu should mirror. Sequence 1 puts it
        # ahead of whatever the live catalogue carries.
        cls.web_parent = Public.create({'name': 'Bridge Web Shelf', 'sequence': 1})
        cls.web_child = Public.create({'name': 'Bridge Web Drives',
                                       'parent_id': cls.web_parent.id,
                                       'sequence': 1})
        cls.quick_product.public_categ_ids = [(6, 0, [cls.web_child.id])]
        cls.hidden = cls.env['product.template'].sudo().create({
            'name': 'Backroom Widget',
            'list_price': 99.0,
            'sale_ok': True,
            'is_published': False,
            'type': 'consu',
            'public_categ_ids': [(6, 0, [cls.web_child.id])],
        })
        cls.request = cls.env['sa.group.request'].sudo().create({
            'group_id': cls.wa_group.id,
            'requester_phone': '+919876500009',
            'raw_text': 'anything',
        })

    def _menu(self):
        return json.loads(self.request.sa_menu_json or '{}')

    # ---------------------------------------------------------- the tree

    def test_menu_walks_the_storefront_tree(self):
        top = self.env['sa.group.request']._sa_menu_categories()
        self.assertIn(self.web_parent, top)
        self.assertTrue(all(c._name == 'product.public.category' for c in top))
        # sequence 1 puts the fixture first - the website's own ordering.
        self.assertEqual(top[0], self.web_parent)

    def test_category_without_published_products_is_hidden(self):
        empty = self.env['product.public.category'].sudo().create(
            {'name': 'Bridge Backroom Only', 'sequence': 2})
        self.hidden.public_categ_ids = [(6, 0, [empty.id])]
        top = self.env['sa.group.request']._sa_menu_categories()
        self.assertNotIn(empty, top)

    def test_menu_lists_published_only(self):
        products, __ = self.env['sa.group.request']._sa_menu_products(
            self.web_child)
        self.assertIn(self.quick_product, products)
        self.assertNotIn(self.hidden, products)

    def test_menu_levels_walk_parent_to_product(self):
        self.request._sa_menu_show('categ:%d' % self.web_parent.id)
        menu = self._menu()
        self.assertIn('Bridge Web Drives', menu)
        self.assertEqual(menu['Bridge Web Drives']['level'],
                         'categ:%d' % self.web_child.id)
        # The child has no sub-categories, so it falls through to products.
        self.request._sa_menu_show('categ:%d' % self.web_child.id)
        menu = self._menu()
        self.assertIn(self.quick_product.name, menu)
        self.assertEqual(menu[self.quick_product.name]['kind'], 'prodpick')

    def test_not_listed_survives_on_every_level(self):
        for level in ('categ', 'categ:%d' % self.web_parent.id,
                      'prod:%d' % self.web_child.id):
            self.request._sa_menu_show(level)
            self.assertTrue([k for k in self._menu() if 'NOT LISTED' in k],
                            'no NOT LISTED on %s' % level)

    def test_tap_opens_an_enquiry_for_the_product(self):
        self.request._sa_menu_show('prod:%d' % self.web_child.id)
        item = self._menu()[self.quick_product.name]
        self.request._sa_menu_tapped(item)
        enquiry = self.env['sa.group.request'].sudo().search(
            [('product_id', '=', self.quick_product.id),
             ('group_id', '=', self.wa_group.id)], order='id desc', limit=1)
        self.assertTrue(enquiry)

    def test_vendor_sourcing_still_reads_the_internal_category(self):
        """The menu walks the website tree; the vendor routing must keep
        reading `categ_id` - that tree kept exactly one job."""
        before = self.quick_product.categ_id
        self.request._sa_menu_show('categ:%d' % self.web_child.id)
        self.assertEqual(self.quick_product.categ_id, before)

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
