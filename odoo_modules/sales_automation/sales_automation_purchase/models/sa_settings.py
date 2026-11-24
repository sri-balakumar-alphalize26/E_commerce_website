# -*- coding: utf-8 -*-
from odoo import fields, models


class SaAiSettingsVendorOrders(models.Model):
    _inherit = 'sa.ai.settings'

    late_min_saving_amount = fields.Float(
        'Smallest Saving', default=20.0,
        help="A cheaper vendor is pointed out only when the whole line becomes at least this "
             "much cheaper, in the company's currency.")
