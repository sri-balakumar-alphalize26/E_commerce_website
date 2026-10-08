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
                         {'p', 'card', 'd', 'variants', 'attrs', 'bundle', 'similar', 'related'})
        # `p` is the same card the home page sends - id, name, price at minimum.
        self.assertLessEqual({'id', 'name', 'price', 'images', 'art', 'unit'},
                             set(payload['p']))

    def test_the_card_matches_the_home_page(self):
        """The product page and the home page must describe a product
        identically, or the app shows two different prices for one thing."""
        helper = self.env['mart369.serializable'].sudo()
        ctx = helper._price_context_for(self.product)
        mode = 'all' if self.product.mart_delivery_text else 'quick'
        expected = helper._serialize_product(self.product, None, ctx, mode)
        card = self._get().json()['p']
        # The page adds the product's own setup - its variant's photos and
        # video, the Variant specs and the description; the rest is the home
        # page's card.
        self.assertEqual(card.pop('description', ''), helper._mart369_description(self.product))
        card.pop('descriptionHtml', None)
        for setup in ('specs', 'images', 'media'):
            card.pop(setup, None)
            expected.pop(setup, None)
        self.assertEqual(card, expected)

    def test_specs_ride_on_the_card_as_an_object(self):
        """The Variant specs are the card's; the old builder tables are gone."""
        payload = self._get().json()
        if 'specs' in payload['p']:
            self.assertIsInstance(payload['p']['specs'], dict)
        for gone in ('specs', 'features', 'returnText', 'disclaimer'):
            self.assertNotIn(gone, payload['d'])
        # "Product information" is back, from the product's real fields only.
        for row in payload['d'].get('info', []):
            self.assertEqual(len(row), 2)
            self.assertTrue(row[1])

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

    def _field(self, key):
        field = self.Field.search([('key', '=', key)])
        self.assertTrue(field, '%s is a builder row' % key)
        return field

    # ---------------------------------------------- About this item, details

    def test_about_this_item_prints_the_lead_in_bold(self):
        self.product.mart_features = (
            'Immersive display — A 6.3-inch Super Retina XDR display.\n\n'
            '- Long battery: up to 23 hours of video.\n'
            'Works with every charger you already own, from the old to the new ones')
        self.assertEqual(self._details()['about'], [
            {'lead': 'Immersive display', 'text': 'A 6.3-inch Super Retina XDR display.'},
            {'lead': 'Long battery', 'text': 'up to 23 hours of video.'},
            {'lead': '', 'text': 'Works with every charger you already own, from the old to the new ones'},
        ])

    def test_product_details_are_label_and_value_rows(self):
        self.product.mart_details = 'Brand: Apple\nnot a row\nModel Name:  iPhone 18 Pro \nEmpty:'
        self.assertEqual(self._details()['details'],
                         [['Brand', 'Apple'], ['Model Name', 'iPhone 18 Pro']])

    def test_the_word_box_is_sent_clean(self):
        self.product.mart_about_html = (
            '<ul><li><b>Display</b> — 6.3-inch</li></ul><script>alert(1)</script>'
            '<p style="color:red" class="x">Plain <a href="https://example.com">link</a></p>')
        html = self._details()['aboutHtml']
        self.assertIn('<b>Display</b>', html)
        self.assertIn('href="https://example.com"', html)
        self.assertNotIn('script', html)
        self.assertNotIn('style=', html)
        self.assertNotIn('class=', html)

    def test_lines_become_the_word_box_on_upgrade(self):
        """19.0.1.6.0 turns the typed lines into a bulleted list, bold leads kept."""
        import importlib.util
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'migrations', '19.0.1.6.0', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('mart369_product_1600', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        self.product.mart_features = 'Display — 6.3-inch <bright>\nLong battery'
        migration.migrate(self.env.cr, '19.0.1.5.8')
        self.product.invalidate_recordset()
        html = str(self.product.mart_about_html)
        self.assertIn('<li><b>Display</b> — 6.3-inch &lt;bright&gt;</li>', html)
        self.assertIn('<li>Long battery</li>', html)

    def test_no_about_or_details_without_them(self):
        d = self._details()
        self.assertNotIn('about', d)
        self.assertNotIn('details', d)

    def test_the_desk_offers_both_boxes(self):
        groups = {g['title']: [b['name'] for b in g['boxes']]
                  for g in self.env['product.template'].mart369_desk_form()['groups']}
        self.assertEqual(groups.get('About this item'), ['mart_about_html', 'mart_details'])

    # ---------------------------------------------- Edit page's switches

    def test_switching_off_the_sales_description_takes_it_off_the_page(self):
        self.product.description_sale = 'Two USB-C ports.'
        self.assertEqual(self.Page.payload(self.product)['p'].get('description'), 'Two USB-C ports.')
        self._field('sales_description').show = False
        self.assertNotIn('description', self.Page.payload(self.product)['p'])

    def _ecommerce(self, html):
        if 'description_ecommerce' not in self.product._fields:
            self.skipTest('website_sale is not installed')
        self.product.description_ecommerce = html

    def test_the_website_tab_description_shows_when_sales_is_empty(self):
        self.product.description_sale = False
        self._ecommerce('<p>RGB LEDs</p>')
        self.assertEqual(self.Page.payload(self.product)['p'].get('description'), 'RGB LEDs')

    def test_the_website_tab_wins_when_both_are_filled(self):
        """The eCommerce Description is the one written for the shop; the
        Sales Description is the stand-in when it is empty."""
        self.product.description_sale = 'Two USB-C ports.'
        self._ecommerce('<p>RGB LEDs</p>')
        p = self.Page.payload(self.product)['p']
        self.assertEqual(p.get('description'), 'RGB LEDs')
        self.assertIn('RGB LEDs', p.get('descriptionHtml', ''))

    def test_the_website_tab_keeps_its_formatting_and_loses_its_scripts(self):
        self.product.description_sale = False
        self._ecommerce('<h2>Specs</h2><p>Has <strong>two</strong> ports '
                        '<span style="color:red" class="x">here</span></p>'
                        '<ul><li>USB-C</li><li>HDMI</li></ul>'
                        '<script>alert(1)</script><img src=x onerror="alert(2)">')
        html = self.Page.payload(self.product)['p']['descriptionHtml']
        for kept in ('<h2>', '<strong>two</strong>', '<ul>', '<li>USB-C</li>'):
            self.assertIn(kept, html)
        for gone in ('<script', 'alert(1)', 'onerror', 'style=', 'class='):
            self.assertNotIn(gone, html)

    def test_a_sales_description_alone_is_plain_text(self):
        self.product.description_sale = 'Two USB-C ports.'
        self._ecommerce(False)
        p = self.Page.payload(self.product)['p']
        self.assertEqual(p.get('description'), 'Two USB-C ports.')
        self.assertNotIn('descriptionHtml', p)

    def test_switching_off_the_description_hides_the_website_tab_text_too(self):
        self.product.description_sale = False
        self._ecommerce('<p>RGB LEDs</p>')
        self._field('sales_description').show = False
        p = self.Page.payload(self.product)['p']
        self.assertNotIn('description', p)
        self.assertNotIn('descriptionHtml', p)

    def test_information_lists_only_what_is_filled(self):
        categ = self.env['product.category'].create({'name': 'Zz Headphones'})
        self.product.write({'categ_id': categ.id, 'default_code': 'BOAT-480',
                            'barcode': False, 'weight': 0.25})
        rows = dict(self.Page.payload(self.product)['d']['info'])
        self.assertEqual(rows.get('Category'), 'Zz Headphones')
        self.assertEqual(rows.get('Item code'), 'BOAT-480')
        self.assertTrue(rows.get('Weight', '').startswith('0.25'))
        self.assertNotIn('Barcode', rows)

    def test_nothing_filled_means_no_information_table(self):
        self.product.write({'categ_id': False, 'default_code': False,
                            'barcode': False, 'weight': 0})
        self.assertNotIn('info', self.Page.payload(self.product)['d'])

    def test_one_product_can_hide_it_alone(self):
        self.product.description_sale = 'Two USB-C ports.'
        other = self.env['product.template'].create({
            'name': 'API Other Product', 'is_published': True, 'description_sale': 'Kept.'})
        self.Field.set_product_state(self._field('sales_description').id, self.product.id, 'hide')
        self.assertNotIn('description', self.Page.payload(self.product)['p'])
        self.assertEqual(self.Page.payload(other)['p'].get('description'), 'Kept.')

    def test_switching_off_the_mrp_takes_it_off_the_page(self):
        self.product.compare_list_price = 150
        self.assertTrue(self.Page.payload(self.product)['p'].get('mrp'))
        self._field('mrp').show = False
        self.assertNotIn('mrp', self.Page.payload(self.product)['p'])

    def test_switching_off_the_variant_specs_takes_them_off_every_variant(self):
        ram = self.env['product.attribute'].create({
            'name': 'Zz API RAM', 'create_variant': 'always',
            'value_ids': [(0, 0, {'name': '8GB'}), (0, 0, {'name': '16GB'})]})
        self.product.attribute_line_ids = [(0, 0, {
            'attribute_id': ram.id, 'value_ids': [(6, 0, ram.value_ids.ids)]})]
        payload = self.Page.payload(self.product)
        self.assertTrue(all(v.get('specs') for v in payload['variants']))
        self._field('variant_specs').show = False
        payload = self.Page.payload(self.product)
        self.assertNotIn('specs', payload['p'])
        self.assertFalse([v for v in payload['variants'] if 'specs' in v])

    def test_a_switched_off_section_takes_its_parts_off(self):
        self.product.description_sale = 'Two USB-C ports.'
        self.env['mart369.product.section'].search([('key', '=', 'description')]).show = False
        self.assertNotIn('description', self.Page.payload(self.product)['p'])

    def test_the_listing_card_is_left_alone(self):
        """Only the page's cards: the home page, search and cart keep theirs."""
        self.product.compare_list_price = 150
        self._field('mrp').show = False
        helper = self.env['mart369.serializable'].sudo()
        card = helper._serialize_product(self.product, None, helper._price_context_for(self.product))
        self.assertTrue(card.get('mrp'))

    def test_the_read_view_shows_a_switched_off_part_as_off(self):
        self.product.description_sale = 'Two USB-C ports.'
        self._field('sales_description').show = False
        page = self.Field.mart369_product_page(self.product.id)
        row = next(r for s in page['sections'] for r in s['fields'] if r['key'] == 'description')
        self.assertEqual(row['value'], 'Two USB-C ports.', 'its value is still shown here')
        self.assertFalse(row['visible'])

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


@tagged('post_install', '-at_install')
class TestProductBuilderTour(HttpCase):

    def test_builder_tour(self):
        # Generous: the first request after an upgrade rebuilds the backend
        # asset bundle, which takes minutes on a big database.
        self.start_tour('/odoo/mart-product-advanced',
                        'mart369_product_builder',
                        login='admin', timeout=600)


@tagged('post_install', '-at_install')
class TestProductEditorTour(HttpCase):

    def test_editor_tour(self):
        # Generous for the same reason as the builder tour above: the first
        # request after an upgrade rebuilds the backend asset bundle.
        self.start_tour('/odoo/mart-product', 'mart369_product_editor',
                        login='admin', timeout=600)
