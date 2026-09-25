"""An order's support tickets, in the order's detail on both Orders screens.

So whoever opens an order sees at once that the customer already complained
about it, and can open that ticket. Rows are the Support screen's own
(`_mart369_admin_row`), so a ticket reads the same in both places.
"""

from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _mart369_admin_detail(self):
        row = super()._mart369_admin_detail()
        tickets = self.env['mart369.ticket'].sudo().search(
            [('order_id', '=', self.id)], order='id desc', limit=10)
        row['tickets'] = [t._mart369_admin_row() for t in tickets]
        return row
