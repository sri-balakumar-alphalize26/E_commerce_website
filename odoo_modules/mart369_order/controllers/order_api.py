"""Orders, for the app.

Same shape as every other 369 Mart route: type='http' answering bare JSON,
called by the storefront's own server rather than straight from a browser, and
failures as {ok: false, error, field?}.

The ownership rule is the one that matters. An order is found by the number the
app holds, and only ever within the signed-in customer's own orders - so a
guessed order number gets a 404, not somebody else's address, basket and phone
number. `_own()` is the only way in, and it has its own test.

Nothing here decides what anything costs. The bill is `mart369_cart`'s, the
order is priced in `_mart369_place`, and what a customer pays is read off the
order by `mart369_payment`. This controller only moves JSON.
"""

import base64
import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'], 'csrf': False, 'sitemap': False}
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'], 'csrf': False, 'sitemap': False}

# What the app may send with a return request. Anything bigger is refused
# rather than quietly truncated.
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTOS = 6


class Mart369OrderApi(http.Controller):

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

    def _own(self, ref):
        """One order, but only if it is this customer's.

        Keyed by the app's own order number rather than the database id: that is
        what the app holds, and it does not walk 1, 2, 3 the way an id does.
        Anything else - another customer's order, a made-up number, a basket
        that was never paid for - comes back empty and the caller answers 404.
        """
        empty = request.env['sale.order'].browse()
        if not ref or not isinstance(ref, str):
            return empty
        order = request.env['sale.order'].sudo().search([
            ('mart369_ref', '=', ref),
            ('partner_id', '=', self._me().id),
        ], limit=1)
        if not order or order.mart369_state in (False, 'draft'):
            # A draft has been created but never paid for. As far as the app is
            # concerned it does not exist yet.
            return empty
        return order

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/orders', **_POST)
    def place(self, **kwargs):
        """Place an order. Safe to call twice with the same order number."""
        body = self._body()
        try:
            order = request.env['sale.order']._mart369_place(self._me(), body)
        except UserError as exc:
            return self._fail(str(exc))
        return self._json({
            'ok': True,
            'ref': order.mart369_ref,
            'total': order.currency_id.round(order.amount_total),
            'order': order._mart369_serialize(),
        }, status=201)

    @http.route('/369mart/orders', **_GET)
    def index(self, **kwargs):
        """Every order this customer has placed, newest first."""
        try:
            limit = min(max(int(kwargs.get('limit') or 30), 1), 100)
        except (TypeError, ValueError):
            limit = 30
        orders = request.env['sale.order'].sudo().search([
            ('partner_id', '=', self._me().id),
            ('mart369_ref', '!=', False),
            ('mart369_state', 'not in', (False, 'draft')),
        ], order='mart369_placed_at desc, id desc', limit=limit)
        return self._json({
            'ok': True,
            'orders': [order._mart369_serialize() for order in orders],
        })

    @http.route('/369mart/orders/<string:ref>', **_GET)
    def show(self, ref, **kwargs):
        order = self._own(ref)
        if not order:
            return self._fail('No such order.', status=404)
        return self._json({'ok': True, 'order': order._mart369_serialize()})

    @http.route('/369mart/orders/<string:ref>/cancel', **_POST)
    def cancel(self, ref, **kwargs):
        order = self._own(ref)
        if not order:
            return self._fail('No such order.', status=404)
        body = self._body()
        try:
            order._mart369_cancel(reason=(body.get('reason') or '').strip() or None)
        except UserError as exc:
            return self._fail(str(exc), status=409)
        return self._json({'ok': True, 'order': order._mart369_serialize()})

    @http.route('/369mart/orders/<string:ref>/return', **_POST)
    def open_return(self, ref, **kwargs):
        """Ask for a refund or a replacement, with the photos really kept."""
        order = self._own(ref)
        if not order:
            return self._fail('No such order.', status=404)
        if order.mart369_state != 'delivered':
            return self._fail(
                'You can ask for a return once the order has been delivered.',
                status=409)

        body = self._body()
        reason = (body.get('reason') or '').strip()
        if not reason:
            return self._fail('Tell us what went wrong.', 'reason')
        kind = body.get('kind') if body.get('kind') in ('refund', 'replace') else 'refund'

        try:
            photos = self._attachments(order, body.get('photos') or [])
        except UserError as exc:
            return self._fail(str(exc), 'photos')

        record = request.env['mart369.order.return'].sudo().create({
            'order_id': order.id,
            'kind': kind,
            'reason': reason,
            'detail': (body.get('detail') or '').strip() or False,
            'amount': order.amount_total,
            'photo_ids': [(6, 0, photos.ids)],
        })
        return self._json({'ok': True, 'return': record._mart369_serialize()}, status=201)

    @http.route('/369mart/orders/<string:ref>/invoice', **_GET)
    def invoice(self, ref, **kwargs):
        """The real document, so the receipt's Download button stops being a
        call to window.print()."""
        order = self._own(ref)
        if not order:
            return self._fail('No such order.', status=404)
        invoices = order.invoice_ids.filtered(lambda m: m.state == 'posted')
        if not invoices:
            return self._fail('No invoice for that order yet.', status=404)
        pdf, __ = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'mart369_order.report_invoice', res_ids=invoices[:1].ids)
        filename = '369mart-%s.pdf' % (order.mart369_ref or order.id)
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', 'attachment; filename="%s"' % filename),
        ])

    # ----------------------------------------------------------- attachments

    def _attachments(self, order, photos):
        """Base64 images off the return form, kept as real attachments.

        In the app these were a number: OrderTrack.jsx:361 counted how many the
        customer picked and then threw them away, which is the one thing a
        damaged-goods claim actually needs.
        """
        if not isinstance(photos, list):
            return request.env['ir.attachment'].browse()
        if len(photos) > MAX_PHOTOS:
            raise UserError(request.env._(
                'Please send no more than %s photos.', MAX_PHOTOS))

        values = []
        for index, photo in enumerate(photos[:MAX_PHOTOS], start=1):
            raw = photo.get('data') if isinstance(photo, dict) else photo
            if not raw or not isinstance(raw, str):
                continue
            if ',' in raw[:64] and raw[:5] == 'data:':
                raw = raw.split(',', 1)[1]
            try:
                blob = base64.b64decode(raw, validate=True)
            except Exception:
                raise UserError(request.env._("One of those photos could not be read."))
            if len(blob) > MAX_PHOTO_BYTES:
                raise UserError(request.env._('Each photo must be under 5 MB.'))
            values.append({
                'name': '%s-return-%d.jpg' % (order.mart369_ref or order.id, index),
                'datas': base64.b64encode(blob),
                'res_model': 'mart369.order.return',
                'type': 'binary',
            })
        if not values:
            return request.env['ir.attachment'].browse()
        return request.env['ir.attachment'].sudo().create(values)
