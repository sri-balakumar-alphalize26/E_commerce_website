"""The three values the app used to invent for itself.

`enrich()` in components/home/catalog.js fills in a product's rating,
popularity and brand when the card does not carry them - and it fills them from
a hash of the product id:

    p.rating = p.rating ?? Math.round((3.8 + (h % 12) / 10) * 10) / 10;
    p.popularity = p.popularity ?? h % 1000;
    p.brand = p.brand || p.unit || "369 Mart";

So "sort by customer rating" sorted by a hash, "most popular" was a hash, and a
laptop's brand was whatever sat in its pack-size column. Those two hashes also
rank search results and pick every "similar" and "bought together" rail.

The fix needs no change in the app: `??` and `||` mean a card that *does* carry
the value wins, so supplying them here retires the fakes quietly.
"""

from odoo import fields, models

# A review only counts once the customer has actually been asked for it, and
# only while staff are still showing it.
#
# Kept in step with `REVIEW_DOMAIN` in
# mart369_product/models/product_page.py by hand - see the note there.
RATING_DOMAIN = [
    ('consumed', '=', True),
    ('is_internal', '=', False),
    ('rating', '>=', 1),
    ('mart369_state', '=', 'published'),
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    mart_brand = fields.Char(
        string='Brand',
        help="Shown on the card and used as the Brand filter on a category "
             "page. Empty falls back to the pack size, which is what the app "
             "does today - so a pair of headphones ends up branded '1 pair'.")

    # ----------------------------------------------------------- the signals

    def _mart369_signal_map(self):
        """{template_id: {'rating': 4.6, 'ratingCount': 12, 'popularity': 37}}

        Two grouped queries for the whole recordset, in the same spirit as
        `_price_context_for` on the home mixin: one pricelist pass for a page,
        not one per card.
        """
        if not self:
            return {}

        signals = {tmpl.id: {'rating': None, 'ratingCount': 0, 'popularity': 0}
                   for tmpl in self}

        # Ratings. Read rating.rating rather than product.rating_avg: that
        # field is restricted to internal users, so on a public route it reads
        # as zero for everyone. mart369_product's reviews() does the same.
        groups = self.env['rating.rating'].sudo()._read_group(
            RATING_DOMAIN + [('res_model', '=', 'product.template'),
                             ('res_id', 'in', self.ids)],
            groupby=['res_id'], aggregates=['rating:avg', '__count'])
        for res_id, average, count in groups:
            if res_id in signals and count:
                signals[res_id]['rating'] = round(average, 1)
                signals[res_id]['ratingCount'] = count

        # Popularity: how many of each has actually been sold. Confirmed
        # orders only, so a draft basket cannot push a product up the list.
        if 'sale.order.line' in self.env:
            variants = self.env['product.product'].sudo().search(
                [('product_tmpl_id', 'in', self.ids)])
            if variants:
                sold = self.env['sale.order.line'].sudo()._read_group(
                    [('product_id', 'in', variants.ids),
                     ('state', '=', 'sale')],
                    groupby=['product_id'], aggregates=['product_uom_qty:sum'])
                for variant, qty in sold:
                    tmpl_id = variant.product_tmpl_id.id
                    if tmpl_id in signals:
                        signals[tmpl_id]['popularity'] += int(qty or 0)
        return signals

    def _mart369_brand(self):
        """What the Brand filter groups by."""
        self.ensure_one()
        return self.mart_brand or ''
