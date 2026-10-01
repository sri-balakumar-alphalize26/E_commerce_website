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

from odoo import api, fields, models

from odoo.addons.mart369_product.models.product_template import (
    ProductTemplate as DeskProductTemplate)

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

    # ------------------------------------------- the website category follows

    # A product's website category is the twin of its Product Category
    # (product_category.py), so the Products desk asks for Category only.
    MART_DESK_HELP = dict(
        DeskProductTemplate.MART_DESK_HELP,
        categ_id="Required. Where the product is listed: on the website, and "
                 "in WhatsApp's NEW ORDER menu. Its vendors are asked for a "
                 "price when this is out of stock.")

    @api.model
    def _mart369_desk_groups(self):
        return [(title, [n for n in names if n != 'public_categ_ids'])
                for title, names in super()._mart369_desk_groups()]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._mart369_follow_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._mart369_follow_vals(vals)
        return super().write(vals)

    @api.model
    def _mart369_follow_vals(self, vals):
        """A Category being set brings its website twin along. A Category
        with no twin (an internal one) leaves the website category alone."""
        if vals.get('categ_id'):
            mirror = self.env['product.category'].browse(vals['categ_id']).sudo().mart_mirror_id
            if mirror:
                vals['public_categ_ids'] = [(6, 0, mirror.ids)]

    def _mart369_follow_category(self):
        """Put these products under their Category's twin."""
        for categ in self.categ_id:
            mirror = categ.sudo().mart_mirror_id
            if mirror:
                self.filtered(lambda t: t.categ_id == categ).write(
                    {'public_categ_ids': [(6, 0, mirror.ids)]})

    @api.onchange('categ_id')
    def _onchange_mart_categ_follow(self):
        """The same on Odoo's own form, before Save - and a new product put
        in a shop category is published, as a website category would."""
        for product in self:
            mirror = product.categ_id.sudo().mart_mirror_id
            if mirror:
                product.public_categ_ids = mirror
        self._onchange_mart_publish_with_category()
