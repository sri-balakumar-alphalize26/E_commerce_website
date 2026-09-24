"""Staff & roles for the app's console. Owner only - checked on the model too.

Nothing is sudo'd here: the model's own Owner check is the fence, and a
refusal comes back as 403 rather than an empty list, so somebody who is not
the Owner does not learn who works here.
"""

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'], 'csrf': False, 'sitemap': False}
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'], 'csrf': False, 'sitemap': False}


class Mart369StaffApi(http.Controller):

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:  # noqa: BLE001
            data = None
        return data if isinstance(data, dict) else {}

    def _run(self, fn):
        try:
            payload = fn()
        except AccessError as exc:
            return self._json({'ok': False, 'error': str(exc)}, status=403)
        except (UserError, ValidationError) as exc:
            return self._json({'ok': False, 'error': str(exc)}, status=400)
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/staff', **_GET)
    def staff(self, q=None, **kwargs):
        return self._run(lambda: request.env['res.users'].mart369_staff_list(q=q))

    @http.route('/369mart/admin/staff/<int:user_id>', **_POST)
    def set_role(self, user_id, **kwargs):
        body = self._body()
        return self._run(lambda: {'row': request.env['res.users'].mart369_staff_set(
            user_id, body.get('role'), bool(body.get('accountant')),
            bool(body.get('rider')), body.get('companies'))})

    @http.route('/369mart/admin/staff/invite', **_POST)
    def invite(self, **kwargs):
        body = self._body()
        return self._run(lambda: {'row': request.env['res.users'].mart369_staff_invite(
            body.get('name'), body.get('email'), body.get('role') or 'user',
            bool(body.get('accountant')), bool(body.get('rider')))})
