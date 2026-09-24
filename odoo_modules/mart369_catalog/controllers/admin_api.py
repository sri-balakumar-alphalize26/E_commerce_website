"""The staff side of searches, for the app's own admin console.

The first admin controller in this module, and it follows the same two rules
as every other one in the suite, for the same reason. Every other route under
/369mart answers "this shopper's own things" and is fenced by the signed-in
partner; nothing here has that fence, so:

* **The group is checked on every route**, first, and somebody who is not
  staff is refused rather than handed an empty list.
* **Nothing is sudo'd.** Records are read and written as the person signed in,
  so Odoo's own access rules do their job rather than being re-implemented
  here badly. The designer group's write on `mart369.search.term` is granted
  in security/ir.model.access.csv, which is why no route here needs to lift
  itself.

There is exactly one thing this controller can write: `trending`. What a term
is, how often it was searched for, how many results it found and when - those
are counts of things that really happened, and a screen that could edit them
could make the catalogue's own gaps disappear by typing over them. The
allow-list is what enforces that rather than a promise in a docstring.
"""

import logging

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'],
        'csrf': False, 'sitemap': False}
_PATCH = {'type': 'http', 'auth': 'user', 'methods': ['PATCH'],
          'csrf': False, 'sitemap': False}
_GET_POST = {'type': 'http', 'auth': 'user', 'methods': ['GET', 'POST'],
             'csrf': False, 'sitemap': False}
_GET_PATCH = {'type': 'http', 'auth': 'user', 'methods': ['GET', 'PATCH'],
              'csrf': False, 'sitemap': False}

EDITOR_GROUP = 'website.group_website_designer'


