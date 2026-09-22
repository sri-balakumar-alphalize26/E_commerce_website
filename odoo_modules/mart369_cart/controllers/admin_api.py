"""The staff side of coupons, for the app's own admin console.

Same two rules as every other admin controller in the suite, for the same
reason. Every other route under /369mart answers "this shopper's own things"
and is fenced by the signed-in partner; nothing here has that fence, so:

* **The group is checked on every route**, first, and somebody who is not
  staff is refused rather than handed an empty list.
* **Nothing is sudo'd.** Records are read and written as the person signed in,
  so Odoo's own access rules do their job rather than being re-implemented
  here badly.

What a coupon is worth is not decided here. `_mart369_discount` on the model
is the only arithmetic, and the cart and the order both call it - this
controller moves JSON and nothing else.
"""

import logging

from psycopg2 import IntegrityError

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
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

# What the console may set. A list rather than "write whatever arrived":
# `used_count` is the order flow's to keep, and a form that can write any
# field can quietly reset it and hand a spent code back to everybody.
WRITABLE = (
    'code', 'title', 'note', 'kind', 'value', 'max_off', 'min_spend',
    'group', 'active', 'starts_on', 'ends_on', 'limit_total',
    'limit_per_customer', 'sequence',
)
TEXT_FIELDS = ('code', 'title', 'note', 'group')
NUMBER_FIELDS = ('value', 'max_off', 'min_spend')
INT_FIELDS = ('limit_total', 'limit_per_customer', 'sequence')
DATE_FIELDS = ('starts_on', 'ends_on')


class Mart369CouponAdminApi(http.Controller):

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

    def _coupons(self):
        """Not sudo'd - on purpose. See the module docstring."""
        return request.env['mart369.coupon'].with_context(active_test=False)

    def _coupon(self, coupon_id):
        try:
            return self._coupons().browse(int(coupon_id)).exists()
        except (TypeError, ValueError):
            return self._coupons()

    def _values(self, body, creating=False):
        """The allow-listed fields, read out of the body in the right types.

        Raises ValueError with a field name so the screen can put the message
        under the control the server is complaining about.
        """
        values = {}
        for field in WRITABLE:
            if field not in body:
                continue
            raw = body[field]
            if field == 'active':
                values[field] = bool(raw)
            elif field in DATE_FIELDS:
                values[field] = (raw or '').strip()[:10] or False
            elif field in INT_FIELDS:
                values[field] = int(raw or 0)
            elif field in NUMBER_FIELDS:
                values[field] = float(raw or 0.0)
            else:
                values[field] = (raw or '').strip()

        if creating:
            for field in ('code', 'title'):
                if not values.get(field):
                    raise ValueError(field)
        for field in ('code', 'title'):
            if field in values and not values[field]:
                raise ValueError(field)

        starts = values.get('starts_on') or None
        ends = values.get('ends_on') or None
        if starts and ends and starts > ends:
            raise ValueError('ends_on')
        return values

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/admin/coupons', **_GET)
    def coupons(self, **kwargs):
        """Every coupon, and the numbers above them."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            payload = self._coupons().mart369_admin_list()
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/coupons', **_POST)
    def create_coupon(self, **kwargs):
        """A new code."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            values = self._values(self._body(), creating=True)
        except ValueError as exc:
            return self._fail(self._why(str(exc)), field=str(exc))
        taken = self._coupons().search(
            [('code', '=', values['code'].upper())], limit=1)
        if taken:
            return self._fail(
                'There is already a coupon with the code %s.' % taken.code,
                field='code', status=409)
        try:
            coupon = self._coupons().create(values)
            # Flushed here on purpose. Without it the unique index on `code`
            # fires after this handler has returned, and the operator gets
            # Odoo's raw integrity error instead of a sentence.
            coupon.flush_recordset()
        except (AccessError, UserError, ValidationError) as exc:
            # The model refuses a nonsense percentage in its own words - it
            # knows why better than this does.
            return self._fail(str(exc))
        except IntegrityError:
            # Two people naming the same code between the check above and
            # here. Rare, and the same answer.
            return self._fail('That code has just been taken.',
                              field='code', status=409)
        return self._json(
            {'ok': True, 'coupon': coupon._mart369_admin_serialize()}, status=201)

    @http.route('/369mart/admin/coupons/<int:coupon_id>', **_PATCH)
    def update_coupon(self, coupon_id, **kwargs):
        """Change one, switching it on and off included."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        coupon = self._coupon(coupon_id)
        if not coupon:
            return self._fail('There is no such coupon.', status=404)
        try:
            values = self._values(self._body())
        except ValueError as exc:
            return self._fail(self._why(str(exc)), field=str(exc))
        if not values:
            return self._fail('Nothing to change.')
        if values.get('code'):
            taken = self._coupons().search(
                [('code', '=', values['code'].upper()), ('id', '!=', coupon.id)],
                limit=1)
            if taken:
                return self._fail(
                    'There is already a coupon with the code %s.' % taken.code,
                    field='code', status=409)
        try:
            coupon.write(values)
            coupon.flush_recordset()
        except (AccessError, UserError, ValidationError) as exc:
            return self._fail(str(exc))
        except IntegrityError:
            return self._fail('That code has just been taken.',
                              field='code', status=409)
        return self._json({'ok': True, 'coupon': coupon._mart369_admin_serialize()})

    @http.route('/369mart/admin/coupons/<int:coupon_id>', **_DELETE)
    def delete_coupon(self, coupon_id, **kwargs):
        """Gone for good.

        No Trash here, unlike home pages: a coupon somebody has used is
        pointed at by the orders that used it, so the database refuses to
        delete it anyway and the honest answer is to switch it off instead.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        coupon = self._coupon(coupon_id)
        if not coupon:
            return self._fail('There is no such coupon.', status=404)
        if coupon.used_count:
            return self._fail(
                'This code has been used %s times, so it belongs to those '
                'orders now. Switch it off instead.' % coupon.used_count,
                status=409)
        try:
            coupon.unlink()
        except (AccessError, UserError) as exc:
            return self._fail(str(exc), status=409)
        return self._json({'ok': True})

    # ---------------------------------------------------------------- saying

    def _why(self, field):
        return {
            'code': 'A coupon needs a code.',
            'title': 'A coupon needs a title - it is what the customer reads.',
            'ends_on': 'The end date is before the start date.',
        }.get(field, 'That is not a value this field can take.')

