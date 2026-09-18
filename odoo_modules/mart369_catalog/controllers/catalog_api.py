"""Category pages and the search box.

Same shape as mart369_home's endpoints - type='http' answering a bare JSON body,
public and cached - because the app fetches them the same way.

What these routes deliberately do **not** return is facets. `useProductFilters`
in components/home/Browse.jsx already builds the brand counts and the price
range from the list it is given, and runs every filter and all five sorts in the
browser. Sending facets from here would mean rewriting that hook; sending the
products means it keeps working untouched.
"""

import logging

from odoo import http
from odoo.http import request

from odoo.addons.mart369.controllers.public import _PUBLIC_JSON

_logger = logging.getLogger(__name__)

# The typeahead under the search box shows eight rows (SearchOverlay.jsx).
SUGGEST_LIMIT = 8
# A category page is long but finite; the app filters client-side from here.
BROWSE_LIMIT = 240
SEARCH_LIMIT = 120

# /369mart/search counts what was searched for, so it cannot run on Odoo's
# read-only cursor the way the rest of these routes do. Everything else about it
# is identical to the public feed.
_PUBLIC_COUNTING = dict(_PUBLIC_JSON, readonly=False)

# Recent searches belong to one customer, so they need a session.
_MINE = {
    'type': 'http', 'auth': 'user', 'csrf': False, 'sitemap': False,
}
_MINE_GET = dict(_MINE, methods=['GET'])
_MINE_POST = dict(_MINE, methods=['POST'])
_MINE_DELETE = dict(_MINE, methods=['DELETE'])


class Mart369CatalogApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _cached(self, payload):
        """Answer with the same cache window the home feed uses."""
        config = request.env['mart369.config'].sudo()._get()
        max_age = max(config.cache_seconds or 0, 0)
        return request.make_json_response(payload, headers=[
            ('Cache-Control', 'public, max-age=%d' % max_age),
        ])

    def _cards(self, templates, mode_key=None):
        """Product cards, priced and signalled in one pass for the whole page."""
        mixin = request.env['mart369.serializable'].sudo()
        templates = templates.sudo()
        price_ctx = mixin._price_context_for(templates)
        return [mixin._serialize_product(t, None, price_ctx, mode_key)
                for t in templates]

    def _category(self, slug):
        """A category by its app address, or an empty recordset."""
        return request.env['product.public.category'].sudo().search(
            [('mart_slug', '=', slug), ('mart_in_app', '=', True)], limit=1)

    def _missing(self, what, value):
        return request.make_json_response(
            {'error': 'not_found', what: value}, status=404)

    # ------------------------------------------------------------ the tree

    @http.route('/369mart/catalog', **_PUBLIC_JSON)
    def catalog(self, **kwargs):
        """Every category the app shows, with its sub-categories.

        Shape: {"categories": [{slug, name, mode, tone, accent, blurb,
                                subs: [{slug, name, ...}]}]}
        matching CATALOG in components/home/catalog.js.
        """
        Category = request.env['product.public.category'].sudo()
        tops = Category.search([
            ('mart_in_app', '=', True), ('parent_id', '=', False),
        ], order='sequence, id')
        return self._cached({
            'categories': [c._mart369_serialize() for c in tops],
        })

    # ------------------------------------------------------ a category page

    @http.route(['/369mart/browse/<string:slug>',
                 '/369mart/browse/<string:slug>/<string:sub>'], **_PUBLIC_JSON)
    def browse(self, slug, sub=None, **kwargs):
        """The products of one category, or of one sub-category.

        Shape: {"category": {...}, "items": [card, ...]}. A category with no
        products still answers 200 with an empty list - "Launching soon" is a
        real state, not an error.
        """
        category = self._category(slug)
        if not category:
            return self._missing('category', slug)

        shown = category
        if sub:
            shown = self._category(sub)
            if not shown or shown.parent_id != category:
                return self._missing('sub', sub)

        templates = request.env['product.template'].sudo().search(
            shown._mart369_product_domain(), limit=BROWSE_LIMIT)
        return self._cached({
            'category': category._mart369_serialize(),
            'sub': shown._mart369_serialize(with_subs=False) if sub else None,
            'items': self._cards(templates, category._mart369_mode()),
        })

    # ---------------------------------------------------------- the search

    def _search_domain(self, q):
        """Name, brand, pack size or category - what a shopper would type."""
        return [
            ('is_published', '=', True),
            '|', '|', '|',
            ('name', 'ilike', q),
            ('mart_brand', 'ilike', q),
            ('mart_unit_text', 'ilike', q),
            ('public_categ_ids.name', 'ilike', q),
        ]

    def _search(self, q, limit):
        q = (q or '').strip()
        if not q:
            return request.env['product.template'].browse()
        return request.env['product.template'].sudo().search(
            self._search_domain(q), limit=limit)

    @http.route('/369mart/search', **_PUBLIC_COUNTING)
    def search(self, q=None, **kwargs):
        """Search results. Also what makes Trending true."""
        templates = self._search(q, SEARCH_LIMIT)
        items = self._cards(templates)
        # Counted after the search, never before: a term that found nothing is
        # worth recording too, but only as the gap it is.
        request.env['mart369.search.term'].sudo()._mart369_record(q, len(items))
        return self._cached({'q': (q or '').strip(), 'items': items})

    @http.route('/369mart/search/suggest', **_PUBLIC_JSON)
    def suggest(self, q=None, **kwargs):
        """The eight rows under the search box as someone types.

        Not counted: every keystroke would arrive here, so counting would make
        "coff" as trending as "coffee".
        """
        templates = self._search(q, SUGGEST_LIMIT)
        return self._cached({'q': (q or '').strip(),
                             'items': self._cards(templates)})

    @http.route('/369mart/search/trending', **_PUBLIC_JSON)
    def trending(self, **kwargs):
        """Shape: {"trending": ["coffee beans", ...]} - the app prints these
        as they are, so they are already normalised."""
        return self._cached({
            'trending': request.env['mart369.search.term'].sudo()._mart369_trending(),
        })

    # -------------------------------------------------- my recent searches

    def _me(self):
        return request.env.user.partner_id

    def _recent(self, found):
        return request.make_json_response({'ok': True, 'recent': found})

    @http.route('/369mart/search/recent', **_MINE_GET)
    def recent(self, **kwargs):
        return self._recent(self._me()._mart369_recent_list())

    @http.route('/369mart/search/recent', **_MINE_POST)
    def recent_add(self, **kwargs):
        try:
            body = request.get_json_data()
        except Exception:  # noqa: BLE001 - an empty or broken body is a 400
            body = None
        term = (body or {}).get('q') if isinstance(body, dict) else None
        if not term:
            return request.make_json_response(
                {'ok': False, 'error': 'Send the search text as q.'}, status=400)
        return self._recent(self._me()._mart369_recent_add(term))

    @http.route('/369mart/search/recent', **_MINE_DELETE)
    def recent_clear(self, **kwargs):
        return self._recent(self._me()._mart369_recent_clear())
