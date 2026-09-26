"""An order from Odoo's Sales is delivered when its last outgoing picking is done.

App orders are not looked at here: they have their own steps (the delivery code
at the door), and earn through `_mart369_set_state`.
"""

from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        result = super()._action_done()
        orders = self.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.sale_id
            and not p.sale_id.mart369_ref).mapped('sale_id')
        for order in orders:
            if order._mart369_points_delivered_at():
                order._mart369_points_staff_step('delivered')
        return result