# What the console may set on a deal. `product_ids` is handled apart because
# it arrives as a list of ids, not a scalar.
DEAL_WRITABLE = ('name', 'note', 'kind', 'value', 'floor', 'active',
                 'starts_on', 'ends_on', 'sequence')
DEAL_NUMBERS = ('value', 'floor')
DEAL_DATETIMES = ('starts_on', 'ends_on')


class Mart369DealAdminApi(Mart369CouponAdminApi):
    """Deals - a price cut on chosen products, for a window.

    Subclassed off the coupon controller for its helpers, not for its routes:
    `_json`, `_fail`, `_body` and `_may_edit` are the same four in every admin
    controller in the suite, and a third copy of them is a third place for the
    group check to drift.
    """

    def _deals(self):
        return request.env['mart369.deal'].with_context(active_test=False)

    def _deal(self, deal_id):
        try:
            return self._deals().browse(int(deal_id)).exists()
        except (TypeError, ValueError):
            return self._deals()

    def _deal_values(self, body, creating=False):
        values = {}
        for field in DEAL_WRITABLE:
            if field not in body:
                continue
            raw = body[field]
            if field == 'active':
                values[field] = bool(raw)
            elif field in DEAL_DATETIMES:
                values[field] = (raw or '').strip()[:19].replace('T', ' ') or False
            elif field in DEAL_NUMBERS:
                values[field] = float(raw or 0.0)
            elif field == 'sequence':
                values[field] = int(raw or 0)
            else:
                values[field] = (raw or '').strip()

        if 'product_ids' in body:
            ids = [int(i) for i in (body.get('product_ids') or [])]
            values['product_ids'] = [(6, 0, ids)]

        if creating and not values.get('name'):
            raise ValueError('name')
        if 'name' in values and not values['name']:
            raise ValueError('name')
        if creating and not values.get('product_ids', [(6, 0, [])])[0][2]:
            raise ValueError('product_ids')

        starts = values.get('starts_on') or None
        ends = values.get('ends_on') or None
        if starts and ends and starts > ends:
            raise ValueError('ends_on')
        return values

    def _deal_why(self, field):
        return {
            'name': 'A deal needs a name - it is how you find it later.',
            'product_ids': 'Pick at least one product to put on offer.',
            'ends_on': 'The end date is before the start date.',
        }.get(field, 'That is not a value this field can take.')

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/admin/deals', **_GET)
    def deals(self, **kwargs):
        """Every deal, and the numbers above them."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            payload = self._deals().mart369_admin_list()
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/deals', **_POST)
    def create_deal(self, **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            values = self._deal_values(self._body(), creating=True)
        except (ValueError, TypeError) as exc:
            field = str(exc) if isinstance(exc, ValueError) else 'product_ids'
            return self._fail(self._deal_why(field), field=field)
        try:
            deal = self._deals().create(values)
        except (AccessError, UserError, ValidationError) as exc:
            # The model refuses a percentage over 90 in its own words.
            return self._fail(str(exc))
        return self._json(
            {'ok': True, 'deal': deal._mart369_admin_serialize()}, status=201)

    @http.route('/369mart/admin/deals/<int:deal_id>', **_PATCH)
    def update_deal(self, deal_id, **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        deal = self._deal(deal_id)
        if not deal:
            return self._fail('There is no such deal.', status=404)
        try:
            values = self._deal_values(self._body())
        except (ValueError, TypeError) as exc:
            field = str(exc) if isinstance(exc, ValueError) else 'product_ids'
            return self._fail(self._deal_why(field), field=field)
        if not values:
            return self._fail('Nothing to change.')
        try:
            deal.write(values)
        except (AccessError, UserError, ValidationError) as exc:
            return self._fail(str(exc))
        return self._json({'ok': True, 'deal': deal._mart369_admin_serialize()})

    @http.route('/369mart/admin/deals/<int:deal_id>', **_DELETE)
    def delete_deal(self, deal_id, **kwargs):
        """Move a deal to the Trash.

        A deal is a list of products somebody picked and a window somebody
        worked out, and the button that removes it sits next to Switch off -
        so it waits rather than going. It stops discounting the moment it is
        trashed; only the record survives.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        deal = self._deal(deal_id)
        if not deal:
            return self._fail('There is no such deal.', status=404)
        try:
            deal.action_trash()
        except (AccessError, UserError) as exc:
            return self._fail(str(exc), status=409)
        return self._json({'ok': True, 'deal': deal._mart369_admin_serialize()})

    @http.route('/369mart/admin/deals/<int:deal_id>/restore', **_POST)
    def restore_deal(self, deal_id, **kwargs):
        """Out of the Trash, exactly as it went in - switched off included."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        deal = self._deal(deal_id)
        if not deal:
            return self._fail('There is no such deal.', status=404)
        try:
            deal.action_restore()
        except (AccessError, UserError) as exc:
            return self._fail(str(exc), status=409)
        return self._json({'ok': True, 'deal': deal._mart369_admin_serialize()})

    @http.route('/369mart/admin/deals/<int:deal_id>/forever', **_DELETE)
    def delete_deal_forever(self, deal_id, **kwargs):
        """Gone now rather than in thirty days.

        Only from the Trash, so nothing is destroyed without having been
        visible there first. Safe in a way a coupon is not: a deal is never
        pointed at by an order - the price it produced was frozen onto the
        line when the order was placed, so this cannot rewrite history.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        deal = self._deal(deal_id)
        if not deal:
            return self._fail('There is no such deal.', status=404)
        if not deal.deleted_at:
            return self._fail('Put it in the Trash first.', status=409)
        try:
            deal.unlink()
        except (AccessError, UserError) as exc:
            return self._fail(str(exc), status=409)
        return self._json({'ok': True})

    @http.route('/369mart/admin/deals/products', **_GET)
    def deal_products(self, q=None, **kwargs):
        """Products to pick from, for the deal form's search box."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        term = (q or '').strip()
        domain = [('is_published', '=', True)]
        if term:
            domain += [('name', 'ilike', term)]
        found = request.env['product.template'].search(
            domain, limit=20, order='name')
        return self._json({
            'ok': True,
            'products': [{'id': t.id, 'name': t.name, 'price': t.list_price}
                         for t in found],
        })
