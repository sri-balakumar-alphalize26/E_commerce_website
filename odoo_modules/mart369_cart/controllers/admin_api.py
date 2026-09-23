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

from ..models.delivery_slot import KIND_CHOICES, MODE_CHOICES

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
            # Inside a savepoint, and flushed inside it. The flush is so the
            # unique index on `code` fires here rather than after this handler
            # has returned, where the operator would get Odoo's raw integrity
            # error instead of a sentence. The savepoint is so that a refusal
            # actually undoes the write: `create` has already put the row in
            # the transaction by the time the constraint speaks, so catching
            # the error and answering 400 without this told the operator no
            # and kept the value anyway.
            with request.env.cr.savepoint():
                coupon = self._coupons().create(values)
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
            with request.env.cr.savepoint():
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
            with request.env.cr.savepoint():
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
            # Flushed, and inside a savepoint - see `create_coupon`. Without
            # the flush the model's refusal arrives at commit, which is after
            # this handler has answered 201, so the operator is told the deal
            # was created and then it is not.
            with request.env.cr.savepoint():
                deal = self._deals().create(values)
                deal.flush_recordset()
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
            with request.env.cr.savepoint():
                deal.write(values)
                deal.flush_recordset()
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
            with request.env.cr.savepoint():
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
            with request.env.cr.savepoint():
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
            with request.env.cr.savepoint():
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


# ---------------------------------------------------------------- delivery

# What the console may set on a delivery rule. Not `mode`: there is one rule
# per storefront and the unique index says so, so letting a form rewrite it
# turns an edit of the Express fee into a collision with the Quick one.
# Not `carrier_id` either - which Odoo carrier actually ships an order is a
# back-office question, and the screen that answers it is in Odoo.
RULE_WRITABLE = ('label', 'eta', 'min_order', 'free_above', 'fee', 'active')
RULE_NUMBERS = ('min_order', 'free_above', 'fee')

# `key` is absent on purpose: see `_slot_values`.
SLOT_WRITABLE = ('mode', 'kind', 'top', 'sub', 'label', 'from_hour', 'to_hour',
                 'day_offset', 'order_before', 'fee', 'capacity', 'sequence',
                 'active')
SLOT_NUMBERS = ('from_hour', 'to_hour', 'order_before', 'fee')
SLOT_INTS = ('day_offset', 'capacity', 'sequence')

AREA_WRITABLE = ('pincode', 'name', 'eta', 'quick', 'express', 'active')
AREA_BOOLS = ('quick', 'express', 'active')


