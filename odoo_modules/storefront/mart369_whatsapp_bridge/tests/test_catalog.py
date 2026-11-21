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

    # ------------------------------- NEW ORDER: "what are you looking for?"

    def _type(self, text):
        msg = self.env['whatsapp.message'].new(
            {'participant_phone': self.request.requester_phone})
        return self.env['sa.group.request']._sa_typed_answer_hook(
            self.wa_group, msg, text)

    def _new_order(self):
        self.request._sa_menu_tapped({'kind': 'new', 'parent': 'main'})

    def test_new_order_asks_what_they_are_looking_for(self):
        self._new_order()
        menu = self._menu()
        self.assertTrue(self.request.sa_menu_ask_at)
        # 21 Nov 2026: no POPULAR NOW and no ALL CATEGORIES - type it, or MAIN MENU
        self.assertNotIn('\U0001F4C2 ALL CATEGORIES', menu)
        self.assertNotIn('⭐ POPULAR NOW', menu)
        self.assertIn('\U0001F3E0 MAIN MENU', menu)
        self.assertFalse([k for k, v in menu.items() if v.get('kind') == 'prodpick'],
                         'no products before they say what they want')

    def test_new_order_is_always_a_poll_with_back_and_main_menu(self):
        self._new_order()
        menu = self._menu()
        self.assertIn('⬅️ BACK', menu)
        self.assertIn('\U0001F3E0 MAIN MENU', menu)
        self.assertEqual(menu['⬅️ BACK']['level'], 'main')
        self.assertTrue(self.request.sa_menu_ask_at, 'a typed product is still searched')

    def test_typed_category_name_opens_that_category(self):
        self._new_order()
        self.assertTrue(self._type('bridge drives'))
        menu = self._menu()
        self.assertIn(self.quick_product.name, menu)
        self.assertNotIn(self.hidden.name, menu)

    def test_typed_product_word_lists_the_matches(self):
        self._new_order()
        self.assertTrue(self._type('bananas'))
        menu = self._menu()
        self.assertIn(self.quick_product.name, menu)
        self.assertEqual(menu[self.quick_product.name]['kind'], 'prodpick')
        self.assertTrue(menu[self.quick_product.name]['parent'].startswith('find'))

    def test_search_never_offers_an_unpublished_product(self):
        self._new_order()
        self._type('backroom widget')
        self.assertNotIn(self.hidden.name, self._menu())

    def test_nothing_found_goes_to_the_ordinary_enquiry(self):
        self._new_order()
        self.assertIsNone(self._type('zqxv blorptastic'))
        self.assertFalse(self.request.sa_menu_ask_at)

    def test_typing_after_the_window_is_the_ordinary_flow(self):
        self._new_order()
        self.request.sa_menu_ask_at = '2020-01-01 00:00:00'
        self.assertIsNone(self._type('bananas'))

    def test_somebody_else_typing_is_not_searched(self):
        self._new_order()
        msg = self.env['whatsapp.message'].new({'participant_phone': '+919876500777'})
        self.assertIsNone(self.env['sa.group.request']._sa_typed_answer_hook(
            self.wa_group, msg, 'bananas'))

    def test_not_listed_ends_the_search(self):
        self._new_order()
        self._type('bananas')
        not_listed = [v for k, v in self._menu().items() if 'NOT LISTED' in k][0]
        self.request._sa_menu_tapped(not_listed)
        self.assertFalse(self.request.sa_menu_ask_at)

    def test_leaving_for_another_menu_ends_the_search(self):
        self._new_order()
        self.request._sa_menu_show('more')
        self.assertFalse(self.request.sa_menu_ask_at)

    def test_every_category_is_reachable_with_more(self):
        Categ = self.env['product.category'].sudo()
        Prod = self.env['product.template'].sudo()
        made = Categ
        for i in range(9):
            c = Categ.create({'name': 'Bridge Aisle %02d' % i, 'sa_menu_sequence': 2})
            Prod.create({'name': 'Bridge Aisle Item %02d' % i, 'sale_ok': True, 'type': 'consu',
                         'is_published': True, 'list_price': 5.0, 'categ_id': c.id})
            made |= c
        seen, level = set(), 'categ'
        for __ in range(40):
            self.request._sa_menu_show(level)
            menu = self._menu()
            self.assertLessEqual(len(menu), 10)
            seen |= set(menu)
            if '➡️ MORE' not in menu:
                break
            level = menu['➡️ MORE']['level']
        for c in made:
            self.assertIn(c.name, seen, '%s never shown' % c.name)

    def test_order_again_lists_their_past_product(self):
        self.env['sa.group.request'].sudo().create({
            'group_id': self.wa_group.id,
            'requester_phone': self.request.requester_phone,
            'raw_text': self.quick_product.name,
            'product_id': self.quick_product.id,
            'state': 'order_created',
        })
        self._new_order()
        menu = self._menu()
        self.assertIn('\U0001F501 ORDER AGAIN', menu)
        self.request._sa_menu_tapped(menu['\U0001F501 ORDER AGAIN'])
        self.assertIn(self.quick_product.name, self._menu())

    def test_picking_a_searched_product_opens_an_enquiry(self):
        self._new_order()
        self._type('bananas')
        self.request._sa_menu_tapped(self._menu()[self.quick_product.name])
        self.assertFalse(self.request.sa_menu_ask_at)
        enquiry = self.env['sa.group.request'].sudo().search(
            [('product_id', '=', self.quick_product.id),
             ('group_id', '=', self.wa_group.id)], order='id desc', limit=1)
        self.assertTrue(enquiry)

    # ------------------------------------- typed at the main menu, typos

    def test_a_word_typed_at_the_main_menu_is_searched(self):
        self.request._sa_menu_show('main')
        self.assertTrue(self.request.sa_menu_ask_at)
        self.assertTrue(self._type('bananas'))
        self.assertIn(self.quick_product.name, self._menu())

    def test_a_misspelt_word_still_finds_the_product(self):
        self._new_order()
        self.assertTrue(self._type('bannanas'))
        self.assertIn(self.quick_product.name, self._menu())
        self.assertEqual(self.request.sa_menu_term, 'bananas')

    def test_a_misspelt_product_is_not_taken_for_a_name(self):
        self.assertFalse(self.request._sa_name_typed_ok('Bannanas', 'ask'))
        self.assertTrue(self.request._sa_name_typed_ok('Karthik Raja', 'ask'))

    def test_a_word_nothing_like_the_shop_is_not_forced(self):
        self._new_order()
        self.assertIsNone(self._type('xylophonez'))

    # ------------------------------------------------- one poll for variants

    def _variant_product(self, values):
        attr = self.env['product.attribute'].sudo().create({
            'name': 'Bridge RAM %d' % len(values), 'create_variant': 'always',
            'value_ids': [(0, 0, {'name': v}) for v in values]})
        return self.env['product.template'].sudo().create({
            'name': 'Bridge Variant Laptop %d' % len(values), 'sale_ok': True, 'type': 'consu',
            'is_published': True, 'list_price': 100.0, 'categ_id': self.shelf.id,
            'attribute_line_ids': [(0, 0, {'attribute_id': attr.id,
                                           'value_ids': [(6, 0, attr.value_ids.ids)]})]})

    def _enquiry_for(self, product):
        return self.env['sa.group.request'].sudo().create({
            'group_id': self.wa_group.id, 'requester_phone': '+919876500010',
            'raw_text': product.name, 'product_id': product.id, 'state': 'new'})

    def test_few_variants_are_one_poll(self):
        product = self._variant_product(['8GB', '16GB', '32GB'])
        req = self._enquiry_for(product)
        req._sa_confirm_customer_send()
        menu = json.loads(req.sa_menu_json or '{}')
        self.assertEqual(sorted(k for k, v in menu.items() if v['kind'] == 'variant'),
                         ['16GB', '32GB', '8GB'])
        self.assertIn('✏️ OTHER', menu)
        req._sa_menu_tapped(menu['16GB'])
        self.assertEqual(req.sa_variant_id.product_template_attribute_value_ids.mapped('name'), ['16GB'])

    def test_other_on_the_variant_poll_asks_attribute_by_attribute(self):
        product = self._variant_product(['8GB', '16GB'])
        req = self._enquiry_for(product)
        req._sa_confirm_customer_send()
        req._sa_menu_tapped(json.loads(req.sa_menu_json)['✏️ OTHER'])
        menu = json.loads(req.sa_menu_json or '{}')
        self.assertTrue(all(v['kind'] == 'attr' for v in menu.values()))

    def test_many_variants_keep_one_question_per_attribute(self):
        product = self._variant_product(['%dGB' % (2 ** i) for i in range(9)])
        req = self._enquiry_for(product)
        req._sa_confirm_customer_send()
        menu = json.loads(req.sa_menu_json or '{}')
        self.assertTrue(menu)
        self.assertTrue(all(v['kind'] == 'attr' for v in menu.values()))

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
