"""The Odoo product form, and whether it agrees with the product page.

Two things are worth pinning here, and they are the two that would go wrong
quietly.

**The form must not drift from the page.** Every product-page row that reads a
column on the product needs a box on the form to fill that column in. Add a row
to the registry, forget the box, and nobody notices until a shopkeeper asks why
a row on the live page is blank - months later, with nothing to point at. The
first test below fails instead, on the day it happens.

**Hiding must be the same answer the shopper gets.** The form asks
`_visible_for` rather than working it out again, so a box is hidden exactly
when the page will not print it. Re-deriving that would let the form hide a box
whose value is on screen in the app, which is worse than asking for too much.
"""

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestProductForm(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Field = self.env['mart369.product.field']
        self.category = self.env['product.public.category'].create({
            'name': 'Form Test Category'})
        self.product = self.env['product.template'].create({
            'name': 'Form Test Product',
            'is_published': True,
            'list_price': 10,
            'public_categ_ids': [(6, 0, [self.category.id])],
        })

    def _arch(self):
        """The product form as Odoo assembles it, every inherit applied."""
        return self.env['product.template'].get_view(
            self.env.ref('product.product_template_form_view').id, 'form')['arch']

    # ------------------------------------------------- the form and the page

    def test_every_page_column_has_a_box_on_the_form(self):
        """A page row reading a product column needs somewhere to type it.

        The one test that catches the whole class of mistake: a registry field
        pointing at an Odoo column that the form never offers. Its value could
        then only ever be empty, and the row on the page would be blank with no
        way to fill it.
        """
        arch = self._arch()
        columns = self.Field.search([('odoo_field', '!=', False)])

        missing = sorted({
            field.odoo_field for field in columns
            if 'name="%s"' % field.odoo_field not in arch
        })
        self.assertFalse(
            missing,
            'These product-page fields read a column with no box on the '
            'product form, so nobody can fill them in: %s' % ', '.join(missing))

    def test_the_photographs_can_be_added(self):
        """The box that was missing entirely.

        Extra photographs were only reachable from Odoo's own eCommerce Media
        group in the Sales tab, which nobody found - not one product in the
        shop had a second photograph.
        """
        arch = self._arch()
        self.assertIn('name="image_1920"', arch)
        self.assertIn('name="product_template_image_ids"', arch)

    # ------------------------------------------------------------ the hiding

    def test_nothing_is_hidden_while_the_page_still_prints_it(self):
        """The default: follow the shop, and the shop shows these."""
        self.product.invalidate_recordset()
        hidden = self.product.mart_page_hidden or ''
        for column in ('mart_material', 'mart_item_width'):
            self.assertNotIn(',%s,' % column, hidden)

    def test_hiding_a_field_takes_its_box_away(self):
        field = self.Field.search(
            [('odoo_field', '=', 'mart_material')], limit=1)
        self.assertTrue(field, 'the registry should map Material to a column')

        self.Field.set_product_state(field.id, self.product.id, 'hide')
        self.product.invalidate_recordset()

        self.assertIn(',mart_material,', self.product.mart_page_hidden)
        self.assertFalse(field._visible_for(self.product),
                         'and the page agrees, which is the point')

    def test_showing_it_again_brings_the_box_back(self):
        field = self.Field.search(
            [('odoo_field', '=', 'mart_material')], limit=1)
        self.Field.set_product_state(field.id, self.product.id, 'hide')
        self.product.invalidate_recordset()
        self.assertIn(',mart_material,', self.product.mart_page_hidden)

        self.Field.set_product_state(field.id, self.product.id, 'show')
        self.product.invalidate_recordset()
        self.assertNotIn(',mart_material,', self.product.mart_page_hidden)

    def test_a_shop_wide_switch_reaches_every_product(self):
        """Whole shop off, and the box goes from products that follow it."""
        field = self.Field.search(
            [('odoo_field', '=', 'mart_material')], limit=1)
        field.show = False
        self.product.invalidate_recordset()

        self.assertIn(',mart_material,', self.product.mart_page_hidden)

    def test_a_product_can_keep_what_the_shop_switched_off(self):
        """The exception that explains 'why is it still on that one'."""
        field = self.Field.search(
            [('odoo_field', '=', 'mart_material')], limit=1)
        field.show = False
        self.Field.set_product_state(field.id, self.product.id, 'show')
        self.product.invalidate_recordset()

        self.assertNotIn(',mart_material,', self.product.mart_page_hidden)

    def test_a_column_two_rows_share_survives_one_of_them_hiding(self):
        """One column, two rows: the box goes only when both are off.

        Taking the box away because one of the two is switched off would lose
        the value the other still prints.

        The second row is made here rather than found in the seed data. Two
        rows did share `mart_unit_text` - the size tag and Net quantity - until
        Net quantity was dropped as grocery wording, and a test that reads the
        catalogue stops testing anything the day the catalogue changes. The
        rule outlives whichever fields happen to share a column.
        """
        first = self.Field.search(
            [('odoo_field', '=', 'mart_unit_text')], limit=1)
        self.assertTrue(first, 'the size tag should read this column')
        second = self.Field.create({
            'key': 'test_second_reader',
            'name': 'A second row on the same column',
            'section_id': first.section_id.id,
            'source': 'odoo',
            'odoo_field': 'mart_unit_text',
        })
        rows = first + second

        self.Field.set_product_state(first.id, self.product.id, 'hide')
        self.product.invalidate_recordset()
        self.assertNotIn(',mart_unit_text,', self.product.mart_page_hidden,
                         'the other row still prints it')

        for row in rows:
            self.Field.set_product_state(row.id, self.product.id, 'hide')
        self.product.invalidate_recordset()
        self.assertIn(',mart_unit_text,', self.product.mart_page_hidden)

    # ----------------------------------------------- what was taken away

    def test_the_shop_asks_nothing_about_food(self):
        """369 Mart sells electricals, so no product is asked if it is veg.

        The vegetarian mark, Net quantity and Shelf life were inherited from a
        grocery template and reached a Wi-Fi adapter's form. The column behind
        the veg mark is gone, so a box for it could only come back by someone
        re-adding the column; the other two are gone from the catalogue.
        """
        arch = self._arch()
        self.assertNotIn('mart_is_veg', arch)
        self.assertNotIn(
            'mart_is_veg', self.env['product.template']._fields,
            'the vegetarian column should be gone from the product itself')

        for key in ('veg', 'net_quantity', 'shelf_life'):
            self.assertFalse(
                self.Field.search([('key', '=', key)]),
                'the product page should no longer offer %s' % key)

    def test_no_column_is_asked_for_twice(self):
        """The mirror of the drift test above.

        That one catches a page row with no box. This catches the opposite
        mistake, which is the one actually made: an "Article ID" box was added
        for `default_code` while Odoo's own Reference was already on the form,
        so the same column appeared twice and either copy could be edited.
        """
        arch = self._arch()
        for column in ('default_code', 'mart_unit_text'):
            self.assertEqual(
                arch.count('name="%s"' % column), 1,
                '%s should have exactly one box on the form' % column)

    def test_a_new_product_is_offered_everything(self):
        """Nothing to resolve against yet, so nothing is taken away.

        Hiding boxes on a product with no category would have somebody save it
        never having been shown the box it needed.
        """
        blank = self.env['product.template'].create({'name': 'No Category Yet'})
        self.assertFalse(blank.public_categ_ids)
        self.assertEqual(blank.mart_page_hidden or '', '')
