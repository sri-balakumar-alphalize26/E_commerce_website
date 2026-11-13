# -*- coding: utf-8 -*-
"""POST /my/orders/<id>/slot - the optional delivery slot picked on the order
page (13 Nov 2026). The order's portal token is the credential; the booking
itself is `sale.order._sa_portal_set_slot` (filled in by the storefront's
WhatsApp bridge; without it there is no picker and this does nothing)."""
from urllib.parse import quote

from odoo import http
from odoo.http import request


class SaPortalSlot(http.Controller):

    @http.route('/my/orders/<int:order_id>/slot', type='http', auth='public', methods=['POST'],
                website=True, sitemap=False)
    def pick_slot(self, order_id, access_token=None, slot_key=None, **kw):
        order = request.env['sale.order'].browse(order_id)._sa_review_check(access_token)
        if not order:
            return request.not_found()
        error = order._sa_portal_set_slot(slot_key or '')
        url = '%s&slot_error=%s#sa_slot' % (order.get_portal_url(), quote(error)) if error \
            else '%s#sa_slot' % order.get_portal_url()
        return request.redirect(url)
