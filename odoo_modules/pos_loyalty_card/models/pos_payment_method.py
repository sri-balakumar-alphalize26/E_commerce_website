from odoo import models, fields


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    is_loyalty_payment = fields.Boolean(
        string='Is Loyalty Payment',
        default=False,
        help='Check if this payment method is for loyalty points redemption'
    )
