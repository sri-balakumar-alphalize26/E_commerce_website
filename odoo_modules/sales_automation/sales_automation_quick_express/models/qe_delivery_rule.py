# -*- coding: utf-8 -*-
"""What a Quick or an Express delivery costs."""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

MODE_CHOICES = [
    ('quick', 'Quick'),
    ('express', 'Express'),
]


class SaQeDeliveryRule(models.Model):
    _name = 'sa.qe.delivery.rule'
    _description = 'Quick / Express Delivery Fee'
    _order = 'mode'
    _rec_name = 'label'

    mode = fields.Selection(MODE_CHOICES, required=True)
    label = fields.Char(required=True)
    eta = fields.Char('Promise', required=True,
                      help="What the customer is told, e.g. Delivery in 13 mins.")
    min_order = fields.Float(
        'Minimum order',
        help="A Quick order below this is flagged, and refused when Delivery "
             "Settings says so. 0 = no minimum.")
    free_above = fields.Float(
        'Free above',
        help="The fee is charged while the goods total is below this. "
             "0 = delivery is always free.")
    fee = fields.Float('Delivery fee')
    active = fields.Boolean(default=True)

    _mode_uniq = models.Constraint(
        'unique(mode)', 'There is already a rule for that delivery.')

    @api.constrains('min_order', 'free_above', 'fee')
    def _check_amounts(self):
        for rule in self:
            if min(rule.min_order, rule.free_above, rule.fee) < 0:
                raise ValidationError(_("Amounts cannot be negative."))

    @api.model
    def _qe_for(self, mode):
        return self.sudo().search([('mode', '=', mode)], limit=1)
