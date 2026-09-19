"""Categories, browsing and search over HTTP.

The tests that matter most:

* test_card_carries_rating_popularity_and_brand - if a card stops carrying
  these, the app silently falls back to `hash(product.id)` and nobody notices,
  because a hash looks exactly like a plausible rating.
* test_recent_searches_are_private - one customer must never read another's.
"""

import json

import psycopg2

from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}


@tagged('post_install', '-at_install')
class TestMart369CatalogApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Category = cls.env['product.public.category']
        cls.fruit = Category.create({
            'name': 'Test Fruits', 'sequence': 1, 'mart_mode': 'quick',
            'mart_tone': '#e8f5e9', 'mart_accent': '#1f7a4c',
            'mart_blurb': 'Farm-fresh produce, picked daily',
        })
        cls.fresh = Category.create({
            'name': 'Test Fresh Fruits', 'parent_id': cls.fruit.id, 'sequence': 1,
        })
        cls.soon = Category.create({
            'name': 'Test Launching Soon', 'sequence': 2, 'mart_mode': 'all',
        })
        cls.hidden = Category.create({
            'name': 'Test Hidden Aisle', 'sequence': 3, 'mart_in_app': False,
        })

        Template = cls.env['product.template']
        cls.apple = Template.create({
            'name': 'Test Shimla Apple 1 kg', 'list_price': 229.0,
            'is_published': True, 'mart_brand': '369 Fresh',
            'mart_unit_text': '1 kg',
            'public_categ_ids': [(6, 0, [cls.fresh.id])],
        })
        cls.banana = Template.create({
            'name': 'Test Robusta Banana 1 kg', 'list_price': 59.0,
            'is_published': True, 'mart_brand': '369 Fresh',
            'public_categ_ids': [(6, 0, [cls.fresh.id])],
        })
        cls.draft = Template.create({
            'name': 'Test Unpublished Melon', 'list_price': 99.0,
            'is_published': False,
            'public_categ_ids': [(6, 0, [cls.fresh.id])],
        })

    # ------------------------------------------------------------- plumbing

    def _get(self, path):
        response = self.opener.request(
            'GET', self.base_url() + path, headers=HEADERS)
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, {}

    def _post(self, path, payload):
        response = self.opener.request(
            'POST', self.base_url() + path, data=json.dumps(payload), headers=HEADERS)
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, {}

    def _signup(self, name, email):
        return self._post('/369mart/auth/signup', {
            'name': name, 'email': email, 'password': 'secret123',
        })

    def _names(self, items):
        return sorted(i['name'] for i in items)

    def _find(self, items, name):
        return next((i for i in items if i['name'] == name), None)

    # ------------------------------------------------------------ the tree

    def test_the_tree_matches_the_shape_the_app_draws(self):
        status, data = self._get('/369mart/catalog')
        self.assertEqual(status, 200)
        tree = {c['slug']: c for c in data['categories']}

        fruit = tree.get('test-fruits')
        self.assertTrue(fruit, 'a top-level category should be in the tree')
        self.assertEqual(fruit['name'], 'Test Fruits')
        self.assertEqual(fruit['mode'], 'quick')
        self.assertEqual(fruit['tone'], '#e8f5e9')
        self.assertEqual(fruit['accent'], '#1f7a4c')
        self.assertEqual(fruit['blurb'], 'Farm-fresh produce, picked daily')
        self.assertEqual([s['slug'] for s in fruit['subs']], ['test-fresh-fruits'])

        self.assertNotIn('test-hidden-aisle', tree, 'hidden means hidden')
        self.assertIn('test-fresh-fruits', [s['slug'] for s in fruit['subs']])

    def test_the_tree_says_what_money_the_prices_are_in(self):
        """The app printed a rupee sign in front of every number it was
        handed, whatever the shop was pricing in. It formats what it is
        told now, so it has to be told."""
        status, data = self._get('/369mart/catalog')
        self.assertEqual(status, 200)
        money = data['currency']
        company = self.env.company.currency_id
        self.assertEqual(money['code'], company.name)
        self.assertEqual(money['decimals'], company.decimal_places)
        self.assertIn(money['position'], ('before', 'after'))
        self.assertTrue(money['symbol'], 'something has to go beside the number')

    def test_a_category_with_nothing_in_it_is_not_an_error(self):
        """Fashion and Books say "Launching soon"; that is a state, not a 404."""
        status, data = self._get('/369mart/browse/test-launching-soon')
        self.assertEqual(status, 200)
        self.assertEqual(data['items'], [])

    def test_the_slug_is_made_from_the_name_and_stays_unique(self):
        Category = self.env['product.public.category']
        twin = Category.create({'name': 'Test Fruits'})
        self.assertEqual(twin.mart_slug, 'test-fruits-2')
        # Renaming does not move the address: a customer may have the link.
        self.fruit.name = 'Test Fruits Renamed'
        self.assertEqual(self.fruit.mart_slug, 'test-fruits')

    def test_two_categories_cannot_share_an_address(self):
        """Enforced in Postgres, not just in the helper that picks a free one.

        Odoo 19 ignores `_sql_constraints` with nothing but a line in the log,
        so this test is the only thing that would notice the constraint quietly
        never reaching the database.
        """
        Category = self.env['product.public.category']
        Category.create({'name': 'Test Twin A', 'mart_slug': 'test-twin'})
        with self.assertRaises(psycopg2.errors.UniqueViolation):
            with self.env.cr.savepoint():
                Category.create({'name': 'Test Twin B', 'mart_slug': 'test-twin'})

    def test_an_address_may_not_contain_spaces_or_capitals(self):
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.env['product.public.category'].create({
                'name': 'Test Bad Address', 'mart_slug': 'Not A Slug',
            })

    def test_a_category_that_predates_the_module_gets_an_address(self):
        """The install hook backfills slugs. Without it every category that
        already existed is unreachable: an empty slug in the tree and a 404
        from every browse."""
        old = self.env['product.public.category'].create({'name': 'Test Legacy Aisle'})
        old.invalidate_recordset()
        self.env.cr.execute(
            "UPDATE product_public_category SET mart_slug = NULL WHERE id = %s", (old.id,))
        old.invalidate_recordset(['mart_slug'])
        self.assertFalse(old.mart_slug)

        from odoo.addons.mart369_catalog import post_init_hook
        post_init_hook(self.env)
        old.invalidate_recordset(['mart_slug'])
        self.assertEqual(old.mart_slug, 'test-legacy-aisle')

    def test_a_child_takes_its_parents_storefront(self):
        self.assertEqual(self.fresh._mart369_mode(), 'quick')
        self.fruit.mart_mode = 'all'
        self.assertEqual(self.fresh._mart369_mode(), 'all')

    # ---------------------------------------------------------- the browse

    def test_browsing_a_category_returns_only_published_products(self):
        status, data = self._get('/369mart/browse/test-fruits')
        self.assertEqual(status, 200)
        names = self._names(data['items'])
        self.assertIn('Test Shimla Apple 1 kg', names)
        self.assertIn('Test Robusta Banana 1 kg', names)
        self.assertNotIn('Test Unpublished Melon', names)

    def test_browsing_a_sub_category_works_and_a_wrong_one_is_404(self):
        status, data = self._get('/369mart/browse/test-fruits/test-fresh-fruits')
        self.assertEqual(status, 200)
        self.assertEqual(data['sub']['slug'], 'test-fresh-fruits')

        status, __ = self._get('/369mart/browse/test-fruits/test-launching-soon')
        self.assertEqual(status, 404, 'a sub-category of another parent is not ours')

        status, __ = self._get('/369mart/browse/no-such-category')
        self.assertEqual(status, 404)

    def test_a_hidden_category_cannot_be_reached_by_its_address(self):
        status, __ = self._get('/369mart/browse/test-hidden-aisle')
        self.assertEqual(status, 404)

    # ------------------------------------------------- the three real values

    def test_card_carries_rating_popularity_and_brand(self):
        """`enrich()` falls back to hash(product.id) when these are missing, so
        their absence is invisible in the app - it just shows a made-up rating."""
        self.env['rating.rating'].create({
            'res_model_id': self.env['ir.model']._get('product.template').id,
            'res_id': self.apple.id,
            'rating': 4.0, 'consumed': True, 'is_internal': False,
        })
        self.env['rating.rating'].create({
            'res_model_id': self.env['ir.model']._get('product.template').id,
            'res_id': self.apple.id,
            'rating': 5.0, 'consumed': True, 'is_internal': False,
        })

        status, data = self._get('/369mart/browse/test-fruits')
        self.assertEqual(status, 200)
        apple = self._find(data['items'], 'Test Shimla Apple 1 kg')
        banana = self._find(data['items'], 'Test Robusta Banana 1 kg')

        self.assertEqual(apple['brand'], '369 Fresh')
        self.assertEqual(apple['rating'], 4.5, 'the average of 4 and 5')
        self.assertEqual(apple['ratingCount'], 2)
        self.assertIn('popularity', apple)
        self.assertEqual(apple['popularity'], 0, 'nothing sold yet')

        self.assertNotIn(
            'rating', banana,
            'a product with no reviews must omit rating, not send 0 - the app '
            'reads `p.rating ?? hash(...)`, and 0 is not nullish so it would '
            'show as zero stars')

    def test_an_internal_note_is_not_a_customer_review(self):
        self.env['rating.rating'].create({
            'res_model_id': self.env['ir.model']._get('product.template').id,
            'res_id': self.banana.id,
            'rating': 1.0, 'consumed': True, 'is_internal': True,
        })
        status, data = self._get('/369mart/browse/test-fruits')
        banana = self._find(data['items'], 'Test Robusta Banana 1 kg')
        self.assertNotIn('rating', banana)

    def test_popularity_counts_confirmed_orders_only(self):
        partner = self.env['res.partner'].create({'name': 'Test Buyer'})
        variant = self.apple.product_variant_id
        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [(0, 0, {'product_id': variant.id, 'product_uom_qty': 7})],
        })
        status, data = self._get('/369mart/browse/test-fruits')
        apple = self._find(data['items'], 'Test Shimla Apple 1 kg')
        self.assertEqual(apple['popularity'], 0, 'a draft basket must not count')

        order.action_confirm()
        status, data = self._get('/369mart/browse/test-fruits')
        apple = self._find(data['items'], 'Test Shimla Apple 1 kg')
        self.assertEqual(apple['popularity'], 7)

    # ---------------------------------------------------------- the search

    def test_search_matches_name_and_brand(self):
        status, data = self._get('/369mart/search?q=shimla')
        self.assertEqual(status, 200)
        self.assertIn('Test Shimla Apple 1 kg', self._names(data['items']))

        status, data = self._get('/369mart/search?q=369 Fresh')
        self.assertIn('Test Robusta Banana 1 kg', self._names(data['items']))

        status, data = self._get('/369mart/search?q=melon')
        self.assertEqual(data['items'], [], 'unpublished products stay hidden')

    def test_suggest_stops_at_eight(self):
        Template = self.env['product.template']
        for n in range(12):
            Template.create({
                'name': 'Test Suggest Widget %d' % n, 'list_price': 10.0,
                'is_published': True,
            })
        status, data = self._get('/369mart/search/suggest?q=Suggest Widget')
        self.assertEqual(status, 200)
        self.assertEqual(len(data['items']), 8,
                         'the typeahead draws eight rows')

    def test_trending_counts_real_searches_and_skips_empty_ones(self):
        for __ in range(3):
            self._get('/369mart/search?q=shimla')
        self._get('/369mart/search?q=nothinglikethis')

        Term = self.env['mart369.search.term'].sudo()
        shimla = Term.search([('term', '=', 'shimla')], limit=1)
        self.assertEqual(shimla.hits, 3)
        self.assertGreater(shimla.results, 0)

        empty = Term.search([('term', '=', 'nothinglikethis')], limit=1)
        self.assertEqual(empty.results, 0)

        status, data = self._get('/369mart/search/trending')
        self.assertIn('shimla', data['trending'])
        self.assertNotIn('nothinglikethis', data['trending'],
                         'suggesting a search that finds nothing is worse than '
                         'suggesting nothing')

    def test_typing_does_not_pollute_trending(self):
        self._get('/369mart/search/suggest?q=shim')
        Term = self.env['mart369.search.term'].sudo()
        self.assertFalse(Term.search([('term', '=', 'shim')]),
                         'every keystroke reaches suggest; counting it would '
                         'make "coff" as trending as "coffee"')

    # ------------------------------------------------- my recent searches

    def test_recent_searches_are_private(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'auth_signup.invitation_scope', 'b2c')

        self._signup('Cat One', 'cat-one@example.com')
        self._post('/369mart/search/recent', {'q': 'dark chocolate'})
        status, mine = self._get('/369mart/search/recent')
        self.assertEqual(status, 200)
        self.assertEqual(mine['recent'], ['dark chocolate'])

        self._post('/369mart/auth/logout', {})
        self._signup('Cat Two', 'cat-two@example.com')
        status, theirs = self._get('/369mart/search/recent')
        self.assertEqual(status, 200)
        self.assertEqual(theirs['recent'], [],
                         "one customer must never see another's searches")

    def test_recent_searches_are_newest_first_without_repeats(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'auth_signup.invitation_scope', 'b2c')
        self._signup('Cat Three', 'cat-three@example.com')

        for term in ('atta', 'coffee', 'Atta'):
            self._post('/369mart/search/recent', {'q': term})
        status, data = self._get('/369mart/search/recent')
        self.assertEqual(data['recent'], ['atta', 'coffee'],
                         'the same search twice is one entry, moved to the top')

        self.opener.request('DELETE', self.base_url() + '/369mart/search/recent',
                            headers=HEADERS)
        status, data = self._get('/369mart/search/recent')
        self.assertEqual(data['recent'], [])

    def test_recent_searches_need_an_account(self):
        response = self.opener.request(
            'GET', self.base_url() + '/369mart/search/recent',
            headers=HEADERS, allow_redirects=False)
        self.assertIn(response.status_code, (302, 303),
                      'a signed-out visitor is sent to the login page')
        self.assertIn('/web/login', response.headers.get('Location', ''))
