"""Discount codes.

Replaces COUPONS in components/home/Cart.jsx, where three codes live in the
browser bundle with their arithmetic as JavaScript closures:

    { code: "QUICK20", group: "quick", min: 199,
      calc: (s) => Math.min(60, Math.round(s.quick * 0.2)) }

which means the browser decides what discount it gets. Anyone can open the
console and give themselves any number.

Not `loyalty.program`. Odoo's loyalty engine computes its discount **on a
sale.order**, and the app shows coupons on the cart page and the offers page,
where no order exists yet. It also has nowhere to keep the two things the app
prints - the short `title` and the `note` under it - and no notion of "Quick
items only". Rather than bend the app around the engine, a coupon is a small
record here, applied to the real order in mart369_order when one is placed.
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError

KIND_CHOICES = [
    ('percent', 'Percentage off'),
    ('flat', 'Flat amount off'),
    ('free_delivery', 'Free delivery'),
]

GROUP_CHOICES = [
    ('quick', 'Quick items only'),
    ('all', 'Express items only'),
]


class Mart369Coupon(models.Model):
    _name = 'mart369.coupon'
    _description = '369 Mart Coupon'
    _order = 'sequence, id'
    _rec_name = 'code'

    sequence = fields.Integer(default=10)
    code = fields.Char(
        string='Code', required=True, index=True,
        help="What the customer types, e.g. QUICK20. Case is ignored.")
    title = fields.Char(
        string='Title', required=True,
        help="The bold line in the app, e.g. 20% off on Quick orders.")
    note = fields.Char(
        string='Small print',
        help="The line under it, e.g. Up to 60 rupees, Quick items above 199.")

    kind = fields.Selection(KIND_CHOICES, string='Discount', required=True, default='flat')
    value = fields.Float(
        string='Amount or percent', default=0.0,
        help="A percentage for Percentage off, an amount for Flat. Ignored "
             "for Free delivery.")
    max_off = fields.Float(
        string='Never more than', default=0.0,
        help="Caps a percentage discount. 0 means no cap.")
    min_spend = fields.Float(
        string='Minimum spend', default=0.0,
        help="The basket must reach this before the code works. Measured on "
             "the chosen storefront only, when one is set.")
    group = fields.Selection(
        GROUP_CHOICES, string='Applies to',
        help="Empty means the whole basket.")

    active = fields.Boolean(default=True)
    starts_on = fields.Date(string='Starts')
    ends_on = fields.Date(string='Ends')
    limit_total = fields.Integer(
        string='Total uses allowed', default=0,
        help="0 means unlimited. Counted across every customer.")
    limit_per_customer = fields.Integer(
        string='Uses per customer', default=0,
        help="0 means unlimited.")
    used_count = fields.Integer(string='Used', default=0, readonly=True, copy=False)

    _code_uniq = models.Constraint(
        'unique (code)',
        'That coupon code already exists.',
    )

    @api.constrains('value', 'kind')
    def _check_value(self):
        for coupon in self:
            if coupon.kind == 'percent' and not 0 < coupon.value <= 100:
                raise ValidationError(self.env._(
                    'A percentage discount must be between 0 and 100.'))
            if coupon.kind == 'flat' and coupon.value <= 0:
                raise ValidationError(self.env._(
                    'A flat discount must be more than zero.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code'):
                vals['code'] = vals['code'].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('code'):
            vals['code'] = vals['code'].strip().upper()
        return super().write(vals)

    # ------------------------------------------------------------- lookup

    @api.model
    def _mart369_find(self, code):
        code = (code or '').strip().upper()
        if not code:
            return self.browse()
        return self.sudo().search([('code', '=', code)], limit=1)

    def _mart369_live(self, today=None):
        """Is this code usable at all today, before looking at the basket?"""
        self.ensure_one()
        today = today or fields.Date.context_today(self)
        if self.starts_on and today < self.starts_on:
            return False
        if self.ends_on and today > self.ends_on:
            return False
        if self.limit_total and self.used_count >= self.limit_total:
            return False
        return True

    # ----------------------------------------------------------- the money

    def _mart369_base(self, sums):
        """What the minimum spend is measured against, and what a percentage
        is taken off: one storefront, or the whole basket."""
        self.ensure_one()
        if self.group:
            return sums.get(self.group, 0.0)
        return sums.get('items', 0.0)

    def _mart369_discount(self, sums):
        """The discount in rupees, or 0.0 if the basket does not qualify.

        Mirrors the arithmetic the app used to do in the browser, including
        `Math.round` on the percentage, so a bill computed here matches a bill
        the app drew before it started asking.
        """
        self.ensure_one()
        if not self._mart369_live():
            return 0.0
        base = self._mart369_base(sums)
        if base < (self.min_spend or 0.0):
            return 0.0

        if self.kind == 'free_delivery':
            off = sums.get('fees', 0.0)
        elif self.kind == 'percent':
            off = round(base * (self.value or 0.0) / 100.0)
            if self.max_off:
                off = min(off, self.max_off)
        else:
            off = self.value or 0.0
        # Never hand money back: a discount stops at the bill.
        return max(0.0, min(off, sums.get('items', 0.0) + sums.get('fees', 0.0)))

    def _mart369_serialize(self):
        """One entry of the app's COUPONS array. `calc` is not sent - the
        server does the arithmetic now, which was the point."""
        self.ensure_one()
        return {
            'code': self.code or '',
            'title': self.title or '',
            'note': self.note or '',
            'group': self.group or None,
            'min': round(self.min_spend or 0.0, 2),
        }
