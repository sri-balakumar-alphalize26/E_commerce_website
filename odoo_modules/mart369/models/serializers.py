"""Shared vocabulary and JSON helpers for the 369 Mart home page.

Everything the phone app can draw is listed here, once. The selections below
are deliberately closed: an operator picks an icon or an artwork the app is
known to have, and can never save a value that would render as a blank box.

Keep these lists in step with the storefront:
  ART_CHOICES   <- the ART map at the bottom of components/home/art.jsx
  ICON_CHOICES  <- the P map at the top of components/home/shared.jsx
  TONE_CHOICES  <- the .hm-tone-* rules in components/home/home.css
"""

import logging
import re

from odoo import api, models

_logger = logging.getLogger(__name__)

# Drawn artwork, used when no photo is uploaded. Names must match ART exactly.
ART_CHOICES = [
    ('Adapter', 'Adapter / dongle'),
    ('Apple', 'Apple'),
    ('Banana', 'Banana'),
    ('Bar', 'Bar (chocolate)'),
    ('Basket', 'Basket'),
    ('Board', 'Board (chopping)'),
    ('Bottle', 'Bottle'),
    ('Box', 'Box'),
    ('Cabinet', 'Cabinet (PC case)'),
    ('Cable', 'Cable'),
    ('Charger', 'Charger'),
    ('Cooler', 'Cooler / CPU fan'),
    ('Cpu', 'Processor'),
    ('Flask', 'Flask'),
    ('Gpu', 'Graphics card'),
    ('Grapes', 'Grapes'),
    ('Headphones', 'Headphones'),
    ('Jar', 'Jar'),
    ('Keyboard', 'Keyboard'),
    ('Lamp', 'Lamp'),
    ('Laptop', 'Laptop'),
    ('Leafy', 'Leafy greens'),
    ('Monitor', 'Monitor'),
    ('Motherboard', 'Motherboard'),
    ('Mouse', 'Mouse'),
    ('Onion', 'Onion'),
    ('Orange', 'Orange'),
    ('Pack', 'Pack (staples)'),
    ('Plates', 'Plates'),
    ('Pomegranate', 'Pomegranate'),
    ('Psu', 'Power supply'),
    ('Ram', 'Memory (RAM)'),
    ('Router', 'Router'),
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
    ('bolt', 'Lightning (quick)'),
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
    ('cpu', 'Chip (components)'),
    ('monitor', 'Monitor (displays)'),
    ('keyboard', 'Keyboard (peripherals)'),
    ('wifi', 'Wi-Fi (networking)'),
    ('laptop', 'Laptop (computers)'),
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
    """Helpers every 369 Mart model shares.

    Lived in mart369_home until the home page stopped being the foundation.
    Four modules outside home use it - cart, catalog, order and product - so it
    belongs in the base rather than in one of the options.
    """

    _name = 'mart369.serializable'
    _description = '369 Mart JSON helpers'

    def _lines_to_list(self, text):
        """A textarea of one value per line -> a clean list, blanks dropped."""
        return [ln.strip() for ln in (text or '').splitlines() if ln.strip()]

    def _api_base(self):
        """Prefix for image URLs. Empty means relative, which is what you
        want whenever the app can proxy /web/image to Odoo."""
        return self.env['mart369.config'].sudo()._get().image_base_url or ''

    def _image_url(self, field='image_512', size='256x256', record=None):
        """A /web/image URL the phone app can load without logging in."""
        record = record if record is not None else self
        record.ensure_one()
        return '%s/web/image/%s/%s/%s/%s' % (
            self._api_base(), record._name, record.id, field, size)

    # ---------------------------------------------------- the money

    @api.model
    def _mart369_currency(self, currency=None):
        """Which money the amounts beside this are in.

        The app printed every price through an `inr()` that put a rupee
        sign in front of whatever it was handed, so an Omani shop pricing
        in dollars showed all three at once. It formats what it is told to
        now, and this is the telling - field for field off res.currency, so
        a screen and the invoice for the same order agree.

        It travels with the amounts rather than being asked for once: the
        catalogue is priced by the website's pricelist and an order by its
        own, and an old order keeps the one it was charged in.
        """
        currency = currency or self.env.company.currency_id
        return {
            'code': currency.name or '',
            'symbol': currency.symbol or currency.name or '',
            'position': currency.position or 'before',
            'decimals': currency.decimal_places,
            # How the digits group is the shop's too. Left to the browser, the
            # same rupee price reads 189,000 in one country and 1,89,000 in
            # another - and only one of those is how the shop writes it.
            'locale': (self.env.lang or 'en_US').replace('_', '-'),
        }

    @api.model
    def _mart369_shop_currency(self):
        """The money a browsing shopper is being quoted in.

        The same source `_price_context_for` prices from, so the symbol on a
        card cannot disagree with the number beside it. Outside a website
        request - tests, cron, the shell - that falls back to the company's,
        exactly as the pricing does.
        """
        if 'website' in self.env:
            try:
                website = self.env['website'].get_current_website()
                currency = website.currency_id or website.company_id.currency_id
                if currency:
                    return self._mart369_currency(currency)
            except Exception:  # noqa: BLE001 - not a website request
                pass
        return self._mart369_currency()

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

        # Only picture URLs that lead somewhere. The app draws its placeholder
        # artwork when a card arrives with no images, but an address that
        # 404s is not the same as no address: it renders as an empty frame,
        # and the drawing never gets its turn. A product without a photograph
        # must therefore send no photograph at all.
        images = []
        if product.image_512:
            images.append(self._image_url('image_512', '512x512', record=product))
        for extra in product.product_template_image_ids[:3]:
            if extra.image_512:
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
            except Exception:  # noqa: BLE001
                # `_get_sales_prices` reads `request.pricelist`, so outside a
                # website request - tests, cron, the shell - it raises and the
                # plain sales price is the right answer.
                #
                # Logged rather than swallowed: this used to be silent, and a
                # pricelist that starts failing inside a real request would
                # quietly sell everything at list price with nothing to find
                # afterwards. Debug, because the no-request case is normal and
                # would otherwise fill the log.
                _logger.debug(
                    'mart369: no pricelist price for %s templates, using the '
                    'list price', len(templates), exc_info=True)
                prices = {}

        # Deals are applied here rather than through a pricelist item, because
        # this is the one function the card, the cart bill and the placed
        # order all price through - see mart369_cart/models/deal.py for why.
        deal_prices = {}
        if 'mart369.deal' in self.env:
            deal_prices = self.env['mart369.deal'].sudo()._mart369_price_map(templates)

        ctx = {}
        for tmpl in templates:
            entry = prices.get(tmpl.id) or {}
            price = entry.get('price_reduce')
            if price is None:
                price = tmpl.list_price

            on_offer = deal_prices.get(tmpl.id)
            if on_offer is not None and on_offer < price:
                price = on_offer

            # What to strike through. The pricelist's own "before" price if it
            # gave one, then the hand-set compare price, and failing both the
            # list price - which is the honest answer whenever a customer is
            # being charged less than it, and is what makes a deal show its
            # saving without anyone setting a compare price per product.
            mrp = (entry.get('base_price')
                   or tmpl.compare_list_price
                   or tmpl.list_price
                   or 0.0)
            ctx[tmpl.id] = {
                'price': price,
                'mrp': mrp if mrp and mrp > price else None,
            }
        return ctx

