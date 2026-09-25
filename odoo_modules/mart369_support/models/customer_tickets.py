"""A customer's support tickets, on the console's customer profile.

The profile itself is mart369_order's (models/customer_profile.py); this adds
the tickets beside the orders, so whoever picks up the phone sees the last
complaint next to the order it was about. Rows are the Support screen's own
(`_mart369_admin_row`), so a ticket reads the same in both places.
"""

from odoo import api, models

TICKETS_SHOWN = 20


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def mart369_admin_profile(self, user_id):
        profile = super().mart369_admin_profile(user_id)
        partner = self._mart369_customer_partner(user_id)
        Ticket = self.env['mart369.ticket'].sudo()
        mine = [('partner_id', 'child_of', partner.id)]
        tickets = Ticket.search(mine, order='id desc', limit=TICKETS_SHOWN)
        profile['tickets'] = [t._mart369_admin_row() for t in tickets]
        profile['openTickets'] = Ticket.search_count(mine + [('state', 'in', ('new', 'open', 'waiting'))])
        return profile
