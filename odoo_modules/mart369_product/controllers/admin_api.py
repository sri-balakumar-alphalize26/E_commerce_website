"""The staff side of the product page, for the app's own admin screens.

The public route next door answers "what does this product page say?" and can
run as the system, because it only ever reads a published product. Nothing
here has that fence, so the same two rules as mart369_home's admin_api apply:

* **The group is checked on every route.** Deciding what the product page
  shows is already `website.group_website_designer` in this module's access
  rules - that is who may switch a field off in Odoo today, so it is who may
  switch one off from the console. No new role invented for the same
  question.
* **Nothing is sudo'd.** Reads and writes run as the person signed in, so
  Odoo's own access rules apply on their own rather than being
  re-implemented here badly. (`builder_load` does sudo internally to build
  the preview card - that is the model's own read, and it predates this
  file.)

Paths stay at five segments or fewer: the storefront proxies these through
/api/mart/<path> and refuses anything longer than six.
"""

import logging

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'],
        'csrf': False, 'sitemap': False}
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'],
         'csrf': False, 'sitemap': False}
_PATCH = {'type': 'http', 'auth': 'user', 'methods': ['PATCH'],
          'csrf': False, 'sitemap': False}
_DELETE = {'type': 'http', 'auth': 'user', 'methods': ['DELETE'],
           'csrf': False, 'sitemap': False}

EDITOR_GROUP = 'website.group_website_designer'


