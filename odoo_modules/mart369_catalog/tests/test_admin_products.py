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

    # ------------------------------------------ the Products desk, same rules

    def _picked(self, **kw):
        data = self.Tmpl.mart369_page_picker(q='Zz Admin', **kw)
        return data, [p['id'] for p in data['products']]

    def test_products_desk_gets_the_stock_desk_tiles(self):
        data, __ = self._picked()
        self.assertEqual(data['tiles'], self.Tmpl.mart369_admin_list()['tiles'])
        self.assertEqual(data['stock'][self.low.id], [3, 'low'])

    def test_products_desk_tabs_filter_like_the_stock_desk(self):
        __, low = self._picked(tab='low')
        self.assertEqual(low, [self.low.id])
        __, out = self._picked(tab='out')
        self.assertEqual(out, [self.out.id])
        __, hidden = self._picked(tab='off')
        self.assertEqual(hidden, [self.hidden.id])
        __, everything = self._picked()
        self.assertNotIn(self.hidden.id, everything, 'All is the published shop')

    def test_products_desk_storefront_and_sort(self):
        __, express = self._picked(mode='all')
        self.assertIn(self.express.id, express)
        __, quick = self._picked(mode='quick')
        self.assertNotIn(self.express.id, quick)
        __, lowest = self._picked(sort='low')
        self.assertEqual(lowest[0], self.out.id, 'lowest stock first')


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


@tagged('post_install', '-at_install')
class TestProductStats(TransactionCase):
    """The numbers strip on the desk's product view: Odoo's own figures."""

    def test_the_strip_reads_odoos_figures(self):
        Tmpl = self.env['product.template']
        if 'free_qty' not in self.env['product.product']._fields:
            raise unittest.SkipTest('Inventory is not installed')
        product = _stocked(self.env, 'Zz Stats', 12, list_price=100.0)
        product.standard_price = 60.0
        stats = Tmpl.mart369_product_stats(product.id)
        self.assertEqual(stats['onHand'], 12)
        self.assertEqual(stats['price'], 100.0)
        self.assertEqual(stats['cost'], 60.0)
        self.assertEqual(stats['margin'], 40)
        self.assertEqual(stats['open']['onHand'], 'action_open_quants')

    def test_no_cost_means_no_margin(self):
        """A margin worked out against a missing cost reads 100% - wrong."""
        product = self.env['product.template'].create({'name': 'Zz No Cost', 'list_price': 50})
        self.assertIsNone(self.env['product.template'].mart369_product_stats(product.id)['margin'])


# A 1x1 PNG: the smallest picture Odoo will accept as an image.
_PNG = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8'
        '/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==')


