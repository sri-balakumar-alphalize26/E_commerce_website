"""The one column that translates the app's five payment keys into Odoo.

`components/home/payment.js` knows five ways to pay: upi, card, netbanking, cod and
wallet. Odoo ships generic payment.method records for the first three and knows
nothing about the last two, which are not gateways at all.

Rather than scatter those five strings through the module, they live here, on one
Selection. Everything else asks this field which method it is looking at - so
switching a provider on, or adding a sixth way to pay, is a data change.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

APP_CODES = [
    ('upi', "UPI"),
    ('card', "Credit / debit card"),
    ('netbanking', "Net banking"),
    ('cod', "Cash on delivery"),
    ('wallet', "369 Wallet"),
]


class PaymentMethod(models.Model):
    _inherit = 'payment.method'

    mart369_app_code = fields.Selection(
        APP_CODES, string="369 Mart method",
        index='btree_not_null', copy=False,
        help="Which of the storefront's five payment choices this method answers.")

    @api.model
    def _mart369_tag_core_methods(self):
        """Tag the four methods Odoo already ships.

        This cannot be done with plain XML: `payment` and `delivery` create their
        records with noupdate set, so a later <record> against the same xmlid is
        skipped on every module update, whoever writes it. A <function> runs
        regardless, and this one only fills the tag in when it is empty - so an
        operator who deliberately re-pointed a method keeps their change.
        """
        wanted = {
            'payment.payment_method_upi': 'upi',
            'payment.payment_method_card': 'card',
            'payment.payment_method_netbanking': 'netbanking',
            'delivery.payment_method_cash_on_delivery': 'cod',
        }
        for xmlid, code in wanted.items():
            method = self.env.ref(xmlid, raise_if_not_found=False)
            if method and not method.mart369_app_code:
                method.sudo().write({'mart369_app_code': code})
                _logger.info('mart369: tagged %s as %s', xmlid, code)
