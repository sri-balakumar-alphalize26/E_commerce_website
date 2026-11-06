"""The order in Odoo's own books: stock that moves, invoices that get paid.

Three things the storefront did its own way and the books never heard of:

**The money never met the bill.** A payment settles in `_post_process`, and
`account_payment` books it there - but the invoice is only made afterwards, in
`_mart369_on_paid`, so the transaction carries no `invoice_ids` and the two
never reconcile. Every invoice read *Not Paid* however it was paid. Here the
invoice is linked to the order's transactions and the payment matched to it,
and the wallet part of a split payment is booked in the 369 Wallet journal.

**The parcel never left the shelf.** Confirming the order makes the outgoing
delivery, and nothing ever validated it, so an order the app called delivered
still had its picking at Ready and the stock never went down.

**A cancelled order stayed billed.** Cancelling credits what was paid, which is
right - but a cash order cancelled before the door had paid nothing, so its
invoice stayed posted and open, and the day's revenue counted an order the shop
never delivered.

Everything here runs after the customer's side is already true - paid,
delivered, cancelled - so each step is swallowed and logged like the invoice in
order_place.py: finance can fix an unmatched payment; an exception here would
undo the thing the customer just did.
"""

import logging

from odoo import Command, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _mart369_transactions(self):
        self.ensure_one()
        if not self.mart369_ref:
            return self.env['payment.transaction']
        return self.env['payment.transaction'].sudo().search([
            ('mart369_order_ref', '=', self.mart369_ref),
            ('mart369_kind', '=', 'order'),
        ])

    # ------------------------------------------------------------- payments

    def _mart369_settle_invoice(self):
        """Match the order's payments to its invoice. Safe to call any time.

        The transactions get the invoice in `invoice_ids` - not the order in
        `sale_order_ids`, which would wake `sale`'s own post-processing and
        have it confirm the order again and email the customer. From then on a
        transaction that settles later (cash at the door) is matched by Odoo
        itself when it books the payment.
        """
        self.ensure_one()
        invoices = self.invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
        if not invoices or not self.mart369_ref:
            return False
        try:
            with self.env.cr.savepoint():
                for tx in self._mart369_transactions():
                    missing = invoices - tx.invoice_ids
                    if missing:
                        tx.invoice_ids = [Command.link(inv.id) for inv in missing]
                    if tx.state == 'done':
                        if tx.payment_id:
                            self._mart369_reconcile(tx.payment_id, invoices)
                        else:
                            tx.with_company(tx.company_id)._create_payment()
                    tx._mart369_book_wallet_leg(invoices)
        except Exception:  # noqa: BLE001 - see the module docstring
            _logger.exception('mart369: could not match payments to %s', self.mart369_ref)
            return False
        return True

    def _mart369_reconcile(self, payment, invoices):
        """Odoo's own match, from `_create_payment`: the open receivable lines
        of the payment against the invoice's."""
        if payment.state in ('draft', 'canceled'):
            return
        lines = (payment.move_id.line_ids + invoices.line_ids).filtered(
            lambda line: line.account_id == payment.destination_account_id
            and not line.reconciled)
        if lines.filtered(lambda l: l.move_id == payment.move_id) and lines.filtered(
                lambda l: l.move_id in invoices):
            lines.reconcile()

    # ------------------------------------------------------------- the parcel

    def _mart369_validate_pickings(self):
        """The delivery is done: take the goods out of stock.

        Every line is sent in full - the doorstep code is the proof it arrived,
        and a line the shop took out is already at zero on the order.
        """
        self.ensure_one()
        pickings = self.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state not in ('done', 'cancel'))
        for picking in pickings:
            try:
                with self.env.cr.savepoint():
                    self._mart369_picking_done(picking)
            except Exception:  # noqa: BLE001 - see the module docstring
                _logger.exception('mart369: could not validate %s for %s',
                                  picking.name, self.mart369_ref)
        return True

    @staticmethod
    def _mart369_picking_done(picking):
        """Send every line in full and mark the picking done. Shared by the
        delivery going out and a return coming back (order_return.py)."""
        for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.with_context(cancel_backorder=True)._action_done()

    # ------------------------------------------------------------ cancelling

    def _action_cancel(self):
        """A bill nobody paid goes when the order goes.

        Paid invoices are left alone: the refund to the 369 Wallet already
        answers them with a credit note (order_refund.py).
        """
        for order in self.filtered('mart369_ref'):
            order._mart369_void_unpaid_invoices()
        return super()._action_cancel()

    def _mart369_void_unpaid_invoices(self):
        self.ensure_one()
        invoices = self.invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
            and m.payment_state == 'not_paid')
        for invoice in invoices:
            try:
                with self.env.cr.savepoint():
                    invoice.sudo()._reverse_moves([{
                        'ref': self.env._('Order cancelled'),
                        'invoice_date': fields.Date.context_today(self),
                    }], cancel=True)
            except Exception:  # noqa: BLE001 - see the module docstring
                _logger.exception('mart369: could not reverse %s for %s',
                                  invoice.name, self.mart369_ref)
        return True


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    mart369_wallet_payment_id = fields.Many2one(
        'account.payment', string='Wallet payment', readonly=True, copy=False,
        help="The 369 Wallet part of a split payment, booked in the 369 Wallet "
             "journal. Set once, so booking it again does nothing.")

    def _mart369_book_wallet_leg(self, invoices):
        """The wallet part of a wallet + card (or cash) payment.

        The transaction's own amount is only what the gateway or the rider
        takes; what the wallet paid is `mart369_wallet_used`, already gone from
        the customer's balance. A wallet-only order is the wallet provider's own
        transaction and is booked by Odoo like any other.
        """
        self.ensure_one()
        if (not self.mart369_wallet_used or self.mart369_wallet_payment_id
                or self.provider_id.mart369_is_wallet
                or self.state not in ('pending', 'authorized', 'done')):
            return False
        company = self.company_id
        journal = self.env['account.journal']._mart369_journal_for('mart369_wallet', company)
        if not journal:
            return False
        values = {
            'amount': self.mart369_wallet_used,
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_id.commercial_partner_id.id,
            'currency_id': self.currency_id.id,
            'journal_id': journal.id,
            'company_id': company.id,
            'memo': '%s - 369 Wallet' % self.reference,
        }
        line = journal.inbound_payment_method_line_ids[:1]
        if line:
            values['payment_method_line_id'] = line.id
        term = invoices.line_ids.filtered(lambda l: l.display_type == 'payment_term')[:1]
        if term:
            values['destination_account_id'] = term.account_id.id
        payment = self.env['account.payment'].sudo().with_company(company).create(values)
        payment.action_post()
        self.mart369_wallet_payment_id = payment
        self.env['sale.order']._mart369_reconcile(payment, invoices)
        return payment

    def _mart369_unbook_wallet_leg(self):
        """The payment failed and the wallet money went back: so does its entry."""
        self.ensure_one()
        payment = self.mart369_wallet_payment_id
        if not payment or payment.state in ('draft', 'canceled'):
            return False
        try:
            with self.env.cr.savepoint():
                payment.sudo().action_draft()
                payment.sudo().action_cancel()
        except Exception:  # noqa: BLE001
            _logger.exception('mart369: could not cancel wallet payment %s', payment.name)
            return False
        return True
