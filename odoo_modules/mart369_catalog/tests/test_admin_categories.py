"""The staff side of the catalog, over HTTP.

What is worth pinning here is mostly what this screen **cannot** do.

**The name and the app address are not editable.** The name is Odoo's own
field, leaned on by the catalogue, the product pages and every report; the
address is a URL a customer may have saved, and changing it breaks that link
silently. A request carrying either must change neither.

**A category has no storefront.** Quick or Express is decided per item, by
the customer's distance to the branch holding the stock - so a request that
still carries one changes nothing.

**A new category needs a name**, and can be put under another one.

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

    def test_a_row_has_no_storefront(self):
        self.authenticate('admin', 'admin')
        __, payload = self._rows()
        child = self._row_for(payload, self.child)
        self.assertNotIn('mode', child)
        self.assertFalse(child['topLevel'])
        self.assertEqual(child['parentId'], self.top.id)
        # Drawn in its main category's colours, so the preview needs them.
        self.assertEqual(child['parentTone'], self.top.mart_tone)
        self.assertEqual(child['parentAccent'], self.top.mart_accent)

    def test_an_old_storefront_filter_is_ignored(self):
        """A caller still sending `mode` gets every category, not none."""
        self.authenticate('admin', 'admin')
        __, everything = self._rows()
        __, with_mode = self._rows(mode='all')
        self.assertEqual(len(with_mode['rows']), len(everything['rows']))

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

    def test_the_line_under_the_title_has_its_own_colour(self):
        self.authenticate('admin', 'admin')
        res = self._patch(self.child, {'mart_blurb_color': '#A32020'})
        self.assertEqual(res.status_code, 200, res.text)
        self.child.invalidate_recordset()
        self.assertEqual(self.child.mart_blurb_color, '#a32020')

        res = self._patch(self.child, {'mart_blurb_color': 'grey'})
        self.assertEqual(res.status_code, 400, res.text)

        # Empty is the way back to the default, not an error.
        res = self._patch(self.child, {'mart_blurb_color': ''})
        self.assertEqual(res.status_code, 200, res.text)
        self.child.invalidate_recordset()
        self.assertFalse(self.child.mart_blurb_color)

    def test_a_row_carries_both_line_colours(self):
        self.top.mart_blurb_color = '#1f7a4c'
        self.authenticate('admin', 'admin')
        __, payload = self._rows()
        self.assertEqual(self._row_for(payload, self.top)['blurbColor'], '#1f7a4c')
        child = self._row_for(payload, self.child)
        self.assertEqual(child['blurbColor'], '')
        self.assertEqual(child['parentBlurbColor'], '#1f7a4c')

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

    def test_a_storefront_can_no_longer_be_written(self):
        """The field is gone; sending it is a request with nothing in it."""
        self.authenticate('admin', 'admin')
        res = self._patch(self.child, {'mart_mode': 'all'})
        self.assertEqual(res.status_code, 400, res.text)
        self.assertNotIn('mart_mode', self.env['product.public.category']._fields)

    # ------------------------------------------------------------- creating

    def test_a_new_category_from_the_desk(self):
        Category = self.env['product.public.category']
        row = Category.mart369_admin_create({
            'name': '  Admin Test New  ', 'parent_id': self.top.id,
            'mart_blurb': 'Fresh in', 'mart_tone': '#E8F5E9'})
        made = Category.browse(row['id'])
        self.assertEqual(made.name, 'Admin Test New')
        self.assertEqual(made.parent_id, self.top)
        self.assertEqual(made.mart_tone, '#e8f5e9')
        self.assertTrue(made.mart_slug, 'the app address is made from the name')

    def test_a_new_sub_category_starts_in_its_main_categorys_colours(self):
        self.top.write({'mart_tone': '#e8f5e9', 'mart_accent': '#1f7a4c'})
        Category = self.env['product.public.category']
        plain = Category.browse(Category.mart369_admin_create(
            {'name': 'Admin Test Plain Sub', 'parent_id': self.top.id})['id'])
        self.assertEqual((plain.mart_tone, plain.mart_accent), ('#e8f5e9', '#1f7a4c'))

    def test_a_sub_category_keeps_the_colours_picked_for_it(self):
        Category = self.env['product.public.category']
        own = Category.browse(Category.mart369_admin_create({
            'name': 'Admin Test Own Sub', 'parent_id': self.top.id,
            'mart_tone': '#FDECEC', 'mart_accent': '#a32020'})['id'])
        self.assertEqual((own.mart_tone, own.mart_accent), ('#fdecec', '#a32020'))
        # And the app is sent them, on the sub-category itself.
        node = own._mart369_serialize(with_subs=False)
        self.assertEqual((node['tone'], node['accent']), ('#fdecec', '#a32020'))

    def test_a_new_category_needs_a_name(self):
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            self.env['product.public.category'].mart369_admin_create({'name': '   '})

    def test_a_new_category_cannot_go_under_a_sub_category(self):
        """The app shows two levels; a third would have no page of its own."""
        from odoo.exceptions import UserError
        with self.assertRaisesRegex(UserError, 'main category'):
            self.env['product.public.category'].mart369_admin_create(
                {'name': 'Admin Test Too Deep', 'parent_id': self.child.id})

    def test_a_new_category_takes_only_the_allowed_fields(self):
        row = self.env['product.public.category'].mart369_admin_create({
            'name': 'Admin Test Allow', 'mart_slug': 'sneaky-address', 'sequence': 999})
        made = self.env['product.public.category'].browse(row['id'])
        self.assertNotEqual(made.mart_slug, 'sneaky-address')
        self.assertNotEqual(made.sequence, 999)

    # -------------------------------------------------------------- editing

    def test_edit_renames_but_keeps_the_app_address(self):
        """A customer may have saved the link, so the address stays."""
        self.child.mart369_admin_edit({'name': '  Admin Test Renamed  '})
        self.assertEqual(self.child.name, 'Admin Test Renamed')
        self.assertEqual(self.child.mart_slug, 'admin-test-shelf')

    def test_edit_needs_a_name(self):
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            self.child.mart369_admin_edit({'name': '  '})

    def test_edit_saves_the_look_too(self):
        self.child.mart369_admin_edit({
            'mart_blurb': 'Thin and light', 'mart_blurb_color': '#A32020',
            'mart_tone': '#fdecec', 'mart_accent': '#a32020'})
        self.assertEqual(self.child.mart_blurb, 'Thin and light')
        self.assertEqual(self.child.mart_blurb_color, '#a32020')
        self.assertEqual((self.child.mart_tone, self.child.mart_accent), ('#fdecec', '#a32020'))

    def test_a_sub_category_can_become_a_main_category(self):
        tone = self.child.mart_tone
        self.child.mart369_admin_edit({'parent_id': False})
        self.assertFalse(self.child.parent_id)
        self.assertEqual(self.child.mart_tone, tone, 'it keeps its colours')

    def test_a_main_category_without_subs_can_become_a_sub_category(self):
        self.hidden.mart369_admin_edit({'parent_id': self.top.id})
        self.assertEqual(self.hidden.parent_id, self.top)

    def test_edit_keeps_two_levels(self):
        from odoo.exceptions import UserError
        # Not under a sub-category.
        with self.assertRaisesRegex(UserError, 'main category'):
            self.hidden.mart369_admin_edit({'parent_id': self.child.id})
        # Not under itself.
        with self.assertRaisesRegex(UserError, 'itself'):
            self.hidden.mart369_admin_edit({'parent_id': self.hidden.id})
        # A main category with sub-categories stays a main category.
        with self.assertRaisesRegex(UserError, 'has sub-categories'):
            self.top.mart369_admin_edit({'parent_id': self.hidden.id})
        self.assertFalse(self.top.parent_id)

    def test_the_web_console_still_cannot_rename(self):
        """Edit is the desk's; the console's PATCH route refuses the name."""
        self.authenticate('admin', 'admin')
        self._patch(self.child, {'name': 'Renamed by the console', 'mart_blurb': 'x'})
        self.child.invalidate_recordset()
        self.assertEqual(self.child.name, 'Admin Test Shelf')

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
