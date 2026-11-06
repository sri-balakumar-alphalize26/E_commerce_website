# -*- coding: utf-8 -*-
"""Quantity-range bargaining, per product.

A product may carry its own table: 5-9 pcs 2 % off, 10-20 pcs 5 % off, 21+
8 % off - any number of rows. For such a product the flat step-down does not
apply: BETTER PRICE is offered only when the customer's quantity falls inside
a row, and it gives that row's percentage, once. Because the quantity decides
whether bargaining exists at all, the assistant asks for it before it offers
ACCEPT / BETTER PRICE.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SaQtyBargain(models.Model):
    _name = 'sa.qty.bargain'
    _description = 'Quantity bargaining range'
    _order = 'qty_min, id'

    product_tmpl_id = fields.Many2one('product.template', ondelete='cascade', index=True)
    settings_id = fields.Many2one('sa.ai.settings', ondelete='cascade', index=True,
                                  help="Set on the shop-wide rows of the Bargaining page.")
    qty_min = fields.Float('From (pcs)', required=True, digits='Product Unit of Measure')
    qty_max = fields.Float('To (pcs)', digits='Product Unit of Measure',
                           help="Leave 0 for no upper limit.")
    percent = fields.Float('Discount %', required=True)

    @api.constrains('qty_min', 'qty_max', 'percent')
    def _check_range(self):
        for r in self:
            if r.qty_min < 1:
                raise ValidationError(_("A range must start at 1 or more."))
            if r.qty_max and r.qty_max < r.qty_min:
                raise ValidationError(_("The upper limit must be at least the lower limit."))
            if not 0 <= r.percent <= 90:
                raise ValidationError(_("The discount must be between 0 and 90 %."))
            if r.product_tmpl_id:
                others = r.product_tmpl_id.sa_qty_bargain_ids - r
            else:
                others = r.settings_id.qty_bargain_ids - r
            for o in others:
                lo, hi = r.qty_min, r.qty_max or float('inf')
                olo, ohi = o.qty_min, o.qty_max or float('inf')
                if lo <= ohi and olo <= hi:
                    raise ValidationError(_(
                        "Ranges overlap: %(a)s and %(b)s.", a=r._label(), b=o._label()))

    def _label(self):
        self.ensure_one()
        if self.qty_max:
            span = '%g-%g' % (self.qty_min, self.qty_max)
        else:
            span = '%g+' % self.qty_min
        return _("%(span)s pcs: %(pct)g%% off", span=span, pct=self.percent)


class ProductTemplateQtyBargain(models.Model):
    _inherit = 'product.template'

    sa_qty_bargain = fields.Boolean(
        'Quantity bargaining on WhatsApp',
        help="Ticked: BETTER PRICE is offered only when the customer's quantity "
             "falls inside one of the ranges below, and gives that range's "
             "discount. The flat bargaining step in AI Settings does not apply.")
    sa_qty_bargain_ids = fields.One2many('sa.qty.bargain', 'product_tmpl_id', 'Quantity ranges')

    def _sa_qty_rows(self):
        """The ranges that apply to this product: its own when ticked and
        filled in; otherwise the shop-wide table from the Bargaining page,
        when the product is ticked or the page says "every product"."""
        self.ensure_one()
        if self.sa_qty_bargain and self.sa_qty_bargain_ids:
            return self.sa_qty_bargain_ids.sorted('qty_min')
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        if settings.qty_bargain_ids and (self.sa_qty_bargain or settings.qty_bargain_all):
            return settings.qty_bargain_ids.sorted('qty_min')
        return self.env['sa.qty.bargain']

    def _sa_qty_tier(self, qty):
        """The range a quantity falls in, or an empty recordset."""
        self.ensure_one()
        if not qty:
            return self.env['sa.qty.bargain']
        for r in self._sa_qty_rows():
            if qty >= r.qty_min and (not r.qty_max or qty <= r.qty_max):
                return r
        return self.env['sa.qty.bargain']

    def _sa_qty_tier_text(self):
        self.ensure_one()
        return ' · '.join(r._label() for r in self._sa_qty_rows())

    def _sa_qty_bargain_from(self):
        self.ensure_one()
        rows = self._sa_qty_rows()
        return rows[:1].qty_min if rows else 0.0


class SaAiSettingsQtyBargain(models.Model):
    _inherit = 'sa.ai.settings'

    qty_bargain_ids = fields.One2many('sa.qty.bargain', 'settings_id', 'Quantity ranges',
                                     help="Shop-wide ranges. A product's own table wins over these.")
    qty_bargain_all = fields.Boolean(
        'Use these ranges for every product',
        help="On: every product bargains by quantity range and the flat step is "
             "never used. Off: only products ticked on their form.")


class SaGroupRequestQtyBargain(models.Model):
    _inherit = 'sa.group.request'

    sa_qty_before_deal = fields.Boolean('Quantity asked before the deal', copy=False)

    def _sa_qty_tiered(self):
        self.ensure_one()
        p = self.product_id
        return bool(p and p._sa_qty_rows())

    def _sa_qty_bargain_allowed(self):
        """Whether BETTER PRICE may be shown right now. Products without
        their own ranges: always (the flat rule decides the rest)."""
        self.ensure_one()
        if not self._sa_qty_tiered():
            return True
        return bool(self.product_id._sa_qty_tier(self.qty)) and self.bargain_count == 0

    def _sa_qty_first(self, body):
        """Tiered product, quantity unknown: say the price and the ranges, ask
        how many, and hold the deal options until the number is in."""
        self.ensure_one()
        if not self._sa_qty_tiered() or self.qty:
            return False
        self._say(body + _("\n\n\U0001F4E6 *Quantity discounts:* %(tiers)s",
                           tiers=self.product_id._sa_qty_tier_text()))
        self.write({'state': 'awaiting_qty', 'sa_qty_before_deal': True})
        self._sa_ask_qty_poll(_("\U0001F522 How many do you need? Tap one, or *Other amount* "
                                "for more \U0001F447"))
        return True

    def _sa_offer_after_qty(self):
        """The number is in: post the offer with the right buttons."""
        self.ensure_one()
        self.sa_qty_before_deal = False
        price = self.agreed_price or self.quoted_price
        name = self.product_id.name or self.ai_search_term or _("this item")
        qty = self.qty or 1
        tier = self.product_id._sa_qty_tier(qty)
        if tier:
            body = _("\U0001F4E6 *%(product)s*\n\U0001F4B0 *%(price).2f* each for %(qty)s pcs "
                     "(total %(total).2f)\n\n\U0001F381 For this quantity you can get *%(pct)g%% off* - "
                     "tap BETTER PRICE.", product=name, price=price,
                     qty=int(qty) if float(qty).is_integer() else qty, total=price * qty, pct=tier.percent)
        else:
            start = self.product_id._sa_qty_bargain_from()
            body = _("\U0001F4E6 *%(product)s*\n\U0001F4B0 *%(price).2f* each for %(qty)s pcs "
                     "(total %(total).2f)\n\nBargaining applies from *%(start)g pcs*.",
                     product=name, price=price, qty=int(qty) if float(qty).is_integer() else qty,
                     total=price * qty, start=start)
        self.state = 'quoted' if self.bargain_count == 0 else 'negotiating'
        rendered = self._ask(body, self._sa_deal_options())
        if rendered != 'poll':
            self._say(self._sa_price_taps(price, accept_only=not tier))
        return True

    def _sa_tier_offer(self, text, tapped=False):
        """BETTER PRICE (or a typed number) on a tiered product: the range's
        percentage, once. Never the flat step."""
        self.ensure_one()
        name = self.product_id.name or self.ai_search_term or _("this item")
        base = self.quoted_price or self.agreed_price or 0.0
        if not self.qty:
            # No quantity yet: the discount depends on it.
            return self._sa_qty_first(_("\U0001F4E6 *%(product)s*\n\U0001F4B0 *%(price).2f*",
                                        product=name, price=base))
        qty = self.qty
        tier = self.product_id._sa_qty_tier(qty)
        current = self.agreed_price or base
        if not tier:
            start = self.product_id._sa_qty_bargain_from()
            self._ask(_("\U0001F4E6 *%(product)s*\n\U0001F4B0 *%(price).2f* - bargaining applies "
                        "from *%(start)g pcs*. For %(qty)g pcs this is the price. \U0001F64F",
                        product=name, price=current, start=start, qty=qty),
                      self._sa_deal_options(allow_bargain=False))
            self.state = 'negotiating'
            return True
        if self.bargain_count >= 1:
            return self._say_final(current, current)
        offer = round(base * (1.0 - tier.percent / 100.0), 2)
        self.write({'agreed_price': offer, 'bargain_count': 1, 'state': 'negotiating'})
        rendered = self._ask(
            _("\U0001F4E6 *%(product)s*\n\U0001F381 For %(qty)g pcs: *%(pct)g%% off*\n"
              "\U0001F4B0 *%(price).2f each* - total *%(total).2f*\n\nThat is our best for this "
              "quantity. \U0001F64F", product=name, qty=qty, pct=tier.percent, price=offer,
              total=offer * qty),
            self._sa_deal_options(allow_bargain=False))
        if rendered != 'poll':
            self._say(self._sa_price_taps(offer, accept_only=True))
        return True
