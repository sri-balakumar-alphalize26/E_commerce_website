"""Telling the customer where their order is.

Hangs off `_mart369_set_state`, which mart369_order already calls once per real
transition and which is already idempotent - so a replayed webhook cannot send
somebody the same message twice.

Whether anything actually goes out is `mart369.whatsapp`'s decision: it checks
the two consents and whether a gateway is installed at all.
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _mart369_set_state(self, state, note=None):
        moved = super()._mart369_set_state(state, note=note)
        if not moved:
            return moved
        try:
            self.env['mart369.whatsapp']._mart369_notify(self, state)
        except Exception:  # noqa: BLE001
            # An update failing is not a reason for the order to stop moving.
            _logger.exception(
                'mart369: could not notify %s about %s', self.mart369_ref, state)
        return moved
