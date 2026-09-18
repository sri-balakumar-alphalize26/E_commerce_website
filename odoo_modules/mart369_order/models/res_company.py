"""Which tax 369 Mart orders carry.

Deliberately a setting rather than a guess. The app quotes prices with tax in
them, the way Indian retail does, so the order total has to equal the number the
customer was shown to the paisa. Picking a tax automatically would either break
that equality or put the wrong rate on an invoice, and both are worse than
asking once.

Left empty, orders carry no tax and the invoice carries no GST - exactly where
things stood before this module. Set to a price-included tax, GST is split out
on the invoice and the customer still pays what the app said.
"""

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    mart369_tax_id = fields.Many2one(
        'account.tax', string='369 Mart tax',
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', id)]",
        help="The tax put on 369 Mart order lines. It must be set to "
             "'Included in price'. Leave empty for no tax.")
