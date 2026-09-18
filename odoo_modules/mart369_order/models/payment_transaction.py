"""The three seams mart369_payment left open.

`mart369_payment` was written before this module existed, and said so in its own
docstrings: `_mart369_on_paid` returned `False`, `_mart369_on_failed` only
handed the wallet leg back, and `_mart369_amount_for` charged whatever the
browser claimed the basket came to and recorded that it had done so. Those three
are filled in here, which is the whole reason this module has to exist before
payments can be trusted.

Everything below has to survive being called twice. A provider's webhook repeats
- that is normal, not an error - so placing, stamping and issuing a delivery
code all check whether they have already happened.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    mart369_order_id = fields.Many2one(
        'sale.order', string='369 Mart order', copy=False, index=True,
        compute='_compute_mart369_order_id', store=True,
        help="The order this payment is for, resolved from its order number.")

    @api.depends('mart369_order_ref')
    def _compute_mart369_order_id(self):
        """`mart369_order_ref` was a free-text Char because there was no record
        behind it. Now there is, so the text resolves to the order once."""
        for tx in self:
            order = self.env['sale.order'].browse()
            if tx.mart369_order_ref:
                order = self.env['sale.order'].sudo().search(
                    [('mart369_ref', '=', tx.mart369_order_ref)], limit=1)
            tx.mart369_order_id = order

    # ------------------------------------------------------------ the money

    @api.model
    def _mart369_amount_for(self, order_ref, claimed_amount, currency=None):
        """What to actually charge: the order's total, not the browser's claim.

        This is the override the seam was written for. The order exists before
        the payment does - the app places it, gets an order number back, then
        pays - so there is always a total to read. `claimed_amount` is now used
        for nothing but a log line when the two disagree.
        """
        order = self.env['sale.order'].sudo().search(
            [('mart369_ref', '=', order_ref or '')], limit=1) if order_ref else None
        if not order:
            # No order behind this reference: a wallet top-up, or an app that
            # has not been wired up yet. Leave the old behaviour in place.
            return super()._mart369_amount_for(order_ref, claimed_amount, currency=currency)

        currency = currency or order.currency_id or self.env.company.currency_id
        amount = currency.round(order.amount_total)
        claimed = currency.round(abs(float(claimed_amount or 0.0)))
        if claimed and currency.compare_amounts(claimed, amount) != 0:
            _logger.warning(
                'mart369: %s claimed %s but order %s totals %s - charging the order',
                self.env.user.login, claimed, order.mart369_ref, amount)
        return amount, False

    # ------------------------------------------------------------- the seams

    def _mart369_on_paid(self):
        """The money is in and verified: the order is really placed.

        Idempotent throughout - `_mart369_set_state` does nothing if the order
        is already placed, and the delivery code is only issued the first time.
        """
        self.ensure_one()
        super()._mart369_on_paid()
        order = self.mart369_order_id
        if not order:
            return False

        order = order.sudo()
        first_time = order.mart369_state in ('draft', False)
        order.write({
            'mart369_paid': order.currency_id.round(self.amount + (self.mart369_wallet_used or 0.0)),
            'mart369_wallet_used': self.mart369_wallet_used or 0.0,
            'mart369_txn': self.mart369_txn or self.reference,
            'mart369_method': self.mart369_app_method or '',
            'mart369_pay_note': self._mart369_pay_note(),
        })
        if first_time:
            order.write({'mart369_placed_at': fields.Datetime.now()})
            order._mart369_set_state('placed')
            order._mart369_spend_coupon()
            order._mart369_confirm()
            order._mart369_issue_otp()
        return True

    def _mart369_on_failed(self):
        """Cancelled or errored: hand the wallet leg back, free what was held.

        super() first, and unconditionally: it is what returns the wallet money,
        and mart369_payment's own docstring warns that skipping it silently
        keeps the wallet leg of a split payment.
        """
        self.ensure_one()
        super()._mart369_on_failed()
        order = self.mart369_order_id
        if not order or order.mart369_state not in ('draft', False):
            # Already placed: a later failed retry must not unplace it.
            return False
        order.sudo()._mart369_release_slot()
        return True

    def _mart369_pay_note(self):
        """The words the app prints under the total, e.g. "HDFC •••• 4242"."""
        self.ensure_one()
        if self.token_id:
            return self.token_id.sudo().display_name
        if self.provider_id.sudo().mart369_is_cod:
            return self.env._('Cash on delivery')
        if self.provider_id.sudo().mart369_is_wallet:
            return self.env._('369 Wallet')
        return self.provider_id.sudo().display_name or ''
