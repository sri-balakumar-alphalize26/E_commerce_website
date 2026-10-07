"""Switch off the two example deals nobody has made their own.

`_mart369_load_demo` no longer runs on install. The deals it made
("Weekend electronics", "Starting on Friday") put random products on offer
for real customers. Matched on the words it wrote - a deal still carrying its
"An example..." note is the example; one renamed or re-noted is the shop's.
Archived, not deleted.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

EXAMPLES = {
    ('Weekend electronics', 'An example - switch it off or delete it.'),
    ('Starting on Friday', 'An example of a deal waiting for its window.'),
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    deals = env['mart369.deal'].search([('active', '=', True)])
    gone = deals.filtered(lambda d: (d.name, d.note) in EXAMPLES)
    gone.write({'active': False})
    _logger.info('mart369_cart: switched off %d example deal(s)', len(gone))
