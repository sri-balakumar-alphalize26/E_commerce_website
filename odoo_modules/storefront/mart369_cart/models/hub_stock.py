"""Stock the shop shows, while the hub rules are on.

Each hub is its own company (Ruwi, Sohar, Salalah), and Odoo counts free stock
only in the companies the reader is in. A shopper is in the shop's own
company, so an item only another hub holds read as sold out ("Notify me",
every option crossed out) - while its badge, which asks every hub
(cart.py `_mart369_hub_offer`), said it comes "Next day" from that hub.

While the hub table has a row, the cards and the product page count every
hub's stock instead, the same hubs the badge asks. With the table empty the
shop counts exactly as before.
"""

from odoo import api, models

from .branch import has_pin


class Mart369SerializableHubs(models.AbstractModel):
    _inherit = 'mart369.serializable'

    @api.model
    def _mart369_stock_context(self):
        context = super()._mart369_stock_context()
        if not self.env['mart369.hub.rule']._mart369_table():
            return context
        hubs = self.env['stock.warehouse'].sudo().search([]).filtered(
            lambda b: has_pin(b.mart369_lat, b.mart369_lng))
        companies = self.env.company | hubs.company_id
        return dict(context, allowed_company_ids=companies.ids)
