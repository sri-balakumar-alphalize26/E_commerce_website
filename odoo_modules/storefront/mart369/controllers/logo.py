"""/369mart/logo - the shop's logo as uploaded in the console (Settings >
Store), for the storefront and for every page sent by link. 404 when none is
uploaded: each caller then shows the logo that ships with it."""
from odoo import http
from odoo.http import request


class Mart369Logo(http.Controller):

    @http.route('/369mart/logo', type='http', auth='public', methods=['GET'], csrf=False,
                sitemap=False, readonly=True, save_session=False)
    def logo(self, **kwargs):
        config = request.env['mart369.config'].sudo()._get()
        if not config.shop_logo:
            return request.not_found()
        # ?v= changes with every upload, so a long cache is safe.
        return request.env['ir.binary']._get_image_stream_from(
            config, field_name='shop_logo').get_response(max_age=86400)
