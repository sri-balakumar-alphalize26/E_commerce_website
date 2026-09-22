"""The staff side of addresses, for the app's own admin console.

Same two rules as every other admin controller in the suite, for the same
reason. Every route in address_api.py answers "this shopper's own addresses"
and is fenced by `_own()`; nothing here has that fence, so:

* **The group is checked on every route**, first, and somebody who is not staff
  is refused rather than handed an empty list. This is where customers live.
* **Nothing is sudo'd.** Records are read as the person signed in, so Odoo's
  own access rules do their job rather than being re-implemented here badly.

**Read-only.** There is no route here that writes an address, and there should
never be one. A customer edits their own; staff look, so they can tell somebody
why a delivery went wrong. The two routes below are both GET, and that is the
whole surface.
"""

import logging

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'],
        'csrf': False, 'sitemap': False}

EDITOR_GROUP = 'website.group_website_designer'


class Mart369AddressAdminApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _fail(self, error, field=None, status=400):
        payload = {'ok': False, 'error': error}
        if field:
            payload['field'] = field
        return self._json(payload, status=status)

    def _may_edit(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        return request.env.user.has_group(EDITOR_GROUP)

    def _addresses(self):
        """Not sudo'd - on purpose. See the module docstring."""
        return request.env['res.partner']

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/admin/addresses', **_GET)
    def addresses(self, tab=None, q=None, limit=None, **kwargs):
        """The addresses, and the numbers above them."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            payload = self._addresses().mart369_admin_list(
                tab=tab, q=q, limit=int(limit or 30))
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (TypeError, ValueError):
            return self._fail('That is not a number we can use.', field='limit')
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/addresses/counts', **_GET)
    def counts(self, **kwargs):
        """The tallies alone, for the sidebar badge."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            payload = self._addresses().mart369_admin_counts()
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)
