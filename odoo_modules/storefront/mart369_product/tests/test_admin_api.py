"""The staff routes: who may call them, and what they refuse to write.

Two things are pinned here. The first is the fence - a shopper must be
refused on every route, not merely served less. The second is the pair of
rules that hold per-product wording and per-product visibility together: they
live in one row, and each has to survive the other being changed.
"""

import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase

BASE = '/369mart/admin/product'


@tagged('post_install', '-at_install')
class TestProductAdminApi(HttpCase):

    def setUp(self):
        super().setUp()
        self.Field = self.env['mart369.product.field']
        self.Override = self.env['mart369.product.override']

        self.product = self.env['product.template'].create({
            'name': 'Parity Test Widget',
            'is_published': True,
        })
        # One field that may differ per product, and one that may not.
        self.field = self.Field.search([('per_product', '=', True)], limit=1)
        self.fixed = self.Field.search([('per_product', '=', False)], limit=1)
        self.section = self.field.section_id

        self.shopper = self.env['res.users'].create({
            'name': 'Parity Shopper',
            'login': 'mart369_product_shopper',
            'password': 'mart369_product_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    # ------------------------------------------------------------- the fence

    def test_a_shopper_is_refused_every_route(self):
        """Refused, not filtered - on all of them, not most of them."""
        self.authenticate('mart369_product_shopper', 'mart369_product_shopper')
        calls = [
            ('GET', '%s/builder' % BASE),
            ('GET', '%s/products?q=a' % BASE),
            ('GET', '%s/categories' % BASE),
            ('GET', '%s/category-values' % BASE),
            ('PATCH', '%s/sections/%s' % (BASE, self.section.id)),
            ('PATCH', '%s/fields/%s' % (BASE, self.field.id)),
            ('POST', '%s/fields/%s/state' % (BASE, self.field.id)),
            ('PATCH', '%s/fields/%s/value' % (BASE, self.field.id)),
            ('POST', '%s/fields/reset' % BASE),
            ('POST', '%s/category-values' % BASE),
            ('PATCH', '%s/category-values/1' % BASE),
            ('DELETE', '%s/category-values/1' % BASE),
        ]
        for method, path in calls:
            response = self.url_open(
                path, method=method, data='{}',
                headers={'Content-Type': 'application/json'})
            self.assertEqual(response.status_code, 403, path)

    def test_a_designer_is_let_in(self):
        self.authenticate('admin', 'admin')
        body = self._get('%s/builder?product_id=%s' % (BASE, self.product.id))
        self.assertTrue(body['ok'])
        self.assertTrue(body['sections'])
        self.assertEqual(body['product']['id'], self.product.id)

    # -------------------------------------------------------- the whitelists

    def test_the_field_route_will_not_write_the_key(self):
        """The app matches on `key`. Renaming one from a form would stop the
        field appearing on the phone with nothing on screen saying why."""
        self.authenticate('admin', 'admin')
        before = self.field.key
        response = self._patch('%s/fields/%s' % (BASE, self.field.id),
                               {'key': 'hacked'})
        self.assertEqual(response.status_code, 400)
        self.field.invalidate_recordset()
        self.assertEqual(self.field.key, before)

    def test_the_field_route_will_not_repoint_the_odoo_field(self):
        """`odoo_field` is an arbitrary read of any product column."""
        self.authenticate('admin', 'admin')
        before = self.field.odoo_field
        for vals in ({'odoo_field': 'standard_price'}, {'source': 'odoo'}):
            response = self._patch('%s/fields/%s' % (BASE, self.field.id), vals)
            self.assertEqual(response.status_code, 400, vals)
        self.field.invalidate_recordset()
        self.assertEqual(self.field.odoo_field, before)

    def test_the_section_route_will_not_write_the_key(self):
        self.authenticate('admin', 'admin')
        before = self.section.key
        response = self._patch('%s/sections/%s' % (BASE, self.section.id),
                               {'key': 'hacked'})
        self.assertEqual(response.status_code, 400)
        self.section.invalidate_recordset()
        self.assertEqual(self.section.key, before)

    # ----------------------------------------------- what a shopper then sees

    def test_a_section_switch_reaches_the_public_payload(self):
        """The point of the module: the admin API and the shopper's own route
        have to agree about what is on the page."""
        self.authenticate('admin', 'admin')
        key = self.field.key
        self._patch('%s/sections/%s' % (BASE, self.section.id),
                    {'show': False})
        try:
            payload = self.env['mart369.product.page'].payload(self.product)
            self.assertNotIn(key, payload['d'])
        finally:
            self._patch('%s/sections/%s' % (BASE, self.section.id),
                        {'show': True})

    # ------------------------------------------- wording and visibility pair

    def test_setting_wording_does_not_force_the_field_visible(self):
        """Typing words is not the same as deciding to show something."""
        self.authenticate('admin', 'admin')
        was = self.field.show
        self.field.show = False
        try:
            self._patch('%s/fields/%s/value' % (BASE, self.field.id),
                        {'product_id': self.product.id, 'value': 'Only here'})
            row = self._row()
            self.assertEqual(row.state, 'follow')
            self.assertFalse(self.field._visible_for(self.product))
        finally:
            self.field.show = was

    def test_following_again_keeps_the_wording(self):
        self.authenticate('admin', 'admin')
        self._patch('%s/fields/%s/value' % (BASE, self.field.id),
                    {'product_id': self.product.id, 'value': 'Only here'})
        self._post('%s/fields/%s/state' % (BASE, self.field.id),
                   {'product_id': self.product.id, 'state': 'hide'})
        self._post('%s/fields/%s/state' % (BASE, self.field.id),
                   {'product_id': self.product.id, 'state': 'follow'})
        row = self._row()
        self.assertTrue(row, 'The row went, and the wording with it.')
        self.assertEqual(row.value, 'Only here')
        self.assertEqual(row.state, 'follow')

    def test_clearing_the_wording_of_a_following_field_removes_the_row(self):
        """A follow row with nothing in it makes "differs" lie."""
        self.authenticate('admin', 'admin')
        self._patch('%s/fields/%s/value' % (BASE, self.field.id),
                    {'product_id': self.product.id, 'value': 'Only here'})
        self._patch('%s/fields/%s/value' % (BASE, self.field.id),
                    {'product_id': self.product.id, 'value': ''})
        self.assertFalse(self._row())

    def test_clearing_the_wording_keeps_an_explicit_hide(self):
        """The show-or-hide choice is separate from the words."""
        self.authenticate('admin', 'admin')
        self._post('%s/fields/%s/state' % (BASE, self.field.id),
                   {'product_id': self.product.id, 'state': 'hide'})
        self._patch('%s/fields/%s/value' % (BASE, self.field.id),
                    {'product_id': self.product.id, 'value': 'Only here'})
        self._patch('%s/fields/%s/value' % (BASE, self.field.id),
                    {'product_id': self.product.id, 'value': ''})
        row = self._row()
        self.assertTrue(row)
        self.assertEqual(row.state, 'hide')
        self.assertFalse(row.value)

    def test_reset_throws_the_wording_away_too(self):
        self.authenticate('admin', 'admin')
        self._patch('%s/fields/%s/value' % (BASE, self.field.id),
                    {'product_id': self.product.id, 'value': 'Only here'})
        self._post('%s/fields/reset' % BASE,
                   {'product_id': self.product.id,
                    'field_ids': [self.field.id]})
        self.assertFalse(self._row())

    def test_a_field_that_cannot_differ_refuses_wording(self):
        if not self.fixed:
            self.skipTest('No per_product=False field is seeded.')
        self.authenticate('admin', 'admin')
        response = self._patch('%s/fields/%s/value' % (BASE, self.fixed.id),
                               {'product_id': self.product.id, 'value': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.Override.search([
            ('product_tmpl_id', '=', self.product.id),
            ('field_id', '=', self.fixed.id),
        ]))

    def test_an_unknown_state_is_refused_rather_than_crashing(self):
        self.authenticate('admin', 'admin')
        response = self._post('%s/fields/%s/state' % (BASE, self.field.id),
                              {'product_id': self.product.id,
                               'state': 'maybe'})
        self.assertEqual(response.status_code, 400)

    # ------------------------------------------------------ category wording

    def test_a_second_value_for_the_same_category_is_a_conflict(self):
        self.authenticate('admin', 'admin')
        categ = self.env['product.public.category'].create({'name': 'Parity'})
        first = self._post('%s/category-values' % BASE,
                           {'field_id': self.field.id, 'categ_id': categ.id,
                            'value': 'One'})
        self.assertEqual(first.status_code, 201)
        second = self._post('%s/category-values' % BASE,
                            {'field_id': self.field.id, 'categ_id': categ.id,
                             'value': 'Two'})
        self.assertEqual(second.status_code, 409)
        # The refusal carries the row that is already there.
        self.assertTrue(second.json()['id'])

    def test_a_blank_category_value_is_removed_rather_than_stored(self):
        """An empty row beats the shop default, because `_value_for` asks
        whether the field is in the map, not whether it has anything in it."""
        self.authenticate('admin', 'admin')
        categ = self.env['product.public.category'].create({'name': 'Parity2'})
        created = self._post('%s/category-values' % BASE,
                             {'field_id': self.field.id, 'categ_id': categ.id,
                              'value': 'Something'}).json()
        row_id = created['value']['id']
        self._patch('%s/category-values/%s' % (BASE, row_id), {'value': ''})
        self.assertFalse(
            self.env['mart369.product.category.value'].browse(row_id).exists())

    # ------------------------------------------------------------ the search

    def test_search_finds_published_products_only(self):
        self.authenticate('admin', 'admin')
        hidden = self.env['product.template'].create({
            'name': 'Parity Test Hidden', 'is_published': False})
        body = self._get('%s/products?q=Parity Test' % BASE)
        ids = [i['id'] for i in body['items']]
        self.assertIn(self.product.id, ids)
        self.assertNotIn(hidden.id, ids)

    def test_a_blank_search_is_not_an_error(self):
        """The box is debounced, so clearing it fires one last time."""
        self.authenticate('admin', 'admin')
        body = self._get('%s/products?q=' % BASE)
        self.assertTrue(body['ok'])
        self.assertEqual(body['items'], [])

    # ------------------------------------------------------- the drift guard

    def test_the_route_and_the_model_agree(self):
        """The route adds `ok` and nothing else."""
        self.authenticate('admin', 'admin')
        body = self._get('%s/builder?product_id=%s' % (BASE, self.product.id))
        body.pop('ok')
        direct = self.Field.builder_load(self.product.id)
        self.assertEqual(set(body), set(direct))
        self.assertEqual(len(body['sections']), len(direct['sections']))

    def test_the_payload_carries_the_rails(self):
        """Without these the editor has no rails to put a handle on, and
        inventing products on an admin screen is not an option."""
        self.authenticate('admin', 'admin')
        body = self._get('%s/builder?product_id=%s' % (BASE, self.product.id))
        self.assertEqual(set(body['preview']),
                         {'variants', 'bundle', 'similar', 'related'})
        row = body['sections'][0]['rows'][0]
        self.assertLessEqual(
            {'product_value', 'value_source', 'has_override',
             'category_values'}, set(row))

    def test_404s(self):
        self.authenticate('admin', 'admin')
        self.assertEqual(
            self._patch('%s/sections/%s' % (BASE, 10 ** 7), {'show': True})
            .status_code, 404)
        self.assertEqual(
            self._patch('%s/fields/%s' % (BASE, 10 ** 7), {'show': True})
            .status_code, 404)
        self.assertEqual(
            self._patch('%s/category-values/%s' % (BASE, 10 ** 7),
                        {'value': 'x'}).status_code, 404)

    # --------------------------------------------------------------- helpers

    def _row(self):
        return self.Override.search([
            ('product_tmpl_id', '=', self.product.id),
            ('field_id', '=', self.field.id),
        ], limit=1)

    def _send(self, path, method, payload=None):
        return self.url_open(
            path, method=method,
            data=json.dumps(payload or {}),
            headers={'Content-Type': 'application/json'})

    def _get(self, path):
        response = self.url_open(path)
        self.assertEqual(response.status_code, 200, path)
        return response.json()

    def _patch(self, path, payload):
        return self._send(path, 'PATCH', payload)

    def _post(self, path, payload):
        return self._send(path, 'POST', payload)
