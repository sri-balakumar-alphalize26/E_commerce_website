"""The customer's loyalty card on the console's profile page, beside the wallet."""

from odoo import api, models

MOVES_SHOWN = 20


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def mart369_admin_profile(self, user_id):
        detail = super().mart369_admin_profile(user_id)
        partner = self.sudo().browse(int(user_id)).partner_id
        # Looked up, never made: opening a profile must not open a card.
        card = self.env['pos.loyalty.card'].sudo()._mart369_card_for(partner)
        detail['points'] = None
        if card:
            rows = self.env['pos.loyalty.history'].sudo().search(
                [('card_id', '=', card.id)], order='id desc', limit=MOVES_SHOWN)
            detail['points'] = dict(
                card._mart369_serialize(),
                moves=[row._mart369_serialize() for row in rows])
        return detail
