"""Settings > Products: a price, a picture, stock - each can be required.

A product missing any one that is switched on is not listed on the web shop.
Looking one up by id, and WhatsApp's use of the similar row, do not change.
"""

import base64
import io
import itertools
import json

from PIL import Image

from odoo.tests import HttpCase, tagged

FLAGS = ('require_price', 'require_image', 'require_stock')


def picture():
    out = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(out, 'PNG')
    return base64.b64encode(out.getvalue())


@tagged('post_install', '-at_install')
class TestMart369Visibility(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Keep test pictures in the database, as the desk tests do.
        cls.env['ir.config_parameter'].sudo().set_param('ai369_image_server.enabled', 'False')
        cls.Template = cls.env['product.template']
        cls.config = cls.env['mart369.config'].sudo()._get()
        cls.categ = cls.env['product.public.category'].create({'name': 'Visibility Shelf'})
        cls.tracks = 'free_qty' in cls.env['product.product']._fields
        # One product for each of the eight combinations of what it has.
        cls.products = {
            has: cls._product('Vistest %d%d%d' % has, *has)
            for has in itertools.product((True, False), repeat=3)}
        cls._flags()

    @classmethod
    def _product(cls, name, price=True, image=True, stock=True, **extra):
        vals = {'name': name, 'is_published': True, 'list_price': 5 if price else 0,
                'image_1920': picture() if image else False,
                'public_categ_ids': [(6, 0, cls.categ.ids)]}
        if cls.tracks:
            vals['is_storable'] = True
        product = cls.Template.create(dict(vals, **extra))
        if stock and cls.tracks and product.is_storable:
            cls._stock(product.product_variant_id, 3)
        return product

    @classmethod
    def _stock(cls, variant, qty):
        warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(
            variant, warehouse.lot_stock_id, qty)
        cls.env.invalidate_all()

    @classmethod
    def _flags(cls, *on):
        cls.config.write({flag: flag in on for flag in FLAGS})

    def _listed(self, product):
        return product in self.Template.search(self.Template._mart369_listed_domain())

    def test_all_off_is_the_rule_as_it_was(self):
        self.assertEqual(self.Template._mart369_listed_domain(),
                         self.Template._mart369_listed_base_domain())

    def test_every_combination(self):
        for on in itertools.product((False, True), repeat=3):
            if on[2] and not self.tracks:
                continue
            self._flags(*[flag for flag, wanted in zip(FLAGS, on) if wanted])
            found = self.Template.search(self.categ._mart369_product_domain())
            for has, product in self.products.items():
                wanted = all(h for h, o in zip(has, on) if o)
                self.assertEqual(product in found, wanted, (on, has))
                # Hand-picked rows ask through filtered_domain.
                self.assertEqual(
                    bool(product.filtered_domain(self.Template._mart369_listed_domain())),
                    wanted, (on, has))

    def test_price_edges(self):
        self._flags('require_price')
        product = self._product('Vistest price')
        for price, wanted in ((False, False), (0, False), (-1, False), (0.01, True)):
            product.list_price = price
            self.assertEqual(self._listed(product), wanted, price)

    def test_an_extra_picture_is_a_picture(self):
        self._flags('require_image')
        product = self._product('Vistest extra', image=False)
        self.assertFalse(self._listed(product))
        self.env['product.image'].create({
            'name': 'extra', 'product_tmpl_id': product.id, 'image_1920': picture()})
        self.assertTrue(self._listed(product))

    def test_an_empty_picture_file_is_not_a_picture(self):
        self._flags('require_image')
        product = self._product('Vistest broken')
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE ir_attachment SET file_size = 0 WHERE res_model = 'product.template'"
            " AND res_field = 'image_1920' AND res_id = %s", [product.id])
        self.env.invalidate_all()
        self.assertFalse(self._listed(product))

    def test_stock_edges(self):
        if not self.tracks:
            self.skipTest('Inventory is not installed')
        self._flags('require_stock')
        product = self._product('Vistest stock', stock=False)
        self.assertFalse(self._listed(product))
        self._stock(product.product_variant_id, -2)
        self.assertFalse(self._listed(product))
        self._stock(product.product_variant_id, 3)
        self.assertTrue(self._listed(product))
        untracked = self._product('Vistest untracked', is_storable=False)
        self.assertFalse(self._listed(untracked), 'no stock number is missing stock')

    def test_one_variant_in_stock_is_enough(self):
        if not self.tracks:
            self.skipTest('Inventory is not installed')
        self._flags('require_stock')
        attribute = self.env['product.attribute'].create({
            'name': 'Vis colour', 'value_ids': [(0, 0, {'name': n}) for n in ('a', 'b')]})
        product = self._product('Vistest variants', stock=False, attribute_line_ids=[
            (0, 0, {'attribute_id': attribute.id,
                    'value_ids': [(6, 0, attribute.value_ids.ids)]})])
        self.assertFalse(self._listed(product))
        self._stock(product.product_variant_ids[1], 1)
        self.assertTrue(self._listed(product))

    def test_search_leaves_them_out_and_by_id_does_not(self):
        self._flags('require_price')
        items = self.url_open('/369mart/search/suggest?q=Vistest').json()
        self.assertEqual(items['total'], 4)
        hidden = self.products[(False, True, True)]
        got = self.url_open('/369mart/products?ids=%d' % hidden.id).json()
        self.assertEqual([i['id'] for i in got['items']], [str(hidden.id)])
        self.assertEqual(self.url_open('/369mart/product/%d' % hidden.id).status_code, 200)

    def test_similar_changes_on_the_web_only(self):
        self._flags('require_price')
        Page = self.env['mart369.product.page']
        product = self.products[(True, True, True)]
        hidden = self.products[(False, True, True)]
        self.assertIn(hidden, Page._guess(product))
        web = Page.with_context(mart369_web_visible=True)
        self.assertNotIn(hidden, web._guess(product))
        self.assertIn(hidden, Page._published(hidden))
        self.assertFalse(web._published(hidden))

    def test_a_hand_picked_row_saves_and_skips_the_hidden(self):
        if 'mart369.home.section' not in self.env:
            self.skipTest('the home page is not installed')
        self._flags('require_price')
        section = self.env['mart369.home.section'].create({
            'mode_id': self.env['mart369.home.mode']._get('quick').id, 'kind': 'rail',
            'name': 'Vis row', 'key': 'vis-row', 'source': 'manual'})
        shown, hidden = self.products[(True, True, True)], self.products[(False, True, True)]
        section._mart369_set_picked([hidden.id, shown.id])
        self.assertEqual(section.picked_product_ids.product_tmpl_id, shown | hidden)
        self.assertEqual(section._resolve_products(), shown)

    def test_the_settings_group(self):
        Config = self.env['mart369.config']
        saved = Config.mart369_admin_save('visibility', {'requirePrice': True})
        self.assertEqual(saved['visibility'], {
            'requirePrice': True, 'requireImage': False, 'requireStock': False})

    def test_a_shopper_cannot_change_it(self):
        self.env['res.users'].create({
            'name': 'Vis shopper', 'login': 'vis_shopper', 'password': 'vis_shopper_1',
            'group_ids': [(6, 0, self.env.ref('base.group_portal').ids)]})
        self.authenticate('vis_shopper', 'vis_shopper_1')
        res = self.url_open('/369mart/admin/settings/visibility',
                            data=json.dumps({'requirePrice': True}),
                            headers={'Content-Type': 'application/json'})
        self.assertEqual(res.status_code, 403)
        self.config.invalidate_recordset()
        self.assertFalse(self.config.require_price)
