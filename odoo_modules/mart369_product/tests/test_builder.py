"""The one call both product-page screens draw from.

The desk editor (editor.js) and the phone builder (product_builder.js) both
load `builder_load` and nothing else. Neither can ask for a key it does not
return, and a key quietly dropped here is a blank panel over there - with no
error anywhere, because QWeb renders `undefined` as nothing at all. So the
shape is frozen here, and the two screens' own expectations are checked
against it.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

# Every key the templates reach for. page_reader.js reads the first four;
# the mock bands read `card` and `preview`.
LOAD_KEYS = frozenset({'sections', 'product', 'card', 'preview'})

SECTION_KEYS = frozenset({'id', 'key', 'name', 'sequence', 'show', 'note', 'rows'})

# The panel binds to all of these by name. `product_value` in particular is
# the raw wording the editor writes back, as opposed to `value`, which is it
# run through _as_text for drawing.
ROW_KEYS = frozenset({
    'id', 'key', 'name', 'section_id', 'sequence', 'show', 'source',
    'odoo_field', 'default_value', 'value_kind', 'per_product', 'note',
    'override_count', 'state', 'visible', 'value', 'product_value',
    'has_override', 'value_source', 'category_values',
})

# The bands the two screens split the page into. page_reader.js sorts every
# section into the accordion, the tail, or one of the named singles; a section
# key that is none of these would silently never be drawn.
DRAWN_KEYS = frozenset({
    'gallery', 'buy', 'features', 'info', 'specs', 'description', 'returns',
    'reviews', 'delivery', 'bundle', 'similar',
})


@tagged('post_install', '-at_install')
class TestProductBuilderLoad(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.template'].create({
            'name': 'Builder Test Widget',
            'list_price': 120.0,
            'is_published': True,
        })
        cls.Field = cls.env['mart369.product.field']

    # ------------------------------------------------------------ the shape

    def test_shape(self):
        data = self.Field.builder_load(self.product.id)
        self.assertEqual(set(data), LOAD_KEYS)
        self.assertTrue(data['sections'], 'the page has no sections at all')
        for section in data['sections']:
            self.assertEqual(set(section), SECTION_KEYS)
            for row in section['rows']:
                self.assertEqual(set(row), ROW_KEYS)

    def test_preview_rails_are_always_there(self):
        """The editor puts a band on each rail, so each has to exist -
        as a list, even when there is nothing in it."""
        preview = self.Field.builder_load(self.product.id)['preview']
        self.assertEqual(
            set(preview), {'variants', 'bundle', 'similar', 'related'})
        for key, rail in preview.items():
            self.assertIsInstance(rail, list, '%s is not a list' % key)

    def test_every_section_is_drawn_by_the_screens(self):
        data = self.Field.builder_load(self.product.id)
        unknown = {s['key'] for s in data['sections']} - DRAWN_KEYS
        self.assertFalse(
            unknown,
            'these sections exist but no screen draws them: %s. Add them to '
            'ACCORDION or TAIL in page_reader.js, or to PageBody.' % unknown)

    # ---------------------------------------------------- picking a product

    def test_it_loads_the_product_it_was_given(self):
        """The screens pass the id from the action context. Loading anything
        else means editing one product while looking at another."""
        other = self.env['product.template'].create({
            'name': 'Another Widget', 'is_published': True,
        })
        data = self.Field.builder_load(other.id)
        self.assertEqual(data['product']['id'], other.id)
        self.assertEqual(data['product']['name'], other.display_name)

    def test_no_product_still_draws(self):
        """Opened with nothing picked, the screen falls back to a published
        product rather than handing the canvas a None to draw."""
        data = self.Field.builder_load()
        self.assertIn('sections', data)
        self.assertTrue(data['sections'])

    # ------------------------------------------------- what the panel edits

    def test_value_and_product_value_are_not_the_same_field(self):
        """`value` is for drawing, `product_value` is for writing back. The
        editor's wording box binds to the second on purpose."""
        row = self._row('info', per_product=True)
        self.Field.set_product_value(row['id'], self.product.id, 'Chennai')
        after = self._row('info', field_id=row['id'])
        self.assertEqual(after['product_value'], 'Chennai')
        self.assertEqual(after['value_source'], 'product')
        self.assertTrue(after['has_override'])

    def test_reset_clears_the_wording_too(self):
        """Why the editor's reset is not optimistic: it clears the state and
        the words, and guessing what the page falls back to is the guess that
        would be wrong."""
        row = self._row('info', per_product=True)
        self.Field.set_product_value(row['id'], self.product.id, 'Chennai')
        self.Field.reset_product_state([row['id']], self.product.id)
        after = self._row('info', field_id=row['id'])
        self.assertEqual(after['product_value'], '')
        self.assertEqual(after['state'], 'follow')
        self.assertFalse(after['has_override'])

    def test_a_bad_state_is_refused(self):
        row = self._row('info')
        with self.assertRaises(ValueError):
            self.Field.set_product_state(row['id'], self.product.id, 'maybe')

    def test_wording_on_a_shared_field_is_refused(self):
        """The panel hides the box for these; the model refuses anyway."""
        row = self._row('info', per_product=False)
        if not row:
            self.skipTest('every field on this section is per-product')
        with self.assertRaises(UserError):
            self.Field.set_product_value(row['id'], self.product.id, 'nope')

    # ------------------------------------------------------------- helpers

    def _row(self, section_key, field_id=None, per_product=None):
        data = self.Field.builder_load(self.product.id)
        section = next(s for s in data['sections'] if s['key'] == section_key)
        rows = section['rows']
        if field_id is not None:
            return next(r for r in rows if r['id'] == field_id)
        if per_product is not None:
            rows = [r for r in rows if r['per_product'] == per_product
                    and r['source'] == 'text']
        return rows[0] if rows else None


