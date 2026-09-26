from odoo import models, fields, api


class PosLoyaltyPointsHistory(models.Model):
    _name = 'pos.loyalty.points.history'
    _description = 'POS Loyalty Points History'
    _rec_name = 'description'
    _order = 'date desc, id desc'

    card_id = fields.Many2one(
        'pos.loyalty.card',
        string='Loyalty Card',
        required=True,
        ondelete='cascade',
    )
    customer_name = fields.Char(
        related='card_id.name',
        string='Customer',
        store=True,
    )
    card_number = fields.Char(
        related='card_id.card_number',
        string='Card Number',
        store=True,
    )
    date = fields.Datetime(
        string='Date',
        default=fields.Datetime.now,
        required=True,
    )
    points = fields.Float(
        string='Points',
        required=True,
        digits=(16, 2),
    )
    transaction_type = fields.Selection([
        ('earned', 'Earned'),
        ('redeemed', 'Redeemed'),
        ('adjusted', 'Adjusted'),
        ('expired', 'Expired'),
    ], string='Type', required=True, default='earned')
    description = fields.Char(
        string='Description',
    )
    amount = fields.Float(
        string='Purchase Amount',
        digits=(16, 2),
    )
    pos_order_id = fields.Many2one(
        'pos.order',
        string='POS Order',
    )
    company_id = fields.Many2one(
        related='card_id.company_id',
        string='Company',
        store=True,
    )
