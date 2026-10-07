"""A service is bought, not browsed.

On the Dubai shop "Top-up eWallet", "Gift Card" and "Repair Service" led the
"New this week" row. Every list a shopper sees asks
`product.template._mart369_listed_domain()`; looking a product up by id does
not, so a gift card in a basket still works.
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMart369Listed(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Product = cls.env['product.template']
        cls.categ = cls.env['product.public.category'].create({'name': 'Listed Test Shelf'})
        cls.goods = Product.create({'name': 'Listed test cable', 'is_published': True,
                                    'list_price': 5, 'public_categ_ids': [(6, 0, cls.categ.ids)]})
        cls.service = Product.create({'name': 'Listed test repair', 'type': 'service',
                                      'is_published': True, 'list_price': 5,
                                      'public_categ_ids': [(6, 0, cls.categ.ids)]})

    def test_a_category_lists_goods_not_services(self):
        found = self.env['product.template'].search(self.categ._mart369_product_domain())
        self.assertIn(self.goods, found)
        self.assertNotIn(self.service, found)

    def test_a_service_is_still_found_by_id(self):
        self.assertTrue(self.service.exists())
        self.assertIn(self.service, self.env['product.template'].search(
            [('id', '=', self.service.id), ('is_published', '=', True)]))

    def test_the_example_categories_leave_the_app_while_empty(self):
        from odoo.addons.mart369_catalog import hide_sample_categories
        fruits = self.env.ref('mart369_home.categ_fruits', raise_if_not_found=False)
        if not fruits:
            self.skipTest('the grocery example is not installed here')
        fruits.mart_in_app = True
        filled = self.env.ref('mart369_home.categ_office')
        filled.mart_in_app = True
        self.goods.public_categ_ids = [(4, filled.id)]
        hide_sample_categories(self.env)
        if not self.env['product.template'].search_count(fruits._mart369_product_domain()):
            self.assertFalse(fruits.mart_in_app)
        self.assertTrue(filled.mart_in_app, 'one with products in it stays showing')
