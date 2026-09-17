from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase


@tagged('post_install', '-at_install')
class TestProductApi(HttpCase):
    """The endpoint the app reads, over real HTTP."""

    def setUp(self):
        super().setUp()
        self.product = self.env['product.template'].search(
            [('is_published', '=', True)], limit=1)
        self.assertTrue(self.product, 'need a published product to test against')

    def _get(self, path=None):
        response = self.url_open(path or '/369mart/product/%d' % self.product.id)
        self.assertEqual(response.status_code, 200)
        return response

    def test_public_and_json(self):
        """A logged-out app can read it, and gets JSON with CORS."""
        response = self._get()
        self.assertTrue(response.headers['Content-Type'].startswith('application/json'))
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), '*')
        self.assertNotIn('session_id', response.headers.get('Set-Cookie', ''))

    def test_allow_origin_sent_once(self):
        """Twice and every browser rejects the response."""
        raw = self._get().raw.headers.get_all('Access-Control-Allow-Origin') or []
        self.assertLessEqual(len(raw), 1)

    def test_shape(self):
        payload = self._get().json()
        self.assertEqual(set(payload),
                         {'p', 'd', 'variants', 'bundle', 'similar', 'related'})
        # `p` is the same card the home page sends - id, name, price at minimum.
        self.assertLessEqual({'id', 'name', 'price', 'images', 'art', 'unit'},
                             set(payload['p']))

    def test_the_card_matches_the_home_page(self):
        """The product page and the home page must describe a product
        identically, or the app shows two different prices for one thing."""
        helper = self.env['mart369.home.serializable'].sudo()
        ctx = helper._price_context_for(self.product)
        mode = 'all' if self.product.mart_delivery_text else 'quick'
        expected = helper._serialize_product(self.product, None, ctx, mode)
        self.assertEqual(self._get().json()['p'], expected)

    def test_info_is_ordered_pairs_and_specs_is_an_object(self):
        d = self._get().json()['d']
        if 'info' in d:
            self.assertIsInstance(d['info'], list)
            for row in d['info']:
                self.assertIsInstance(row, list)
                self.assertEqual(len(row), 2, 'each row is [label, value]')
        if 'specs' in d:
            self.assertIsInstance(d['specs'], dict)

    def test_no_nulls_anywhere(self):
        """A field that is switched off is absent, never null."""
        def walk(node, path='payload'):
            if isinstance(node, dict):
                for key, value in node.items():
                    self.assertIsNotNone(value, '%s.%s is null' % (path, key))
                    walk(value, '%s.%s' % (path, key))
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    walk(value, '%s[%d]' % (path, i))
        walk(self._get().json())

    def test_distribution_has_five_bars(self):
        d = self._get().json()['d']
        if 'dist' in d:
            self.assertEqual(len(d['dist']), 5)
            for pct in d['dist']:
                self.assertGreaterEqual(pct, 0)
                self.assertLessEqual(pct, 100)

    def test_unknown_product_is_404(self):
        self.assertEqual(
            self.url_open('/369mart/product/99999999').status_code, 404)

    def test_health(self):
        payload = self._get('/369mart/product/health').json()
        self.assertTrue(payload['ok'])
        self.assertGreater(payload['fields'], 0)


@tagged('post_install', '-at_install')
class TestProductApiDetails(TransactionCase):
    """The parts that need a write first, checked on the serializer.

    With --test-enable Odoo answers readonly routes from a separate
    connection that cannot see this transaction, so mutate-then-read has to
    go through the code rather than over HTTP.
    """

    def setUp(self):
        super().setUp()
        self.Page = self.env['mart369.product.page']
        self.Field = self.env['mart369.product.field']
        self.product = self.env['product.template'].create({
            'name': 'API Detail Product', 'is_published': True, 'list_price': 99,
        })

    def _details(self):
        shown = self.Field._resolve_sections(self.product)
        keys = {f.key for rows in shown.values() for f, _v in rows}
        return self.Page.details(self.product, shown, keys)

    def test_hidden_field_leaves_the_table(self):
        field = self.Field.search([('key', '=', 'sold_by')])
        rows = dict(self._details().get('info', []))
        self.assertIn(field.name, rows)

        field.show = False
        rows = dict(self._details().get('info', []))
        self.assertNotIn(field.name, rows, 'switched off means absent')

    def test_returnable_reads_as_a_real_boolean(self):
        self.assertIsInstance(self._details().get('returnable'), bool)

    def test_no_reviews_yet_says_so(self):
        d = self._details()
        self.assertEqual(d.get('reviews'), [],
                         'a product with no reviews sends an empty list')
        self.assertNotIn('rating', d, 'and claims no rating')

    def test_placeholder_and_internal_ratings_are_ignored(self):
        """Odoo creates unconsumed ratings just to mint access tokens, and
        internal notes are not customer reviews."""
        Rating = self.env['rating.rating']
        common = {
            'res_model_id': self.env['ir.model']._get_id('product.template'),
            'res_id': self.product.id,
        }
        Rating.create(dict(common, rating=0, consumed=False, feedback='token'))
        Rating.create(dict(common, rating=5, consumed=True, feedback='real one'))

        d = self._details()
        texts = [r['text'] for r in d.get('reviews', [])]
        self.assertIn('real one', texts)
        self.assertNotIn('token', texts)
        self.assertEqual(d.get('ratingCount'), 1)
