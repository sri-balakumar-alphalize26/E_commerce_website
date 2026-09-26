"""WhatsApp sells the storefront's shelf, at the storefront's price."""

from odoo.tests import tagged

from .common import Mart369BridgeCase


@tagged('post_install', '-at_install')
class TestCatalog(Mart369BridgeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A category of the tests' own: the database this runs on carries the
        # live catalogue, and a page of six ordered by name would never show
        # the fixtures.
        cls.categ = cls.env['product.category'].sudo().create(
            {'name': 'Bridge Test Shelf'})
        cls.quick_product.categ_id = cls.categ
        cls.hidden = cls.env['product.template'].sudo().create({
            'name': 'Backroom Widget',
            'list_price': 99.0,
            'sale_ok': True,
            'is_published': False,
            'type': 'consu',
            'categ_id': cls.categ.id,
        })
        cls.request = cls.env['sa.group.request'].sudo().create({
            'group_id': cls.wa_group.id,
            'requester_phone': '+919876500009',
            'raw_text': 'anything',
        })

    def test_menu_lists_published_only(self):
        products, __ = self.env['sa.group.request']._sa_menu_products(self.categ)
        self.assertIn(self.quick_product, products)
        self.assertNotIn(self.hidden, products)

    def test_menu_categories_need_published_products(self):
        Categ = self.env['product.category'].sudo()
        empty = Categ.create({'name': 'Backroom Only'})
        self.hidden.categ_id = empty
        listed = self.env['sa.group.request']._sa_menu_categories()
        self.assertNotIn(empty, listed)

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
