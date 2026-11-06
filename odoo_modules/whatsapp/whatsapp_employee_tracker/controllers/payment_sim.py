# -*- coding: utf-8 -*-
"""Legacy pay-link route, reduced to a redirect.

This module used to render dummy UPI/card pages and expose
`/wa/pay/<id>/confirm`, which marked an order paid with no gateway behind it.
That route was `auth='public'`, `csrf=False` and accepted GET, so anyone
holding the link the customer was sent could confirm payment, and the order
would confirm, invoice itself as paid, and dispatch a rider told to collect
nothing. It is gone.

What remains is `/wa/pay/<id>` as a redirect to the order's real portal page,
because links already sitting in customers' WhatsApp history must land
somewhere sensible rather than on a 404. The portal page offers whichever
payment providers the database actually has enabled.
"""

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WaPaymentSim(http.Controller):

    def _get_order(self, order_id, token):
        order = request.env['sale.order'].sudo().browse(int(order_id))
        if not order.exists() or not token or token != order.access_token:
            return None
        return order

    @http.route('/wa/pay/<int:order_id>', type='http', auth='public', csrf=False)
    def wa_pay(self, order_id, method='upi', token=None, **kw):
        """Send the customer to the real payment page.

        The old dummy pages are not rendered any more. `method` is still
        accepted and ignored: old links carry it, and the provider choice now
        belongs to the portal page.
        """
        order = self._get_order(order_id, token)
        if not order:
            return request.not_found()
        order._portal_ensure_token()
        return request.redirect(order.get_portal_url(), code=303)