class Mart369DeliveryAdminApi(Mart369CouponAdminApi):
    """Fees, slots and service areas, for the app's own admin console.

    Subclassed off the coupon controller for its four helpers, not its routes,
    for the reason given on the deal controller: `_json`, `_fail`, `_body` and
    `_may_edit` are the same in every admin controller in the suite, and
    another copy of them is another place for the group check to drift.

    **One GET for all three lists.** The console shows them as three tabs of
    one screen off one poll, and none of the three is long - two rules, a
    handful of slots, however many pincodes a shop actually reaches. Three
    endpoints would mean three round trips and three chances for the tabs to
    disagree about how fresh they are.

    **Nothing here deletes.** A rule, a slot and an area are all pointed at by
    orders that have already gone out, so each is switched off instead. That is
    an ordinary `active` write through the same PATCH, not a route of its own:
    unlike a notice, which is retired as a thing in itself, switching a slot
    off is one more field on the same form.
    """

    # --------------------------------------------------------------- lookups

    def _rules(self):
        """Not sudo'd - on purpose. See the module docstring."""
        return request.env['mart369.delivery.rule'].with_context(active_test=False)

    def _slots(self):
        return request.env['mart369.delivery.slot'].with_context(active_test=False)

    def _areas(self):
        return request.env['mart369.service.area'].with_context(active_test=False)

    def _one(self, records, record_id):
        try:
            return records.browse(int(record_id)).exists()
        except (TypeError, ValueError):
            return records

    # ------------------------------------------------------------- coercion

    def _typed(self, body, allowed, numbers=(), integers=(), booleans=('active',)):
        """The allow-listed fields, read out of the body in the right types.

        Raises ValueError with a field name, so the screen can put the message
        under the control the server is complaining about. Range is not
        checked here - 0 to 24 is the model's rule and it already enforces it
        on every write, including the ones Odoo's own list view makes.
        """
        values = {}
        for field in allowed:
            if field not in body:
                continue
            raw = body[field]
            if field in booleans:
                values[field] = bool(raw)
            elif field in numbers:
                try:
                    values[field] = float(raw or 0.0)
                except (TypeError, ValueError):
                    raise ValueError(field)  # noqa: B904
            elif field in integers:
                try:
                    values[field] = int(raw or 0)
                except (TypeError, ValueError):
                    raise ValueError(field)  # noqa: B904
            else:
                values[field] = (raw or '').strip()
        return values

    def _rule_values(self, body):
        values = self._typed(body, RULE_WRITABLE, numbers=RULE_NUMBERS)
        for field in ('label', 'eta'):
            if field in values and not values[field]:
                raise ValueError(field)
        return values

    def _slot_values(self, body, creating=False):
        values = self._typed(body, SLOT_WRITABLE,
                             numbers=SLOT_NUMBERS, integers=SLOT_INTS)
        if 'mode' in values and values['mode'] not in dict(MODE_CHOICES):
            raise ValueError('mode')
        if 'kind' in values and values['kind'] not in dict(KIND_CHOICES):
            raise ValueError('kind')
        if 'top' in values and not values['top']:
            raise ValueError('top')

        # The key is set once and never rewritten. It is what the app calls
        # the slot in its own state and what `sale.order.mart369_slot_key`
        # stores when somebody books one, so renaming it would quietly orphan
        # every order already out for that window - and the capacity count,
        # which finds those orders by key, would start reading zero.
        if creating:
            key = (body.get('key') or '').strip()
            if not key:
                raise ValueError('key')
            values['key'] = key
            if not values.get('top'):
                raise ValueError('top')
        return values

    def _area_values(self, body, creating=False):
        values = self._typed(body, AREA_WRITABLE, booleans=AREA_BOOLS)
        if 'pincode' in values:
            # Whitespace out first: a pincode pasted from a spreadsheet
            # arrives as '682 016', which is digits with a space in it, and
            # refusing that teaches nobody anything.
            values['pincode'] = ''.join(values['pincode'].split())
            if not values['pincode']:
                raise ValueError('pincode')
        if creating and not values.get('pincode'):
            raise ValueError('pincode')
        return values

    def _why(self, field):
        """What each refusal means, in the operator's words.

        Overrides the coupon controller's, which is right about `code` and
        `title` and knows nothing about hours.
        """
        return {
            'label': 'A storefront needs a name - it is the word on the basket.',
            'eta': 'Write the delivery promise the customer reads.',
            'top': 'A slot needs a heading - it is the bold line on the chip.',
            'key': 'A slot needs a key. Keep it short: now, eve, tm, std.',
            'mode': 'That is not one of the storefronts.',
            'kind': 'That is not a kind of slot.',
            'pincode': 'A pincode is digits only.',
            'from_hour': 'An hour is a number: 18.5 is half past six.',
            'to_hour': 'An hour is a number: 18.5 is half past six.',
            'order_before': 'A cut-off is a number: 17 means five in the afternoon.',
            'fee': 'A fee is a number.',
            'min_order': 'A minimum order is a number.',
            'free_above': 'That is a number - 0 means delivery is never free.',
            'capacity': 'Orders per slot is a whole number. 0 means no limit.',
            'day_offset': 'Days ahead is a whole number. 0 is today.',
        }.get(field, 'That is not a value this field can take.')

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/admin/delivery', **_GET)
    def delivery(self, **kwargs):
        """The three lists, and the words for the two choice rows.

        The choices ship with the list so neither side keeps its own copy of
        what a storefront or a kind of slot is called.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            # The model assembles it, not this. The desk in Odoo calls the
            # same method through the ORM, so the two screens cannot come to
            # different conclusions about what delivery costs.
            payload = self._rules().mart369_admin_list()
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/delivery/rules/<int:rule_id>', **_PATCH)
    def update_rule(self, rule_id, **kwargs):
        """Change what a storefront's delivery costs.

        No create and no delete: there is one rule per storefront, both are
        seeded with the module, and a third would fail the unique index.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        rule = self._one(self._rules(), rule_id)
        if not rule:
            return self._fail('There is no such delivery rule.', status=404)
        try:
            values = self._rule_values(self._body())
        except ValueError as exc:
            return self._fail(self._why(str(exc)), field=str(exc))
        if not values:
            return self._fail('Nothing to change.')
        try:
            # Inside a savepoint, and flushed inside it. The model refuses a
            # negative fee on flush, which is after `write` has already put it
            # in the transaction - so catching that and answering 400 without
            # this would send the operator a refusal and keep the number.
            with request.env.cr.savepoint():
                rule.write(values)
                rule.flush_recordset()
        except (AccessError, UserError, ValidationError) as exc:
            return self._fail(str(exc))
        return self._json({'ok': True, 'rule': rule._mart369_admin_row()})

    @http.route('/369mart/admin/delivery/slots', **_POST)
    def create_slot(self, **kwargs):
        """A new window on the checkout's slot step."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            values = self._slot_values(self._body(), creating=True)
        except ValueError as exc:
            return self._fail(self._why(str(exc)), field=str(exc))
        taken = self._slots().search(
            [('mode', '=', values.get('mode') or 'quick'),
             ('key', '=', values['key'])], limit=1)
        if taken:
            return self._fail(
                'That key is already used by the %s slot %s.'
                % (dict(MODE_CHOICES).get(taken.mode, '').lower(), taken.top),
                field='key', status=409)
        try:
            with request.env.cr.savepoint():
                slot = self._slots().create(values)
                slot.flush_recordset()
        except (AccessError, UserError, ValidationError) as exc:
            return self._fail(str(exc))
        except IntegrityError:
            where = dict(MODE_CHOICES).get(values.get('mode') or 'quick', '')
            return self._fail(
                'That key is already used by another %s slot.' % where.lower(),
                field='key', status=409)
        return self._json({'ok': True, 'slot': slot._mart369_admin_row()}, status=201)

    @http.route('/369mart/admin/delivery/slots/<int:slot_id>', **_PATCH)
    def update_slot(self, slot_id, **kwargs):
        """Change a window, switching it off included."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        slot = self._one(self._slots(), slot_id)
        if not slot:
            return self._fail('There is no such slot.', status=404)
        try:
            values = self._slot_values(self._body())
        except ValueError as exc:
            return self._fail(self._why(str(exc)), field=str(exc))
        if not values:
            return self._fail('Nothing to change.')
        try:
            with request.env.cr.savepoint():
                slot.write(values)
                slot.flush_recordset()
        except (AccessError, UserError, ValidationError) as exc:
            return self._fail(str(exc))
        except IntegrityError:
            # Moving a slot to the other storefront, where its key is taken.
            return self._fail('That key is already used in that storefront.',
                              field='mode', status=409)
        return self._json({'ok': True, 'slot': slot._mart369_admin_row()})

    @http.route('/369mart/admin/delivery/areas', **_POST)
    def create_area(self, **kwargs):
        """Start delivering somewhere."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            values = self._area_values(self._body(), creating=True)
        except ValueError as exc:
            return self._fail(self._why(str(exc)), field=str(exc))
        taken = self._areas().search([('pincode', '=', values['pincode'])], limit=1)
        if taken:
            return self._fail('There is already an area for %s.' % taken.pincode,
                              field='pincode', status=409)
        try:
            with request.env.cr.savepoint():
                area = self._areas().create(values)
                area.flush_recordset()
        except (AccessError, UserError, ValidationError) as exc:
            return self._fail(str(exc))
        except IntegrityError:
            # Two people adding the same pincode between the check and here.
            return self._fail('That pincode has just been added.',
                              field='pincode', status=409)
        return self._json({'ok': True, 'area': area._mart369_admin_row()}, status=201)

    @http.route('/369mart/admin/delivery/areas/<int:area_id>', **_PATCH)
    def update_area(self, area_id, **kwargs):
        """Change an area, or stop delivering to it."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        area = self._one(self._areas(), area_id)
        if not area:
            return self._fail('There is no such service area.', status=404)
        try:
            values = self._area_values(self._body())
        except ValueError as exc:
            return self._fail(self._why(str(exc)), field=str(exc))
        if not values:
            return self._fail('Nothing to change.')
        if values.get('pincode'):
            taken = self._areas().search(
                [('pincode', '=', values['pincode']), ('id', '!=', area.id)], limit=1)
            if taken:
                return self._fail('There is already an area for %s.' % taken.pincode,
                                  field='pincode', status=409)
        try:
            with request.env.cr.savepoint():
                area.write(values)
                area.flush_recordset()
        except (AccessError, UserError, ValidationError) as exc:
            return self._fail(str(exc))
        except IntegrityError:
            return self._fail('That pincode has just been added.',
                              field='pincode', status=409)
        return self._json({'ok': True, 'area': area._mart369_admin_row()})
