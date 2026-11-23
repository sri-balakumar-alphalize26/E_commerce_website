# -*- coding: utf-8 -*-
"""POST /my/orders/<id>/address - pick, edit or add the delivery address on the
sign page (23 Nov 2026). The order's portal token is the credential, as for the
delivery slot; every rule is checked again in models/sa_portal_address.py."""
from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


class SaPortalAddress(http.Controller):

    @http.route('/my/orders/<int:order_id>/address', type='http', auth='public', methods=['POST'],
                website=True, sitemap=False)
    def address(self, order_id, access_token=None, do=None, address_id=None, **kw):
        order = request.env['sale.order'].browse(order_id)._sa_review_check(access_token)
        if not order:
            return request.not_found()
        picked = str(address_id or '')
        addr = request.env['res.partner'].sudo().browse(int(picked) if picked.isdigit() else 0).exists()
        error = ''
        if do in ('add', 'edit'):
            try:
                link = order._sa_portal_addr_link(do, addr)
                return request.redirect('/wa/address/%s' % link.sudo().token)
            except UserError as err:
                error = str(err.args[0] if err.args else err)
        else:
            error = order._sa_portal_use_address(addr)
        url = order.get_portal_url()
        return request.redirect('%s&addr_error=%s#sa_address' % (url, quote(error)) if error
                                else '%s#sa_address' % url)
