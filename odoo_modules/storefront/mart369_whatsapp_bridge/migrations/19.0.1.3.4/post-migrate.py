"""Address copies take the senior's naming.

Until 19.0.1.3.3 an address copied from a WhatsApp contact into the shop's
book was labelled "WhatsApp". It is now called what the customer calls it -
the senior's `_sa_label()` (the label given on WhatsApp, else the shop's,
else "Home"). The copies already saved are renamed the same way.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Partner = env['res.partner'].with_context(active_test=False)
    copies = Partner.search([('mart369_label', '=', 'WhatsApp'), ('parent_id', '!=', False)])
    renamed = 0
    for address in copies:
        try:
            with cr.savepoint():
                address.mart369_label = Partner._mart369_label_for(address)
                renamed += 1
        except Exception:  # noqa: BLE001 - one odd address stops nothing
            _logger.exception('bridge: could not rename address %s', address.id)
    _logger.info('bridge: %s WhatsApp address copies renamed', renamed)
