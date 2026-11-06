"""The staff side of payments and wallets, for the app's own admin console.

The first admin controller in this module, following the same two rules as
every other one in the suite:

* **The group is checked on every route**, first, and somebody who is not
  staff is refused rather than handed an empty list.
* **Nothing is sudo'd on the way in.** The wallet reads reach for `sudo()`
  inside the model because a `loyalty.card` belongs to its customer, and staff
  reading every customer's wallet is exactly what these screens are for - but
  the check that says who may do that is `_mart369_admin_may_read` on the
  model, shared with the backend desk so the two front ends cannot disagree.

**There is not one write in this file, and that is the point.**

A payment becomes true in `_post_process`, after the provider's own webhook
has verified the signature. Nothing the app sends can reach that, and nothing
here should either - a console button that marked a payment paid would be a
claim about money that nobody received. The one settlement that happens away
from a gateway is cash at the door, and it keeps its existing button on the
Odoo form, where it is pressed by somebody who knows whether the rider was
handed the notes.

Wallets are the same argument with sharper teeth: a wallet holds real money
the shop owes a customer. The only thing that moves a balance is
`_mart369_move`, called by a top-up, an order, a refund or a reward - each a
thing that actually happened. There is deliberately nothing here to call, the
same stance the rewards controller takes, and `loyalty.card.write()` would
refuse a raw balance write anyway.

Refunds are not missing: they belong to Returns, which already moves the
wallet leg back.
"""

import logging

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'],
        'csrf': False, 'sitemap': False}

EDITOR_GROUP = 'website.group_website_designer'


class Mart369PaymentAdminApi(http.Controller):

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

    def _payments(self):
        return request.env['payment.transaction']

    def _wallets(self):
        return request.env['loyalty.card']

    # --------------------------------------------------------- the payments

    @http.route('/369mart/admin/payments', **_GET)
    def payments(self, tab='all', method='', kind='', q='', **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        if tab not in self._payments().ADMIN_TABS:
            tab = 'all'
        try:
            payload = self._payments().mart369_admin_list(
                tab=tab, method=method, kind=kind, q=q)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)

    # ---------------------------------------------------------- the wallets

    @http.route('/369mart/admin/wallets', **_GET)
    def wallets(self, tab='all', q='', **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        if tab not in self._wallets().ADMIN_TABS:
            tab = 'all'
        try:
            payload = self._wallets().mart369_admin_list(tab=tab, q=q)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/wallets/<int:card_id>/ledger', **_GET)
    def wallet_ledger(self, card_id, before=None, **kwargs):
        """One wallet's movements - the same rows the customer sees."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            payload = self._wallets().mart369_admin_ledger(card_id, before=before)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (UserError, ValidationError) as exc:
            return self._fail(str(exc), status=404)
        payload['ok'] = True
        return self._json(payload)
