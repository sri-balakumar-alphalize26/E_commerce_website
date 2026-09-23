"""The products desk's read.

`mart369_product_page` answers a different question from `_resolve_sections`,
and the difference is the whole reason it exists. That one answers "what does
the shopper get", so it returns visible fields and nothing else. This one
answers "what will this product show, and what did it decide not to" - so a
switched-off section has to come back *marked* switched off rather than simply
be absent. Missing and deliberately-hidden look identical to somebody reading
the screen, and only one of them is a decision anybody made.

What is not re-tested here is the ladder itself. `test_resolver.py` already
pins the nine-way visibility truth table and the exact merge order; these
assert that the desk reads that ladder rather than a second copy of it.
"""

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestProductDesk(TransactionCase):

    def setUp(self):
        super().setUp()
        self.category = self.env['product.public.category'].create({
            'name': 'Desk Test Category'})
        self.product = self.env['product.template'].create({
            'name': 'Desk Test Product',
            'is_published': True,
            'list_price': 10,
            'public_categ_ids': [(6, 0, [self.category.id])],
        })

    def _page(self, product=None):
        return self.env['mart369.product.field'].mart369_product_page(
            (product or self.product).id)

    def _section_named(self, page, key):
        for section in page['sections']:
            if section['key'] == key:
                return section
        return None

    def _row_named(self, section, key):
        for row in section['fields']:
            if row['key'] == key:
                return row
        return None

    # ---------------------------------------------------------------- shape

    def test_it_answers_for_a_real_product(self):
        page = self._page()
        self.assertEqual(page['product']['id'], self.product.id)
        self.assertTrue(page['sections'], 'the shop has sections')

    def test_a_product_that_is_not_there_is_empty_not_a_crash(self):
        self.assertEqual(
            self.env['mart369.product.field'].mart369_product_page(999999), {})

    def test_every_field_is_listed_not_only_the_overridden_ones(self):
        """The product form already had a list of overrides. It shows the
        exceptions, which is why it tells you nothing about a product nobody
        has touched - this has to show the whole page."""
        page = self._page()
        listed = sum(len(s['fields']) for s in page['sections'])
        self.assertEqual(listed, self.env['mart369.product.field'].search_count([]))

    # ----------------------------------------------------- hidden, not gone

    def test_a_hidden_field_is_marked_rather_than_dropped(self):
        field = self.env['mart369.product.field'].search([], limit=1)
        self.env['mart369.product.field'].set_product_state(
            field.id, self.product.id, 'hide')

        section = self._section_named(self._page(), field.section_id.key)
        row = self._row_named(section, field.key)
        self.assertIsNotNone(row, 'still listed')
        self.assertFalse(row['visible'], 'and marked as off')

    def test_a_switched_off_section_still_comes_back(self):
        section = self.env['mart369.product.section'].search([], limit=1)
        section.show = False

        got = self._section_named(self._page(), section.key)
        self.assertIsNotNone(got, 'the band is reported, not omitted')
        self.assertFalse(got['show'])
        self.assertEqual(got['shown'], 0, 'nothing inside it shows')
        self.assertTrue(got['total'], 'though it still has fields')

    def test_the_counts_are_what_the_screen_prints(self):
        section = self.env['mart369.product.section'].search(
            [('field_ids', '!=', False)], limit=1)
        field = section.field_ids[0]
        self.env['mart369.product.field'].set_product_state(
            field.id, self.product.id, 'hide')

        got = self._section_named(self._page(), section.key)
        self.assertEqual(got['total'], len(section.field_ids))
        self.assertEqual(got['shown'], got['total'] - 1)

    # ------------------------------------------------------- where it came from

    def test_a_value_set_on_the_product_says_so(self):
        field = self.env['mart369.product.field'].search(
            [('per_product', '=', True)], limit=1)
        self.env['mart369.product.field'].set_product_value(
            field.id, self.product.id, 'Only for this one')

        row = self._row_named(
            self._section_named(self._page(), field.section_id.key), field.key)
        self.assertEqual(row['value'], 'Only for this one')
        self.assertEqual(row['source'], 'product')

    def test_an_inherited_value_says_the_shop(self):
        """The column that stops the same wording being typed twice: without
        it an inherited value and one set here read identically."""
        field = self.env['mart369.product.field'].search(
            [('source', '=', 'text'), ('per_product', '=', True)], limit=1)
        field.default_value = 'The shop says this'
        self.env['mart369.product.field'].reset_product_state(
            field.id, self.product.id)

        row = self._row_named(
            self._section_named(self._page(), field.section_id.key), field.key)
        self.assertEqual(row['value'], 'The shop says this')
        self.assertEqual(row['source'], 'default')

    # --------------------------------------------- agreeing with the shopper

    def test_it_agrees_with_what_the_shopper_is_served(self):
        """The point of reading the same ladder. Whatever this screen reports
        as visible must be exactly what `_resolve_sections` - the thing behind
        /369mart/product/<id> - hands the app."""
        Field = self.env['mart369.product.field']
        field = Field.search([], limit=1)
        Field.set_product_state(field.id, self.product.id, 'hide')

        shopper = Field._resolve_sections(self.product)
        shopper_keys = {f.key for rows in shopper.values() for f, __ in rows}

        desk_keys = {
            row['key']
            for section in self._page()['sections'] if section['show']
            for row in section['fields'] if row['visible']
        }
        self.assertEqual(desk_keys, shopper_keys)
