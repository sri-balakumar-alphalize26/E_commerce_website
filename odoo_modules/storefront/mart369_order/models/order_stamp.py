"""When the order reached each step.

The app drew its timeline from a timer: `liveStatus()` in
components/home/orderState.js worked out where an order "should" be from how
long ago it was placed, which meant the timeline was a different story every
time the page was reloaded and could not survive the demo clock being removed.

A stamp is written once, when the order really reaches a state, so the timeline
is a record of what happened rather than a guess.
"""

from odoo import fields, models

from .sale_order import STATE_CHOICES


class Mart369OrderStamp(models.Model):
    _name = 'mart369.order.stamp'
    _description = '369 Mart Order Step'
    _order = 'at asc, id asc'

    order_id = fields.Many2one(
        'sale.order', string='Order', required=True, ondelete='cascade', index=True)
    state = fields.Selection(STATE_CHOICES, string='Step', required=True)
    at = fields.Datetime(string='At', required=True, default=fields.Datetime.now)
    note = fields.Char(string='Note')
    user_id = fields.Many2one(
        'res.users', string='By', default=lambda self: self.env.user,
        ondelete='set null')

    _step_uniq = models.Constraint(
        'unique (order_id, state)',
        'That order has already been stamped with that step.',
    )

    def _mart369_serialize(self):
        self.ensure_one()
        return {
            'state': self.state,
            'at': int(self.at.timestamp() * 1000) if self.at else None,
            'note': self.note or '',
        }
