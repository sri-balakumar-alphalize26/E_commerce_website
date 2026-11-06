# -*- coding: utf-8 -*-
"""The promise follows the Quick / Express decision made on the order."""

from odoo import fields, models


class SaDeliverySettings(models.Model):
    _inherit = 'sa.delivery.settings'

    qe_enabled = fields.Boolean(
        'Decide Quick or Express by reach, stock and area', default=True,
        help="On: an order is Quick when a shop that does Quick, within its "
             "reach of the customer's map pin, holds every line; otherwise "
             "the customer's pincode area decides. Off: the order's own "
             "warehouse stock decides, as before.")
    qe_auto_fee = fields.Boolean(
        'Add the delivery fee when the order is confirmed', default=False,
        help="Off (default): the fee is added only when somebody presses Add "
             "delivery fee on the order, so a total the customer has already "
             "agreed on WhatsApp does not change.")
    qe_enforce_minimum = fields.Boolean(
        'Refuse a Quick order below the minimum', default=False,
        help="Off (default): an order below the Quick minimum is only flagged.")

    def _promise_for(self, picking):
        kind, promised = super()._promise_for(picking)
        order = picking.sale_id
        if not (self.qe_enabled and order and order.qe_decided and order.qe_mode):
            return kind, promised

        mode = order.qe_mode if self.quick_enabled else 'express'
        due = order._qe_due() if mode == order.qe_mode else False
        if not due:
            now = fields.Datetime.now()
            if mode == 'quick':
                due = fields.Datetime.add(now, hours=max(1, self.quick_hours))
                if self.cutoff_hour and now.hour >= self.cutoff_hour:
                    due = fields.Datetime.add(due, days=1)
            else:
                due = fields.Datetime.add(now, days=max(1, self.express_days))
        order.sudo().write({'qe_due_at': due})
        return mode, due
