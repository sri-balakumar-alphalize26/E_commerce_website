"""The stock list for the app's own admin console.

Read-only. Every number is one the shop already keeps:

* **In stock** is `free_qty` - what is on hand and not promised to an order,
  which is the number the storefront card reads, so the console never says
  "12 left" about a product the app shows as sold out.
* **Low** is `mart_low_stock_at`, the threshold the storefront already uses for
  "Only N left". A second reorder level kept here would disagree with it.
* **Sold / 7d** is one grouped read over confirmed order lines for the page.
* **Storefront** is Express when the product sits in a category whose
  top-level parent is an Express storefront - the rule the Catalog screen and
  the app's own navigation use - or when it carries a delivery time, which is
  the test the product page uses.

Stock is not a stored field, so the stock tabs and the "lowest stock" sort
cannot be a SQL domain. They are worked out over the whole filtered set, in
Python, before the page is cut - filtering the page you were sent is not
filtering the shop.
"""

from datetime import timedelta

from odoo import api, fields, models

MAX_ROWS = 200

TABS = ('all', 'low', 'out', 'off')

SORTS = ('low', 'sold', 'price', 'name')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # ------------------------------------------------------------- helpers

    @api.model
    def _mart369_admin_tracks_stock(self):
        # `free_qty` lives on the variant, not the template - Inventory only
        # adds `qty_available` and friends to product.template.
        return 'free_qty' in self.env['product.product']._fields

    def _mart369_admin_qty(self):
        """{template id: free quantity summed over its variants}, or {} when
        Inventory is not installed. One batched compute over every variant."""
        if not self._mart369_admin_tracks_stock():
            return {}
        # A product Inventory does not track (a service, a plain consumable)
        # has no stock to run out of; it is left out, and reads as "-" rather
        # than as "out of stock".
        tracked = self.filtered(lambda t: 'is_storable' not in t._fields or t.is_storable)
        out = {t.id: 0.0 for t in tracked}
        for variant in tracked.with_context(active_test=False).product_variant_ids:
            out[variant.product_tmpl_id.id] += variant.free_qty
        return out

    def _mart369_admin_state(self, qty):
        """'out', 'low' or 'ok' for one product at this quantity."""
        self.ensure_one()
        if qty is None:
            return 'ok'
        if qty <= 0:
            return 'out'
        if self.mart_low_stock_at and qty <= self.mart_low_stock_at:
            return 'low'
        return 'ok'

    def _mart369_admin_sold7(self):
        """{template id: units sold in the last 7 days}, in one grouped read."""
        return self._mart369_admin_sold(7)

    def _mart369_admin_sold(self, days):
        """{template id: units sold in the last `days` days}, one grouped read."""
        if not self or 'sale.order.line' not in self.env:
            return {}
        since = fields.Datetime.now() - timedelta(days=days)
        groups = self.env['sale.order.line']._read_group(
            [('product_id.product_tmpl_id', 'in', self.ids),
             ('order_id.state', '=', 'sale'),
             ('order_id.date_order', '>=', since)],
            groupby=['product_id'], aggregates=['product_uom_qty:sum'])
        out = {}
        for product, qty in groups:
            key = product.product_tmpl_id.id
            out[key] = out.get(key, 0.0) + (qty or 0.0)
        return out

    @api.model
    def _mart369_admin_express_domain(self):
        """Products on the Express storefront, as a domain.

        A child category's storefront is its top-level parent's, which no
        domain can see - so the Express categories are worked out here and
        handed to the domain as ids."""
        Categ = self.env['product.public.category']
        express = Categ.search([]).filtered(lambda c: c._mart369_mode() == 'all')
        return ['|', ('mart_delivery_text', '!=', False),
                ('public_categ_ids', 'in', express.ids)]

    @api.model
    def _mart369_admin_domain(self, categ=None, mode=None, q=None):
        domain = [('sale_ok', '=', True)]
        if categ:
            domain += [('public_categ_ids', 'child_of', int(categ))]
        if mode == 'all':
            domain += self._mart369_admin_express_domain()
        elif mode == 'quick':
            domain += ['!'] + self._mart369_admin_express_domain()
        term = (q or '').strip()
        if term:
            domain += ['|', ('name', 'ilike', term), ('default_code', 'ilike', term)]
        return domain

    @api.model
    def _mart369_admin_shop(self):
        """The whole shop, once: (products, qty, states, tiles, tab counts).

        Shared by this list and the Products desk, so the two sets of tiles
        cannot disagree about what "low" means."""
        shop = self.search([('sale_ok', '=', True)])
        shop_qty = shop._mart369_admin_qty()
        states = {t.id: t._mart369_admin_state(shop_qty.get(t.id)) for t in shop}
        currency = self.env.company.currency_id
        tiles = {
            'count': len(shop),
            'value': currency.round(sum(
                max(shop_qty.get(t.id) or 0.0, 0.0) * t.list_price for t in shop)),
            'low': sum(1 for s in states.values() if s == 'low'),
            'out': sum(1 for s in states.values() if s == 'out'),
            # False when Inventory is not installed, so the screen can say so
            # rather than show every product as out of stock.
            'stock': self._mart369_admin_tracks_stock(),
        }
        counts = {
            'all': len(shop),
            'low': tiles['low'],
            'out': tiles['out'],
            'off': len(shop.filtered(lambda t: not t.is_published)),
        }
        return shop, shop_qty, states, tiles, counts

    # ------------------------------------------------------ the products desk
    #
    # mart369_product's desk lists products through its picker, which cannot
    # see stock or storefronts on its own. These fill its hooks with the same
    # rules as the list above.

    @api.model
    def _mart369_picker_domain(self, tab=None):
        # Low and out count the whole shop, published or not, so the tab has
        # to list the same set its badge counted.
        if tab in ('low', 'out'):
            return [('sale_ok', '=', True)]
        return super()._mart369_picker_domain(tab)

    @api.model
    def _mart369_picker_mode_domain(self, mode=None):
        if mode == 'all':
            return self._mart369_admin_express_domain()
        if mode == 'quick':
            return ['!'] + self._mart369_admin_express_domain()
        return super()._mart369_picker_mode_domain(mode)

    @api.model
    def _mart369_picker_narrow(self, found, tab=None, sort=None):
        found = super()._mart369_picker_narrow(found, tab, sort)
        if tab not in ('low', 'out') and sort not in ('low', 'sold', 'price'):
            return found
        qty = found._mart369_admin_qty()
        if tab in ('low', 'out'):
            found = found.filtered(
                lambda t: t._mart369_admin_state(qty.get(t.id)) == tab)
        if sort == 'low':
            found = found.sorted(lambda t: (t.id not in qty, qty.get(t.id) or 0.0, t.name or ''))
        elif sort == 'sold':
            sold = found._mart369_admin_sold7()
            found = found.sorted(lambda t: (-sold.get(t.id, 0.0), t.name or ''))
        elif sort == 'price':
            found = found.sorted(lambda t: (-t.list_price, t.name or ''))
        return found

    @api.model
    def _mart369_picker_extras(self, page):
        extras = super()._mart369_picker_extras(page)
        __, __, __, tiles, counts = self._mart369_admin_shop()
        qty = page._mart369_admin_qty()
        sold = page._mart369_admin_sold7()  # one grouped read for the page
        extras.update({
            'tiles': tiles,
            'counts': counts,
            'currency': self.env['mart369.serializable']._mart369_currency(
                self.env.company.currency_id),
            # {id: [qty or None, 'ok' | 'low' | 'out']} for the rows on screen.
            'stock': {
                t.id: [None if t.id not in qty else round(qty[t.id], 2),
                       t._mart369_admin_state(qty.get(t.id))]
                for t in page},
            # {id: row} - what the web admin's Products list shows per product
            # (unit, category, sold in 7 days, in stock, live), so the desk's
            # list and cards can show the same.
            'rows': {
                t.id: t._mart369_admin_row(qty.get(t.id), sold.get(t.id, 0.0))
                for t in page},
        })
        return extras

    # --------------------------------------------- On hand in the desk editor

    @api.model
    def _mart369_desk_on_hand_box(self, product):
        """The On hand box: what is in stock now, typed over to recount it.

        Offered only where one number can mean something - stock is kept, and
        the product has a single variant. A product with sizes or colours has
        a count per variant, which is Odoo's own form's job."""
        if not self._mart369_admin_tracks_stock():
            return None
        box = {
            'name': 'mart_on_hand',
            'label': 'On hand',
            'help': 'How many you have now. Change it and Save to recount - it '
                    'is booked as an inventory adjustment, as in Odoo.',
            'widget': 'number',
            # Only asked for once the product is counted at all.
            'showIf': 'is_storable',
        }
        if product and len(product.product_variant_ids) > 1:
            box['readonly'] = True
            box['help'] = 'This product has variants - count each one in Odoo.'
        value = round(product.qty_available, 2) if product else ''
        return box, value if value else ''

    def _mart369_desk_set_on_hand(self, product, qty):
        """Book `qty` as the counted stock, the way Odoo's own "Update
        quantity" does: an inventory-mode quant, applied. Only when the
        product is storable, single-variant, and the count really changed."""
        if not self._mart369_admin_tracks_stock() or 'stock.quant' not in self.env:
            return False
        if 'is_storable' in product._fields and not product.is_storable:
            return False
        if len(product.product_variant_ids) != 1:
            return False
        if abs((product.qty_available or 0.0) - qty) < 1e-9:
            return False
        location = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1).lot_stock_id
        if not location:
            return False
        Quant = self.env['stock.quant'].with_context(inventory_mode=True)
        quant = Quant.search([('product_id', '=', product.product_variant_id.id),
                              ('location_id', '=', location.id)], limit=1)
        if quant:
            quant.inventory_quantity = qty
        else:
            quant = Quant.create({
                'product_id': product.product_variant_id.id,
                'location_id': location.id,
                'inventory_quantity': qty,
            })
        quant.action_apply_inventory()
        return True

    @api.model
    def _mart369_product_stats(self, product):
        """The numbers strip on the desk's product view: the same figures as
        Odoo's own header - on hand, forecast, sales - plus price, cost and
        margin. `open` says which of Odoo's own screens each tile can open."""
        out = super()._mart369_product_stats(product)
        tracks = self._mart369_admin_tracks_stock() and 'qty_available' in product._fields
        tracked = tracks and ('is_storable' not in product._fields or product.is_storable)
        price = product.list_price or 0.0
        cost = product.standard_price or 0.0
        out.update({
            'onHand': round(product.qty_available, 2) if tracked else None,
            'forecast': round(product.virtual_available, 2) if tracked else None,
            'sold': round(product._mart369_admin_sold(30).get(product.id, 0.0), 2),
            'soldDays': 30,
            'price': price,
            'cost': cost,
            # Only when both are known: a margin off a missing cost is 100%,
            # which is a number nobody should be shown.
            'margin': round((price - cost) / price * 100) if price and cost else None,
            'currency': self.env['mart369.serializable']._mart369_currency(
                self.env.company.currency_id),
            'open': {
                'onHand': 'action_open_quants' if tracked and hasattr(product, 'action_open_quants') else None,
                'forecast': 'action_product_tmpl_forecast_report' if tracked and hasattr(product, 'action_product_tmpl_forecast_report') else None,
                'sold': 'action_view_sales' if hasattr(product, 'action_view_sales') else None,
            },
        })
        return out

    # ------------------------------------------------------------- reading

    @api.model
    def mart369_admin_list(self, tab=None, categ=None, mode=None, q=None,
                           sort=None, limit=50, offset=0):
        """One page of the stock list, the whole shop's tiles, and the filters.

        `total` counts the filter; the tiles and tab counts count the shop.
        """
        tab = tab if tab in TABS else 'all'
        sort = sort if sort in SORTS else 'low'
        limit = max(1, min(int(limit or 50), MAX_ROWS))
        offset = max(0, int(offset or 0))

        shop, shop_qty, states, tiles, counts = self._mart369_admin_shop()
        currency = self.env.company.currency_id

        # The filter, over the shop - then the stock tabs, then the sort.
        found = self.search(self._mart369_admin_domain(categ=categ, mode=mode, q=q))
        if tab == 'off':
            found = found.filtered(lambda t: not t.is_published)
        elif tab in ('low', 'out'):
            found = found.filtered(lambda t: states.get(t.id) == tab)
        sold = found._mart369_admin_sold7() if sort == 'sold' else {}
        if sort == 'low':
            found = found.sorted(lambda t: (t.id not in shop_qty, shop_qty.get(t.id) or 0.0, t.name or ''))
        elif sort == 'sold':
            found = found.sorted(lambda t: (-sold.get(t.id, 0.0), t.name or ''))
        elif sort == 'price':
            found = found.sorted(lambda t: (-t.list_price, t.name or ''))
        else:
            found = found.sorted(lambda t: (t.name or '').lower())

        page = found[offset:offset + limit]
        if sort != 'sold':
            sold = page._mart369_admin_sold7()
        express = set(page.filtered_domain(self._mart369_admin_express_domain()).ids)
        return {
            'rows': [t._mart369_admin_row(shop_qty.get(t.id), sold.get(t.id, 0.0),
                                          t.id in express)
                     for t in page],
            'total': len(found),
            'limit': limit,
            'offset': offset,
            'tiles': tiles,
            'counts': counts,
            'categories': [
                {'id': c.id, 'name': c.display_name}
                for c in self.env['product.public.category'].search(
                    [('mart_in_app', '=', True)], order='sequence, name')],
            'currency': self.env['mart369.serializable']._mart369_currency(currency),
        }

    def _mart369_admin_row(self, qty=None, sold7=0.0, express=None):
        """One line of the list. Everything the row draws, and nothing more."""
        self.ensure_one()
        mrp = self.compare_list_price if self.compare_list_price > self.list_price else None
        image = None
        if self.image_128:
            image = self.env['mart369.serializable']._image_url(
                'image_512', '256x256', record=self)
        categ = self.public_categ_ids[:1]
        return {
            'id': self.id,
            'name': self.name or '',
            'code': self.default_code or '',
            'unit': self.mart_unit_text or self.uom_id.name or '',
            'price': self.list_price,
            'mrp': mrp,
            'image': image,
            'cat': categ.display_name if categ else '',
            'delivery': bool(self.mart_delivery_text) if express is None else express,
            'deliveryText': self.mart_delivery_text or '',
            'qty': qty if qty is None else round(qty, 2),
            'sold7': round(sold7, 2),
            'active': bool(self.is_published),
            'reorder': self.mart_low_stock_at or 0,
            'state': self._mart369_admin_state(qty),
        }
