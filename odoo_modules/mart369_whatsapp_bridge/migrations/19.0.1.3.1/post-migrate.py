"""One address, once: fold the duplicates the WhatsApp copy left behind.

Before this version an address typed in the chat joined the storefront's
book unless exactly the same text was already there - so 'beach road,kollam'
and 'Beach road,Kollam' became two entries, each with its PIN shown twice.
`_mart369_book_tidy` folds them (archived, so old orders keep their address).
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("""
        SELECT parent_id FROM res_partner
         WHERE parent_id IS NOT NULL AND active AND type IN ('delivery', 'other')
         GROUP BY parent_id HAVING count(*) > 1
    """)
    folded = 0
    for (parent_id,) in cr.fetchall():
        customer = env['res.partner'].browse(parent_id)
        try:
            with cr.savepoint():
                folded += len(customer._mart369_book_tidy())
        except Exception:  # noqa: BLE001 - one odd book stops nothing
            _logger.exception('bridge: could not tidy the address book of %s', parent_id)
    _logger.info('bridge: folded %s duplicate addresses', folded)
