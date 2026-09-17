"""A payment, and the moment it becomes true.

Today the browser decides all of this. ``demoGateway.netbanking()`` and
``.wallet()`` take no arguments at all and return success unconditionally
(payment.js:107); ``newTxnId()`` is a slice of the clock; and the order object the
app then writes carries ``paid``, ``txn`` and ``status`` that nothing ever checked
(Checkout.jsx:617-631).

Here a payment is a ``payment.transaction`` and there is exactly one place where it
becomes paid: :meth:`_post_process`, which Odoo calls after the provider's own
webhook has verified the signature. Nothing the app sends can reach it.

Two payments have no gateway behind them and so settle differently:

* **the wallet**, which settles the instant the ledger row is written, because the
  money moved inside our own books and there is nothing external to confirm;
* **cash on delivery**, which stays *pending* until somebody says the cash arrived -
  because it has not. The app marks a cash order ``paid: payable`` the moment it is
  placed, which is simply false, and is the single most misleading thing on the
  receipt.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Provider error codes worth offering a retry for. A wrong OTP is the customer's
# to fix; a declined card is not.
RETRYABLE = ('otp', 'incorrect_otp', 'timeout', 'authentication_failed')


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    mart369_kind = fields.Selection(
        [('order', "Order"), ('topup', "Wallet top-up"), ('validation', "Saving a method")],
        string="369 Mart kind", default='order', index='btree_not_null', copy=False)
    mart369_app_method = fields.Selection(
        related='payment_method_id.mart369_app_code', store=True, string="369 Mart method")
    mart369_order_ref = fields.Char(
        string="App order reference", index='btree_not_null', copy=False,
        help="The 369M-/369E- id the app shows, until sale.order owns it.")
    mart369_wallet_card_id = fields.Many2one(
        'loyalty.card', string="Wallet", ondelete='set null', copy=False)
    mart369_wallet_used = fields.Monetary(
        string="Paid from wallet", currency_field='currency_id', copy=False)
    mart369_history_id = fields.Many2one(
        'loyalty.history', string="Wallet movement", readonly=True, copy=False,
        help="Set once. A repeated webhook finds it filled and does nothing.")
    mart369_amount_client = fields.Boolean(
        string="Amount came from the app", readonly=True, copy=False,
        help="No sale order existed to price this, so the amount is the one the "
             "browser sent. mart369_cart and mart369_order close this.")
    mart369_txn = fields.Char(
        string="Transaction id", compute='_compute_mart369_txn',
        help="The only thing the app should ever print as its txn.")
    mart369_retryable = fields.Boolean(compute='_compute_mart369_txn')

    # --------------------------------------------------------------- computes

    @api.depends('provider_reference', 'reference', 'state', 'state_message')
    def _compute_mart369_txn(self):
        for tx in self:
            tx.mart369_txn = tx.provider_reference or tx.reference
            message = (tx.state_message or '').lower()
            tx.mart369_retryable = tx.state == 'error' and any(
                code in message for code in RETRYABLE)

    # ------------------------------------------------------------ the one seam

    def _post_process(self):
        """Odoo calls this once the provider has confirmed. Everything hangs here.

        super() first so `sale`'s own handling still runs; then our two hooks. This
        method is reached from the provider's webhook controller, after its
        signature check - which is the entire reason `paid` can be trusted now and
        could not be before.
        """
        super()._post_process()
        for tx in self:
            try:
                if tx.mart369_kind == 'topup':
                    tx._mart369_credit_wallet()
                elif tx.state == 'done':
                    tx._mart369_on_paid()
                elif tx.state in ('cancel', 'error'):
                    tx._mart369_on_failed()
            except Exception:  # noqa: BLE001 - one bad transaction must not stop the rest
                _logger.exception('mart369: post-processing %s failed', tx.reference)

    def _mart369_on_paid(self):
        """The money is in and verified.

        SEAM: mart369_order overrides this to move the order to 'placed', stamp the
        paid amount and the txn onto it, and issue the delivery OTP. Called once per
        transaction from _post_process, after the provider's signature check.

        Must stay idempotent - a webhook can repeat, and providers do resend.
        """
        self.ensure_one()
        return False

    def _mart369_on_failed(self):
        """Cancelled or errored: give back whatever the wallet had already paid.

        SEAM: mart369_order overrides this to release the stock reservation and mark
        the order's payment failed. It must call super(), or the wallet leg of a
        split payment is silently kept.
        """
        self.ensure_one()
        self._mart369_refund_wallet_leg()
        return False

    @api.model
    def _mart369_amount_for(self, order_ref, claimed_amount, currency=None):
        """What to actually charge.

        SEAM: mart369_order overrides this to read the total off the sale.order and
        ignore `claimed_amount` outright, and to stop setting mart369_amount_client.

        Until then the browser is the only thing that knows what the basket came to,
        because there is no cart on the server yet. That is a real hole, so it is
        recorded on every transaction rather than left implicit.
        """
        currency = currency or self.env.company.currency_id
        amount = currency.round(abs(float(claimed_amount or 0.0)))
        if currency.is_zero(amount):
            raise UserError(_("A payment needs an amount."))
        return amount, True

    # ---------------------------------------------------------------- wallet

    def _mart369_credit_wallet(self):
        """Put a confirmed top-up into the wallet. Exactly once, ever.

        mart369_history_id is the idempotency key: a replayed webhook finds it set
        and returns. Without it a provider retrying three times would credit three
        times, and the customer would be right to keep the money.
        """
        self.ensure_one()
        if self.state != 'done' or self.mart369_history_id:
            return False
        card = self.mart369_wallet_card_id or self.env['loyalty.card']._mart369_wallet(
            self.partner_id)
        card._mart369_move(
            self.amount, 'add', _("Money added"),
            sub=_("Via %s", self.payment_method_id.name or self.provider_id.name),
            transaction=self)
        return True

    def _mart369_refund_wallet_leg(self):
        """Give back the wallet part of a split payment that then failed.

        The app has no concept of this at all: it debits the wallet locally after
        writing the order (Home.jsx:443), so a failed gateway leg leaves the money
        gone and the order unpaid.
        """
        self.ensure_one()
        if not self.mart369_wallet_used or not self.mart369_wallet_card_id:
            return False
        already = self.env['loyalty.history'].sudo().search_count([
            ('card_id', '=', self.mart369_wallet_card_id.id),
            ('mart369_kind', '=', 'refund'),
            ('mart369_sub', '=', self.reference),
        ])
        if already:
            return False
        self.mart369_wallet_card_id._mart369_move(
            self.mart369_wallet_used, 'refund', _("Payment failed"), sub=self.reference)
        return True

    def _mart369_mark_cod_collected(self):
        """The rider came back with the cash.

        An operator button today. When mart369_order exists, the delivery transition
        calls this same method - which is why it is a method and not a button
        handler.
        """
        self.ensure_one()
        if not self.provider_id.mart369_is_cod:
            raise UserError(_("Only a cash-on-delivery payment can be collected."))
        if self.state == 'done':
            return False
        self._set_done(state_message=_("Cash collected on delivery."))
        self._post_process()
        return True

    # ------------------------------------------------------------- the app's view

    def _mart369_serialize(self):
        """What the pay and status routes answer with.

        The three shapes are demoGateway's own, so PaySheet.finish() and
        submitOtp() (Checkout.jsx:429,459) keep working unchanged - they poll a
        route instead of awaiting a promise.
        """
        self.ensure_one()
        if self.state == 'done':
            return {'ok': True, 'state': 'done', 'txn': self.mart369_txn}
        if self.state in ('error', 'cancel'):
            payload = {
                'ok': False,
                'error': self.state_message or _("Your bank declined this transaction."),
            }
            if self.mart369_retryable:
                payload['retry'] = True
            return payload
        return {'ok': True, 'state': 'pending', 'txn': self.mart369_txn}
