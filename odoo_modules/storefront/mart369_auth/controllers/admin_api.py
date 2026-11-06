"""The staff side of customers, for the app's own admin console.

Same two rules as every admin route in the suite:

* **The group is checked on every route**, first, and a shopper is refused
  rather than filtered - these routes list every customer's email and phone,
  and there is no `_own()` fence behind the group check.
* **Nothing is sudo'd.** Records are read as the person signed in.

Read-only. What a row says lives on `res.users` (see models/customer_admin.py),
so the console and the backend Customers screen tell the same story.
"""

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'],
        'csrf': False, 'sitemap': False}

EDITOR_GROUP = 'website.group_website_designer'


class Mart369CustomerAdminApi(http.Controller):

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _fail(self, error, status=400):
        return self._json({'ok': False, 'error': error}, status=status)

    def _may_edit(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        return request.env.user.has_group(EDITOR_GROUP)

    @http.route('/369mart/admin/customers', **_GET)
    def customers(self, tab=None, q=None, area=None, joined=None, wallet=None,
                  sort=None, limit=None, offset=None, **kwargs):
        """One page of the list, the tab counts and the area dropdown."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            page = request.env['res.users'].mart369_admin_list(
                tab=tab, q=q, area=area, joined=joined, wallet=wallet, sort=sort,
                limit=limit or 50, offset=offset or 0)
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc))
        page['ok'] = True
        return self._json(page)

    @http.route('/369mart/admin/customers/<int:user_id>', **_GET)
    def customer(self, user_id, **kwargs):
        """One customer and their recent orders, for the drawer."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            row = request.env['res.users'].mart369_admin_detail(user_id)
        except (AccessError, UserError) as exc:
            return self._fail(str(exc))
        if not row:
            return self._fail('There is no such customer.', status=404)
        return self._json({'ok': True, 'customer': row})
