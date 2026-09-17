"""The endpoint the 369 Mart app reads its home page from.

Deliberately type='http' returning a plain JSON body, not type='json'. In
Odoo 19 type='json' is a deprecated alias for 'jsonrpc', which only accepts
POST and wraps everything in a {"jsonrpc": "2.0", "result": ...} envelope the
app would have to unwrap. A browser fetch() wants a GET and a bare object.
"""

from odoo import http
from odoo.http import request

# website=True gives the pricelist and fiscal position the price calculation
# needs. It also switches on Odoo's language redirects, so multilang=False is
# then required or a French browser gets a 302 to /fr/369mart/home.
_PUBLIC_JSON = {
    'type': 'http',
    'auth': 'public',
    'methods': ['GET'],
    'cors': '*',
    'csrf': False,
    'website': True,
    'multilang': False,
    'sitemap': False,
    'readonly': True,
    'save_session': False,
}


class Mart369HomeApi(http.Controller):

    @http.route('/369mart/home', **_PUBLIC_JSON)
    def home(self, **kwargs):
        """The whole home page, both modes.

        Shape: {"quick": {tabs, banners, categories, sections, freeDeliveryAt},
                "all": {...}}
        """
        config = request.env['mart369.home.config'].sudo()._get()
        return self._respond(config._serialize_modes(), config)

    @http.route('/369mart/home/<string:mode_key>', **_PUBLIC_JSON)
    def home_mode(self, mode_key, **kwargs):
        """One mode only, for a client that loads the second tab later."""
        config = request.env['mart369.home.config'].sudo()._get()
        mode = request.env['mart369.home.mode'].sudo()._get(mode_key)
        if not mode or not mode.active:
            return request.make_json_response(
                {'error': 'unknown_mode', 'mode': mode_key}, status=404)
        return self._respond(mode._serialize(), config)

    @http.route('/369mart/home/health', **_PUBLIC_JSON)
    def health(self, **kwargs):
        """A cheap check that the module is installed and configured."""
        config = request.env['mart369.home.config'].sudo()._get()
        return request.make_json_response({
            'ok': True,
            'modes': config.mode_ids.filtered('active').mapped('key'),
        })

    def _respond(self, payload, config):
        # Do not set Access-Control-Allow-Origin here. Odoo already set it from
        # cors='*' above, and the response headers are extended rather than
        # replaced - setting it again emits it twice and browsers reject that.
        max_age = max(config.cache_seconds or 0, 0)
        return request.make_json_response(payload, headers=[
            ('Cache-Control', 'public, max-age=%d' % max_age),
        ])
