from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PosLoyaltyPointsRule(models.Model):
    _name = 'pos.loyalty.points.rule'
    _description = 'POS Loyalty Points Rule'
    _rec_name = 'name'
    _order = 'sequence, id'

    name = fields.Char(
        string='Rule Name',
        required=True,
        default='Default Points Rule',
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    currency_amount = fields.Float(
        string='Amount Spent',
        required=True,
        default=100.0,
        help='Amount spent to earn points',
    )
    points_earned = fields.Float(
        string='Points Earned',
        required=True,
        default=10.0,
        help='Points earned per currency amount',
    )
    points_value = fields.Float(
        string='Points Value',
        required=True,
        default=1.0,
        help='Currency value of earned points',
    )
    
    # Redemption Settings
    min_redemption_points = fields.Float(
        string='Minimum Redemption Points',
        default=5000.0,
        help='Minimum points required for redemption',
    )
    redemption_points_per_unit = fields.Float(
        string='Points per Unit Currency',
        default=10.0,
        help='Number of points required for 1 unit of currency discount',
    )
    max_redemption_percent = fields.Float(
        string='Max Redemption % of Order',
        default=100.0,
        help='Maximum percentage of order that can be paid via points (0-100)',
    )
    allow_partial_redemption = fields.Boolean(
        string='Allow Partial Redemption',
        default=True,
        help='Allow customers to redeem part of their points',
    )
    
    is_active = fields.Boolean(
        string='Active',
        default=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    conversion_display = fields.Char(
        string='Conversion Rule',
        compute='_compute_conversion_display',
    )
    redemption_display = fields.Char(
        string='Redemption Rule',
        compute='_compute_redemption_display',
    )

    @api.depends('currency_amount', 'points_earned', 'points_value')
    def _compute_conversion_display(self):
        for record in self:
            record.conversion_display = '%.2f spent = %.2f points = %.2f value' % (
                record.currency_amount, record.points_earned, record.points_value)

    @api.depends('min_redemption_points', 'redemption_points_per_unit')
    def _compute_redemption_display(self):
        for record in self:
            if record.redemption_points_per_unit > 0:
                value = record.min_redemption_points / record.redemption_points_per_unit
                record.redemption_display = 'Min %.0f points = %.2f value' % (
                    record.min_redemption_points, value)
            else:
                record.redemption_display = 'Min %.0f points' % record.min_redemption_points

    @api.constrains('currency_amount', 'points_earned', 'points_value')
    def _check_positive_values(self):
        for record in self:
            if record.currency_amount <= 0:
                raise ValidationError(_('Amount spent must be greater than zero.'))
            if record.points_earned <= 0:
                raise ValidationError(_('Points earned must be greater than zero.'))
            if record.points_value < 0:
                raise ValidationError(_('Points value cannot be negative.'))

    @api.constrains('min_redemption_points', 'redemption_points_per_unit', 'max_redemption_percent')
    def _check_redemption_values(self):
        for record in self:
            if record.min_redemption_points < 0:
                raise ValidationError(_('Minimum redemption points cannot be negative.'))
            if record.redemption_points_per_unit <= 0:
                raise ValidationError(_('Points per unit currency must be greater than zero.'))
            if record.max_redemption_percent < 0 or record.max_redemption_percent > 100:
                raise ValidationError(_('Max redemption percentage must be between 0 and 100.'))

    def action_activate(self):
        self.ensure_one()
        other_rules = self.search([('id', '!=', self.id)])
        other_rules.write({'is_active': False})
        self.is_active = True
        return True

    def action_deactivate(self):
        self.ensure_one()
        self.is_active = False
        return True
    
    def get_redemption_value(self, points):
        """Calculate the currency value for given points"""
        self.ensure_one()
        if self.redemption_points_per_unit > 0:
            return points / self.redemption_points_per_unit
        return 0.0
    
    def get_points_for_value(self, value):
        """Calculate points needed for given currency value"""
        self.ensure_one()
        return value * self.redemption_points_per_unit
