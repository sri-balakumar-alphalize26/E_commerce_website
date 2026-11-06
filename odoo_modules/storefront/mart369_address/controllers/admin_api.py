"""The staff side of addresses, for the app's own admin console.

Same two rules as every other admin controller in the suite, for the same
reason. Every route in address_api.py answers "this shopper's own addresses"
and is fenced by `_own()`; nothing here has that fence, so:

* **The group is checked on every route**, first, and somebody who is not staff
  is refused rather than handed an empty list. This is where customers live.
* **Nothing is sudo'd here.** Lists are read as the person signed in, so
  Odoo's own access rules do their job rather than being re-implemented here
  badly.

**Staff can fix, never delete.** It started read-only. Then support needed to
do what Amazon's and Flipkart's do: open a customer, see every address they
keep, fix a wrong flat number, add one taken over the phone, choose the
default. Those writes go through res.partner's staff methods
(models/address_staff.py), which check the group again themselves and leave a
note in the customer's history. An address an order already went to is copied
rather than rewritten, so the order keeps what it was placed with. Removing an
address stays the customer's call - there is no DELETE here.
"""

import logging

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'],
        'csrf': False, 'sitemap': False}
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'],
         'csrf': False, 'sitemap': False}
_PATCH = {'type': 'http', 'auth': 'user', 'methods': ['PATCH'],
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

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:
            data = None
        return data if isinstance(data, dict) else {}

    def _answer(self, result, status=200):
        """A staff method's {ok, ...} as a response: 400 with the field when it
        says no, 404 when there was nothing to act on."""
        if result.get('ok'):
            return self._json(result, status=status)
        return self._fail(result.get('error'), field=result.get('field'),
                          status=400 if result.get('field') else 404)

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

    # ------------------------------------------------ one customer's book

    @http.route('/369mart/admin/customers/<int:user_id>/addresses', **_GET)
    def book(self, user_id, **kwargs):
        """Every address one customer keeps, the default first."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        return self._answer(self._addresses().mart369_admin_book(user_id))

    @http.route('/369mart/admin/customers/<int:user_id>/addresses', **_POST)
    def add(self, user_id, **kwargs):
        """Add an address for a customer - one taken over the phone."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        return self._answer(self._addresses().mart369_admin_add(user_id, self._body()), status=201)

    @http.route('/369mart/admin/addresses/<int:address_id>', **_PATCH)
    def edit(self, address_id, **kwargs):
        """Fix an address. The answer may carry a new id: see the docstring."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        return self._answer(self._addresses().mart369_admin_edit(address_id, self._body()))

    @http.route('/369mart/admin/addresses/<int:address_id>/default', **_POST)
    def make_default(self, address_id, **kwargs):
        """Choose where the customer's orders ship by default."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        return self._answer(self._addresses().mart369_admin_make_default(address_id))
