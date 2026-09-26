"""Put back in stock the goods of returns finished before 19.0.1.4.0.

Refunds were issued but nothing ever came back into Inventory. A second return
on the same order finds nothing left to return and does nothing.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    returns = env['mart369.order.return'].search([('state', '=', 'done')], order='id')
    restocked = returns.filtered(lambda r: r._mart369_restock())
    _logger.info('mart369: %s of %s finished returns put back in stock',
                 len(restocked), len(returns))
