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
        self.categ = self.env['product.category'].create({'name': 'Desk Test Product Category'})
        self.product = self.Product.create({
            'name': 'Desk Test Product',
            'is_published': True,
            'list_price': 10,
            'public_categ_ids': [(6, 0, [self.category.id])],
        })

    def _boxes(self, form):
        return {b['name'] for g in form['groups'] for b in g['boxes']}

    # ------------------------------------------------------- what it offers

    # The manual, *Adding a Product*, box for box and in its order.
    MANUAL = ['sale_ok', 'purchase_ok', 'type', 'is_storable', 'tracking', 'list_price',
              'taxes_id', 'standard_price', 'supplier_taxes_id', 'categ_id',
              'default_code', 'barcode', 'description_sale']

    def test_a_new_product_is_offered_the_senior_setup(self):
        """The manual's boxes, and the website's own extras - nothing that
        repeats a fact the setup already holds."""
        form = self.Product.mart369_desk_form()
        self.assertIsNone(form['id'])
        boxes = self._boxes(form)
        # The website's own Categories box is mart369_catalog's to take away
        # (it follows Category there), so it is not asserted either way.
        for column in ['name'] + self.MANUAL:
            if column in self.Product._fields:
                self.assertIn(column, boxes)
        for column in ('mart_material', 'mart_item_width', 'mart_features',
                       'description_ecommerce', 'mart_brand', 'weight', 'wa_retail_price'):
            self.assertNotIn(column, boxes, '%s repeats the setup or is not asked' % column)

    def test_the_product_boxes_follow_the_manuals_order(self):
        group = next(g for g in self.Product.mart369_desk_form()['groups'] if g['title'] == 'Product')
        names = [b['name'] for b in group['boxes']]
        self.assertEqual(names[0], 'name')
        self.assertEqual([n for n in names if n in self.MANUAL],
                         [n for n in self.MANUAL if n in self.Product._fields])

    def test_website_extras_are_one_folded_group(self):
        form = self.Product.mart369_desk_form()
        group = next(g for g in form['groups'] if g['title'] == 'Website only')
        self.assertTrue(group['folded'])
        self.assertFalse(group['deskOnly'], "Odoo's product form shows it too")
        self.assertIn('compare_list_price', {b['name'] for b in group['boxes']})

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
        for column in ('name', 'list_price', 'categ_id'):
            self.assertIn(column, boxes)

    def test_the_labels_come_from_the_fields(self):
        """Not a second list kept in JavaScript, which would drift."""
        form = self.Product.mart369_desk_form()
        labels = {b['name']: b['label']
                  for g in form['groups'] for b in g['boxes']}
        self.assertEqual(labels['mart_note'],
                         self.Product._fields['mart_note'].string)

    def test_the_setup_guides_words_are_used(self):
        """The words PRODUCT_SETUP_FLOW.md uses, so the guide and the screen
        read the same."""
        form = self.Product.mart369_desk_form()
        labels = {b['name']: b['label']
                  for g in form['groups'] for b in g['boxes']}
        self.assertEqual(labels['list_price'], 'Sales Price')
        self.assertEqual(labels['standard_price'], 'Cost')
        self.assertEqual(labels['categ_id'], 'Category')
        self.assertEqual(labels['description_sale'], 'Sales Description')
        if 'public_categ_ids' in labels:
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
            'categ_id': str(self.categ.id),
        })
        made = self.Product.browse(pid)
        self.assertTrue(made.is_published)
        self.assertEqual(made.list_price, 49)
        self.assertEqual(made.categ_id, self.categ)

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

        Published is not on this screen, and sending it must not work -
        otherwise the screen's honesty about what it edits is only skin deep.
        """
        self.Product.mart369_desk_save(
            {'name': 'Still Fine', 'is_published': False},
            product_id=self.product.id)
        self.assertTrue(self.product.is_published)

    def test_the_page_configuration_is_not_touched(self):
        """The builder's half of the split stays the builder's."""
        field = self.Field.search([('key', '=', 'variant_specs')], limit=1)
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
        self.categ = str(self.env['product.category'].create({'name': 'Zz Kinds'}).id)

    def _box(self, name):
        form = self.Product.mart369_desk_form()
        return next(b for g in form['groups'] for b in g['boxes'] if b['name'] == name)

    def test_each_box_says_how_it_is_drawn(self):
        self.assertEqual(self._box('mart_unit_text')['kind'], 'measure')
        self.assertIn('g', self._box('mart_unit_text')['units'])
        self.assertEqual(self._box('mart_per_unit')['kind'], 'per_unit')
        self.assertIn('New', self._box('mart_home_tag')['options'])
        delivery = self._box('mart_delivery_text')
        self.assertTrue(delivery['range'])
        self.assertEqual(delivery['units'], ['days', 'weeks', 'months'])

    def test_plain_boxes_stay_plain(self):
        self.assertNotIn('kind', self._box('mart_note'))
        self.assertNotIn('kind', self._box('name'))

    def test_joined_values_are_stored_as_the_app_reads_them(self):
        pid = self.Product.mart369_desk_save({
            'name': 'Kinds Test',
            'categ_id': self.categ,
            'mart_unit_text': '250 g',
            'mart_per_unit': '17.25 per 250 g',
            'mart_home_tag': 'New',
            'mart_delivery_text': '3-5 days',
        })
        product = self.Product.browse(pid)
        self.assertEqual(product.mart_unit_text, '250 g')
        self.assertEqual(product.mart_per_unit, '17.25 per 250 g')
        self.assertEqual(product.mart_delivery_text, '3-5 days')

        values = self.Product.mart369_desk_form(product_id=pid)['values']
        self.assertEqual(values['mart_home_tag'], 'New')

    def test_an_old_value_that_does_not_fit_comes_back_untouched(self):
        product = self.Product.create({
            'name': 'Old Wording', 'mart_unit_text': 'Approx 1 kilo'})
        values = self.Product.mart369_desk_form(product_id=product.id)['values']
        self.assertEqual(values['mart_unit_text'], 'Approx 1 kilo')

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
            {'name': 'Swap Test', 'categ_id': self.categ, 'image_1920': red},
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

    def test_the_product_section_is_desk_only(self):
        form = self.Product.mart369_desk_form()
        group = self._group(form, 'Product')
        self.assertTrue(group['deskOnly'], "Odoo's form already shows these")

    def test_each_box_says_how_it_is_drawn(self):
        form = self.Product.mart369_desk_form()
        self.assertEqual(self._box(form, 'type')['kind'], 'select')
        self.assertEqual(self._box(form, 'categ_id')['kind'], 'select')
        self.assertEqual(self._box(form, 'sale_ok')['kind'], 'bool')
        self.assertEqual(self._box(form, 'purchase_ok')['kind'], 'bool')
        self.assertEqual(self._box(form, 'taxes_id')['kind'], 'tags')
        self.assertEqual(self._box(form, 'supplier_taxes_id')['kind'], 'tags')
        if 'tracking' in self.Product._fields:
            self.assertIn('serial', [k for k, _label in self._box(form, 'tracking')['options']])
        website = self._box(form, 'public_categ_ids')
        if website:  # mart369_catalog takes it away: it follows Category
            self.assertNotIn('kind', website, 'the app categories keep their own chip list')

    def test_a_new_product_starts_from_odoos_defaults(self):
        values = self.Product.mart369_desk_form()['values']
        defaults = self.Product.default_get(['type'])
        if 'type' in defaults:
            self.assertEqual(values.get('type'), defaults['type'])

    def test_odoo_fields_are_saved(self):
        categ = self.env['product.category'].search([], limit=1)
        tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'), ('company_id', '=', self.env.company.id)], limit=1)
        pid = self.Product.mart369_desk_save({
            'name': 'Zz Odoo Fields', 'type': 'service', 'categ_id': str(categ.id),
            'sale_ok': False, 'purchase_ok': False, 'description_sale': 'Two USB-C ports',
            'default_code': 'ZZ-LAP-1', 'barcode': '0036900100017', 'taxes_id': tax.ids,
        })
        product = self.Product.browse(pid)
        self.assertEqual(product.type, 'service')
        self.assertEqual(product.categ_id, categ)
        self.assertFalse(product.sale_ok)
        self.assertFalse(product.purchase_ok)
        self.assertEqual(product.description_sale, 'Two USB-C ports')
        self.assertEqual(product.default_code, 'ZZ-LAP-1')
        self.assertEqual(product.barcode, '0036900100017', 'leading zeros kept')
        self.assertEqual(product.taxes_id, tax)

    def test_a_laptop_can_be_tracked_by_serial(self):
        if 'tracking' not in self.Product._fields:
            self.skipTest('Inventory is not installed')
        categ = self.env['product.category'].search([], limit=1)
        pid = self.Product.mart369_desk_save({
            'name': 'Zz Serial', 'type': 'consu', 'is_storable': True,
            'tracking': 'serial', 'categ_id': str(categ.id)})
        self.assertEqual(self.Product.browse(pid).tracking, 'serial')


@tagged('post_install', '-at_install')
class TestProductDeskCategory(TransactionCase):
    """Category is the manual's one starred box."""

    def setUp(self):
        super().setUp()
        self.Product = self.env['product.template']
        self.categ = self.env['product.category'].create({'name': 'Zz Required'})

    def _box(self, form, name):
        return next(b for g in form['groups'] for b in g['boxes'] if b['name'] == name)

    def test_the_box_is_required_and_starts_empty(self):
        box = self._box(self.Product.mart369_desk_form(), 'categ_id')
        self.assertTrue(box['required'])
        self.assertEqual(box['options'][0], ['', 'Choose one'])
        self.assertIn([str(self.categ.id), self.categ.display_name], box['options'])

    def test_a_new_product_without_one_is_refused(self):
        with self.assertRaisesRegex(UserError, 'Choose a Category'):
            self.Product.mart369_desk_save({'name': 'Zz No Category', 'categ_id': ''})
        with self.assertRaisesRegex(UserError, 'Choose a Category'):
            self.Product.mart369_desk_save({'name': 'Zz No Category'})

    def test_it_cannot_be_taken_away(self):
        product = self.Product.create({'name': 'Zz Has One', 'categ_id': self.categ.id})
        with self.assertRaisesRegex(UserError, 'Choose a Category'):
            self.Product.mart369_desk_save({'categ_id': ''}, product_id=product.id)
        self.assertEqual(product.categ_id, self.categ)

    def test_a_save_that_leaves_it_out_still_works(self):
        """An older product with none, saved by a caller that does not send
        the box, keeps its price."""
        product = self.Product.create({'name': 'Zz Old', 'categ_id': False})
        self.Product.mart369_desk_save({'list_price': '12'}, product_id=product.id)
        self.assertEqual(product.list_price, 12)


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
        categ = self.env['product.category'].create({'name': 'Zz Numbers'})
        with self.assertRaisesRegex(UserError, 'On hand must be a number'):
            self.env['product.template'].mart369_desk_save(
                {'name': 'Zz N', 'categ_id': str(categ.id), 'mart_on_hand': '1e'})




