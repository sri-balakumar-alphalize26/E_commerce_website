from odoo import models, fields, api


class PosConfig(models.Model):
    _inherit = 'pos.config'

    enable_loyalty_cards = fields.Boolean(
        string='Enable Loyalty Cards',
        default=True,
        help='Enable or disable the Loyalty Card system for this POS. '
             'When disabled, loyalty buttons will be hidden and no points '
             'will be earned or redeemed on orders from this POS.'
    )
    loyalty_active = fields.Boolean(
        string='Loyalty Active', compute='_compute_loyalty_active',
        help='Effective loyalty state = master switch AND this shop switch.')

    @api.depends('enable_loyalty_cards')
    def _compute_loyalty_active(self):
        master = self.env['pos.loyalty.card.settings'].get_settings().enable_loyalty
        for rec in self:
            rec.loyalty_active = bool(rec.enable_loyalty_cards) and bool(master)

    # Mobile config is GLOBAL (Configuration > Loyalty > Loyalty Settings).
    # These are computed so the POS frontend keeps reading them from pos.config
    # while the single source of truth is pos.loyalty.card.settings.
    loyalty_mobile_number_length = fields.Integer(
        string='Mobile Number Length',
        compute='_compute_loyalty_mobile_config',
        help='Global loyalty mobile number length (set in Configuration > Loyalty > Loyalty Settings).'
    )
    loyalty_country_dial_code = fields.Char(
        string='Country Dial Code',
        compute='_compute_loyalty_mobile_config',
        help='Global loyalty country dial code (set in Configuration > Loyalty > Loyalty Settings).'
    )

    def _compute_loyalty_mobile_config(self):
        cfg = self.env['pos.loyalty.card.settings'].get_settings()
        length = cfg.mobile_number_length or 10
        dial = cfg.country_dial_code or '91'
        for rec in self:
            rec.loyalty_mobile_number_length = length
            rec.loyalty_country_dial_code = dial

    @api.model
    def _load_pos_data_read(self, records, config):
        # Ensure the loyalty on/off flag reaches the POS frontend (this is the dict
        # the base pos.config already augments with _base_url/_server_version).
        read_records = super()._load_pos_data_read(records, config)
        if read_records:
            read_records[0]['enable_loyalty_cards'] = bool(config.enable_loyalty_cards)
            read_records[0]['loyalty_active'] = bool(config.loyalty_active)
        return read_records