@tagged('post_install', '-at_install')
class TestAdminProductEditRoutes(HttpCase):
    """The app's console edits a product through the same desk methods as
    Odoo's own Products desk - so the routes are thin, and these check the
    wrapping: who may call them, and that what was sent is what was saved."""

    def setUp(self):
        super().setUp()
        self.authenticate('admin', 'admin')
        self.Tmpl = self.env['product.template']

    def _send(self, method, url, body):
        return self.url_open(url, json=body, method=method)

    def test_blank_form_offers_every_box(self):
        res = self.url_open('/369mart/admin/products/form')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body['ok'])
        self.assertIsNone(body['id'])
        names = [b['name'] for g in body['groups'] for b in g['boxes']]
        self.assertIn('name', names)
        self.assertIn('list_price', names)
        self.assertIn('categories', body)

    def test_create_with_photos_then_edit(self):
        categ = self.env['product.public.category'].create({'name': 'Zz Route Categ'})
        res = self._send('POST', '/369mart/admin/products', {
            'values': {'name': 'Zz Route Made', 'list_price': '12.5',
                       'mart_unit_text': '250 g', 'image_1920': _PNG,
                       'public_categ_ids': [categ.id]},
            'photos': {'add': [{'name': 'side', 'data': _PNG}]},
        })
        self.assertEqual(res.status_code, 200, res.text)
        new_id = res.json()['id']
        product = self.Tmpl.browse(new_id)
        self.assertEqual(product.name, 'Zz Route Made')
        self.assertEqual(product.list_price, 12.5)
        self.assertEqual(product.public_categ_ids, categ)
        self.assertTrue(product.image_1920)
        self.assertTrue(product.is_published, 'made on the desk means live')
        self.assertEqual(len(product.product_template_image_ids), 1)

        form = self.url_open('/369mart/admin/products/form?id=%s' % new_id).json()
        self.assertEqual(form['values']['name'], 'Zz Route Made')
        self.assertEqual(len(form['photos']), 1)
        self.assertTrue(form['photo'])

        gallery = product.product_template_image_ids
        res = self._send('PATCH', '/369mart/admin/products/%s' % new_id, {
            'values': {'name': 'Zz Route Renamed', 'list_price': 9},
            'photos': {'remove': [gallery.id]},
        })
        self.assertEqual(res.status_code, 200, res.text)
        product.invalidate_recordset()
        self.assertEqual(product.name, 'Zz Route Renamed')
        self.assertEqual(product.list_price, 9)
        self.assertFalse(product.product_template_image_ids.exists())

        detail = self.url_open('/369mart/admin/products/%s' % new_id).json()
        self.assertTrue(detail['ok'])
        self.assertEqual(detail['product']['name'], 'Zz Route Renamed')
        self.assertTrue(detail['product']['photo'])
        self.assertIn('sections', detail)
        self.assertEqual(detail['stats'].get('price'), 9)

    def test_set_a_gallery_photo_on_the_card(self):
        product = self.Tmpl.create({'name': 'Zz Route Promote', 'image_1920': _PNG})
        extra = self.env['product.image'].create({
            'name': 'x', 'image_1920': _PNG, 'product_tmpl_id': product.id})
        res = self._send('PATCH', '/369mart/admin/products/%s' % product.id, {
            'values': {}, 'photos': {'promote': extra.id, 'demote': True}})
        self.assertEqual(res.status_code, 200, res.text)
        product.invalidate_recordset()
        self.assertFalse(extra.exists(), 'promoted off the gallery')
        self.assertEqual(len(product.product_template_image_ids), 1,
                         'the old card picture moved into the gallery')

    def test_a_nameless_product_is_refused_whole(self):
        before = self.Tmpl.search_count([])
        res = self._send('POST', '/369mart/admin/products', {
            'values': {'name': '  ', 'list_price': 5}, 'photos': {}})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.json()['ok'])
        self.assertEqual(self.Tmpl.search_count([]), before)

    def test_missing_product_is_404(self):
        self.assertEqual(self.url_open('/369mart/admin/products/999999999').status_code, 404)
        res = self._send('PATCH', '/369mart/admin/products/999999999',
                         {'values': {'name': 'x'}, 'photos': {}})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(
            self.url_open('/369mart/admin/products/form?id=999999999').status_code, 404)

    def test_a_shopper_may_not_edit(self):
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Edit Snoop', 'login': 'edit.snoop@example.com',
            'password': 'edit-snoop-369',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        product = self.Tmpl.create({'name': 'Zz Route Guarded'})
        self.authenticate('edit.snoop@example.com', 'edit-snoop-369')
        self.assertEqual(self.url_open('/369mart/admin/products/form').status_code, 403)
        self.assertEqual(
            self.url_open('/369mart/admin/products/%s' % product.id).status_code, 403)
        res = self._send('POST', '/369mart/admin/products',
                         {'values': {'name': 'Zz Sneaked In'}, 'photos': {}})
        self.assertEqual(res.status_code, 403)
        res = self._send('PATCH', '/369mart/admin/products/%s' % product.id,
                         {'values': {'name': 'Zz Defaced'}, 'photos': {}})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(product.name, 'Zz Route Guarded')
        self.assertFalse(self.Tmpl.search([('name', '=', 'Zz Sneaked In')]))


@tagged('post_install', '-at_install')
class TestDeskOnHand(TransactionCase):
    """On hand typed on the desk is booked as Odoo's own inventory count."""

    def setUp(self):
        super().setUp()
        if 'free_qty' not in self.env['product.product']._fields:
            raise unittest.SkipTest('Inventory is not installed')
        self.Tmpl = self.env['product.template']

    def _box(self, form, name):
        return next((b for g in form['groups'] for b in g['boxes'] if b['name'] == name), None)

    def test_a_new_product_starts_with_its_count(self):
        pid = self.Tmpl.mart369_desk_save({
            'name': 'Zz Counted', 'type': 'consu', 'is_storable': True, 'mart_on_hand': '24'})
        self.assertEqual(self.Tmpl.browse(pid).qty_available, 24)

    def test_recounting_books_the_difference(self):
        pid = self.Tmpl.mart369_desk_save({
            'name': 'Zz Recount', 'type': 'consu', 'is_storable': True, 'mart_on_hand': '24'})
        self.Tmpl.mart369_desk_save({'mart_on_hand': '20'}, product_id=pid)
        product = self.Tmpl.browse(pid)
        product.invalidate_recordset()
        self.assertEqual(product.qty_available, 20)

    def test_the_box_only_shows_once_the_product_is_counted(self):
        box = self._box(self.Tmpl.mart369_desk_form(), 'mart_on_hand')
        self.assertEqual(box['showIf'], 'is_storable')

    def test_a_service_is_not_counted(self):
        pid = self.Tmpl.mart369_desk_save({
            'name': 'Zz Service', 'type': 'service', 'mart_on_hand': '5'})
        self.assertEqual(self.Tmpl.browse(pid).qty_available, 0)
