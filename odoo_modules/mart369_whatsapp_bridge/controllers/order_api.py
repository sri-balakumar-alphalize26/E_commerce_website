"""My Orders shows the WhatsApp orders too.

The storefront lists orders by their 369M- number, and a WhatsApp order
deliberately has none (sale_order_channel.py). So a customer whose WhatsApp
contact joined their account - or who signed in with the number they order on
WhatsApp from - would still not see those orders. Here they are listed, and
opened by their Odoo number (S00042), which cannot collide with a 369M- one.
"""

from odoo import http
from odoo.http import request

from odoo.addons.mart369_order.controllers.order_api import Mart369OrderApi, _GET


class Mart369OrderApiBridge(Mart369OrderApi):

    def _own(self, ref):
        order = super()._own(ref)
        if order or not ref or not isinstance(ref, str):
            return order
        return request.env['sale.order'].sudo().search([
            ('name', '=', ref),
            ('mart369_channel', '=', 'whatsapp'),
            ('partner_id', '=', self._me().id),
            ('mart369_state', 'not in', (False, 'draft')),
        ], limit=1)

    @http.route('/369mart/orders', **_GET)
    def index(self, **kwargs):
        """Both doors' orders, newest first."""
        try:
            limit = min(max(int(kwargs.get('limit') or 30), 1), 100)
        except (TypeError, ValueError):
            limit = 30
        orders = request.env['sale.order'].sudo().search([
            ('partner_id', '=', self._me().id),
            '|', ('mart369_ref', '!=', False), ('mart369_channel', '=', 'whatsapp'),
            ('mart369_state', 'not in', (False, 'draft')),
        ], order='mart369_placed_at desc, date_order desc, id desc', limit=limit)
        return self._json({
            'ok': True,
            'orders': [order._mart369_serialize() for order in orders],
        })
