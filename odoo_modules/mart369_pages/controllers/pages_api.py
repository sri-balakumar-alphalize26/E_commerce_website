"""The footer pages, read by the shop. Public: they are the shop's own words."""

from odoo import http
from odoo.http import request

_GET = {'type': 'http', 'auth': 'public', 'methods': ['GET'], 'csrf': False, 'sitemap': False}


class Mart369PagesApi(http.Controller):

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status, headers=[
            ('Cache-Control', 'public, max-age=60'),
        ])

    @http.route('/369mart/pages', **_GET)
    def pages(self, **kwargs):
        """The footer's columns of page links."""
        return self._json({'ok': True, 'columns': request.env['mart369.info.page']._mart369_footer_columns()})

    @http.route('/369mart/footer', **_GET)
    def footer(self, **kwargs):
        """The footer: tagline, app links, payment chips, the Shop column's
        categories and the page columns - all set in Odoo."""
        return self._json(dict(request.env['mart369.config']._mart369_footer(), ok=True))

    @http.route('/369mart/pages/<string:slug>', **_GET)
    def page(self, slug, **kwargs):
        page = request.env['mart369.info.page'].sudo().search([('slug', '=', slug)], limit=1)
        if not page:
            return self._json({'ok': False, 'error': 'No such page.'}, status=404)
        return self._json(dict(page._mart369_serialize(), ok=True))
