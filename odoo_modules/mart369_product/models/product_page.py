"""Assembling one product page.

Kept on a model rather than in the controller so the same code answers the
app, the tests and the builder preview. A controller method would need an
HTTP request to exist, which is exactly what made this untestable before.
"""

from odoo import api, fields, models

# Reviews that count: really submitted, publicly visible, actually rated,
# and not taken down by staff.
#
# There is a second copy of this list: `RATING_DOMAIN` in
# mart369_catalog/models/product_template.py, which feeds the star on every
# card. Neither module depends on the other, so the two cannot share a
# constant - change one and change the other, or a hidden review stays out of
# the page while its score still moves the average on every listing.
REVIEW_DOMAIN = [
    ('consumed', '=', True),
    ('is_internal', '=', False),
    ('rating', '>=', 1),
    ('mart369_state', '=', 'published'),
]


class Mart369ProductPage(models.AbstractModel):
    _name = 'mart369.product.page'
    _description = '369 Mart Product Page Payload'

    # (builder field key, the card's part it switches): left out of the page's
    # cards when the field is not shown.
    SWITCHED_PARTS = (
        ('variant_specs', 'specs'),
        ('sales_description', 'description'),
        ('mrp', 'mrp'),
        ('low_stock', 'low'),
    )

    # --------------------------------------------------------- the whole page

    @api.model
    def payload(self, product, variant=None):
        """Exactly what components/home/ProductDetail.jsx consumes.

        For a product with a choice (Brand, RAM, Colour...) `p` is one
        variant's card - the one asked for, else the default - `variants` is
        every variant's card and `attrs` the questions, in attribute order.
        Otherwise both are empty and `p` is the product's card, as before."""
        helper = self.env['mart369.serializable'].sudo()
        Field = self.env['mart369.product.field'].sudo()

        shown = Field._resolve_sections(product)
        keys = {f.key for rows in shown.values() for f, _v in rows}

        bundle = self._bundle(product, keys)
        similar = self._similar(product, keys)
        related = self._related(product, keys, bundle, similar)

        everything = product | bundle | similar | related
        price_ctx = helper._price_context_for(everything)
        mode_key = 'all' if product.mart_delivery_text else 'quick'

        def card(tmpl):
            return helper._serialize_product(tmpl, None, price_ctx, mode_key)

        own = card(product)
        variants, attrs, main = [], [], own
        if helper._mart369_has_variants(product):
            siblings = product.sudo().product_variant_ids
            variants = helper._serialize_variants(siblings, mode_key, price_ctx=price_ctx)
            attrs = helper._mart369_attrs(product)
            chosen = (variant if variant and variant in siblings
                      else self._default_variant(siblings))
            main = next(c for c in variants
                        if c['id'] == helper._mart369_variant_key(chosen))
        elif product.product_variant_id:
            # No choice to make: the product's one variant still carries the
            # setup's facts - its photos, its specs table - and the page
            # shows them, with the Sales Description, as for any variant.
            single = product.sudo().product_variant_id
            main = dict(own, images=helper._mart369_variant_images(single) or own['images'])
            specs = helper._mart369_variant_specs(single)
            if specs:
                main['specs'] = specs
            description = helper._mart369_description(product)
            if description:
                main['description'] = description

        # What the builder switched off (shop-wide, by category or for this
        # product) leaves the page's cards, so the website does not draw it.
        # These cards only: the listings, the cart and orders keep theirs.
        # The desk's read view asks for everything (`mart369_page_all_parts`)
        # to show a switched-off part as switched off, value and all.
        main = dict(main)
        variants = [dict(v) for v in variants]
        if not self.env.context.get('mart369_page_all_parts'):
            for card_vals in [main] + variants:
                for key, part in self.SWITCHED_PARTS:
                    if key not in keys:
                        card_vals.pop(part, None)

        return {
            'p': main,
            # The product's own card too: a basket or wishlist holding the
            # product's id (not a variant's) must still resolve from here.
            'card': own,
            'd': self.details(product, shown, keys),
            'variants': variants,
            'attrs': attrs,
            'bundle': [card(b) for b in bundle],
            'similar': [card(s) for s in similar],
            'related': [card(r) for r in related],
        }

    @api.model
    def _default_variant(self, variants):
        """The variant a bare product link opens on: the first one in stock."""
        storable = variants[:1].product_tmpl_id
        if 'free_qty' in variants._fields and (
                'is_storable' not in storable._fields or storable.is_storable):
            in_stock = variants.filtered(lambda v: v.free_qty > 0)
            if in_stock:
                return in_stock[0]
        return variants[0]

    # ------------------------------------------------------------- the d block

    @api.model
    def details(self, product, shown=None, keys=None):
        """Everything the page shows around the product card."""
        Field = self.env['mart369.product.field'].sudo()
        if shown is None:
            shown = Field._resolve_sections(product)
        if keys is None:
            keys = {f.key for rows in shown.values() for f, _v in rows}

        values = {f.key: v for rows in shown.values() for f, v in rows}
        d = {}
        # The product's own setup - its specs and Sales Description - rides
        # on the card (`p`); this block is the category and the real reviews.
        category = product.public_categ_ids[:1]
        if category:
            d['category'] = category.name

        d.update(self.reviews(product, keys, values))
        return d

    @api.model
    def _as_text(self, field, value, product):
        """A table cell: a readable string, or '' to leave the row out."""
        if value in (None, False, ''):
            return ''
        if field.value_kind == 'bool':
            return 'Yes' if self._as_bool(value) else 'No'
        if isinstance(value, float):
            text = ('%.2f' % value).rstrip('0').rstrip('.')
            if field.odoo_field == 'weight' and product.weight_uom_name:
                text = '%s %s' % (text, product.weight_uom_name)
            return text
        return str(value)

    @api.model
    def _as_bool(self, value):
        if isinstance(value, bool):
            return value
        return str(value or '').strip().lower() in ('1', 'true', 'yes', 'y', 'on')

    # ---------------------------------------------------------- the reviews

    @api.model
    def reviews(self, product, keys, values):
        """Real customer reviews, from Odoo's own rating records.

        Read straight off rating.rating rather than product.rating_avg: that
        field is restricted to internal users, so on a public route it would
        silently read as zero for everyone.
        """
        if 'reviews' not in keys and 'rating' not in keys:
            return {}

        ratings = self.env['rating.rating'].sudo().search(
            REVIEW_DOMAIN + [('res_model', '=', 'product.template'),
                             ('res_id', '=', product.id)],
            order='create_date desc')

        out = {}
        if not ratings:
            # No reviews yet: say so, rather than inventing any.
            out['reviews'] = []
            if 'review_empty' in keys and values.get('review_empty'):
                out['reviewsEmptyText'] = values['review_empty']
            return out

        scores = [r.rating for r in ratings]
        if 'rating' in keys:
            out['rating'] = round(sum(scores) / len(scores), 1)
        if 'rating_count' in keys:
            out['ratingCount'] = len(ratings)
        if 'rating_bars' in keys:
            buckets = {n: 0 for n in range(1, 6)}
            for score in scores:
                buckets[min(5, max(1, int(round(score))))] += 1
            # [5*, 4*, 3*, 2*, 1*] - the order the app draws the bars.
            out['dist'] = [round(buckets[n] * 100 / len(ratings))
                           for n in (5, 4, 3, 2, 1)]

        if 'reviews' in keys:
            out['reviews'] = [{
                'name': r.partner_id.name or 'Customer',
                'stars': int(round(r.rating)),
                'when': self._ago(r.create_date),
                'text': r.feedback or '',
                'helpful': 0,
            } for r in ratings[:20]]
        return out

    @api.model
    def _ago(self, when):
        """"2 weeks ago" - the app prints this string as it is."""
        if not when:
            return ''
        days = (fields.Datetime.now() - when).days
        if days <= 0:
            return 'today'
        if days == 1:
            return 'yesterday'
        if days < 7:
            return '%d days ago' % days
        if days < 30:
            weeks = days // 7
            return '%d week%s ago' % (weeks, '' if weeks == 1 else 's')
        if days < 365:
            months = days // 30
            return '%d month%s ago' % (months, '' if months == 1 else 's')
        years = days // 365
        return '%d year%s ago' % (years, '' if years == 1 else 's')

    # ------------------------------------------------- the surrounding rows

    @api.model
    def _published(self, templates, exclude=None):
        exclude = exclude or self.env['product.template'].browse()
        return templates.filtered(lambda t: t.is_published and t not in exclude)

    @api.model
    def _bundle(self, product, keys):
        """Frequently bought together: what the shop curated, else a guess."""
        if 'bundle_items' not in keys:
            return self.env['product.template'].browse()
        # accessory_product_ids are product.product, so map back to templates
        # or every mart_* read would be against the wrong record.
        curated = self._published(product.accessory_product_ids.product_tmpl_id,
                                  exclude=product)
        if curated:
            return curated[:2]
        return self._guess(product)[:2]

    @api.model
    def _similar(self, product, keys):
        if 'similar_items' not in keys:
            return self.env['product.template'].browse()
        curated = self._published(product.alternative_product_ids, exclude=product)
        if curated:
            return curated[:12]
        return self._guess(product)[:12]

    @api.model
    def _related(self, product, keys, bundle, similar):
        if 'related_items' not in keys:
            return self.env['product.template'].browse()
        return self._guess(product, exclude=product | bundle | similar)[:10]

    @api.model
    def _guess(self, product, exclude=None):
        """Products from the same shop category, in stock and cheapest first."""
        Template = self.env['product.template'].sudo()
        categories = product.public_categ_ids
        if not categories:
            return Template.browse()
        found = Template.search([
            ('is_published', '=', True),
            ('id', '!=', product.id),
            ('public_categ_ids', 'in', categories.ids),
        ], limit=40)
        if exclude:
            found = found.filtered(lambda t: t not in exclude)
        in_stock = found.filtered(
            lambda t: 'free_qty' not in t._fields or t.free_qty > 0)
        return (in_stock or found).sorted(key=lambda t: t.list_price)
