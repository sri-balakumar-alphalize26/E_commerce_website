from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_enable_loyalty_cards = fields.Boolean(
        related='pos_config_id.enable_loyalty_cards',
        readonly=False,
    )
