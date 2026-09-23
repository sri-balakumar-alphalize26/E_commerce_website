"""The console's Settings screen.

Same rules as every admin route in the suite: the group is checked first on
every route and a shopper is refused, and nothing is sudo'd - saving the
company still needs Odoo's own settings right, and the error says so.

What each field is, and where it is stored, is on the model
(models/settings_admin.py). This file only carries it.
"""

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'],
        'csrf': False, 'sitemap': False}
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'],
         'csrf': False, 'sitemap': False}

EDITOR_GROUP = 'website.group_website_designer'


class Mart369SettingsAdminApi(http.Controller):

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

    @http.route('/369mart/admin/settings', **_GET)
    def settings(self, **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            groups = request.env['mart369.config'].mart369_admin_settings()
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        return self._json({'ok': True, 'settings': groups})

    @http.route('/369mart/admin/settings/<string:group>', **_POST)
    def save(self, group, **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            groups = request.env['mart369.config'].mart369_admin_save(group, self._body())
        except AccessError:
            return self._fail(
                'Only someone with Odoo\'s Settings access can change this.', status=403)
        except (UserError, ValidationError) as exc:
            return self._fail(str(exc))
        return self._json({'ok': True, 'settings': groups})
