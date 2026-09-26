"""WhatsApp sells by the product's own "Sell when Out-of-Stock" (stock_rule.py)."""

from unittest.mock import patch

from odoo.tests import tagged

from .common import Mart369BridgeCase


@tagged('post_install', '-at_install')
class TestStockRule(Mart369BridgeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Public = cls.env['product.public.category'].sudo()
        cls.shelf = Public.create({'name': 'Bridge Stock Shelf', 'sequence': 1})
        cls.lonely = Public.create({'name': 'Bridge Sold Out Shelf', 'sequence': 2})
        Tmpl = cls.env['product.template'].sudo()

        def make(name, storable, allow, categ):
            return Tmpl.create({
                'name': name, 'list_price': 50.0, 'sale_ok': True,
                'is_published': True, 'type': 'consu', 'is_storable': storable,
                'allow_out_of_stock_order': allow,
                'public_categ_ids': [(6, 0, [categ.id])],
            })

        cls.untracked = make('Bridge Loose Tea', False, False, cls.shelf)
        cls.strict = make('Bridge Strict Ghee', True, False, cls.shelf)
        cls.sourced = make('Bridge Sourced Honey', True, True, cls.shelf)
        cls.sold_out = make('Bridge Sold Out Jam', True, False, cls.lonely)

    def _request(self, product, qty):
        return self.env['sa.group.request'].sudo().create({
            'group_id': self.wa_group.id,
            'requester_phone': '+917009900031',
            'raw_text': product.name,
            'product_id': product.id,
            'qty': qty,
        })

    def _stock(self, product, qty):
        request = self._request(product, 1)
        company = request._mart369_stock_company()
        warehouse = self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', company.id)], limit=1)
        self.env['stock.quant'].sudo()._update_available_quantity(
            product.product_variant_id, warehouse.lot_stock_id, qty)

    @staticmethod
    def _accepted(request):
        """The customer pressed ACCEPT on the product page - the confirm
        module holds `_on_confirmed` back until then."""
        return request.with_context(sa_confirm_accepted=True)._on_confirmed()

    def assertFromShelf(self, request):
        """The flow priced it from stock rather than asking vendors or
        refusing. The pricing itself is the stack's and needs a live
        employee session, so only the choice is recorded here."""
        quoted = []
        Request = type(self.env['sa.group.request'])

        def record(this, product):
            quoted.append(product)
            return True

        with patch.object(Request, '_quote_from_stock', record):
            self._accepted(request)
        self.assertEqual(quoted, [request.product_id], 'priced from the shelf')
        self.assertNotIn(request.state, ('sourcing', 'dropped'), 'not sourced, not refused')

    def _said(self, words):
        return any(words in body for __, body in self.wa_sent)

    # ---------------------------------------------------------- untracked

    def test_an_untracked_product_is_on_the_shelf(self):
        """It used to read 0 on hand and go to the vendors."""
        request = self._request(self.untracked, 3)
        request._assess_availability(self.untracked)
        self.assertEqual(request.stock_status, 'in_stock')
        self.assertFromShelf(request)

    # ------------------------------------------- "Sell when Out-of-Stock" off

    def test_a_sold_out_product_is_not_offered(self):
        products, __ = self.env['sa.group.request']._sa_menu_products(self.shelf)
        self.assertIn(self.untracked, products)
        self.assertIn(self.sourced, products)
        self.assertNotIn(self.strict, products, 'none free, so not on the menu')
        hits = self.env['sa.group.request']._search_products_loose('Bridge Strict Ghee')
        self.assertNotIn(self.strict, hits)

    def test_a_category_with_nothing_to_sell_disappears(self):
        top = self.env['sa.group.request']._sa_menu_categories()
        self.assertIn(self.shelf, top)
        self.assertNotIn(self.lonely, top)

    def test_a_sold_out_product_is_refused_not_sourced(self):
        request = self._request(self.strict, 1)
        request._on_confirmed()
        self.assertEqual(request.state, 'dropped')
        self.assertEqual(request.drop_reason, 'unavailable')
        self.assertTrue(self._said('out of stock'))

    def test_asking_for_more_than_is_left_says_how_many(self):
        self._stock(self.strict, 2)
        request = self._request(self.strict, 5)
        request._on_confirmed()
        self.assertEqual(request.drop_reason, 'unavailable')
        self.assertTrue(self._said('only have *2*'))

    def test_enough_left_is_sold_from_the_shelf(self):
        self._stock(self.strict, 2)
        products, __ = self.env['sa.group.request']._sa_menu_products(self.shelf)
        self.assertIn(self.strict, products, 'back on the menu once some is free')
        request = self._request(self.strict, 2)
        request._assess_availability(self.strict)
        self.assertEqual(request.stock_status, 'in_stock')
        self.assertFromShelf(request)

    def test_the_last_unit_gone_before_confirm_makes_no_order(self):
        self._stock(self.strict, 2)
        request = self._request(self.strict, 2)
        self.assertFromShelf(request)
        self._stock(self.strict, -2)          # somebody else took them
        orders = self.env['sale.order'].sudo().search_count([])
        request._place_order()
        self.assertEqual(self.env['sale.order'].sudo().search_count([]), orders)
        self.assertEqual(request.drop_reason, 'unavailable')

    # -------------------------------------------- "Sell when Out-of-Stock" on

    def test_a_product_allowed_to_sell_out_is_still_sourced(self):
        request = self._request(self.sourced, 1)
        request._assess_availability(self.sourced)
        self.assertEqual(request.stock_status, 'on_order')
        self._accepted(request)
        self.assertNotEqual(request.drop_reason, 'unavailable',
                            'the vendors are asked, as before')
