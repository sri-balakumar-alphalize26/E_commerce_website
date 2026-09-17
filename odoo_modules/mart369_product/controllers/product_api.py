"""What the 369 Mart app reads for one product page.

The shape is exactly what components/home/ProductDetail.jsx already consumes,
so the storefront needs no change: a `p` block identical to the card the home
API sends, and a `d` block holding everything the page shows around it.

Which of those fields appear at all is decided in 369 Mart > Product Page - a
field switched off is simply absent, never null. The assembling lives on
mart369.product.page so the tests and the builder preview share it.
"""

from odoo import http
from odoo.http import request

from odoo.addons.mart369_home.controllers.home_api import _PUBLIC_JSON


class Mart369ProductApi(http.Controller):

    @http.route('/369mart/product/<int:product_id>', **_PUBLIC_JSON)
    def product(self, product_id, **kwargs):
        env = request.env
        product = env['product.template'].sudo().browse(product_id).exists()
        if not product or not product.is_published:
            return request.make_json_response(
                {'error': 'not_found', 'id': product_id}, status=404)

        payload = env['mart369.product.page'].sudo().payload(product)
        config = env['mart369.home.config'].sudo()._get()
        return request.make_json_response(payload, headers=[
            ('Cache-Control',
             'public, max-age=%d' % max(config.cache_seconds or 0, 0)),
        ])

    @http.route('/369mart/product/health', **_PUBLIC_JSON)
    def health(self, **kwargs):
        Field = request.env['mart369.product.field'].sudo()
        return request.make_json_response({
            'ok': True,
            'fields': Field.search_count([]),
            'shown': Field.search_count([('show', '=', True)]),
        })
