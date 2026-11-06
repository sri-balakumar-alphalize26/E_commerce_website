"""Put the real rating, popularity and brand on every product card.

`_serialize_product` lives on the shared mixin in mart369_home precisely so the
home feed and the product page cannot drift. Extending it here means a card is
identical wherever it comes from - a home row, a category page, a search result.

Batching matters. `_serialize_product` is called once per card but reads its
prices out of `price_ctx`, a dict the caller built for the whole page in one
pass. The signals ride along in that same dict, so a 40-product page costs two
extra queries in total rather than eighty.

Nothing in mart369_home or mart369_product is edited: both call
`_price_context_for` already, so both pick this up by themselves.
"""

from odoo import models


class Mart369Serializable(models.AbstractModel):
    _inherit = 'mart369.serializable'

    def _price_context_for(self, templates):
        """The prices, plus the three values the app used to fake."""
        ctx = super()._price_context_for(templates)
        if not templates or self.env.context.get('mart369_prices_only'):
            return ctx
        signals = templates._mart369_signal_map()
        for tmpl in templates:
            entry = ctx.setdefault(tmpl.id, {})
            entry.update(signals.get(tmpl.id) or {})
            entry['brand'] = tmpl._mart369_brand()
        return ctx

    def _serialize_product(self, product, line, price_ctx, mode_key=None):
        vals = super()._serialize_product(product, line, price_ctx, mode_key=mode_key)

        entry = price_ctx.get(product.id)
        if entry is None or 'popularity' not in entry:
            # A caller that built its price context before this module was
            # installed, or one product on its own. Correct either way.
            entry = dict(entry or {})
            entry.update((product._mart369_signal_map() or {}).get(product.id) or {})
            entry.setdefault('brand', product._mart369_brand())

        # Empty rather than absent would be worse than useless here: the app
        # reads `p.rating ?? hash(...)`, and null is not undefined, so sending
        # a null rating would show 0 stars instead of falling back. Omit it.
        brand = entry.get('brand')
        if brand:
            vals['brand'] = brand
        if entry.get('rating'):
            vals['rating'] = entry['rating']
            vals['ratingCount'] = entry.get('ratingCount') or 0
        # Popularity is always sent, including zero: a product nobody has
        # bought should sort last, not be handed a random rank by the hash.
        vals['popularity'] = int(entry.get('popularity') or 0)

        facets = self._mart369_facets(product)
        if facets:
            vals['facets'] = facets
        return vals

    def _serialize_suggestion(self, product, price_ctx):
        """One row under the search box: only what that row draws and what its
        add button needs. It answers on every pause in typing, so it skips the
        ratings, sales totals, attribute values and photo gallery of a full
        card. The app merges this into any full card it already holds, so the
        keys left out here are not lost.

        `image` and `thumb` rather than `images` and `thumbs`: those lists would
        overwrite a full card's gallery with one picture."""
        prices = price_ctx.get(product.id) or {}
        price = prices.get('price')
        if price is None:
            price = product.list_price
        vals = {
            'id': str(product.id),
            'name': product.name,
            'unit': product.mart_unit_text or self._mart369_real_unit(product),
            'price': round(price or 0.0, 2),
            'art': product.mart_art or 'Pack',
        }
        if self._mart369_has_picture(product):
            vals['image'] = self._image_url('image_512', '512x512', record=product)
            vals['thumb'] = self._mart369_thumb_url(product)
        if prices.get('mrp'):
            vals['mrp'] = round(prices['mrp'], 2)
        if product.mart_color:
            vals['color'] = product.mart_color
        if product.mart_badge:
            vals['label'] = product.mart_badge
        if product.mart_delivery_text:
            vals['delivery'] = product.mart_delivery_text
        qty = self._mart369_free_qty(product)
        if qty is not None and qty <= 0:
            vals['stock'] = 0
        if self._mart369_has_variants(product):
            vals['variantGroup'] = str(product.id)
            vals['hasVariants'] = True
        return vals

    def _mart369_facets(self, product):
        """[{name, value, image?, color?}]: every attribute value the product
        is offered in - Type (the old sub-category), Brand, RAM... - for the
        category page's filter chips, built in the browser like the brand
        and price filters (catalog_api.py). A Color value brings its colour
        for a dot, a value with an image (Type) its picture."""
        out = []
        lines = product.attribute_line_ids.sorted(
            lambda l: (l.attribute_id.sequence, l.attribute_id.id))
        for line in lines:
            attribute = line.attribute_id
            # bin_size: only whether there is a picture, not its bytes.
            for value in line.value_ids.with_context(bin_size=True):
                facet = {'name': attribute.name, 'value': value.name}
                if attribute.display_type == 'color' and value.html_color:
                    facet['color'] = value.html_color
                if value.image:
                    facet['image'] = self._image_url('image', '128x128', record=value)
                out.append(facet)
        return out