@tagged('post_install', '-at_install')
class TestProductDeskVariants(TransactionCase):
    """The Variants block: attributes, price extras, and each variant's own
    image, photos, specs and stock - PRODUCT_SETUP_FLOW.md 2.1, 2.4, 2.5."""

    GIF = 'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'

    def setUp(self):
        super().setUp()
        self.Product = self.env['product.template']
        self.ram = self.env['product.attribute'].create({
            'name': 'Zz Desk RAM', 'create_variant': 'always',
            'value_ids': [(0, 0, {'name': '8GB'}), (0, 0, {'name': '16GB'})],
        })
        self.eight, self.sixteen = self.ram.value_ids
        categ = self.env['product.category'].create({'name': 'Zz Desk Computers'})
        self.pid = self.Product.mart369_desk_save(
            {'name': 'Zz Desk Laptop', 'list_price': 600, 'categ_id': str(categ.id)})
        self.product = self.Product.browse(self.pid)

    def _lines(self, **extras):
        return [{'attribute_id': self.ram.id,
                 'value_ids': [self.eight.id, self.sixteen.id],
                 'extras': extras}]

    def test_the_form_offers_the_attributes_and_the_rows(self):
        block = self.Product.mart369_desk_form(product_id=self.pid)['variants']
        self.assertIn(self.ram.id, [a['id'] for a in block['attributes']])
        self.assertEqual(block['lines'], [])
        self.assertEqual(len(block['rows']), 1, 'a product with no choice is one variant')

    def test_every_attribute_is_offered_with_its_default_extra(self):
        """The manual's Attributes & Variants tab: a Never attribute (Depth)
        is offered too, and a value carries its Default Extra Price."""
        depth = self.env['product.attribute'].create({
            'name': 'Zz Desk Depth', 'create_variant': 'no_variant',
            'value_ids': [(0, 0, {'name': '20 mm'})]})
        self.sixteen.default_extra_price = 200
        block = self.Product.mart369_desk_form(product_id=self.pid)['variants']
        offered = {a['id']: a for a in block['attributes']}
        self.assertEqual(offered[depth.id]['variants'], 'no_variant')
        self.assertEqual({v['id']: v.get('extra') for v in offered[self.ram.id]['values']},
                         {self.eight.id: None, self.sixteen.id: 200})
        self.assertIn('makes the variants again', block['warning'])

    def test_a_newly_picked_value_starts_at_its_default_extra(self):
        self.sixteen.default_extra_price = 150
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={'lines': self._lines()})
        self.assertEqual(sorted(self.product.product_variant_ids.mapped('lst_price')), [600.0, 750.0])

    def test_a_never_attribute_adds_no_variant(self):
        depth = self.env['product.attribute'].create({
            'name': 'Zz Desk Depth', 'create_variant': 'no_variant',
            'value_ids': [(0, 0, {'name': '20 mm'})]})
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={'lines': [
            {'attribute_id': depth.id, 'value_ids': depth.value_ids.ids}]})
        self.assertEqual(self.product.attribute_line_ids.attribute_id, depth)
        self.assertEqual(len(self.product.product_variant_ids), 1)

    def test_an_extra_below_zero_survives_a_save(self):
        """Set in Odoo's own form ("8GB -100"), sent back with the lines."""
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={
            'lines': self._lines(**{str(self.eight.id): '-100', str(self.sixteen.id): '200'})})
        self.assertEqual(sorted(self.product.product_variant_ids.mapped('lst_price')), [500.0, 800.0])

    def test_a_value_typed_as_a_number_is_not_read_as_an_id(self):
        """A new value "<n>" keyed by its name must not price value id n."""
        colour = self.env['product.attribute'].create({
            'name': 'Zz Desk Colour', 'create_variant': 'always',
            'value_ids': [(0, 0, {'name': 'Black'})]})
        black = colour.value_ids
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={'lines': [
            {'attribute_id': self.ram.id, 'value_ids': [self.eight.id],
             'new_values': [str(black.id)], 'extras': {str(black.id): '100'}},
            {'attribute_id': colour.id, 'value_ids': [black.id], 'extras': {}},
        ]})
        ptavs = self.product.attribute_line_ids.product_template_value_ids
        self.assertEqual(ptavs.filtered(lambda p: p.product_attribute_value_id == black).price_extra, 0.0)
        self.assertEqual(ptavs.filtered(lambda p: p.name == str(black.id)).price_extra, 100.0)

    def test_saving_lines_makes_the_variants_with_their_extras(self):
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={
            'lines': self._lines(**{str(self.sixteen.id): '200'})})
        self.assertEqual(len(self.product.product_variant_ids), 2)
        prices = sorted(self.product.product_variant_ids.mapped('lst_price'))
        self.assertEqual(prices, [600.0, 800.0])
        line = self.Product.mart369_desk_form(product_id=self.pid)['variants']['lines'][0]
        self.assertEqual(line['extras'], {str(self.sixteen.id): 200.0})

    def test_a_typed_value_is_added_to_the_attribute(self):
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={'lines': [{
            'attribute_id': self.ram.id, 'value_ids': [self.eight.id],
            'new_values': ['32GB'], 'extras': {'32GB': '500'}}]})
        self.assertIn('32GB', self.ram.value_ids.mapped('name'))
        self.assertEqual(sorted(self.product.product_variant_ids.mapped('lst_price')), [600.0, 1100.0])

    def test_removing_the_line_leaves_one_variant(self):
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={'lines': self._lines()})
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={'lines': []})
        self.assertEqual(len(self.product.product_variant_ids), 1)

    def test_a_variant_gets_its_own_image(self):
        variant = self.product.product_variant_id
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={
            'per': {str(variant.id): {'image': self.GIF}}})
        self.assertTrue(variant.image_variant_1920)

    def test_another_products_variant_is_left_alone(self):
        other = self.Product.create({'name': 'Zz Someone Else'}).product_variant_id
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={
            'per': {str(other.id): {'image': self.GIF}}})
        self.assertFalse(other.image_variant_1920)

    def test_variant_photos_and_specs_when_the_tabs_exist(self):
        """The Variant images / Variant specs tabs come from the WhatsApp
        package, through mart369_whatsapp_bridge; skipped without it."""
        if not self.Product._mart369_desk_media_ok():
            self.skipTest('no module gives variants photos and specs')
        variant = self.product.product_variant_id
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={'per': {str(variant.id): {
            'pictures': {'add': [{'name': 'back', 'data': self.GIF}], 'remove': [], 'order': []},
            'specs': [{'name': 'Warranty', 'value': '1 year'}, {'name': 'Ports', 'value': '2x USB-C'}],
        }}})
        row = self.Product.mart369_desk_form(product_id=self.pid)['variants']['rows'][0]
        self.assertEqual([p['name'] for p in row['pictures']], ['back'])
        self.assertEqual([(s['name'], s['value']) for s in row['specs']],
                         [('Warranty', '1 year'), ('Ports', '2x USB-C')])

        # The whole table is sent back in its new order; a missing row goes.
        first, second = row['specs']
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={'per': {str(variant.id): {
            'specs': [{'id': second['id'], 'name': 'Ports', 'value': '2x USB-C'}],
            'pictures': {'add': [], 'remove': [row['pictures'][0]['id']], 'order': []},
        }}})
        row = self.Product.mart369_desk_form(product_id=self.pid)['variants']['rows'][0]
        self.assertEqual([s['name'] for s in row['specs']], ['Ports'])
        self.assertEqual(row['pictures'], [])
