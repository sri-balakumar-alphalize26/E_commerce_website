"""A credit note on an order from Odoo's Sales takes back the points it earned.

That is how money goes back on such an order - there is no wallet refund - so
this is the Sales twin of the app's `_mart369_refund_to_wallet` hook. App
orders are skipped: their credit notes follow a wallet refund, which has already
taken the points back.
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda m: m.move_type == 'out_refund'):
            # A reversal keeps each line's sale line, so this finds the order.
            lines = move.invoice_line_ids.filtered(lambda l: l.sale_line_ids)
            for order in lines.sale_line_ids.order_id.filtered(lambda o: not o.mart369_ref):
                value = sum(lines.filtered(
                    lambda l: order in l.sale_line_ids.order_id).mapped('price_total'))
                try:
                    with self.env.cr.savepoint():
                        order._mart369_points_take_back(value)
                        refunded = sum(order.invoice_ids.filtered(
                            lambda m: m.move_type == 'out_refund' and m.state == 'posted'
                        ).mapped('amount_total'))
                        if order.currency_id.compare_amounts(refunded, order.amount_total) >= 0:
                            # Refunded in full: what it spent comes back too.
                            order._mart369_points_give_spent()
                except Exception:  # noqa: BLE001
                    _logger.exception('mart369 loyalty: points on credit note %s failed', move.name)
        return posted
