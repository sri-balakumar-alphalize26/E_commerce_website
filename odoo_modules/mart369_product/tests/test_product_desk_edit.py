"""Creating and editing a product from the Products desk.

The desk writes a product's own columns; the builder writes what its page
prints. Keeping those apart is the whole design, so the tests that matter are
the ones that would let them blur: a column the desk should not be able to
write, a box it should not be offering, and who is allowed to write at all.
"""

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestProductDeskEditing(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Product = self.env['product.template']
        self.Field = self.env['mart369.product.field']
        self.category = self.env['product.public.category'].create(
            {'name': 'Desk Test Category'})
        self.product = self.Product.create({
            'name': 'Desk Test Product',
            'is_published': True,
            'list_price': 10,
            'public_categ_ids': [(6, 0, [self.category.id])],
        })

    def _boxes(self, form):
        return {b['name'] for g in form['groups'] for b in g['boxes']}

    # ------------------------------------------------------- what it offers

    def test_a_new_product_is_offered_everything(self):
        """Nothing to resolve against yet, so nothing is taken away."""
        form = self.Product.mart369_desk_form()
        self.assertIsNone(form['id'])
        boxes = self._boxes(form)
        for column in ('name', 'list_price', 'public_categ_ids',
                       'mart_material', 'mart_item_width'):
            self.assertIn(column, boxes)

    def test_a_hidden_field_is_not_asked_for(self):
        """The same answer the Odoo form and the shopper's page get."""
        field = self.Field.search(
            [('odoo_field', '=', 'mart_material')], limit=1)
        self.Field.set_product_state(field.id, self.product.id, 'hide')
        self.product.invalidate_recordset()

        form = self.Product.mart369_desk_form(product_id=self.product.id)
        self.assertNotIn('mart_material', self._boxes(form))
        self.assertIn('mart_item_width', self._boxes(form),
                      'only the hidden one should go')

    def test_the_structural_boxes_are_always_asked_for(self):
        """A product with no name, price or category is not a product.

        Hiding the category box would be the worst of them: the four layers
        key off it, so the rest of the form would change for reasons nothing
        on screen could explain.
        """
        for key in ('name', 'price'):
            row = self.Field.search([('key', '=', key)], limit=1)
            if row:
                row.show = False
        self.product.invalidate_recordset()

        boxes = self._boxes(
            self.Product.mart369_desk_form(product_id=self.product.id))
        for column in ('name', 'list_price', 'public_categ_ids'):
            self.assertIn(column, boxes)

    def test_the_labels_come_from_the_fields(self):
        """Not a second list kept in JavaScript, which would drift."""
        form = self.Product.mart369_desk_form()
        labels = {b['name']: b['label']
                  for g in form['groups'] for b in g['boxes']}
        self.assertEqual(labels['mart_material'],
                         self.Product._fields['mart_material'].string)

    def test_the_shop_words_are_used_where_odoo_differs(self):
        """A shopkeeper meets "Article ID" on the page, so they meet it here.

        The Odoo product form makes the same relabels. Three screens saying
        "Article ID", "Internal Reference" and "Article ID" for one column is
        how somebody concludes there are two of them.
        """
        form = self.Product.mart369_desk_form()
        labels = {b['name']: b['label']
                  for g in form['groups'] for b in g['boxes']}
        self.assertEqual(labels['default_code'], 'Article ID')
        self.assertEqual(labels['list_price'], 'Price')
        self.assertEqual(labels['public_categ_ids'], 'Categories')

    # ------------------------------------------------------------- writing

    def test_creating_a_product_publishes_it(self):
        """Or it would vanish from the list the moment it was saved.

        The desk's list is built on `mart369_page_picker`, which shows only
        published products.
        """
        pid = self.Product.mart369_desk_save({
            'name': 'Made On The Desk',
            'list_price': 49,
            'public_categ_ids': [self.category.id],
        })
        made = self.Product.browse(pid)
        self.assertTrue(made.is_published)
        self.assertEqual(made.list_price, 49)
        self.assertEqual(made.public_categ_ids, self.category)

    def test_editing_writes_only_what_was_sent(self):
        self.product.mart_material = 'Steel'
        self.Product.mart369_desk_save(
            {'name': 'Renamed'}, product_id=self.product.id)
        self.assertEqual(self.product.name, 'Renamed')
        self.assertEqual(self.product.mart_material, 'Steel',
                         'a column nobody sent should be left alone')

    def test_a_product_needs_a_name(self):
        with self.assertRaises(UserError):
            self.Product.mart369_desk_save({'list_price': 5})

    def test_a_column_the_desk_does_not_show_cannot_be_written(self):
        """The allowlist, which is the reason this method is safe to expose.

        `standard_price` is the cost. It is not on this screen, it is nobody's
        business from here, and sending it must not work - otherwise the
        screen's honesty about what it edits is only skin deep.
        """
        before = self.product.standard_price
        self.Product.mart369_desk_save(
            {'name': 'Still Fine', 'standard_price': 999.0},
            product_id=self.product.id)
        self.assertEqual(self.product.standard_price, before)

    def test_the_page_configuration_is_not_touched(self):
        """The builder's half of the split stays the builder's."""
        field = self.Field.search(
            [('odoo_field', '=', 'mart_material')], limit=1)
        self.Field.set_product_state(field.id, self.product.id, 'hide')
        before = self.product.mart_page_differs

        self.Product.mart369_desk_save(
            {'name': 'Renamed Again'}, product_id=self.product.id)
        self.product.invalidate_recordset()
        self.assertEqual(self.product.mart_page_differs, before)

    # ------------------------------------------------------- photographs

    def test_photographs_are_added_and_removed(self):
        if 'product_template_image_ids' not in self.Product._fields:
            self.skipTest('website_sale is not installed')
        # A 1x1 gif, small enough to write out here.
        gif = ('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')

        self.Product.mart369_desk_save(
            {'name': self.product.name}, product_id=self.product.id,
            photos={'add': [{'name': 'Side view', 'data': gif}]})
        images = self.product.product_template_image_ids
        self.assertEqual(len(images), 1)
        self.assertEqual(images.name, 'Side view')

        self.Product.mart369_desk_save(
            {'name': self.product.name}, product_id=self.product.id,
            photos={'remove': [images.id]})
        self.assertFalse(self.product.product_template_image_ids)

    def test_the_card_photograph_can_be_taken_away(self):
        """'' and "not mentioned" mean different things, and must."""
        gif = ('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
        self.Product.mart369_desk_save(
            {'name': self.product.name, 'image_1920': gif},
            product_id=self.product.id)
        self.assertTrue(self.product.image_1920)

        self.Product.mart369_desk_save(
            {'name': self.product.name}, product_id=self.product.id)
        self.assertTrue(self.product.image_1920,
                        'not mentioning it should leave it alone')

        self.Product.mart369_desk_save(
            {'name': self.product.name, 'image_1920': ''},
            product_id=self.product.id)
        self.assertFalse(self.product.image_1920)

    # ------------------------------------------------------------- who may

    def test_somebody_without_the_role_is_refused(self):
        """Refused, not filtered - the rule the admin routes already follow."""
        user = new_test_user(self.env, login='desk_nobody',
                             groups='base.group_user')
        with self.assertRaises(AccessError):
            self.Product.with_user(user).mart369_desk_form()
        with self.assertRaises(AccessError):
            self.Product.with_user(user).mart369_desk_save({'name': 'Nope'})
