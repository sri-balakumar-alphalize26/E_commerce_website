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

        `sale_ok` - whether the product can be sold at all - is not on this
        screen, and sending it must not work - otherwise the screen's honesty
        about what it edits is only skin deep. (Cost used to be the example;
        it is a box on the screen now.)
        """
        self.assertTrue(self.product.sale_ok)
        self.Product.mart369_desk_save(
            {'name': 'Still Fine', 'sale_ok': False},
            product_id=self.product.id)
        self.assertTrue(self.product.sale_ok)

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


@tagged('post_install', '-at_install')
class TestProductDeskBoxKinds(TransactionCase):
    """Number-and-unit boxes, dropdowns and feature points.

    The screen splits a value into parts and joins it back; the column keeps
    the same plain text the app has always printed. So the server's half is
    small - say which box is which, and store exactly what arrives.
    """

    def setUp(self):
        super().setUp()
        self.Product = self.env['product.template']

    def _box(self, name):
        form = self.Product.mart369_desk_form()
        return next(b for g in form['groups'] for b in g['boxes'] if b['name'] == name)

    def test_each_box_says_how_it_is_drawn(self):
        self.assertEqual(self._box('mart_unit_text')['kind'], 'measure')
        self.assertIn('g', self._box('mart_unit_text')['units'])
        self.assertEqual(self._box('mart_per_unit')['kind'], 'per_unit')
        self.assertIn('cm', self._box('mart_item_height')['units'])
        self.assertIn('New', self._box('mart_home_tag')['options'])
        self.assertEqual(self._box('mart_material')['kind'], 'choice')
        self.assertEqual(self._box('mart_features')['kind'], 'points')
        self.assertEqual(self._box('mart_in_the_box')['sep'], ', ')
        delivery = self._box('mart_delivery_text')
        self.assertTrue(delivery['range'])
        self.assertEqual(delivery['units'], ['days', 'weeks', 'months'])

    def test_plain_boxes_stay_plain(self):
        self.assertNotIn('kind', self._box('mart_note'))
        self.assertNotIn('kind', self._box('name'))

    def test_joined_values_are_stored_as_the_app_reads_them(self):
        features = 'Fast charging\nFoldable plug\nTwo ports'
        pid = self.Product.mart369_desk_save({
            'name': 'Kinds Test',
            'mart_unit_text': '250 g',
            'mart_per_unit': '17.25 per 250 g',
            'mart_home_tag': 'New',
            'mart_features': features,
            'mart_in_the_box': 'Product, cable, user manual',
            'mart_item_height': '12 cm',
            'mart_delivery_text': '3-5 days',
        })
        product = self.Product.browse(pid)
        self.assertEqual(product.mart_unit_text, '250 g')
        self.assertEqual(product.mart_per_unit, '17.25 per 250 g')
        self.assertEqual(product.mart_features, features)
        self.assertEqual(product.mart_in_the_box, 'Product, cable, user manual')
        self.assertEqual(product.mart_delivery_text, '3-5 days')

        values = self.Product.mart369_desk_form(product_id=pid)['values']
        self.assertEqual(values['mart_item_height'], '12 cm')
        self.assertEqual(values['mart_home_tag'], 'New')

    def test_an_old_value_that_does_not_fit_comes_back_untouched(self):
        product = self.Product.create({
            'name': 'Old Wording', 'mart_unit_text': 'Approx 1 kilo'})
        values = self.Product.mart369_desk_form(product_id=product.id)['values']
        self.assertEqual(values['mart_unit_text'], 'Approx 1 kilo')

    def test_weight_is_a_number_box_in_kg(self):
        box = self._box('weight')
        self.assertTrue(box['numeric'])
        self.assertEqual(box['units'][0], 'kg', 'the unit Odoo stores it in comes first')

    def test_an_empty_price_box_is_empty_not_zero(self):
        product = self.Product.create({'name': 'No MRP'})
        values = self.Product.mart369_desk_form(product_id=product.id)['values']
        self.assertEqual(values['compare_list_price'], '')
        self.assertEqual(values['mart_low_stock_at'], 0, '0 means "warning off" there')

    def test_mrp_help_is_the_shops_wording(self):
        self.assertNotIn('/shop', self._box('compare_list_price')['help'])

    def test_a_gallery_picture_can_go_on_the_card(self):
        """The old card picture moves into the gallery; nothing is lost."""
        red = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC'
        blue = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYPgPAAEDAQAIicLsAAAAAElFTkSuQmCC'
        pid = self.Product.mart369_desk_save(
            {'name': 'Swap Test', 'image_1920': red},
            photos={'add': [{'name': 'b', 'data': blue}]})
        product = self.Product.browse(pid)
        gallery = product.product_template_image_ids
        self.assertEqual(len(gallery), 1)
        blue_stored = gallery.image_1920

        self.Product.mart369_desk_save(
            {}, product_id=pid, photos={'promote': gallery.id, 'demote': True})
        product.invalidate_recordset()
        self.assertEqual(product.image_1920, blue_stored, 'the chosen one is on the card')
        self.assertEqual(len(product.product_template_image_ids), 1,
                         'the old card picture is in the gallery, the chosen one left it')
        self.assertFalse(gallery.exists())


@tagged('post_install', '-at_install')
class TestProductDeskReadView(TransactionCase):

    def test_photos_row_counts_the_pictures(self):
        """It used to say "Nothing set" beside a product with a photograph."""
        red = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC'
        product = self.env['product.template'].create({'name': 'Pictured', 'image_1920': red})
        page = self.env['mart369.product.field'].mart369_product_page(product.id)
        row = next(f for s in page['sections'] for f in s['fields'] if f['key'] == 'images')
        self.assertEqual(row['value'], '1 photo')


@tagged('post_install', '-at_install')
class TestProductFormEditor(TransactionCase):
    """Odoo's product form carries the desk's editor, and nothing twice."""

    def _arch(self):
        return self.env['product.template'].get_view(view_type='form')['arch']

    def test_the_editor_is_on_general_information(self):
        from lxml import etree
        arch = etree.fromstring(self._arch())
        general = arch.xpath("//page[@name='general_information']")[0]
        self.assertTrue(general.xpath(".//widget[@name='mart369_product_editor']"))
        tab = arch.xpath("//page[@name='mart369']")[0]
        self.assertIn(tab.get('invisible'), ('1', 'True', 'true'),
                      'the tab is empty now, so it is hidden')

    def test_the_old_card_boxes_are_not_drawn_twice(self):
        """The editor draws these; the form only carries them, invisibly."""
        from lxml import etree
        arch = etree.fromstring(self._arch())
        for name in ('mart_unit_text', 'mart_home_tag', 'mart_features'):
            shown = [f for f in arch.xpath("//field[@name='%s']" % name)
                     if f.get('invisible') not in ('1', 'True', 'true')]
            self.assertFalse(shown, '%s is drawn by the editor only' % name)

    def test_cost_is_a_box_in_the_editor(self):
        form = self.env['product.template'].mart369_desk_form()
        names = {b['name'] for g in form['groups'] for b in g['boxes']}
        self.assertIn('standard_price', names)


@tagged('post_install', '-at_install')
class TestProductDeskOdooFields(TransactionCase):
    """Odoo's own fields on the desk: type, taxes, company, category."""

    def setUp(self):
        super().setUp()
        self.Product = self.env['product.template']

    def _group(self, form, title):
        return next((g for g in form['groups'] if g['title'] == title), None)

    def _box(self, form, name):
        return next((b for g in form['groups'] for b in g['boxes'] if b['name'] == name), None)

    def test_the_section_is_desk_only(self):
        form = self.Product.mart369_desk_form()
        group = self._group(form, 'Stock, tax and company')
        self.assertTrue(group['deskOnly'], "Odoo's form already shows these")

    def test_each_box_says_how_it_is_drawn(self):
        form = self.Product.mart369_desk_form()
        self.assertEqual(self._box(form, 'type')['kind'], 'select')
        self.assertEqual(self._box(form, 'categ_id')['kind'], 'select')
        self.assertEqual(self._box(form, 'taxes_id')['kind'], 'tags')
        self.assertEqual(self._box(form, 'company_id')['options'][0], ['', 'All companies'])
        self.assertNotIn('kind', self._box(form, 'public_categ_ids'),
                         'the app categories keep their own chip list')

    def test_a_new_product_starts_from_odoos_defaults(self):
        """The company's taxes and default category, as Odoo's own form."""
        values = self.Product.mart369_desk_form()['values']
        defaults = self.Product.default_get(['type', 'taxes_id'])
        if 'type' in defaults:
            self.assertEqual(values.get('type'), defaults['type'])
        if defaults.get('taxes_id'):
            self.assertTrue(values.get('taxes_id'), "the company's sale tax is filled in")

    def test_odoo_fields_are_saved(self):
        tax = self.env['account.tax'].search([('type_tax_use', '=', 'sale')], limit=1)
        categ = self.env['product.category'].search([], limit=1)
        pid = self.Product.mart369_desk_save({
            'name': 'Zz Odoo Fields', 'type': 'service', 'barcode': '0036900100017',
            'categ_id': str(categ.id), 'taxes_id': tax.ids, 'company_id': '',
        })
        product = self.Product.browse(pid)
        self.assertEqual(product.type, 'service')
        self.assertEqual(product.barcode, '0036900100017', 'leading zeros kept')
        self.assertEqual(product.categ_id, categ)
        self.assertEqual(product.taxes_id, tax)
        self.assertFalse(product.company_id)


