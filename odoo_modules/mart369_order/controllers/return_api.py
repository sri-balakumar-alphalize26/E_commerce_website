"""The console's returns queue.

The same two rules as admin_api.py, and for the same reasons: the editor group
is checked on every route, and **nothing is sudo'd**, so Odoo's own access
rules still apply to whoever is signed in. Paths stay short because the
storefront proxies them through /api/mart/<path>.

Its own file rather than more of admin_api.py: that one is being worked on
elsewhere, and a returns queue is a separate screen anyway.

The photo route is the reason this screen is worth building. Until now nobody
outside Odoo's own form could see a damage photo - which is the one thing a
damaged-goods claim actually needs.
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

EDITOR_GROUP = 'website.group_website_designer'


class Mart369ReturnAdminApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _fail(self, error, status=400):
        return self._json({'ok': False, 'error': error}, status=status)

    def _may_edit(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        return request.env.user.has_group(EDITOR_GROUP)

    def _returns(self):
        """Not sudo'd - on purpose."""
        return request.env['mart369.order.return']

    def _int(self, value, fallback=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    def _act(self, method, return_id):
        """One write, with the refusals the model is entitled to make.

        A UserError here is the model saying the screen is out of date - the
        return already finished, or the refund already went - so it answers
        409 and the screen reloads rather than arguing.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            data = getattr(self._returns(), method)(return_id)
        except UserError as exc:
            return self._fail(str(exc), status=409)
        except AccessError:
            return self._fail('You do not have access to this.', status=403)
        except ValueError as exc:
            return self._fail(str(exc), status=404)
        return self._json(dict(data, ok=True))

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/admin/returns', **_GET)
    def returns(self, tab='needs', kind=None, q='', sort='old',
                limit='25', offset='0', **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        data = self._returns().mart369_returns_list(
            tab=tab or 'needs',
            kind=kind or None,
            q=q or '',
            sort=sort or 'old',
            limit=self._int(limit, 25),
            offset=self._int(offset, 0),
        )
        return self._json(dict(data, ok=True))

    @http.route('/369mart/admin/returns/<int:return_id>', **_GET)
    def one(self, return_id, **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        data = self._returns().mart369_returns_detail(return_id)
        if not data:
            return self._fail('No such return.', status=404)
        return self._json(dict(data, ok=True))

    @http.route('/369mart/admin/returns/<int:return_id>/advance', **_POST)
    def advance(self, return_id, **kwargs):
        return self._act('mart369_returns_advance', return_id)

    @http.route('/369mart/admin/returns/<int:return_id>/refuse', **_POST)
    def refuse(self, return_id, **kwargs):
        return self._act('mart369_returns_refuse', return_id)

    @http.route('/369mart/admin/returns/<int:return_id>/photo/<int:photo_id>', **_GET)
    def photo(self, return_id, photo_id, **kwargs):
        """One of the customer's photos.

        Fenced two ways rather than serving ir.attachment directly: the group
        is checked, and the attachment must belong to *this* return. Otherwise
        the route is a way to read any attachment in the database by guessing
        a number.
        """
        if not self._may_edit():
            return request.not_found()
        record = self._returns()._mart369_admin_find(return_id)
        if not record or photo_id not in record.photo_ids.ids:
            return request.not_found()
        # sudo only to stream the bytes, after the return has been read as the
        # signed-in user and the photo proven to belong to it.
        return request.env['ir.binary']._get_image_stream_from(
            record.photo_ids.sudo().browse(photo_id), field_name='datas',
        ).get_response()
