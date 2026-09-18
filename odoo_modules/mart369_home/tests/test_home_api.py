import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged('post_install', '-at_install')
class TestMart369HomeApi(HttpCase):

    def setUp(self):
        super().setUp()
        self.config = self.env['mart369.config']._get()
        self.mode = self.env['mart369.home.mode']._get('quick')

    def _fetch(self, path='/369mart/home'):
        response = self.url_open(path)
        self.assertEqual(response.status_code, 200)
        return response

    # ------------------------------------------------------------ the route

    def test_endpoint_is_public(self):
        """A logged-out app can read the home page, and gets no cookie."""
        response = self._fetch()
        self.assertTrue(
            response.headers['Content-Type'].startswith('application/json'),
            'The app expects JSON, got %s' % response.headers['Content-Type'])
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), '*')
        # save_session=False keeps Odoo from opening a session for a visitor
        # who only reads the home page. The website layer still sets a
        # frontend_lang cookie, which is harmless - session_id is the one
        # that would make this endpoint uncacheable.
        self.assertNotIn(
            'session_id', response.headers.get('Set-Cookie', ''),
            'A cacheable public endpoint must not open a session.')

    def test_cors_preflight(self):
        """The browser's OPTIONS check is answered before our code runs."""
        response = self.opener.options(self.base_url() + '/369mart/home')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), '*')
        self.assertIn('GET', response.headers.get('Access-Control-Allow-Methods', ''))
        self.assertIn('Access-Control-Allow-Headers', response.headers)

    def test_allow_origin_sent_once(self):
        """Emitting it twice makes every browser reject the response."""
        response = self._fetch()
        raw = response.raw.headers.get_all('Access-Control-Allow-Origin') or []
        self.assertLessEqual(len(raw), 1, 'Allow-Origin was sent more than once.')

    def test_unknown_mode_is_404(self):
        response = self.url_open('/369mart/home/nope')
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------ the shape

    def test_top_level_shape(self):
        """Exactly what <Home modes={...} /> expects."""
        payload = self._fetch().json()
        self.assertEqual(set(payload), {'quick', 'all'})
        for mode in payload.values():
            self.assertEqual(
                set(mode),
                {'tabs', 'banners', 'categories', 'sections', 'freeDeliveryAt'})

    def test_tabs_and_banners_shape(self):
        mode = self._fetch().json()['quick']
        self.assertTrue(mode['tabs'], 'The seed data should ship tabs.')
        for tab in mode['tabs']:
            self.assertEqual(set(tab), {'key', 'label', 'icon'})
        self.assertTrue(mode['banners'], 'The seed data should ship banners.')
        for banner in mode['banners']:
            self.assertLessEqual(
                {'id', 'kicker', 'title', 'note', 'tone', 'art'}, set(banner))
            self.assertIsInstance(banner['art'], list)

    def test_no_null_values_anywhere(self):
        """Optional keys are left out, never sent as null."""
        raw = self._fetch().text

        def walk(node, path='payload'):
            if isinstance(node, dict):
                for key, value in node.items():
                    self.assertIsNotNone(value, '%s.%s is null' % (path, key))
                    walk(value, '%s.%s' % (path, key))
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    walk(value, '%s[%d]' % (path, i))

        walk(json.loads(raw))

    # ---------------------------------------------------------- the sections

    def test_banner_strip_carries_only_banner(self):
        """That single key is how the app tells a strip from a product row."""
        sections = self._fetch().json()['quick']['sections']
        strips = [s for s in sections if 'banner' in s]
        self.assertTrue(strips, 'The seed data should ship a banner strip.')
        for strip in strips:
            self.assertEqual(set(strip), {'banner'})
            self.assertTrue(strip['banner'])

    def test_hidden_banner_disappears_everywhere(self):
        """Turning a banner off removes it from the carousel and the strips.

        Checked on the serializer rather than over HTTP: the route is
        readonly=True, and with --test-enable Odoo serves readonly routes from
        a separate connection (orm/registry.py, `_db_readonly`) that cannot see
        this test's uncommitted write. In production there is no replica, so
        the route reads the same database.
        """
        banner = self.env.ref('mart369_home.banner_b3')
        banner.active = False
        try:
            mode = self.mode._serialize()
            self.assertNotIn('b3', [b['id'] for b in mode['banners']])
            for section in mode['sections']:
                self.assertNotIn('b3', section.get('banner', []))
        finally:
            banner.active = True

    def test_hand_picked_order_is_preserved(self):
        """The order the operator drags them into, not alphabetical.

        A many2many would come back sorted by product name - this is the
        reason the chosen products live in their own line model.
        """
        Product = self.env['product.template']
        charlie = Product.create({'name': 'ZZZ Charlie', 'is_published': True,
                                  'list_price': 30})
        alpha = Product.create({'name': 'AAA Alpha', 'is_published': True,
                                'list_price': 10})
        bravo = Product.create({'name': 'MMM Bravo', 'is_published': True,
                                'list_price': 20})

        section = self.env['mart369.home.section'].create({
            'mode_id': self.mode.id,
            'kind': 'rail',
            'name': 'Order check',
            'key': 'order-check',
            'source': 'manual',
            'sequence': 999,
            'picked_product_ids': [
                (0, 0, {'product_tmpl_id': charlie.id, 'sequence': 10}),
                (0, 0, {'product_tmpl_id': alpha.id, 'sequence': 20}),
                (0, 0, {'product_tmpl_id': bravo.id, 'sequence': 30}),
            ],
        })
        self.assertEqual(
            section._resolve_products().ids, [charlie.id, alpha.id, bravo.id])

        payload = section._serialize(self.mode._price_context(section))
        self.assertEqual(
            [item['name'] for item in payload['items']],
            ['ZZZ Charlie', 'AAA Alpha', 'MMM Bravo'])

    def test_empty_row_is_left_out(self):
        """A row with nothing in it would render as a bare heading."""
        section = self.env['mart369.home.section'].create({
            'mode_id': self.mode.id,
            'kind': 'rail',
            'name': 'Nothing here',
            'key': 'nothing-here',
            'source': 'manual',
            'sequence': 998,
        })
        self.assertIsNone(section._serialize({}))

    def test_best_sellers_work_for_the_public_user(self):
        """product.template.sales_count computes to zero for anyone who is not
        a salesperson, and sudo() does not change that. This row must not go
        empty or arbitrary when the app - a public visitor - asks for it."""
        self.env['product.template'].create({
            'name': 'Seller check', 'is_published': True, 'list_price': 10})
        section = self.env['mart369.home.section'].create({
            'mode_id': self.mode.id,
            'kind': 'rail',
            'name': 'Most loved',
            'key': 'most-loved-check',
            'source': 'rule',
            'rule': 'best',
            'sequence': 997,
        })
        public_env = section.with_user(self.env.ref('base.public_user'))
        self.assertTrue(
            public_env._resolve_products(),
            'Best sellers came back empty for the public user.')

    # ------------------------------------------------------------ the images

    def test_tile_image_is_public(self):
        """The app loads tile pictures without logging in."""
        tile = self.env.ref('mart369_home.tile_q_fruits')
        tile.image_1920 = (
            b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8'
            b'z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
        response = self.url_open(
            '/web/image/mart369.home.tile/%d/image_512' % tile.id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers['Content-Type'].startswith('image/'))
