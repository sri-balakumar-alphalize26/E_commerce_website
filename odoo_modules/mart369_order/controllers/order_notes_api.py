"""Staff notes on an order, for the admin console.

The model does the work (models/order_customer.py), so the Odoo desk - which
calls the same methods through the ORM - refuses the same things.
"""

import json

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

EDITOR_GROUP = 'website.group_website_designer'
_BASE = {'type': 'http', 'auth': 'user', 'csrf': False, 'sitemap': False}


class Mart369OrderNotesApi(http.Controller):

    def _answer(self, fn):
        if not request.env.user.has_group(EDITOR_GROUP):
            return request.make_json_response(
                {'ok': False, 'error': 'You do not have access to this.'}, status=403)
        try:
            body = json.loads(request.httprequest.get_data(as_text=True) or '{}')
        except ValueError:
            body = {}
        body = body if isinstance(body, dict) else {}
        try:
            with request.env.cr.savepoint():
                notes = fn(body)
        except AccessError as exc:
            return request.make_json_response({'ok': False, 'error': str(exc)}, status=403)
        except UserError as exc:
            return request.make_json_response({'ok': False, 'error': str(exc)}, status=400)
        return request.make_json_response({'ok': True, 'notes': notes})

    @http.route('/369mart/admin/orders/<string:ref>/notes', methods=['POST'], **_BASE)
    def add(self, ref, **kwargs):
        return self._answer(lambda b: request.env['sale.order'].mart369_admin_add_order_note(ref, b.get('text')))

    @http.route('/369mart/admin/orders/<string:ref>/notes/<int:note_id>', methods=['PATCH'], **_BASE)
    def edit(self, ref, note_id, **kwargs):
        return self._answer(lambda b: request.env['sale.order'].mart369_admin_edit_order_note(ref, note_id, b.get('text')))

    @http.route('/369mart/admin/orders/<string:ref>/notes/<int:note_id>', methods=['DELETE'], **_BASE)
    def delete(self, ref, note_id, **kwargs):
        return self._answer(lambda b: request.env['sale.order'].mart369_admin_delete_order_note(ref, note_id))
