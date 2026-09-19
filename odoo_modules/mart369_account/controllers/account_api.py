"""The account routes.

Same shape as every other 369 Mart controller: type='http' answering bare JSON,
called by the storefront's own server, failures as {ok: false, error, field?}.

Everything here is one customer's own data, so every route resolves through
`_me()` and nothing takes an id that is not checked against it. A review, an
invite, a scratch card and a wishlist row are all found *within* the signed-in
customer's records rather than found and then checked - so a guessed id is
simply not there, and answers 404 rather than confirming it exists.
"""

import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'], 'csrf': False, 'sitemap': False}
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'], 'csrf': False, 'sitemap': False}
_PATCH = {'type': 'http', 'auth': 'user', 'methods': ['PATCH'], 'csrf': False, 'sitemap': False}
_DELETE = {'type': 'http', 'auth': 'user', 'methods': ['DELETE'], 'csrf': False, 'sitemap': False}


class Mart369AccountApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:
            data = None
        return data if isinstance(data, dict) else {}

    def _fail(self, error, field=None, status=400):
        payload = {'ok': False, 'error': error}
        if field:
            payload['field'] = field
        return self._json(payload, status=status)

    def _me(self):
        return request.env.user.partner_id

    def _website(self):
        """The shop a wishlist row belongs to.

        `product.wishlist.website_id` is required, and these routes are not
        website routes - there is no `request.website` to inherit one from, so
        `get_current_website()` is asked and the only website there is serves
        as the answer when it cannot say. Without this the insert fails on a
        not-null constraint, which is a 422 the storefront can do nothing with.
        """
        Website = request.env['website'].sudo()
        try:
            website = Website.get_current_website()
        except Exception:
            website = Website.browse()
        return website or Website.search([], limit=1)

    def _product(self, product_id):
        """A published product, or nothing."""
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return request.env['product.template'].browse()
        product = request.env['product.template'].sudo().browse(product_id).exists()
        if not product or not product.is_published:
            return request.env['product.template'].browse()
        return product

    # --------------------------------------------------------------- profile

    @http.route('/369mart/profile', **_PATCH)
    def save_profile(self, **kwargs):
        """The write the app never had.

        `onSave` is synchronous and the screen says "Saved" before this answers,
        with no error path at all - so a refusal has to be a real HTTP failure
        the caller can notice, rather than an ok body nobody reads.
        """
        ok, error = self._me()._mart369_write_profile(self._body())
        if not ok:
            message, field = error
            status = 409 if field == 'email' else 400
            return self._fail(message, field, status=status)
        return self._json(request.env.user._mart369_profile())

    # --------------------------------------------------------------- reviews

    @http.route('/369mart/reviews', **_GET)
    def reviews(self, **kwargs):
        """Every review this customer has written, keyed by product id.

        A map rather than a list because that is what the app holds: it reads
        `myReviews[p.id]`, which is also why there can only ever be one review
        per product.
        """
        rows = request.env['rating.rating'].sudo().search([
            ('res_model', '=', 'product.template'),
            ('partner_id', '=', self._me().id),
            ('consumed', '=', True),
        ])
        return self._json({
            'ok': True,
            'reviews': {str(row.res_id): row._mart369_serialize() for row in rows},
        })

    @http.route('/369mart/reviews/<int:product_id>', **_POST)
    def write_review(self, product_id, **kwargs):
        product = self._product(product_id)
        if not product:
            return self._fail('No such product.', status=404)
        body = self._body()
        try:
            stars = int(body.get('stars') or 0)
        except (TypeError, ValueError):
            stars = 0
        if not 1 <= stars <= 5:
            return self._fail('Choose a rating first.', 'stars')

        row = request.env['rating.rating']._mart369_write_review(
            self._me(), product, body)
        return self._json({
            'ok': True,
            'productId': str(product.id),
            'review': row._mart369_serialize(),
        }, status=201)

    @http.route('/369mart/reviews/<int:product_id>', **_DELETE)
    def drop_review(self, product_id, **kwargs):
        row = request.env['rating.rating']._mart369_review_for(
            self._me(), self._product(product_id))
        if not row:
            return self._fail('No such review.', status=404)
        row.sudo().unlink()
        return self._json({'ok': True})

    @http.route('/369mart/orders/<string:ref>/rate', **_POST)
    def rate_order(self, ref, **kwargs):
        """The order and rider rating the app kept in orderPatches."""
        order = request.env['sale.order'].sudo().search([
            ('mart369_ref', '=', ref),
            ('partner_id', '=', self._me().id),
        ], limit=1)
        if not order or order.mart369_state in (False, 'draft'):
            return self._fail('No such order.', status=404)
        if order.mart369_state != 'delivered':
            return self._fail('You can rate an order once it has arrived.', status=409)
        body = self._body()
        try:
            stars = int(body.get('stars') or 0)
        except (TypeError, ValueError):
            stars = 0
        if not 1 <= stars <= 5:
            return self._fail('Choose a rating first.', 'stars')
        row = request.env['rating.rating']._mart369_rate_order(self._me(), order, body)
        return self._json({'ok': True, 'rating': {
            'stars': int(round(row.rating)),
            'comment': row.feedback or '',
            'tags': [t for t in (row.mart369_tags or '').split(',') if t],
            'at': int(row.create_date.timestamp() * 1000) if row.create_date else None,
        }}, status=201)

    # --------------------------------------------------------- notifications

    @http.route('/369mart/notifications', **_GET)
    def notifications(self, **kwargs):
        payload = request.env['mart369.notifications']._mart369_for(self._me())
        payload['ok'] = True
        payload['prefs'] = self._me()._mart369_prefs()
        return self._json(payload)

    @http.route('/369mart/notifications/read', **_POST)
    def mark_read(self, **kwargs):
        """Mark some, or all, as read."""
        body = self._body()
        ids = body.get('ids')
        if not isinstance(ids, list):
            ids = [ids] if ids else []
        if body.get('all'):
            feed = request.env['mart369.notifications']._mart369_for(self._me())
            ids = [row['id'] for row in feed['notifications']]
        read = self._me()._mart369_add_ids('mart369_read_ids', ids)
        return self._json({'ok': True, 'read': read})

    @http.route('/369mart/notifications/dismiss', **_POST)
    def dismiss(self, **kwargs):
        body = self._body()
        ids = body.get('ids')
        if not isinstance(ids, list):
            ids = [ids] if ids else []
        if not ids:
            return self._fail('Nothing to dismiss.')
        dismissed = self._me()._mart369_add_ids('mart369_dismissed_ids', ids)
        return self._json({'ok': True, 'dismissed': dismissed})

    @http.route('/369mart/notifications/prefs', **_PATCH)
    def prefs(self, **kwargs):
        return self._json({'ok': True, 'prefs': self._me()._mart369_write_prefs(self._body())})

    # -------------------------------------------------------------- referrals

    @http.route('/369mart/referrals', **_GET)
    def referrals(self, **kwargs):
        me = self._me()
        code = me.sudo()._mart369_code()
        rows = me.mart369_referral_ids
        payload = {
            'ok': True,
            'code': code,
            'link': 'https://369mart.in/r/%s' % code,
            'referrals': [row._mart369_serialize() for row in rows],
        }
        payload.update(me._mart369_referral_stats())
        return self._json(payload)

    @http.route('/369mart/referrals', **_POST)
    def invite(self, **kwargs):
        """Record an invite. The customer can only ever create an `invited` row -
        joining and ordering are claims only the server can make."""
        body = self._body()
        name = (body.get('name') or '').strip()
        if not name:
            return self._fail('Who are you inviting?', 'name')
        row = request.env['mart369.referral'].sudo().create({
            'partner_id': self._me().id,
            'name': name[:80],
            'contact': (body.get('contact') or '').strip()[:120] or False,
        })
        return self._json({'ok': True, 'referral': row._mart369_serialize()}, status=201)

    # --------------------------------------------------------------- wishlist

    @http.route('/369mart/wishlist', **_GET)
    def wishlist(self, **kwargs):
        return self._json({'ok': True, 'ids': self._mart369_wish_ids()})

    @http.route('/369mart/wishlist', **_POST)
    def wishlist_add(self, **kwargs):
        product = self._product(self._body().get('id'))
        if not product:
            return self._fail('No such product.', status=404)
        website = self._website()
        if not website:
            return self._fail('Your list is unavailable right now.', status=503)
        Wishlist = request.env['product.wishlist'].sudo()
        existing = Wishlist.search([
            ('partner_id', '=', self._me().id),
            ('product_id', '=', product.product_variant_id.id),
        ], limit=1)
        if not existing:
            Wishlist.create({
                'partner_id': self._me().id,
                'product_id': product.product_variant_id.id,
                'website_id': website.id,
            })
        return self._json({'ok': True, 'ids': self._mart369_wish_ids()}, status=201)

    @http.route('/369mart/wishlist/<int:product_id>', **_DELETE)
    def wishlist_drop(self, product_id, **kwargs):
        rows = request.env['product.wishlist'].sudo().search([
            ('partner_id', '=', self._me().id),
            ('product_id.product_tmpl_id', '=', product_id),
        ])
        if not rows:
            return self._fail('Not on your list.', status=404)
        rows.unlink()
        return self._json({'ok': True, 'ids': self._mart369_wish_ids()})

    def _mart369_wish_ids(self):
        """Template ids, newest first, as the app's `369mart.list` holds them.

        Unpublished products are dropped rather than returned: the app hides ids
        it cannot resolve anyway, and a list that silently shrinks on screen is
        worse than one that arrives already correct.
        """
        rows = request.env['product.wishlist'].sudo().search(
            [('partner_id', '=', self._me().id)], order='id desc')
        out = []
        for row in rows:
            template = row.product_id.product_tmpl_id
            if template.is_published and str(template.id) not in out:
                out.append(str(template.id))
        return out

    # ---------------------------------------------------------------- rewards

    @http.route('/369mart/rewards', **_GET)
    def rewards(self, **kwargs):
        payload = request.env['mart369.scratch']._mart369_rewards_for(self._me())
        payload['ok'] = True
        payload['coupons'] = [
            coupon._mart369_serialize()
            for coupon in request.env['mart369.coupon'].sudo().search([])
            if coupon._mart369_live()
        ]
        return self._json(payload)

    @http.route('/369mart/rewards/<int:card_id>/scratch', **_POST)
    def scratch(self, card_id, **kwargs):
        card = request.env['mart369.scratch'].sudo().search([
            ('id', '=', card_id), ('partner_id', '=', self._me().id),
        ], limit=1)
        if not card:
            return self._fail('No such card.', status=404)
        try:
            card._mart369_scratch()
        except UserError as exc:
            return self._fail(str(exc))
        return self._json({'ok': True, 'card': card._mart369_serialize()})
