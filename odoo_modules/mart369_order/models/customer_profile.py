"""A customer's full profile, for the console's profile page.

The drawer (res.users.mart369_admin_detail) is a glance: four figures, the
addresses, the last six orders. The profile is the whole story - every order
they have placed, with its state, and every movement of their wallet.

It lives here rather than in mart369_auth because it needs the orders (this
module) and the wallet (mart369_payment, which this depends on); auth knows
neither. The drawer's own detail is reused as it is, so the two never disagree
about who this customer is.
"""

from odoo import api, models
from odoo.exceptions import AccessError, UserError

EDITOR_GROUP = 'website.group_website_designer'
ORDERS_SHOWN = 100
MOVES_SHOWN = 100


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def mart369_admin_profile(self, user_id):
        if not self.env.user.has_group(EDITOR_GROUP):
            raise AccessError(self.env._('You do not have access to this.'))
        detail = self.mart369_admin_detail(user_id)
        if not detail:
            raise UserError(self.env._('There is no such customer.'))
        user = self.sudo().browse(int(user_id))
        partner = user.partner_id.commercial_partner_id

        # Every order they placed - an unpaid online basket (`draft`) never
        # became one, so it is left out; cancelled ones stay, they happened.
        Order = self.env['sale.order'].sudo()
        domain = [('partner_id', 'child_of', partner.id),
                  ('mart369_state', 'not in', (False, 'draft'))]
        orders = Order.search(domain, order='mart369_placed_at desc, id desc', limit=ORDERS_SHOWN)
        detail['orders'] = [o._mart369_admin_row() for o in orders]
        detail['orderTotal'] = Order.search_count(domain)

        # The wallet's ledger, if they have a wallet. Looked up, never made:
        # opening a profile must not open an account.
        card = self.env['loyalty.card'].sudo().search(
            [('partner_id', '=', partner.id), ('mart369_is_wallet', '=', True)], limit=1)
        moves = []
        if card:
            currency = card.currency_id or self.env.company.currency_id
            for row in card._mart369_ledger(limit=MOVES_SHOWN):
                move = row._mart369_serialize()
                move['amountText'] = currency.format(move['amount'])
                moves.append(move)
        detail['walletMoves'] = moves
        detail['currency'] = self.env['mart369.serializable']._mart369_currency(
            self.env.company.currency_id)
        return detail
