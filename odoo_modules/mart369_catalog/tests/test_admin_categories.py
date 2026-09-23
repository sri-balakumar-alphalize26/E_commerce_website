"""The staff side of the catalog, over HTTP.

What is worth pinning here is mostly what this screen **cannot** do.

**The name and the app address are not editable.** The name is Odoo's own
field, leaned on by the catalogue, the product pages and every report; the
address is a URL a customer may have saved, and changing it breaks that link
silently. A request carrying either must change neither.

**A sub-category has no storefront of its own.** It follows its top-level
parent - so accepting one would store a value the app never reads and then
show a storefront the category is not in.

**A colour has to be a colour.** The storefront drops these straight into CSS,
so anything else is a silently broken category page rather than an error
anybody sees.
"""

import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}

LIST = '/369mart/admin/categories'


@tagged('post_install', '-at_install')
class TestAdminCategories(HttpCase):

    def setUp(self):
        super().setUp()
        Category = self.env['product.public.category'].sudo()
        self.top = Category.create({
            'name': 'Admin Test Aisle',
            'mart_slug': 'admin-test-aisle',
            'mart_mode': 'quick',
            'mart_in_app': True,
        })
        self.child = Category.create({
            'name': 'Admin Test Shelf',
            'mart_slug': 'admin-test-shelf',
            'parent_id': self.top.id,
        })
        self.hidden = Category.create({
            'name': 'Admin Test Hidden',
            'mart_slug': 'admin-test-hidden',
            'mart_in_app': False,
        })

        self.shopper = self.env['res.users'].sudo().create({
            'name': 'Catalog Shopper',
            'login': 'mart369_catalog_shopper',
            'password': 'mart369_catalog_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    def _send(self, method, path, payload=None):
        return self.url_open(
            path, data=json.dumps(payload or {}), headers=HEADERS, method=method)

    def _patch(self, category, payload):
        return self._send('PATCH', '%s/%s' % (LIST, category.id), payload)

    def _rows(self, **params):
        query = '&'.join('%s=%s' % kv for kv in params.items())
        res = self.url_open(LIST + ('?%s' % query if query else ''))
        return res.status_code, res.json()

    def _row_for(self, payload, category):
        return next((r for r in payload['rows'] if r['id'] == category.id), None)

    # ---------------------------------------------------------------- the lock

    def test_a_shopper_is_refused_every_admin_route(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        self.authenticate('mart369_catalog_shopper', 'mart369_catalog_shopper')
        for res in (self.url_open(LIST),
                    self._patch(self.top, {'mart_in_app': False})):
            self.assertEqual(res.status_code, 403)
            self.assertFalse(res.json().get('ok'))

    def test_a_shopper_cannot_hide_a_category(self):
        self.authenticate('mart369_catalog_shopper', 'mart369_catalog_shopper')
        self._patch(self.top, {'mart_in_app': False})
        self.top.invalidate_recordset()
        self.assertTrue(self.top.mart_in_app)

    # -------------------------------------------------------------- the screen

    def test_each_tab_is_a_domain_not_a_suggestion(self):
        self.authenticate('admin', 'admin')

        status, live = self._rows(tab='live')
        self.assertEqual(status, 200)
        self.assertTrue(all(r['inApp'] for r in live['rows']))
        self.assertIsNotNone(self._row_for(live, self.top))
        self.assertIsNone(self._row_for(live, self.hidden))

        __, hidden = self._rows(tab='hidden')
        self.assertTrue(all(not r['inApp'] for r in hidden['rows']))
        self.assertIsNotNone(self._row_for(hidden, self.hidden))

    def test_a_child_reports_its_parents_storefront(self):
        """`mode` is what the app really uses; `ownMode` is what the record
        holds. Showing only the second would print a setting that does
        nothing."""
        self.authenticate('admin', 'admin')
        self.top.mart_mode = 'all'
        __, payload = self._rows()
        child = self._row_for(payload, self.child)
        self.assertEqual(child['mode'], 'all')
        self.assertFalse(child['topLevel'])

    def test_the_storefront_filter_follows_the_parent_too(self):
        """A child has no mart_mode of its own, so a plain domain would drop
        it out of its own storefront."""
        self.authenticate('admin', 'admin')
        self.top.mart_mode = 'all'
        __, express = self._rows(mode='all')
        self.assertIsNotNone(self._row_for(express, self.child))
        __, quick = self._rows(mode='quick')
        self.assertIsNone(self._row_for(quick, self.child))

    def test_the_tiles_count_everything_not_the_filtered_rows(self):
        self.authenticate('admin', 'admin')
        __, everything = self._rows()
        __, searched = self._rows(q='Admin Test Aisle')
        self.assertEqual(len(searched['rows']), 1)
        self.assertEqual(searched['tiles'], everything['tiles'])
        self.assertEqual(searched['counts'], everything['counts'])

    def test_search_matches_the_name_and_the_app_address(self):
        self.authenticate('admin', 'admin')
        __, by_name = self._rows(q='Admin Test Hidden')
        self.assertIsNotNone(self._row_for(by_name, self.hidden))
        __, by_slug = self._rows(q='admin-test-hidden')
        self.assertIsNotNone(self._row_for(by_slug, self.hidden))

    # --------------------------------------------------------------- the write

    def test_staff_can_hide_and_show_a_category(self):
        self.authenticate('admin', 'admin')

        res = self._patch(self.top, {'mart_in_app': False})
        self.assertEqual(res.status_code, 200, res.text)
        self.top.invalidate_recordset()
        self.assertFalse(self.top.mart_in_app)

        res = self._patch(self.top, {'mart_in_app': True})
        self.assertEqual(res.status_code, 200, res.text)
        self.top.invalidate_recordset()
        self.assertTrue(self.top.mart_in_app)

    def test_staff_can_change_how_it_looks(self):
        self.authenticate('admin', 'admin')
        res = self._patch(self.top, {
            'mart_blurb': 'Picked this morning',
            'mart_tone': '#E8F5E9',
            'mart_accent': '#1F7A4C',
        })
        self.assertEqual(res.status_code, 200, res.text)
        self.top.invalidate_recordset()
        self.assertEqual(self.top.mart_blurb, 'Picked this morning')
        # Folded to lower case, so the same colour is not stored two ways.
        self.assertEqual(self.top.mart_tone, '#e8f5e9')
        self.assertEqual(self.top.mart_accent, '#1f7a4c')

    def test_the_name_and_the_address_are_not_editable_here(self):
        """The two fields this screen refuses. A request carrying them must
        change neither - the allow-list is what enforces that."""
        self.authenticate('admin', 'admin')
        res = self._patch(self.top, {
            'mart_blurb': 'Still saved',
            'name': 'Renamed by the console',
            'mart_slug': 'renamed-by-the-console',
        })
        self.assertEqual(res.status_code, 200, res.text)
        self.top.invalidate_recordset()
        self.assertEqual(self.top.name, 'Admin Test Aisle')
        self.assertEqual(self.top.mart_slug, 'admin-test-aisle')
        self.assertEqual(self.top.mart_blurb, 'Still saved')

    def test_a_sub_category_cannot_be_given_its_own_storefront(self):
        """It follows its parent, so storing one would show a storefront this
        category is not in."""
        self.authenticate('admin', 'admin')
        res = self._patch(self.child, {'mart_mode': 'all'})
        self.assertEqual(res.status_code, 400, res.text)
        self.assertIn('top-level', res.json()['error'])
        self.child.invalidate_recordset()
        self.assertNotEqual(self.child.mart_mode, 'all')

    def test_a_colour_has_to_be_a_colour(self):
        """The storefront drops these straight into CSS."""
        self.authenticate('admin', 'admin')
        was = self.top.mart_tone
        for bad in ('red', '#12345', 'javascript:alert(1)', '#ggghhh'):
            res = self._patch(self.top, {'mart_tone': bad})
            self.assertEqual(res.status_code, 400, res.text)
        self.top.invalidate_recordset()
        self.assertEqual(self.top.mart_tone, was)

    def test_an_empty_request_says_so_rather_than_pretending(self):
        self.authenticate('admin', 'admin')
        res = self._patch(self.top, {'name': 'only a refused field'})
        self.assertEqual(res.status_code, 400, res.text)

    def test_a_category_that_is_gone_is_a_404(self):
        self.authenticate('admin', 'admin')
        missing = self.hidden.id
        self.hidden.unlink()
        res = self._send('PATCH', '%s/%s' % (LIST, missing), {'mart_in_app': True})
        self.assertEqual(res.status_code, 404)
