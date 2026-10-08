"""The console's "Choose products" for a home row (`_mart369_set_picked`,
PUT /369mart/admin/home/bands/section/<id>/products): up to 12 products, shown
in the order they were ticked."""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRowPicker(TransactionCase):

    def setUp(self):
        super().setUp()
        self.mode = self.env['mart369.home.mode']._get('quick')
        Product = self.env['product.template']
        self.products = Product.browse([Product.create({
            'name': 'Zz Pick %02d' % i, 'is_published': True, 'list_price': 10 + i}).id
            for i in range(14)])
        self.row = self.env['mart369.home.section'].create({
            'mode_id': self.mode.id, 'kind': 'rail', 'name': 'Picker check',
            'key': 'picker-check', 'source': 'category', 'sequence': 999})

    def _names(self):
        return [item['name'] for item in
                self.row._serialize(self.mode._price_context(self.row))['items']]

    def test_ticked_products_show_in_tick_order(self):
        p = self.products
        self.row._mart369_set_picked([p[3].id, p[0].id, p[7].id])
        self.assertEqual(self.row.source, 'manual')
        self.assertEqual(self._names(), ['Zz Pick 03', 'Zz Pick 00', 'Zz Pick 07'])

    def test_reordering_keeps_a_lines_own_wording(self):
        p = self.products
        self.row._mart369_set_picked([p[0].id, p[1].id])
        line = self.row.picked_product_ids.filtered(lambda l: l.product_tmpl_id == p[1])
        line.name_override = 'Our pick'
        self.row._mart369_set_picked([p[1].id, p[2].id])
        self.assertTrue(line.exists(), 'still ticked, so the same line')
        self.assertEqual(self._names(), ['Our pick', 'Zz Pick 02'])

    def test_twelve_is_the_most(self):
        ids = self.products[:12].ids
        self.row._mart369_set_picked(ids)
        self.assertEqual(len(self._names()), 12)
        with self.assertRaises(UserError):
            self.row._mart369_set_picked(self.products[:13].ids)
        self.assertEqual(self.row.picked_product_ids.product_tmpl_id.ids, ids, 'nothing changed')

    def test_a_product_not_on_the_shop_is_refused(self):
        hidden = self.env['product.template'].create({'name': 'Zz Hidden', 'is_published': False})
        with self.assertRaises(UserError):
            self.row._mart369_set_picked([self.products[0].id, hidden.id])
        self.assertEqual(self.row.source, 'category', 'nothing changed')

    def test_an_empty_list_leaves_the_row_with_nothing_to_show(self):
        self.row._mart369_set_picked([self.products[0].id])
        self.row._mart369_set_picked([])
        self.assertFalse(self.row.picked_product_ids)
        self.assertIsNone(self.row._serialize(self.mode._price_context(self.row)))
