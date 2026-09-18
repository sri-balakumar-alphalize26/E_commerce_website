"""Order lines.

Three things on an order are not basket items: the delivery fee, the priority
fee and the coupon. They are still order lines - Odoo has to invoice them - but
the app has always shown them in the bill rather than the basket, so they are
tagged here and kept out of `items` and `snap` when the order is serialized.

`mart369_mrp` carries the price the product was struck through at, because the
app prints a "you saved" line and the strike-through price is not something a
`sale.order.line` otherwise remembers.
"""

from odoo import fields, models

KIND_CHOICES = [
    ('fee', 'Delivery or priority fee'),
    ('coupon', 'Coupon discount'),
]


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    mart369_kind = fields.Selection(
        KIND_CHOICES, string='369 Mart line', copy=False, index=True,
        help="Set on the lines the app shows in the bill rather than the "
             "basket. Empty means an ordinary basket line.")
    mart369_mrp = fields.Float(
        string='Was', copy=False, digits='Product Price',
        help="The struck-through price at the moment of ordering, so the "
             "saving the customer was shown can still be printed later.")
