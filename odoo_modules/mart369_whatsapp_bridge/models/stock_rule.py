"""One stock rule for both doors: the product's own "Sell when Out-of-Stock".

`website_sale_stock` puts the switch on every product
(`allow_out_of_stock_order`), and the website obeys it. The WhatsApp flow
never read it, and judged stock by `qty_available` - which is 0 for anything
not tracked in stock, so every WhatsApp order for an untracked storefront
product went off to be sourced from vendors although the shop had it.

From here, on WhatsApp as on the website:

* not tracked in stock - always on the shelf;
* tracked, enough free stock - on the shelf;
* tracked, short, "Sell when Out-of-Stock" on - sourced from vendors, as
  before (the WhatsApp version of Express: it comes, later);
* tracked, short, switch off - not sold. Hidden from the NEW ORDER menu and
  from search while none is free; when a few are left the customer is told
  how many, and the enquiry ends.

"Free" is `free_qty` in the order's company - the figure the stack's own
placement check (`_sa_lines_in_stock`) and the storefront already use.
"""

import logging

from odoo import _, api, models

_logger = logging.getLogger(__name__)


class SaGroupRequestStock(models.Model):
    _inherit = 'sa.group.request'

    # ------------------------------------------------------------ the rule

    def _mart369_stock_company(self):
        """The company whose stock counts: the enquiry's, else the user's."""
        if len(self) == 1 and self.group_id:
            return self.finder_company_id or self._company_for(self.group_id)
        return self.env.company

    @api.model
    def _mart369_stock_verdict(self, product, qty, company):
        """('shelf' | 'source' | 'refuse', free quantity) for `qty` of `product`."""
        if not getattr(product, 'is_storable', False):
            return 'shelf', float(qty or 0.0)
        variants = product.sudo().product_variant_ids.with_company(company)
        # Read fresh: the check before placing an order exists to see stock
        # that went since the quote, and `free_qty` is cached for the whole
        # transaction once read.
        variants.invalidate_recordset(['free_qty', 'qty_available', 'virtual_available'])
        free = float(sum(variants.mapped('free_qty')))
        if free >= float(qty or 1.0) and free > 0:
            return 'shelf', free
        if getattr(product, 'allow_out_of_stock_order', True):
            return 'source', free
        return 'refuse', free

    @api.model
    def _mart369_sellable_domain(self, company=None):
        """Products WhatsApp may offer: untracked, allowed to be sold out,
        or with something free right now. A search domain, so the menu's
        paging stays right."""
        company = company or self.env.company
        in_stock = self.env['product.product'].sudo().with_company(company).search([
            ('is_storable', '=', True),
            ('allow_out_of_stock_order', '=', False),
            ('free_qty', '>', 0),
        ]).product_tmpl_id
        return ['|', '|', ('is_storable', '=', False),
                ('allow_out_of_stock_order', '=', True),
                ('id', 'in', in_stock.ids)]

    def _mart369_refuse(self, product, free):
        """Tell the customer, and end the enquiry. Nothing is sourced."""
        self.ensure_one()
        if free > 0:
            self._say(_(
                "Sorry - we only have *%(free)s* of *%(name)s* right now. "
                "Tap *NEW ORDER* and ask for up to %(free)s. \U0001F64F",
                free=('%g' % free), name=product.name))
        else:
            self._say(_(
                "Sorry - *%(name)s* is out of stock right now. \U0001F64F",
                name=product.name))
        _logger.info('bridge: enquiry %s refused - %s has %s free, %s asked',
                     self.id, product.display_name, free, self.qty)
        return self._drop('unavailable')

    # ---------------------------------------------------- where it applies

    def _assess_availability(self, product):
        """The stack's answer, corrected to the rule above. `free_qty` also
        wins over the group's "use forecast stock" option: one rule, both
        doors."""
        super()._assess_availability(product)
        verdict, free = self._mart369_stock_verdict(
            product, self.qty or 1.0, self._mart369_stock_company())
        self.available_qty = free
        self.stock_status = 'in_stock' if verdict == 'shelf' else 'on_order'

    def _on_confirmed(self):
        """A product the shop will not sell short is refused, not sourced."""
        self.ensure_one()
        product = self.product_id
        if product:
            verdict, free = self._mart369_stock_verdict(
                product, self.qty or 1.0, self._mart369_stock_company())
            if verdict == 'refuse':
                return self._mart369_refuse(product, free)
        return super()._on_confirmed()

    def _place_order(self):
        """The last unit may have gone since the quote: check again before
        an order - and a pay link - exist. Nothing has been paid yet (group
        orders pay after placing), so there is nothing to give back."""
        self.ensure_one()
        product = self.product_id
        if product:
            verdict, free = self._mart369_stock_verdict(
                product, self.qty or 1.0, self._mart369_stock_company())
            if verdict == 'refuse':
                return self._mart369_refuse(product, free)
        return super()._place_order()
