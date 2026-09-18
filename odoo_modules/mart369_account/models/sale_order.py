"""What an order sets off.

Two of this module's pieces are not things a customer does - they are things
that happen to them because an order moved. Both hang off
`_mart369_set_state`, which mart369_order already calls once per real
transition and which is already idempotent, so neither can fire twice for the
same step.

* **placed** - if this customer came from somebody's referral code and this is
  their first order, the inviter is paid.
* **delivered** - a scratch card is minted. The app never minted one, which is
  why every customer's rewards screen showed the same four cards forever.
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _mart369_set_state(self, state, note=None):
        moved = super()._mart369_set_state(state, note=note)
        if not moved:
            # Already in that state: a replayed webhook, not a new event.
            return moved
        try:
            if state == 'placed':
                self.env['mart369.referral']._mart369_on_first_order(self)
            elif state == 'delivered':
                self.env['mart369.scratch']._mart369_mint_for_order(self)
        except Exception:  # noqa: BLE001
            # A reward is not worth failing a delivery over. The order moving on
            # is the thing that must not be lost.
            _logger.exception(
                'mart369: rewarding %s on %s failed', self.mart369_ref, state)
        return moved
