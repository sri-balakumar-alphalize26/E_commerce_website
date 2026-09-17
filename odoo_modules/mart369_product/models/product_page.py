"""Assembling one product page.

Kept on a model rather than in the controller so the same code answers the
app, the tests and the builder preview. A controller method would need an
HTTP request to exist, which is exactly what made this untestable before.
"""

from odoo import api, fields, models
from odoo.tools import is_html_empty

# Reviews that count: really submitted, publicly visible, actually rated.
REVIEW_DOMAIN = [
    ('consumed', '=', True),
    ('is_internal', '=', False),
    ('rating', '>=', 1),
]


class Mart369ProductPage(models.AbstractModel):
    _name = 'mart369.product.page'
    _description = '369 Mart Product Page Payload'

    # --------------------------------------------------------- the whole page

    @api.model
    def payload(self, product):
        """Exactly what components/home/ProductDetail.jsx consumes."""
        helper = self.env['mart369.home.serializable'].sudo()
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

        return {
            'p': card(product),
            'd': self.details(product, shown, keys),
            'variants': [],
            'bundle': [card(b) for b in bundle],
            'similar': [card(s) for s in similar],
            'related': [card(r) for r in related],
        }

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
        helper = self.env['mart369.home.serializable'].sudo()
        d = {}

        if 'brand' in keys and values.get('brand'):
            d['brand'] = values['brand']
        category = product.public_categ_ids[:1]
        if category:
            d['category'] = category.name

        if 'features' in keys:
            features = helper._lines_to_list(values.get('features'))
            if features:
                d['features'] = features

        # The information table keeps its order and its labels. The veg row is
        # the literal "veg", which the app draws as the green square.
        info = []
        for field, value in shown.get('info', []):
            if field.key == 'veg':
                if value:
                    info.append([field.name, 'veg'])
                continue
            text = self._as_text(field, value, product)
            if text:
                info.append([field.name, text])
        if info:
            d['info'] = info

        specs = {}
        for field, value in shown.get('specs', []):
            text = self._as_text(field, value, product)
            if text:
                specs[field.name] = text
        if specs:
            d['specs'] = specs

        if 'description' in keys:
            description = values.get('description')
            if is_html_empty(description):
                description = product.description_sale or ''
            if description:
                d['description'] = description
        if 'disclaimer' in keys and values.get('disclaimer'):
            d['disclaimer'] = values['disclaimer']

        if 'returnable' in keys:
            d['returnable'] = self._as_bool(values.get('returnable'))
        if 'return_text' in keys and values.get('return_text'):
            d['returnText'] = values['return_text']
        if 'policy_link' in keys and values.get('policy_link'):
            d['policyUrl'] = values['policy_link']

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
