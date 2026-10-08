"""Shared vocabulary and JSON helpers for the 369 Mart home page.

Everything the phone app can draw is listed here, once. The selections below
are deliberately closed: an operator picks an icon or an artwork the app is
known to have, and can never save a value that would render as a blank box.

Keep these lists in step with the storefront:
  ART_CHOICES   <- the ART map at the bottom of components/home/art.jsx
  ICON_CHOICES  <- the P map at the top of components/home/shared.jsx
  TONE_CHOICES  <- the .hm-tone-* rules in components/home/home.css

The two built-in logo lists are also copied, with labels, into LOGO_ICONS and
LOGO_ART in components/admin/LogoField.jsx. Odoo's screens cannot draw
art.jsx, so each drawing is also a file in static/img/art/; after changing a
drawing, run `node scripts/export-art.mjs`.
"""

import logging
import re

from odoo import api, fields, models
from odoo.tools import html2plaintext, html_sanitize

_logger = logging.getLogger(__name__)

# Drawn artwork, used when no photo is uploaded. Names must match ART exactly.
# How many gallery photos beyond the main one reach the app. It was 3, which
# silently dropped a fourth: the storefront gallery pages through whatever it
# is given and has no fixed size, so nothing anywhere said no. A bound is still
# wanted - a product somebody has put forty photos on should not put forty URLs
# in every card payload - but it should be high enough that nobody meets it by
# accident.
MAX_EXTRA_IMAGES = 12

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
        """A /web/image URL the phone app can load without logging in.

        Its save time rides on the end. Without it Odoo answers every
        picture "no-cache", so a phone asks again for all of them on every
        screen; with it the answer is "keep for a year", and a replaced
        picture gets a new address instead of hiding behind the old one.
        """
        record = record if record is not None else self
        record.ensure_one()
        stamp = int(record.write_date.timestamp()) if record.write_date else 0
        return '%s/web/image/%s/%s/%s/%s?unique=%d' % (
            self._api_base(), record._name, record.id, field, size, stamp)

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
        for extra in product.product_template_image_ids[:MAX_EXTRA_IMAGES]:
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
            'unit': pick('unit_override', product.mart_unit_text or self._mart369_real_unit(product)),
            'price': round(price or 0.0, 2),
            'art': pick('art_override', product.mart_art or 'Pack'),
        }

        # Optional keys are left out entirely, never sent as null.
        if mrp:
            vals['mrp'] = round(mrp, 2)
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

        qty = self._mart369_free_qty(product)
        if qty is not None:
            if qty <= 0:
                vals['stock'] = 0
            elif product.mart_low_stock_at and qty <= product.mart_low_stock_at:
                vals['low'] = int(qty)

        # A product with a choice to make (Brand, RAM, Colour...). This card
        # stands for the whole model line in a listing; the product page swaps
        # in the chosen variant's own card (_serialize_variant), and the app
        # opens the page rather than adding a variant nobody picked.
        if self._mart369_has_variants(product):
            vals['variantGroup'] = str(product.id)
            vals['hasVariants'] = True

        return vals

    # ------------------------------------------------------- the variants

    @api.model
    def _mart369_has_variants(self, template):
        """True when the customer has something to choose on this product."""
        return template.product_variant_count > 1

    @api.model
    def _mart369_variant_key(self, variant):
        """The id the app holds for one variant: 'v' + its product.product id.

        Plain numbers stay template ids, so every basket, list and link made
        before variants existed still means what it meant."""
        return 'v%d' % variant.id

    @api.model
    def _mart369_card_key(self, variant):
        """The id of the card a sold variant belongs to: its own key when its
        product has a choice, else the template id the app has always used."""
        tmpl = variant.product_tmpl_id
        if self._mart369_has_variants(tmpl):
            return self._mart369_variant_key(variant)
        return str(tmpl.id)

    @api.model
    def _mart369_parse_key(self, key):
        """'41' -> ('template', 41), 'v123' -> ('variant', 123), else None."""
        key = str(key or '').strip()
        if key[:1] == 'v' and key[1:].isdigit():
            return 'variant', int(key[1:])
        if key.isdigit():
            return 'template', int(key)
        return None

    @api.model
    def _mart369_published_variants(self, ids):
        """The variants behind these ids whose product is on the website."""
        return self.env['product.product'].sudo().search([
            ('id', 'in', list(ids)),
            ('product_tmpl_id.is_published', '=', True),
        ])

    @api.model
    def _mart369_combo(self, variant):
        """{attribute id: template value id} for the attributes that are asked
        - a line with a single value (Brand: Apple) is not a question."""
        combo = {}
        for ptav in variant.product_template_attribute_value_ids:
            if len(ptav.attribute_line_id.value_ids) > 1:
                combo[str(ptav.attribute_id.id)] = ptav.id
        return combo

    @api.model
    def _mart369_attrs(self, template):
        """The questions the product page asks, in the attributes' order:
        [{id, name, display, values: [{id, name, color}]}].

        Only attributes that make variants and have a real choice: one value
        (Brand: Apple) is not a question, and a 'never create variants' one
        (Gift wrap) has no variant that could answer it."""
        out = []
        lines = template.attribute_line_ids.sorted(
            lambda l: (l.attribute_id.sequence, l.attribute_id.id))
        for line in lines:
            if len(line.value_ids) < 2 or line.attribute_id.create_variant == 'no_variant':
                continue
            values = line.product_template_value_ids.filtered('ptav_active')
            out.append({
                'id': str(line.attribute_id.id),
                'name': line.attribute_id.name,
                'display': line.attribute_id.display_type or 'radio',
                'values': [{
                    'id': v.id,
                    'name': v.name,
                    **({'color': v.html_color} if v.html_color else {}),
                } for v in values.sorted(lambda v: (v.product_attribute_value_id.sequence, v.id))],
            })
        return out

    @api.model
    def _mart369_real_unit(self, product):
        """The product's unit of measure when it says something ("500 g",
        "1 L"); nothing for Odoo's default "Units", which tells a shopper
        nothing and printed under every card."""
        name = (product.uom_name or '').strip()
        return '' if name.lower() in ('unit', 'units') else name

    @api.model
    def _mart369_gallery_item(self, image):
        """One `product.image` (Odoo's Extra Product / Variant Media) as a
        gallery entry: a photo, or a video with its picture as the poster.
        None for a row with neither."""
        poster = (self._image_url('image_512', '512x512', record=image)
                  if image.image_512 else None)
        if image.video_url:
            embed = None
            try:
                from odoo.addons.html_editor.tools import get_video_url_data
                embed = (get_video_url_data(image.video_url) or {}).get('embed_url')
            except Exception:  # noqa: BLE001 - a bad link is just not shown
                embed = None
            if embed:
                src = 'https:' + embed if embed.startswith('//') else embed
                return dict({'type': 'video', 'src': src}, **({'poster': poster} if poster else {}))
        if poster:
            return {'type': 'photo', 'src': poster}
        return None

    @api.model
    def _mart369_variant_media(self, variant):
        """The gallery for one variant, in order: [{type, src, poster?}].

        Its own first - the variant's image, then its Extra Variant Media
        (website_sale `product_variant_image_ids`). The product's picture and
        Extra Product Media only when the variant has nothing of its own, so a
        red phone never shows the white one's photo. Never the attribute
        value's image: that is the option button's icon, shared by every
        product."""
        tmpl = variant.product_tmpl_id
        own = []
        if variant.image_variant_1920:
            own.append({'type': 'photo',
                        'src': self._image_url('image_512', '512x512', record=variant)})
        if 'product_variant_image_ids' in variant._fields:
            for image in variant.product_variant_image_ids.sorted(
                    lambda i: (i.sequence, i.id))[:MAX_EXTRA_IMAGES]:
                item = self._mart369_gallery_item(image)
                if item:
                    own.append(item)
        if own:
            return own
        shared = []
        if tmpl.image_512:
            shared.append({'type': 'photo',
                           'src': self._image_url('image_512', '512x512', record=tmpl)})
        for image in tmpl.product_template_image_ids.sorted(
                lambda i: (i.sequence, i.id))[:MAX_EXTRA_IMAGES]:
            item = self._mart369_gallery_item(image)
            if item:
                shared.append(item)
        return shared

    @api.model
    def _mart369_variant_images(self, variant):
        """The photos of that gallery, as plain URLs - what cards and the
        basket draw. A video counts by its poster picture."""
        return [item.get('poster') if item['type'] == 'video' else item['src']
                for item in self._mart369_variant_media(variant)
                if item['type'] == 'photo' or item.get('poster')]

    @api.model
    def _mart369_description(self, tmpl):
        """The product's words as plain text: the eCommerce Description from
        the Website tab when it has any, else the Sales Description. Plain for
        the readers that cannot draw formatting (the WhatsApp page, search);
        the product page draws `_mart369_description_html`."""
        if 'description_ecommerce' in tmpl._fields:
            text = html2plaintext(tmpl.description_ecommerce or '').strip()
            if text:
                return text
        return (tmpl.description_sale or '').strip()

    @api.model
    def _mart369_description_html(self, tmpl):
        """The eCommerce Description with its formatting kept - bold, lists,
        headings, paragraphs - cleaned of scripts, styles and classes. None
        when it is empty: the Sales Description is plain text and goes as
        `description`."""
        if 'description_ecommerce' not in tmpl._fields:
            return None
        html = tmpl.description_ecommerce or ''
        if not html2plaintext(html).strip():
            return None
        cleaned = html_sanitize(html, strip_style=True, strip_classes=True)
        return str(cleaned) if cleaned and html2plaintext(cleaned).strip() else None

    @api.model
    def _mart369_variant_spec_rows(self, variant):
        """[(label, value)] for the specs table, in order: here the attribute
        values the variant differs from its siblings by. mart369_whatsapp_bridge
        swaps in the Variant specs tab, the rows the WhatsApp page lists."""
        ptavs = variant.product_template_variant_value_ids.sorted(
            lambda x: (x.attribute_id.sequence, x.attribute_id.id))
        return [(x.attribute_id.name, x.name) for x in ptavs]

    @api.model
    def _mart369_variant_specs(self, variant):
        """{label: value} for the specs table, in order, empty rows left out."""
        return {label: value for label, value in self._mart369_variant_spec_rows(variant)
                if label and value}

    @api.model
    def _mart369_website_variant_prices(self, variants, website):
        """{variant id: {'price', 'mrp'?}} priced as website_sale prices a
        template (`_get_sales_prices`), but for each variant: the pricelist
        rule runs on the variant's own price, extras included, so 10% off a
        600 laptop with +200 for 16GB is 720 - what Odoo, the chat and the
        order all charge - and a rule aimed at one variant applies to it.

        Raises outside a website request, like the template version."""
        from odoo.http import request
        pricelist = request.pricelist
        currency = website.currency_id
        fiscal_position = request.fiscal_position
        date = fields.Date.context_today(self)
        rule_prices = pricelist._compute_price_rule(variants, 1.0)
        Template = self.env['product.template']
        Item = self.env['product.pricelist.item']
        out = {}
        for variant in variants:
            price, rule_id = rule_prices[variant.id]
            product_taxes = variant.sudo().taxes_id._filter_taxes_by_company(self.env.company)
            taxes = fiscal_position.map_tax(product_taxes)
            entry = {'price': Template._apply_taxes_to_price(
                price, currency, product_taxes, taxes, variant, website=website)}
            item = Item.browse(rule_id)
            if item._show_discount_on_shop():
                before = item._compute_price_before_discount(
                    product=variant, quantity=1.0, date=date,
                    uom=variant.uom_id, currency=currency)
                if currency.compare_amounts(before, price) == 1:
                    entry['mrp'] = Template._apply_taxes_to_price(
                        before, currency, product_taxes, taxes, variant, website=website)
            out[variant.id] = entry
        return out

    @api.model
    def _price_context_for_variants(self, variants):
        """{variant id: {'price', 'mrp'}} for these variants in one pass - the
        same rules `_price_context_for` applies to a template, applied to each
        variant's own price (its extras included): the website pricelist,
        then any live deal on its product, then what to strike through."""
        variants = variants.sudo()
        if not variants:
            return {}
        prices = {}
        if 'website' in self.env:
            website = self.env['website'].get_current_website()
            try:
                prices = self._mart369_website_variant_prices(variants, website)
            except Exception:  # noqa: BLE001 - not a website request
                _logger.debug(
                    'mart369: no pricelist price for %s variants, using the '
                    'list price', len(variants), exc_info=True)
                prices = {}

        deals = (self.env['mart369.deal'].sudo()._mart369_live_deals()
                 if 'mart369.deal' in self.env else [])
        out = {}
        for variant in variants:
            tmpl = variant.product_tmpl_id
            listed = variant.lst_price  # list price + this variant's extras
            entry = prices.get(variant.id) or {}
            price = entry.get('price')
            if price is None:
                price = listed

            # A deal names the product, so it covers every variant of it,
            # each from its own list price - as the template's card is priced.
            offers = [deal._mart369_apply(listed) for deal in deals
                      if tmpl in deal.product_ids]
            if offers and min(offers) < price:
                price = min(offers)

            mrp = (entry.get('mrp')
                   or (tmpl.compare_list_price + (variant.price_extra or 0.0)
                       if tmpl.compare_list_price else 0.0)
                   or listed
                   or 0.0)
            out[variant.id] = {
                'price': price,
                'mrp': mrp if mrp and mrp > price else None,
            }
        return out

    @api.model
    def _serialize_variant(self, variant, price_ctx, variant_ctx, mode_key=None, base=None):
        """One variant's card: the product's card, with this variant's id,
        price, stock, pictures and specs. `price_ctx` is keyed by template
        (as for _serialize_product), `variant_ctx` by variant. `base` is the
        product's card already built, so siblings share one."""
        tmpl = variant.product_tmpl_id
        vals = dict(base) if base is not None else self._serialize_product(
            tmpl, None, price_ctx, mode_key)
        entry = variant_ctx.get(variant.id) or {}

        size = ' · '.join(variant.product_template_attribute_value_ids.sorted(
            lambda x: (x.attribute_id.sequence, x.attribute_id.id)).mapped('name'))
        vals.update({
            'id': self._mart369_variant_key(variant),
            'variantGroup': str(tmpl.id),
            # Reached from the product page, never listed on its own: the
            # listing shows the product once, not once per colour.
            'hidden': True,
            'combo': self._mart369_combo(variant),
            'images': self._mart369_variant_images(variant),
            'media': self._mart369_variant_media(variant),
            'price': round(entry.get('price', vals['price']) or 0.0, 2),
        })
        vals.pop('hasVariants', None)
        vals.pop('mrp', None)
        if entry.get('mrp'):
            vals['mrp'] = round(entry['mrp'], 2)
        if size:
            vals['size'] = size
            vals['unit'] = size
        specs = self._mart369_variant_specs(variant)
        if specs:
            vals['specs'] = specs
        # The product's words: plain text for every reader, and the eCommerce
        # Description's own formatting for the product page.
        description = self._mart369_description(tmpl)
        if description:
            vals['description'] = description
        description_html = self._mart369_description_html(tmpl)
        if description_html:
            vals['descriptionHtml'] = description_html

        vals.pop('stock', None)
        vals.pop('low', None)
        if 'free_qty' in variant._fields and (
                'is_storable' not in tmpl._fields or tmpl.is_storable):
            qty = variant.free_qty
            if qty <= 0:
                vals['stock'] = 0
            elif tmpl.mart_low_stock_at and qty <= tmpl.mart_low_stock_at:
                vals['low'] = int(qty)
        return vals

    @api.model
    def _serialize_variants(self, variants, mode_key=None, price_ctx=None):
        """Cards for these variants, priced in one pass, each product's card
        built once and shared by its variants."""
        variants = variants.sudo()
        if price_ctx is None:
            price_ctx = self._price_context_for(variants.product_tmpl_id)
        variant_ctx = self._price_context_for_variants(variants)
        bases = {}
        out = []
        for v in variants:
            tmpl = v.product_tmpl_id
            key = ('all' if tmpl.mart_delivery_text else 'quick') if mode_key == 'own' else mode_key
            if (tmpl.id, key) not in bases:
                bases[(tmpl.id, key)] = self._serialize_product(tmpl, None, price_ctx, key)
            out.append(self._serialize_variant(
                v, price_ctx, variant_ctx, key, base=bases[(tmpl.id, key)]))
        return out

    # ------------------------------------------------------ the prices

    def _mart369_free_qty(self, product):
        """Free stock for a template, or None when there is none to speak of.

        This used to read `product.free_qty` behind `if 'free_qty' in
        product._fields`, and `product` is a product.template, which has no
        such field - Inventory puts `free_qty` on the variant and gives the
        template only `qty_available` and friends. So the guard was always
        False and the app was never once told a product was out of stock or
        running low. Sold-out items read as buyable.

        None rather than 0.0 for "no answer", because the two mean opposite
        things to a shopper: nothing to say is not the same as none left, and
        a service or an untracked consumable must not be marked sold out.

        `mart369_catalog` already counts stock this way for the staff list
        (`product_admin.py._mart369_admin_qty`); this is the shopper's side of
        the same sum.
        """
        if 'free_qty' not in self.env['product.product']._fields:
            return None  # Inventory is not installed; nothing tracks stock.
        if 'is_storable' in product._fields and not product.is_storable:
            return None  # Nothing Inventory tracks has nothing to run out of.
        # sudo: free stock is what the shop shows everyone, but reading it walks
        # stock.move, which a website designer without stock rights may not.
        return sum(product.sudo().product_variant_ids.mapped('free_qty'))

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

