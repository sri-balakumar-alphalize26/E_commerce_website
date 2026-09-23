"""The stock list in the app's own console.

**Who may look.** The group check is the only fence; a shopper is refused.

**Stock tabs are the shop, not the page.** Stock is not stored, so "low" and
"out" are worked out in Python - and a version that did it after cutting the
page would pass on a small database and lie on a real one. The tests put the
low product past the first page and expect to find it anyway.

**"Low" is the storefront's threshold.** The console and the product card must
agree about when a product is running low, so both read `mart_low_stock_at`.
"""

import unittest

from odoo.tests import HttpCase, TransactionCase, tagged


def _stocked(env, name, qty, low_at=0, **vals):
    tmpl = env['product.template'].create(dict({
        'name': name, 'sale_ok': True, 'list_price': 50.0,
        'mart_low_stock_at': low_at, 'is_published': True,
    }, **vals))
    if 'is_storable' in tmpl._fields:
        tmpl.is_storable = True
    if qty and 'stock.quant' in env:
        location = env['stock.warehouse'].search(
            [('company_id', '=', env.company.id)], limit=1).lot_stock_id
        env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': tmpl.product_variant_id.id,
            'location_id': location.id,
            'inventory_quantity': qty,
        }).action_apply_inventory()
    return tmpl


@tagged('post_install', '-at_install')
class TestAdminProductList(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Tmpl = cls.env['product.template']
        if 'free_qty' not in cls.env['product.product']._fields:
            raise unittest.SkipTest('Inventory is not installed')
        cls.plenty = _stocked(cls.env, 'Zz Admin Plenty', 100, low_at=5)
        cls.low = _stocked(cls.env, 'Zz Admin Low', 3, low_at=5)
        cls.out = _stocked(cls.env, 'Zz Admin Out', 0, low_at=5)
        cls.hidden = _stocked(cls.env, 'Zz Admin Hidden', 20, is_published=False)
        cls.express = _stocked(cls.env, 'Zz Admin Express', 20,
                               mart_delivery_text='2-5 days')

    def _ids(self, **kw):
        page = self.Tmpl.mart369_admin_list(limit=200, **kw)
        return {r['id'] for r in page['rows']}

    def test_row_carries_what_the_table_draws(self):
        row = self.Tmpl.mart369_admin_list(q='Zz Admin Low')['rows'][0]
        for key in ('id', 'name', 'unit', 'price', 'mrp', 'image', 'cat', 'delivery',
                    'qty', 'sold7', 'active', 'reorder', 'state'):
            self.assertIn(key, row)
        self.assertEqual(row['qty'], 3)
        self.assertEqual(row['reorder'], 5)
        self.assertEqual(row['state'], 'low')

    def test_stock_tabs_use_the_storefront_threshold(self):
        low = self._ids(tab='low')
        self.assertIn(self.low.id, low)
        self.assertNotIn(self.plenty.id, low)
        self.assertNotIn(self.out.id, low, 'out of stock is its own tab')
        self.assertIn(self.out.id, self._ids(tab='out'))
        self.assertIn(self.hidden.id, self._ids(tab='off'))
        self.assertNotIn(self.plenty.id, self._ids(tab='off'))

    def test_stock_tab_is_the_shop_not_the_first_page(self):
        # Sorted by name the low product is last among ours; a page of one
        # that filtered after cutting would miss it.
        page = self.Tmpl.mart369_admin_list(tab='low', q='Zz Admin', sort='name', limit=1)
        self.assertEqual(page['total'], 1)
        self.assertEqual(page['rows'][0]['id'], self.low.id)

    def test_storefront_filter_and_sort(self):
        self.assertIn(self.express.id, self._ids(mode='all', q='Zz Admin'))
        self.assertNotIn(self.express.id, self._ids(mode='quick', q='Zz Admin'))
        rows = self.Tmpl.mart369_admin_list(q='Zz Admin', sort='low', limit=200)['rows']
        self.assertEqual(rows[0]['id'], self.out.id, 'lowest stock first')

    def test_storefront_follows_the_top_category(self):
        Categ = self.env['product.public.category']
        top = Categ.create({'name': 'Zz Express Top', 'mart_mode': 'all'})
        child = Categ.create({'name': 'Zz Express Child', 'parent_id': top.id})
        self.plenty.public_categ_ids = [(6, 0, [child.id])]
        self.assertIn(self.plenty.id, self._ids(mode='all', q='Zz Admin'))
        self.assertNotIn(self.plenty.id, self._ids(mode='quick', q='Zz Admin'))
        row = self.Tmpl.mart369_admin_list(q='Zz Admin Plenty')['rows'][0]
        self.assertTrue(row['delivery'], 'the row says Express too')

    def test_tiles_count_the_shop_not_the_filter(self):
        everything = self.Tmpl.mart369_admin_list()['tiles']
        filtered = self.Tmpl.mart369_admin_list(q='Zz Admin Plenty')
        self.assertEqual(filtered['tiles'], everything)
        self.assertEqual(filtered['total'], 1)


@tagged('post_install', '-at_install')
class TestAdminProductRoutes(HttpCase):

    def test_a_shopper_is_refused(self):
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Stock Snoop', 'login': 'stock.snoop@example.com',
            'password': 'stock-snoop-369',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        self.authenticate('stock.snoop@example.com', 'stock-snoop-369')
        res = self.url_open('/369mart/admin/products')
        self.assertEqual(res.status_code, 403)
        self.assertNotIn('rows', res.text)

    def test_staff_get_a_page(self):
        self.authenticate('admin', 'admin')
        res = self.url_open('/369mart/admin/products?limit=1')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body['ok'])
        self.assertLessEqual(len(body['rows']), 1)
        self.assertIn('low', body['tiles'])
