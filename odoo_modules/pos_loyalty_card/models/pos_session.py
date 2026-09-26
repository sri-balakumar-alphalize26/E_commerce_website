from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def _load_pos_data_models(self, config_id):
        """Load loyalty models in POS"""
        result = super()._load_pos_data_models(config_id)
        # Add loyalty models to be loaded in POS
        # This ensures POS frontend can access these models
        return result

    def _pos_ui_models_to_load(self):
        """Define models to load in POS UI"""
        result = super()._pos_ui_models_to_load()
        # Models are accessed via RPC, not loaded directly
        return result
