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
        if not templates:
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
        return vals