class Mart369SearchAdminApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _fail(self, error, field=None, status=400):
        payload = {'ok': False, 'error': error}
        if field:
            payload['field'] = field
        return self._json(payload, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:  # noqa: BLE001
            data = None
        return data if isinstance(data, dict) else {}

    def _may_edit(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        return request.env.user.has_group(EDITOR_GROUP)

    def _terms(self):
        """Not sudo'd - on purpose. See the module docstring."""
        return request.env['mart369.search.term']

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/admin/searches', **_GET)
    def searches(self, tab='all', q='', **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        if tab not in self._terms().ADMIN_TABS:
            tab = 'all'
        try:
            payload = self._terms().mart369_admin_list(tab=tab, q=q)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/searches/<int:term_id>', **_PATCH)
    def set_trending(self, term_id, **kwargs):
        """Allow or stop one term as a shopper-facing suggestion.

        The only write in this file. It changes nothing about what was
        searched for - the term keeps being counted either way.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)

        term = self._terms().browse(term_id).exists()
        if not term:
            return self._fail('That search term no longer exists.', status=404)

        trending = self._body().get('trending')
        if not isinstance(trending, bool):
            return self._fail(
                'A term is either allowed in Trending or it is not.',
                field='trending')

        try:
            row = term.mart369_admin_set_trending(trending)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (UserError, ValidationError) as exc:
            return self._fail(str(exc))

        _logger.info('369 Mart: search term %s trending=%s by %s',
                     term.term, trending, request.env.user.login)
        return self._json({'ok': True, 'term': row})

    # --------------------------------------------------------------- products

    @http.route('/369mart/admin/products', **_GET_POST)
    def products(self, tab=None, categ=None, mode=None, q=None, sort=None,
                 limit=None, offset=None, **kwargs):
        """The stock list: one page, the shop's tiles and the filter options.

        GET reads. POST creates a product the way the Odoo Products desk does
        (see `_desk_save`). Stock is still never typed over: a stock change is
        an inventory adjustment, and the desk's allowlist has no stock column.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        if request.httprequest.method == 'POST':
            return self._desk_save(None)
        try:
            payload = request.env['product.template'].mart369_admin_list(
                tab=tab, categ=categ or None, mode=mode, q=q, sort=sort,
                limit=limit or 50, offset=offset or 0)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (UserError, ValueError) as exc:
            return self._fail(str(exc))
        payload['ok'] = True
        return self._json(payload)

    # ------------------------------------------------ the Products desk's editor
    #
    # Thin wrappers over the same ORM methods the Odoo Products desk calls, so
    # the app's console and the backend desk cannot disagree about which boxes
    # exist, what they are called or what may be written. Those methods check
    # the designer group again themselves; the check here refuses a shopper
    # before anything is read.

    def _desk_save(self, product_id):
        body = self._body()
        values = body.get('values')
        photos = body.get('photos') or {}
        if not isinstance(values, dict) or not isinstance(photos, dict):
            return self._fail('Send the product as values and photos.')
        try:
            # A savepoint, because the failure is caught and answered: without
            # one, a photograph that fails after the values were written would
            # still commit those values, and half a save is worse than none.
            with request.env.cr.savepoint():
                new_id = request.env['product.template'].mart369_desk_save(
                    values, product_id=product_id, photos=photos)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (UserError, ValidationError) as exc:
            return self._fail(str(exc))
        except (ValueError, TypeError) as exc:
            return self._fail('Some of the values are not valid: %s' % exc)
        _logger.info('369 Mart: product %s %s by %s', new_id,
                     'updated' if product_id else 'created',
                     request.env.user.login)
        return self._json({'ok': True, 'id': new_id})

    # ------------------------------------------------------------ categories
    # The console's Catalog screen. Its model methods and tests were in place;
    # the two routes were not, so the screen said it could not reach the shop.

    @http.route('/369mart/admin/categories', **_GET_POST)
    def categories(self, tab='all', mode='', q='', **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        if request.httprequest.method == 'POST':
            try:
                row = request.env['product.public.category'].mart369_admin_create(self._body())
            except AccessError as exc:
                return self._fail(str(exc), status=403)
            except (UserError, ValidationError) as exc:
                return self._fail(str(exc))
            return self._json({'ok': True, 'row': row})
        payload = request.env['product.public.category'].mart369_admin_list(
            tab=tab or 'all', mode=mode or '', q=q or '')
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/categories/<int:categ_id>',
                type='http', auth='user', methods=['PATCH', 'PUT'], csrf=False, sitemap=False)
    def category_write(self, categ_id, **kwargs):
        """PATCH: how it looks. PUT: everything, from the Edit button - the
        name and where it sits too (`mart369_admin_edit`)."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        category = request.env['product.public.category'].browse(categ_id).exists()
        if not category:
            return self._fail('That category no longer exists.', status=404)
        try:
            if request.httprequest.method == 'PUT':
                row = category.mart369_admin_edit(self._body())
            else:
                row = category.mart369_admin_write(self._body())
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (UserError, ValidationError) as exc:
            return self._fail(str(exc))
        return self._json({'ok': True, 'row': row})

    @http.route('/369mart/admin/products/form', **_GET)
    def product_form(self, id=None, **kwargs):  # noqa: A002 - the query name
        """The editor's boxes, values and photographs. No id: a blank form."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        product_id = None
        if id:
            try:
                product_id = int(id)
            except ValueError:
                return self._fail('That is not a product.', status=404)
            if not request.env['product.template'].browse(product_id).exists():
                return self._fail('That product no longer exists.', status=404)
        try:
            payload = request.env['product.template'].mart369_desk_form(product_id)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/products/<int:product_id>', **_GET_PATCH)
    def product_one(self, product_id, **kwargs):
        """GET: the detail view - what its page shows, and Odoo's figures.
        PATCH: save the editor."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        product = request.env['product.template'].browse(product_id).exists()
        if not product:
            return self._fail('That product no longer exists.', status=404)
        if request.httprequest.method == 'PATCH':
            return self._desk_save(product_id)
        try:
            page = request.env['mart369.product.field'].mart369_product_page(product_id)
            stats = request.env['product.template'].mart369_product_stats(product_id)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        fields = product._fields
        photos = [{
            'id': image.id,
            'url': '/web/image/product.image/%s/image_512' % image.id,
        } for image in product.product_template_image_ids] \
            if 'product_template_image_ids' in fields else []
        unique = int(product.write_date.timestamp()) if product.write_date else 0
        info = dict(page.get('product') or {})
        info.update({
            'id': product.id,
            'name': info.get('name') or product.display_name,
            'code': product.default_code or '',
            'published': bool(product.is_published),
            'price': product.list_price,
            'mrp': product.compare_list_price if 'compare_list_price' in fields else 0,
            'unit': (product.mart_unit_text or '') if 'mart_unit_text' in fields else '',
            'photo': ('/web/image/product.template/%s/image_512?unique=%s'
                      % (product.id, unique)) if product.image_1920 else '',
            'photos': photos,
        })
        return self._json({
            'ok': True,
            'product': info,
            'sections': page.get('sections') or [],
            'stats': stats or {},
        })
