"""Which products the shop lists.

Published is not enough. A service is published so it can be bought - the
wallet top-up, a gift card, a repair charge - but it is not something to
browse: on the Dubai shop "Top-up eWallet", "Gift Card" and "Repair Service"
led the "New this week" row. Archived is not listed either: a hand-picked home
row filters the products already picked, which Odoo's own skipping of archived
records never sees. So every list a shopper sees - rows, categories, search,
offers - asks this one rule, and only those lists do. Looking a
product up by id (the cart, a shared link, the product page) does not, so a
gift card in a basket still works.
"""

from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _mart369_listed_domain(self):
        return [('active', '=', True), ('is_published', '=', True), ('type', '!=', 'service')]
