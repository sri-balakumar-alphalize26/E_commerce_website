# -*- coding: utf-8 -*-
"""POST /my/orders/<id>/location - the phone's position from the order page
(23 Nov 2026). The order's portal token is the credential; every rule is in
models/sa_portal_location.py."""
from urllib.parse import quote

from odoo import http
from odoo.http import request

from .link_expired import visit_expired


class SaPortalLocation(http.Controller):

    @http.route('/my/orders/<int:order_id>/location', type='http', auth='public', methods=['POST'],
                website=True, sitemap=False)
    def location(self, order_id, access_token=None, lat=None, lng=None, **kw):
        order = request.env['sale.order'].browse(order_id)._sa_review_check(access_token)
        quiet = request.httprequest.headers.get('X-Requested-With') == 'fetch'
        if not order or visit_expired(order):
            return request.make_json_response({'ok': False}, status=404) if quiet else request.not_found()
        error, changed = order._sa_portal_set_location(lat, lng)
        if quiet:
            return request.make_json_response({'ok': not error, 'error': str(error or ''), 'reload': bool(changed)})
        url = order.get_portal_url()
        return request.redirect('%s&addr_error=%s#sa_location' % (url, quote(str(error))) if error
                                else '%s#sa_location' % url)
