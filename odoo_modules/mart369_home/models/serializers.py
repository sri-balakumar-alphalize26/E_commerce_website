"""Shared vocabulary and JSON helpers for the 369 Mart home page.

Everything the phone app can draw is listed here, once. The selections below
are deliberately closed: an operator picks an icon or an artwork the app is
known to have, and can never save a value that would render as a blank box.

Keep these lists in step with the storefront:
  ART_CHOICES   <- the ART map at the bottom of components/home/art.jsx
  ICON_CHOICES  <- the P map at the top of components/home/shared.jsx
  TONE_CHOICES  <- the .hm-tone-* rules in components/home/home.css
"""

import re

from odoo import models

# Drawn artwork, used when no photo is uploaded. Names must match ART exactly.
ART_CHOICES = [
    ('Apple', 'Apple'),
    ('Banana', 'Banana'),
    ('Bar', 'Bar (chocolate)'),
    ('Basket', 'Basket'),
    ('Board', 'Board (chopping)'),
    ('Bottle', 'Bottle'),
    ('Box', 'Box'),
    ('Charger', 'Charger'),
    ('Flask', 'Flask'),
    ('Grapes', 'Grapes'),
    ('Headphones', 'Headphones'),
    ('Jar', 'Jar'),
    ('Lamp', 'Lamp'),
    ('Leafy', 'Leafy greens'),
    ('Onion', 'Onion'),
    ('Orange', 'Orange'),
    ('Pack', 'Pack (staples)'),
    ('Plates', 'Plates'),
    ('Pomegranate', 'Pomegranate'),
    ('Soap', 'Soap bottle'),
    ('SoapBar', 'Soap bar'),
    ('Speaker', 'Speaker'),
    ('Ssd', 'SSD / storage'),
    ('Tomato', 'Tomato'),
    ('Towels', 'Towels'),
    ('Webcam', 'Webcam'),
]

# Tab icons.
ICON_CHOICES = [
    ('bag', 'Shopping bag'),
    ('basket', 'Basket'),
    ('leaf', 'Leaf (fresh)'),
    ('plug', 'Plug (electronics)'),
    ('pot', 'Pot (kitchen)'),
    ('pen', 'Pen (stationery)'),
    ('ticket', 'Ticket (offers)'),
    ('grid', 'Grid (everything)'),
    ('shirt', 'Shirt (fashion)'),
    ('book', 'Book'),
]

# Banner background gradients.
TONE_CHOICES = [
    ('green', 'Green'),
    ('navy', 'Navy'),
    ('brown', 'Brown'),
    ('orange', 'Orange'),
    ('teal', 'Teal'),
    ('indigo', 'Indigo'),
]

# Same gradients as .hm-tone-* in home.css, for the in-form previews.
TONE_CSS = {
    'green': 'linear-gradient(120deg, #13613c, #2d9a5a)',
    'navy': 'linear-gradient(120deg, #083b59, #0a78ab)',
    'brown': 'linear-gradient(120deg, #7a4326, #b8774a)',
    'orange': 'linear-gradient(120deg, #d86a0c, #f7a23a)',
    'teal': 'linear-gradient(120deg, #0e5a63, #1c8c8f)',
    'indigo': 'linear-gradient(120deg, #26306b, #4a5bb0)',
}

_SLUG_STRIP = re.compile(r'[^a-z0-9]+')


def slugify(value):
    """'Fresh Fruits!' -> 'fresh-fruits'. Used to fill an empty key."""
    return _SLUG_STRIP.sub('-', (value or '').strip().lower()).strip('-')