# What the picker hands the screens. Frozen for the same reason as the
# builder's: a key quietly dropped here is an empty rail over there, and QWeb
# renders `undefined` as nothing at all rather than raising.
PICKER_KEYS = frozenset({
    'categories', 'uncategorised', 'products', 'total', 'limit', 'all_count',
})
PICKER_CATEG_KEYS = frozenset({'id', 'name', 'parent_id', 'count'})
PICKER_PRODUCT_KEYS = frozenset({'id', 'name', 'code', 'image', 'differs'})


@tagged('post_install', '-at_install')
class TestProductPicker(TransactionCase):
    """Browsing the shop, rather than spelling a product's name."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Product = cls.env['product.template']
        Categ = cls.env['product.public.category']

        cls.parent = Categ.create({'name': 'Picker Computers'})
        cls.child = Categ.create({
            'name': 'Picker Laptops', 'parent_id': cls.parent.id})

        cls.laptop = cls.Product.create({
            'name': 'Picker Laptop One', 'default_code': 'PCK-LAP-1',
            'is_published': True, 'public_categ_ids': [(6, 0, cls.child.ids)],
        })
        cls.loose = cls.Product.create({
            'name': 'Picker Loose Thing', 'is_published': True,
        })
        cls.hidden = cls.Product.create({
            'name': 'Picker Unpublished', 'is_published': False,
            'public_categ_ids': [(6, 0, cls.child.ids)],
        })

    def _ids(self, **kw):
        return [p['id'] for p in self.Product.mart369_page_picker(**kw)['products']]

    def _categ(self, data, categ):
        return next(c for c in data['categories'] if c['id'] == categ.id)

    # ------------------------------------------------------------ the shape

    def test_shape(self):
        data = self.Product.mart369_page_picker()
        self.assertEqual(set(data), PICKER_KEYS)
        for categ in data['categories']:
            self.assertEqual(set(categ), PICKER_CATEG_KEYS)
        for product in data['products']:
            self.assertEqual(set(product), PICKER_PRODUCT_KEYS)

    def test_the_tile_has_something_to_draw(self):
        """The grid needs a picture per tile, and the rail a parent to nest
        under - both come from here or not at all."""
        data = self.Product.mart369_page_picker()
        row = next(p for p in data['products'] if p['id'] == self.laptop.id)
        self.assertEqual(
            row['image'],
            '/web/image/product.template/%s/image_128' % self.laptop.id)
        self.assertEqual(row['code'], 'PCK-LAP-1')
        self.assertEqual(self._categ(data, self.child)['parent_id'],
                         self.parent.id)

    # ----------------------------------------------------------- the filter

    def test_a_parent_category_finds_what_is_under_it(self):
        """The whole point of the rail. "Computers" is a heading, not a shelf:
        nothing is filed directly against it, so a plain equality test would
        show an empty grid next to a count of one."""
        self.assertIn(self.laptop.id, self._ids(categ_id=self.parent.id))
        self.assertIn(self.laptop.id, self._ids(categ_id=self.child.id))

    def test_the_count_matches_what_clicking_shows(self):
        data = self.Product.mart369_page_picker()
        self.assertEqual(self._categ(data, self.parent)['count'],
                         len(self._ids(categ_id=self.parent.id)))
        self.assertEqual(self._categ(data, self.child)['count'],
                         len(self._ids(categ_id=self.child.id)))

    def test_a_product_in_parent_and_child_is_counted_once(self):
        """Filed under both, it is still one product under the parent."""
        self.laptop.public_categ_ids = [(6, 0, (self.parent + self.child).ids)]
        data = self.Product.mart369_page_picker()
        self.assertEqual(self._categ(data, self.parent)['count'],
                         len(self._ids(categ_id=self.parent.id)))

    def test_products_filed_nowhere_are_reachable(self):
        """Without the bucket, a product with no category is in the shop and
        in no list - unreachable from this screen entirely."""
        data = self.Product.mart369_page_picker()
        self.assertGreaterEqual(data['uncategorised'], 1)
        loose = self._ids(categ_id=0)
        self.assertIn(self.loose.id, loose)
        self.assertNotIn(self.laptop.id, loose)

    def test_unpublished_products_stay_out(self):
        """This edits the page a shopper sees; an unpublished product has
        none."""
        self.assertNotIn(self.hidden.id, self._ids())
        self.assertNotIn(self.hidden.id, self._ids(categ_id=self.child.id))

    def test_search_covers_the_code_as_well_as_the_name(self):
        self.assertIn(self.laptop.id, self._ids(q='Picker Laptop'))
        self.assertIn(self.laptop.id, self._ids(q='PCK-LAP'))
        self.assertNotIn(self.loose.id, self._ids(q='PCK-LAP'))

    def test_only_edited_finds_what_somebody_changed(self):
        """The second question the screen exists to answer."""
        self.assertEqual(self._ids(only_edited=True), [])
        field = self.env['mart369.product.field'].search([], limit=1)
        self.env['mart369.product.override'].create({
            'product_tmpl_id': self.laptop.id,
            'field_id': field.id,
            'state': 'hide',
        })
        edited = self._ids(only_edited=True)
        self.assertEqual(edited, [self.laptop.id])
        row = next(p for p in self.Product.mart369_page_picker()['products']
                   if p['id'] == self.laptop.id)
        self.assertEqual(row['differs'], 1)

    def test_all_count_is_not_the_sum_of_the_branches(self):
        """It is the honest total: a product under two top-level categories
        would be counted twice by adding the rows up."""
        data = self.Product.mart369_page_picker()
        self.assertEqual(data['all_count'], len(self._ids()))