class Mart369ProductAdminApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _fail(self, error, status=400):
        return self._json({'ok': False, 'error': error}, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:  # noqa: BLE001
            data = None
        return data if isinstance(data, dict) else {}

    def _may_edit(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        return request.env.user.has_group(EDITOR_GROUP)

    def _fields(self):
        """Not sudo'd - on purpose. See the module docstring."""
        return request.env['mart369.product.field']

    def _int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _product(self, product_id):
        pid = self._int(product_id)
        if pid is None:
            return None
        return request.env['product.template'].browse(pid).exists()

    # Which fields of a section the console may change. A list rather than
    # "write whatever arrived": `key` is missing on purpose, because the app
    # and the public API match on it, and renaming one from a form stops that
    # band appearing on the phone with nothing on screen saying why.
    SECTION_FIELDS = ('name', 'sequence', 'show', 'note', 'active')

    # Same for a field, and three more exclusions worth naming:
    #
    # `key`        - as above; `_key_uniq` would turn a typo into a 500.
    # `source`     - switching text -> odoo silently blanks every default
    #                anybody typed, because `_value_for` never reaches
    #                `default_value` once the source is odoo. A data-model
    #                decision, not page configuration.
    # `odoo_field` - free text that `_value_for` uses to index the product.
    #                An unknown name is guarded to '' rather than crashing,
    #                so a mistake here quietly empties the field for the
    #                whole shop. It is also an arbitrary read of any
    #                product.template column, and standard_price is one.
    # `section_id` - moving a field between bands reorders two pages at once
    #                and orphans two stored related fields.
    FIELD_FIELDS = ('name', 'sequence', 'show', 'default_value',
                    'value_kind', 'per_product', 'note', 'active')

    BOOLS = ('show', 'active', 'per_product')

    def _clean(self, body, allowed, record):
        """The body, reduced to what may be written and typed as the model
        wants it. An unknown key is dropped; a body with nothing left is an
        error, because a form that silently does nothing is worse than one
        that says no."""
        vals = {}
        for key, value in body.items():
            if key not in allowed:
                continue
            if key in self.BOOLS:
                vals[key] = bool(value)
            elif key == 'sequence':
                number = self._int(value)
                if number is None:
                    raise ValueError(request.env._('That is not a number.'))
                vals[key] = number
            elif key == 'value_kind':
                kinds = dict(record._fields['value_kind'].selection)
                if value not in kinds:
                    raise ValueError(
                        request.env._('There is no such kind of value.'))
                vals[key] = value
            else:
                vals[key] = (value or '').strip()
        return vals

    def _row(self, field, product=None):
        """Every route that returns one row goes through the model, so a row
        written here and a row loaded by the builder cannot disagree."""
        return field._builder_row(product) if product else field._builder_row()

    def _serialize_section(self, section):
        return {
            'id': section.id, 'key': section.key, 'name': section.name,
            'sequence': section.sequence, 'show': section.show,
            'note': section.note or '', 'field_count': section.field_count,
            'active': section.active,
        }

    def _serialize_catval(self, row):
        return {
            'id': row.id,
            'field_id': row.field_id.id,
            'field_key': row.field_id.key,
            'categ_id': row.public_categ_id.id,
            'categ_name': row.public_categ_id.display_name,
            'value': row.value or '',
        }

    # ----------------------------------------------------------- the builder

    @http.route('/369mart/admin/product/builder', **_GET)
    def builder(self, product_id=None, **kwargs):
        """Everything the Product page screen draws from.

        `builder_load` already assembles exactly this for Odoo's own builder,
        so this route resolves the product and hands that back rather than
        growing a second, drifting copy of it.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        pid = None
        if product_id not in (None, '', 'null'):
            pid = self._int(product_id)
            if pid is None:
                return self._fail('That is not a product.', status=400)
        try:
            data = self._fields().builder_load(pid)
        except (AccessError, UserError) as exc:
            return self._fail(str(exc), status=400)
        data['ok'] = True
        return self._json(data)

    @http.route('/369mart/admin/product/products', **_GET)
    def products(self, q='', limit='20', **kwargs):
        """The toolbar's product search.

        A blank query answers with an empty list rather than an error: the box
        is debounced, so clearing it fires one last time.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        term = (q or '').strip()
        if not term:
            return self._json({'ok': True, 'items': []})
        count = min(self._int(limit) or 20, 50)
        found = request.env['product.template'].search([
            ('is_published', '=', True), ('name', 'ilike', term),
        ], limit=count, order='name')
        return self._json({'ok': True, 'items': [
            {'id': p.id, 'name': p.display_name, 'ref': p.default_code or ''}
            for p in found
        ]})

    @http.route('/369mart/admin/product/categories', **_GET)
    def categories(self, q='', **kwargs):
        """Shop categories, for the per-category wording picker."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        domain = []
        term = (q or '').strip()
        if term:
            domain = [('name', 'ilike', term)]
        found = request.env['product.public.category'].search(
            domain, limit=50, order='name')
        return self._json({'ok': True, 'categories': [
            {'id': c.id, 'name': c.display_name} for c in found
        ]})

    # -------------------------------------------------------- the whole shop

    @http.route('/369mart/admin/product/sections/<int:section_id>', **_PATCH)
    def update_section(self, section_id, **kwargs):
        """A section is a master switch: off hides the band and every field in
        it, whatever those fields say."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        section = request.env['mart369.product.section'].browse(
            section_id).exists()
        if not section:
            return self._fail('No such section.', status=404)
        try:
            vals = self._clean(self._body(), self.SECTION_FIELDS, section)
        except ValueError as exc:
            return self._fail(str(exc), status=400)
        if not vals:
            return self._fail('Nothing to change.', status=400)
        try:
            section.write(vals)
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc), status=400)
        return self._json({'ok': True,
                           'section': self._serialize_section(section)})

    @http.route('/369mart/admin/product/fields/<int:field_id>', **_PATCH)
    def update_field(self, field_id, **kwargs):
        """The shop-wide switch, and the shop's own default wording."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        field = self._fields().browse(field_id).exists()
        if not field:
            return self._fail('No such field.', status=404)
        try:
            vals = self._clean(self._body(), self.FIELD_FIELDS, field)
        except ValueError as exc:
            return self._fail(str(exc), status=400)
        if not vals:
            return self._fail('Nothing to change.', status=400)
        try:
            field.write(vals)
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc), status=400)
        return self._json({'ok': True, 'field': self._row(field)})

    # ----------------------------------------------------------- one product

    @http.route('/369mart/admin/product/fields/<int:field_id>/state', **_POST)
    def set_state(self, field_id, **kwargs):
        """Follow the shop default, always show, or always hide - here only."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        field = self._fields().browse(field_id).exists()
        if not field:
            return self._fail('No such field.', status=404)
        body = self._body()
        product = self._product(body.get('product_id'))
        if not product:
            return self._fail('No such product.', status=404)
        try:
            self._fields().set_product_state(
                field.id, product.id, body.get('state'))
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc), status=400)
        return self._json({'ok': True, 'row': self._row(field, product)})

    @http.route('/369mart/admin/product/fields/<int:field_id>/value', **_PATCH)
    def set_value(self, field_id, **kwargs):
        """Wording for one product. Clearing it means "use the default"."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        field = self._fields().browse(field_id).exists()
        if not field:
            return self._fail('No such field.', status=404)
        body = self._body()
        product = self._product(body.get('product_id'))
        if not product:
            return self._fail('No such product.', status=404)
        try:
            self._fields().set_product_value(
                field.id, product.id, body.get('value'))
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc), status=400)
        return self._json({'ok': True, 'row': self._row(field, product)})

    @http.route('/369mart/admin/product/fields/reset', **_POST)
    def reset(self, **kwargs):
        """Put fields back to following the shop default.

        This throws away the per-product wording as well as the show-or-hide
        choice - they live in the same row. The console says so before asking.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        body = self._body()
        product = self._product(body.get('product_id'))
        if not product:
            return self._fail('No such product.', status=404)
        raw = body.get('field_ids') or []
        if not isinstance(raw, list):
            return self._fail('That is not a list of fields.', status=400)
        ids = [i for i in (self._int(v) for v in raw) if i is not None]
        fields_hit = self._fields().browse(ids).exists()
        try:
            self._fields().reset_product_state(fields_hit.ids, product.id)
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc), status=400)
        return self._json({'ok': True, 'rows': [
            self._row(f, product) for f in fields_hit
        ]})

    # ---------------------------------------------------------- one category

    @http.route('/369mart/admin/product/category-values', **_GET)
    def category_values(self, field_id=None, categ_id=None, **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        domain = []
        if field_id:
            domain.append(('field_id', '=', self._int(field_id) or 0))
        if categ_id:
            domain.append(('public_categ_id', '=', self._int(categ_id) or 0))
        rows = request.env['mart369.product.category.value'].search(domain)
        return self._json({'ok': True, 'values': [
            self._serialize_catval(r) for r in rows
        ]})

    @http.route('/369mart/admin/product/category-values', **_POST)
    def create_category_value(self, **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        body = self._body()
        field = self._fields().browse(
            self._int(body.get('field_id')) or 0).exists()
        categ = request.env['product.public.category'].browse(
            self._int(body.get('categ_id')) or 0).exists()
        if not field or not categ:
            return self._fail('No such field or category.', status=404)
        Value = request.env['mart369.product.category.value']
        existing = Value.search([
            ('field_id', '=', field.id), ('public_categ_id', '=', categ.id),
        ], limit=1)
        if existing:
            # The id goes back with the refusal, so the console can change the
            # row that is already there instead of asking somebody to find it.
            return self._json({
                'ok': False,
                'error': 'That category already has wording for this field.',
                'id': existing.id,
            }, status=409)
        try:
            row = Value.create({
                'field_id': field.id, 'public_categ_id': categ.id,
                'value': (body.get('value') or '').strip(),
            })
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc), status=400)
        return self._json({'ok': True, 'value': self._serialize_catval(row)},
                          status=201)

    @http.route('/369mart/admin/product/category-values/<int:value_id>',
                **_PATCH)
    def update_category_value(self, value_id, **kwargs):
        """Clearing the box removes the row - see `set_value` on the model."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        row = request.env['mart369.product.category.value'].browse(
            value_id).exists()
        if not row:
            return self._fail('No such wording.', status=404)
        body = self._body()
        if 'value' not in body:
            return self._fail('Nothing to change.', status=400)
        try:
            kept = row.set_value(body.get('value'))
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc), status=400)
        if not kept:
            return self._json({'ok': True, 'id': str(value_id),
                               'removed': True})
        return self._json({'ok': True, 'value': self._serialize_catval(row)})

    @http.route('/369mart/admin/product/category-values/<int:value_id>',
                **_DELETE)
    def delete_category_value(self, value_id, **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        row = request.env['mart369.product.category.value'].browse(
            value_id).exists()
        if not row:
            return self._fail('No such wording.', status=404)
        try:
            row.unlink()
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc), status=400)
        return self._json({'ok': True, 'id': str(value_id)})
