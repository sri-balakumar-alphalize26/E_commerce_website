"""The products desk's read view: what this product's page shows.

`mart369_product_page` is read off the shopper's own payload, so the desk (and
the console, over the admin route) describe the page that is served: the
product's own setup - photos, brand, name, price, the choices, the Variant
specs, the Sales Description - plus real reviews and the rails below. None of
the page builder's rows the page no longer prints.
"""

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

SECTIONS = ['top', 'choices', 'specs', 'description', 'reviews', 'rails']


@tagged('post_install', '-at_install')
class TestProductDesk(TransactionCase):

    def setUp(self):
        super().setUp()
        self.product = self.env['product.template'].create({
            'name': 'Desk Test Product',
            'is_published': True,
            'list_price': 10,
            'description_sale': 'Two USB-C ports.',
        })

    def _page(self, product=None):
        return self.env['mart369.product.field'].mart369_product_page(
            (product or self.product).id)

    def _section(self, page, key):
        return next((s for s in page['sections'] if s['key'] == key), None)

    def _rows(self, page, key):
        section = self._section(page, key)
        return section['fields'] if section else []

    def _row(self, page, section, key):
        return next((r for r in self._rows(page, section) if r['key'] == key), None)

    # ---------------------------------------------------------------- shape

    def test_it_answers_for_a_real_product(self):
        page = self._page()
        self.assertEqual(page['product']['id'], self.product.id)
        self.assertTrue(page['sections'])

    def test_a_product_that_is_not_there_is_empty_not_a_crash(self):
        self.assertEqual(
            self.env['mart369.product.field'].mart369_product_page(999999), {})

    def test_only_what_the_page_draws_in_page_order(self):
        keys = [s['key'] for s in self._page()['sections']]
        self.assertEqual(keys, [k for k in SECTIONS if k in keys])
        self.assertNotIn('choices', keys, 'a product with no choice asks nothing')

    def test_none_of_the_old_builder_rows(self):
        names = {r['name'] for s in self._page()['sections'] for r in s['fields']}
        for old in ('Key features', 'Country of origin', 'Manufacturer name',
                    'Return policy wording', 'Disclaimer', 'Material'):
            self.assertNotIn(old, names)

    # ------------------------------------------------ agreeing with the shopper

    def test_it_reads_what_the_shopper_is_served(self):
        served = self.env['mart369.product.page'].sudo().payload(self.product)['p']
        page = self._page()
        self.assertEqual(self._row(page, 'top', 'name')['value'], served['name'])
        self.assertEqual(float(self._row(page, 'top', 'price')['value']), served['price'])
        self.assertEqual(self._row(page, 'description', 'description')['value'],
                         'Two USB-C ports.')

    def test_the_specs_are_the_variant_specs_the_page_lists(self):
        served = self.env['mart369.product.page'].sudo().payload(self.product)['p']
        rows = self._rows(self._page(), 'specs')
        if served.get('specs'):
            self.assertEqual([(r['name'], r['value']) for r in rows],
                             list(served['specs'].items()))
        else:
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0]['visible'], 'an empty table is listed as not shown')

    def test_an_empty_description_is_listed_as_not_shown(self):
        self.product.description_sale = False
        row = self._row(self._page(), 'description', 'description')
        self.assertEqual(row['value'], '')
        self.assertFalse(row['visible'])

    def test_a_product_with_a_choice_lists_it(self):
        ram = self.env['product.attribute'].create({
            'name': 'Zz Desk View RAM', 'create_variant': 'always',
            'value_ids': [(0, 0, {'name': '8GB'}), (0, 0, {'name': '16GB'})]})
        self.product.attribute_line_ids = [(0, 0, {
            'attribute_id': ram.id, 'value_ids': [(6, 0, ram.value_ids.ids)]})]
        page = self._page()
        row = next(r for r in self._rows(page, 'choices') if r['name'] == 'Zz Desk View RAM')
        self.assertEqual(row['value'], '8GB, 16GB')
        self.assertEqual(self._row(page, 'choices', 'variants')['value'], '2')

    def test_every_row_says_it_is_the_product_record(self):
        sources = {r['source'] for s in self._page()['sections'] for r in s['fields']}
        self.assertEqual(sources, {'odoo'})

    def test_the_counts_are_what_the_screen_prints(self):
        for section in self._page()['sections']:
            self.assertEqual(section['total'], len(section['fields']))
            self.assertEqual(section['shown'], sum(1 for r in section['fields'] if r['visible']))