@tagged('post_install', '-at_install')
class TestProductDeskNumbers(TransactionCase):
    """Number boxes take numbers - refused in words otherwise."""

    def test_letters_are_refused_in_words(self):
        with self.assertRaisesRegex(UserError, 'Price must be a number'):
            self.env['product.template'].mart369_desk_save({'name': 'Zz N', 'list_price': 'abc'})

    def test_below_zero_is_refused(self):
        with self.assertRaisesRegex(UserError, 'below zero'):
            self.env['product.template'].mart369_desk_save({'name': 'Zz N', 'standard_price': '-5'})

    def test_a_count_must_be_whole(self):
        with self.assertRaisesRegex(UserError, 'whole number'):
            self.env['product.template'].mart369_desk_save({'name': 'Zz N', 'mart_low_stock_at': '2.5'})

    def test_on_hand_letters_are_refused(self):
        with self.assertRaisesRegex(UserError, 'On hand must be a number'):
            self.env['product.template'].mart369_desk_save({'name': 'Zz N', 'mart_on_hand': '1e'})


@tagged('post_install', '-at_install')
class TestProductDeskTaxes(TransactionCase):
    """One "5%", not one per company."""

    def _box(self, form, name):
        return next(b for g in form['groups'] for b in g['boxes'] if b['name'] == name)

    def test_a_new_product_is_offered_this_companys_taxes(self):
        form = self.env['product.template'].mart369_desk_form()
        offered = self.env['account.tax'].browse([o[0] for o in self._box(form, 'taxes_id')['options']])
        self.assertEqual(offered.company_id, self.env.company)
        self.assertTrue(set(form['values'].get('taxes_id', [])) <= set(offered.ids),
                        'the default taxes are ones the box can show')

    def test_a_tax_the_product_already_has_stays_offered(self):
        other = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'), ('company_id', '!=', self.env.company.id)], limit=1)
        if not other:
            self.skipTest('only one company')
        product = self.env['product.template'].create({'name': 'Zz Tax', 'taxes_id': [(6, 0, other.ids)]})
        form = self.env['product.template'].mart369_desk_form(product_id=product.id)
        self.assertIn(other.id, [o[0] for o in self._box(form, 'taxes_id')['options']])


@tagged('post_install', '-at_install')
class TestProductDeskBarcode(TransactionCase):
    """Barcodes are digits. An old one with letters is left alone."""

    def test_letters_are_refused(self):
        with self.assertRaisesRegex(UserError, 'digits only'):
            self.env['product.template'].mart369_desk_save({'name': 'Zz B', 'barcode': 'ABC123'})

    def test_an_old_letter_barcode_left_alone_still_saves(self):
        product = self.env['product.template'].create({'name': 'Zz Old', 'barcode': 'OLD-369-X'})
        self.env['product.template'].mart369_desk_save(
            {'name': 'Zz Old', 'barcode': 'OLD-369-X', 'list_price': '5'}, product_id=product.id)
        self.assertEqual(product.list_price, 5)

    def test_the_box_is_digits(self):
        form = self.env['product.template'].mart369_desk_form()
        box = next(b for g in form['groups'] for b in g['boxes'] if b['name'] == 'barcode')
        self.assertEqual((box['kind'], box['max']), ('digits', 14))
