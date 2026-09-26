"""Bring orders placed before 19.0.1.3.0 into the books.

Before this version no 369 Mart payment was ever matched to its invoice, no
delivery was ever validated, and a cash order cancelled before the door kept
its invoice. The code now does all three as orders move; this does them once
for the orders that already moved.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env['sale.order'].search([('mart369_ref', '!=', False)])

    voided = orders.filtered(lambda o: o.state == 'cancel')
    for order in voided:
        order._mart369_void_unpaid_invoices()

    delivered = orders.filtered(lambda o: o.mart369_state == 'delivered')
    for order in delivered:
        order._mart369_validate_pickings()

    settled = orders.filtered(lambda o: o.state == 'sale')
    for order in settled:
        order._mart369_settle_invoice()

    _logger.info('mart369: books repaired - %s cancelled, %s delivered, %s open orders checked',
                 len(voided), len(delivered), len(settled))
