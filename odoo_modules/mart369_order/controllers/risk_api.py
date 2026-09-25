"""Cash on delivery per customer, and goodwill credit - for the admin console.

The model does the work (models/customer_risk.py), so the Odoo desk, which
calls the same methods through the ORM, refuses the same things. The group is
checked first; a shopper is refused, not filtered.
"""

import json

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

EDITOR_GROUP = 'website.group_website_designer'
_BASE = {'type': 'http', 'auth': 'user', 'csrf': False, 'sitemap': False}


class Mart369CustomerRiskApi(http.Controller):

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
                payload = fn(body)
        except AccessError as exc:
            return request.make_json_response({'ok': False, 'error': str(exc)}, status=403)
        except UserError as exc:
            return request.make_json_response({'ok': False, 'error': str(exc)}, status=400)
        return request.make_json_response(dict({'ok': True}, **payload))

    @http.route('/369mart/admin/customers/<int:user_id>/cod', methods=['PATCH'], **_BASE)
    def set_cod(self, user_id, **kwargs):
        return self._answer(lambda body: {
            'risk': request.env['res.users'].mart369_admin_set_cod(user_id, bool(body.get('off')))})

    @http.route('/369mart/admin/customers/<int:user_id>/goodwill', methods=['POST'], **_BASE)
    def goodwill(self, user_id, **kwargs):
        return self._answer(lambda body: request.env['res.users'].mart369_admin_goodwill(
            user_id, body.get('amount'), body.get('reason')))
