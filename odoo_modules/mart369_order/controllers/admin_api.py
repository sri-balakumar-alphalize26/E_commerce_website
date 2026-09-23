"""The staff side of orders, for the app's own admin console.

Same two rules as the home page's admin routes, for the same reason. Every
other route under /369mart answers "this shopper's own things" and is fenced by
`_own()`; nothing here has that fence, so:

* **The group is checked on every route**, first, and a shopper is refused
  rather than filtered - somebody who is not staff must not learn that this
  exists by watching an empty list come back.
* **Nothing is sudo'd.** The shopper API searches as the system because it has
  already narrowed to one partner. Here the records are read and written as the
  person signed in, so Odoo's own access rules do their job.

Moving an order on is `mart369_action_advance()` and cancelling it is
`_mart369_cancel()` - the same two methods the backend board's buttons call.
This controller does not know the order of the steps and must not learn it: a
second copy of the ladder is a second thing to get wrong.
"""

import logging

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.mart369_order.models.order_admin import CANCEL_REASONS

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'],
        'csrf': False, 'sitemap': False}
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'],
         'csrf': False, 'sitemap': False}

EDITOR_GROUP = 'website.group_website_designer'

# The list of cancellation reasons lives on the model, because the backend
# screen offers the same one.


class Mart369OrderAdminApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _fail(self, error, field=None, status=400):
        """Same shape as every other controller in the suite, field included -
        so a screen can put the message under the control it is about."""
        payload = {'ok': False, 'error': error}
        if field:
            payload['field'] = field
        return self._json(payload, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:  # noqa: BLE001
            data = None
        return data if isinstance(data, dict) else {}

    def _may_edit(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        return request.env.user.has_group(EDITOR_GROUP)

    def _orders(self):
        """Not sudo'd - on purpose. See the module docstring."""
        return request.env['sale.order']

    def _order(self, ref):
        """One order by the number the console shows.

        The lookup itself is on the model, so the backend screen and this find
        the same record by the same rule.
        """
        return self._orders()._mart369_admin_find(ref)

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/admin/orders', **_GET)
    def orders(self, tab=None, mode=None, when=None, q=None, sort=None,
               limit=None, offset=None, **kwargs):
        """One page of the list the console draws."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            page = self._orders().mart369_admin_list(
                tab=tab, mode=mode, when=when, q=q, sort=sort,
                limit=limit or 30, offset=offset or 0)
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc))
        page['ok'] = True
        return self._json(page)

    @http.route('/369mart/admin/orders/counts', **_GET)
    def counts(self, **kwargs):
        """The tiles above the list, and the number on each tab.

        Its own route because the console's shell wants these for the sidebar
        badge without loading a page of orders it is not going to show.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            payload = self._orders().mart369_admin_counts()
        except (AccessError, UserError) as exc:
            return self._fail(str(exc))
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/orders/<string:ref>', **_GET)
    def order(self, ref, **kwargs):
        """One order, in full, for the drawer."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        order = self._order(ref)
        if not order:
            return self._fail('There is no such order.', status=404)
        return self._json({'ok': True, 'order': order._mart369_admin_detail()})

    @http.route('/369mart/admin/orders/<string:ref>/advance', **_POST)
    def advance(self, ref, **kwargs):
        """Move the order on by one step.

        Which step that is belongs to the order, not to this route and not to
        the screen: a quick order is packed next and an express one is shipped
        next, and `mart369_action_advance` is the one place that knows.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        order = self._order(ref)
        if not order:
            return self._fail('There is no such order.', status=404)
        try:
            order.mart369_action_advance()
        except UserError as exc:
            # It moved while the screen was looking at it, or it is already
            # delivered. Not the operator's mistake, so not a 400.
            return self._fail(str(exc), status=409)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        return self._json({'ok': True, 'order': order._mart369_admin_detail()})

    @http.route('/369mart/admin/orders/<string:ref>/deliver', **_POST)
    def deliver(self, ref, **kwargs):
        """Close a delivery with the code from the customer's doorstep.

        Separate from `advance` because it is not the same kind of act. Every
        other step is the shop moving its own work along; this one is the
        customer confirming they have their things, and the code is the only
        evidence of that. `mart369_action_advance` refuses to reach delivered
        precisely so this route is the only way through.

        The arithmetic is not here. `mart369_action_deliver` on the order
        knows what a valid code is, and the rider app will call that same
        method rather than carry a second opinion about it.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        order = self._order(ref)
        if not order:
            return self._fail('There is no such order.', status=404)
        code = (self._body().get('code') or '').strip()
        if not code:
            return self._fail('Ask the customer for their delivery code.',
                              field='code')
        try:
            order.mart369_action_deliver(code)
        except UserError as exc:
            # A wrong code is the operator mistyping, or the customer reading
            # out the wrong thing: 400, and the screen keeps the box open. An
            # order that is not out for delivery moved while the screen was
            # looking at it: 409, the same as `advance` answers.
            wrong = 'not right' in str(exc)
            return self._fail(str(exc), field='code' if wrong else None,
                              status=400 if wrong else 409)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        return self._json({'ok': True, 'order': order._mart369_admin_detail()})

    @http.route('/369mart/admin/orders/<string:ref>/invoice', **_GET)
    def invoice(self, ref, **kwargs):
        """The same document the customer can download, for the operator.

        Its own route rather than a link to the shopper's one: that route is
        fenced to the signed-in customer's own orders, so staff opening it for
        anybody else's order would get a 404 and no clue why.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        order = self._order(ref)
        if not order:
            return self._fail('There is no such order.', status=404)
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

    @http.route('/369mart/admin/orders/<string:ref>/cancel', **_POST)
    def cancel(self, ref, **kwargs):
        """Cancel the order and give the money back."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        order = self._order(ref)
        if not order:
            return self._fail('There is no such order.', status=404)
        reason = (self._body().get('reason') or '').strip()
        if reason not in CANCEL_REASONS:
            return self._fail('Pick a reason for the cancellation.')
        try:
            order._mart369_cancel(reason=reason)
        except UserError as exc:
            # Already packed. The model refuses it, and the screen should not
            # have offered the button - but a stale screen will.
            return self._fail(str(exc), status=409)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        return self._json({'ok': True, 'order': order._mart369_admin_detail()})