class Mart369Serializable(models.AbstractModel):
    """Helpers every home-page model shares."""

    _name = 'mart369.home.serializable'
    _description = '369 Mart JSON helpers'

    def _lines_to_list(self, text):
        """A textarea of one value per line -> a clean list, blanks dropped."""
        return [ln.strip() for ln in (text or '').splitlines() if ln.strip()]

    def _api_base(self):
        """Prefix for image URLs. Empty means relative, which is what you
        want whenever the app can proxy /web/image to Odoo."""
        return self.env['mart369.home.config'].sudo()._get().image_base_url or ''

    def _image_url(self, field='image_512', size='256x256', record=None):
        """A /web/image URL the phone app can load without logging in."""
        record = record if record is not None else self
        record.ensure_one()
        return '%s/web/image/%s/%s/%s/%s' % (
            self._api_base(), record._name, record.id, field, size)

    # ------------------------------------------------- the product card

    def _serialize_product(self, product, line, price_ctx, mode_key=None):
        """One product card, exactly as the app expects it.

        The single place that decides what the app receives about a
        product. It lives on the mixin, not on the home section, so the
        product page can emit an identical card - two copies would drift.

        `line` carries per-placement overrides (a hand-picked product in
        a home row); pass None when there is none. `mode_key` is "quick"
        or "all" - only "all" gets a delivery time.
        """
        prices = price_ctx.get(product.id) or {}
        price = prices.get('price')
        if price is None:
            price = product.list_price
        mrp = prices.get('mrp')

        images = [self._image_url('image_512', '512x512', record=product)]
        for extra in product.product_template_image_ids[:3]:
            images.append(self._image_url('image_512', '512x512', record=extra))

        def pick(field, fallback):
            """A line override beats the product's own value."""
            value = getattr(line, field, False) if line else False
            return value or fallback

        vals = {
            'id': str(product.id),
            'images': images,
            'name': pick('name_override', product.name),
            'unit': pick('unit_override',
                         product.mart_unit_text or product.uom_name or ''),
            'price': round(price or 0.0, 2),
            'art': pick('art_override', product.mart_art or 'Pack'),
        }

        # Optional keys are left out entirely, never sent as null.
        if mrp:
            vals['mrp'] = round(mrp, 2)
        if product.mart_is_veg:
            vals['veg'] = True

        colour = pick('color_override', product.mart_color)
        if colour:
            vals['color'] = colour
        badge = pick('label_override', product.mart_badge)
        if badge:
            vals['label'] = badge
        note = pick('note_override', product.mart_note)
        if note:
            vals['note'] = note
        tag = pick('tag_override', product.mart_home_tag)
        if tag:
            vals['tag'] = tag
        if product.mart_per_unit:
            vals['perUnit'] = product.mart_per_unit

        # `delivery` is what tells the app an item belongs to Express.
        if mode_key == 'all':
            delivery = pick('delivery_override', product.mart_delivery_text)
            if delivery:
                vals['delivery'] = delivery

        if 'free_qty' in product._fields:
            qty = product.free_qty
            if qty <= 0:
                vals['stock'] = 0
            elif product.mart_low_stock_at and qty <= product.mart_low_stock_at:
                vals['low'] = int(qty)

        return vals

    # ------------------------------------------------------ the prices

    def _price_context_for(self, templates):
        """{template_id: {'price': x, 'mrp': y or None}} for these
        products, priced with the website pricelist in a single pass.

        Doing this per product instead would fire one pricelist
        computation per card - the quickest way to make an endpoint slow.
        """
        if not templates:
            return {}

        prices = {}
        if 'website' in self.env:
            website = self.env['website'].get_current_website()
            try:
                prices = templates._get_sales_prices(website)
            except Exception:
                # Called outside a website request (tests, cron, shell):
                # fall back to the plain sales price.
                prices = {}

        ctx = {}
        for tmpl in templates:
            entry = prices.get(tmpl.id) or {}
            price = entry.get('price_reduce')
            if price is None:
                price = tmpl.list_price
            mrp = entry.get('base_price') or tmpl.compare_list_price or 0.0
            ctx[tmpl.id] = {
                'price': price,
                'mrp': mrp if mrp and mrp > price else None,
            }
        return ctx

