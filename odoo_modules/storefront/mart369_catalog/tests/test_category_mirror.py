"""One category tree: a Product Category and its website twin.

The WhatsApp package files products under Product Categories; the website
draws `product.public.category`. A name is typed once, and a product's website
category is always its Product Category's twin.
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCategoryMirror(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Categ = self.env['product.category']
        self.Public = self.env['product.public.category']
        self.Product = self.env['product.template']
        self.computers = self.Categ.create({'name': 'Zz Mirror Computers'})

    # ----------------------------------------------------------- the twin

    def test_a_product_category_gets_a_website_twin(self):
        twin = self.computers.mart_mirror_id
        self.assertTrue(twin)
        self.assertEqual(twin.name, 'Zz Mirror Computers')
        self.assertTrue(twin.mart_slug, 'addressable by the app like any category')

    def test_the_twin_keeps_the_tree(self):
        child = self.Categ.create({'name': 'Zz Mirror Laptops', 'parent_id': self.computers.id})
        self.assertEqual(child.mart_mirror_id.parent_id, self.computers.mart_mirror_id)

    def test_a_name_is_typed_once_either_side(self):
        self.computers.name = 'Zz Mirror PCs'
        self.assertEqual(self.computers.mart_mirror_id.name, 'Zz Mirror PCs')
        self.computers.mart_mirror_id.name = 'Zz Mirror Desktops'
        self.assertEqual(self.computers.name, 'Zz Mirror Desktops')

    def test_the_slug_survives_a_rename(self):
        slug = self.computers.mart_mirror_id.mart_slug
        self.computers.name = 'Zz Mirror Renamed'
        self.assertEqual(self.computers.mart_mirror_id.mart_slug, slug,
                         'a customer may have the old link')

    def test_a_removed_category_leaves_the_app_but_keeps_its_twin(self):
        twin = self.computers.mart_mirror_id
        self.computers.unlink()
        self.assertTrue(twin.exists())
        self.assertFalse(twin.mart_in_app)

    def test_the_console_creates_both(self):
        row = self.Public.mart369_admin_create({'name': 'Zz Console Printers'})
        twin = self.Public.browse(row['id'])
        source = twin._mart369_source()
        self.assertEqual(source.name, 'Zz Console Printers')
        self.assertEqual(source.mart_mirror_id, twin, 'one twin, not a second one')

    # -------------------------------------------------------- the products

    def test_a_products_website_category_follows_its_category(self):
        product = self.Product.create({'name': 'Zz Mirror Laptop', 'categ_id': self.computers.id})
        self.assertEqual(product.public_categ_ids, self.computers.mart_mirror_id)
        parts = self.Categ.create({'name': 'Zz Mirror Parts'})
        product.categ_id = parts
        self.assertEqual(product.public_categ_ids, parts.mart_mirror_id)

    def test_an_internal_category_leaves_the_website_alone(self):
        aisle = self.Public.create({'name': 'Zz Mirror Aisle'})
        internal = self.Categ.with_context(mart369_mirror_sync=True).create({'name': 'Zz Internal'})
        self.assertFalse(internal.mart_mirror_id)
        product = self.Product.create({'name': 'Zz Mirror Gift', 'public_categ_ids': [(6, 0, aisle.ids)]})
        product.categ_id = internal
        self.assertEqual(product.public_categ_ids, aisle)

    def test_linking_an_existing_aisle_moves_the_products(self):
        aisle = self.Public.create({'name': 'Zz Mirror Old Aisle'})
        # Made without a twin, then used as any category is (no sync flag).
        internal = self.Categ.browse(self.Categ.with_context(
            mart369_mirror_sync=True).create({'name': 'Zz Mirror Old Aisle'}).id)
        product = self.Product.create({'name': 'Zz Mirror Mouse', 'categ_id': internal.id})
        internal.mart_mirror_id = aisle
        self.assertEqual(product.public_categ_ids, aisle)

    def test_the_desk_asks_for_category_only(self):
        form = self.Product.mart369_desk_form()
        names = {b['name'] for g in form['groups'] for b in g['boxes']}
        self.assertIn('categ_id', names)
        self.assertNotIn('public_categ_ids', names)
        pid = self.Product.mart369_desk_save({'name': 'Zz Mirror Desk', 'categ_id': str(self.computers.id)})
        self.assertEqual(self.Product.browse(pid).public_categ_ids, self.computers.mart_mirror_id)


@tagged('post_install', '-at_install')
class TestAttributeFacets(TransactionCase):
    """Each card carries its attribute values for the category page's chips."""

    GIF = 'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'

    def test_a_card_carries_its_attribute_values(self):
        Attribute = self.env['product.attribute']
        kind = Attribute.create({'name': 'Zz Type', 'sequence': 1, 'display_type': 'image',
                                 'value_ids': [(0, 0, {'name': 'Laptop', 'image': self.GIF})]})
        colour = Attribute.create({'name': 'Zz Colour', 'sequence': 2, 'display_type': 'color',
                                   'value_ids': [(0, 0, {'name': 'Black', 'html_color': '#000000'}),
                                                 (0, 0, {'name': 'Silver', 'html_color': '#c0c0c0'})]})
        product = self.env['product.template'].create({
            'name': 'Zz Facet Laptop', 'is_published': True,
            'attribute_line_ids': [
                (0, 0, {'attribute_id': kind.id, 'value_ids': [(6, 0, kind.value_ids.ids)]}),
                (0, 0, {'attribute_id': colour.id, 'value_ids': [(6, 0, colour.value_ids.ids)]}),
            ]})
        Mixin = self.env['mart369.serializable'].sudo()
        card = Mixin._serialize_product(product, None, Mixin._price_context_for(product))
        facets = card['facets']
        self.assertEqual([(f['name'], f['value']) for f in facets],
                         [('Zz Type', 'Laptop'), ('Zz Colour', 'Black'), ('Zz Colour', 'Silver')])
        self.assertIn('/web/image/product.attribute.value/', facets[0]['image'])
        self.assertEqual(facets[1]['color'], '#000000')
        self.assertNotIn('image', facets[1])

    def test_a_plain_product_has_no_facets(self):
        product = self.env['product.template'].create({'name': 'Zz Plain', 'is_published': True})
        Mixin = self.env['mart369.serializable'].sudo()
        card = Mixin._serialize_product(product, None, Mixin._price_context_for(product))
        self.assertNotIn('facets', card)
