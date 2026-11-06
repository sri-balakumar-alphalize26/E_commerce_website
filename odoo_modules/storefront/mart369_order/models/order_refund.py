"""Giving money back, the one way the shop does it: to the 369 Wallet, in full.

A return and a cancellation used to hand back only what had come *from* the
wallet; whatever was paid by UPI or card stayed with the shop until somebody
remembered to refund it at the gateway, and the books never heard of it. Now
every refund is the whole amount still owed, straight to the customer's 369
Wallet, and a credit note says so to accounting.

"Still owed" is what was paid less what already went back - an item taken out
(order_items.py), an earlier return, a cancellation, a parcel that came back
(order_delivery.py) - so no two of those can refund the same money twice.
"""

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    mart369_cancel_refund = fields.Monetary(
        string='Refunded on cancel', copy=False, readonly=True, currency_field='currency_id')

    def _mart369_refunded(self):
        """Everything already given back on this order."""
        self.ensure_one()
        total = self.mart369_cancel_refund or 0.0
        if 'mart369_removed_refund' in self.order_line._fields:
            total += sum(self.order_line.mapped('mart369_removed_refund'))
        if 'mart369_returned_refund' in self._fields:
            total += self.mart369_returned_refund or 0.0
        total += sum(self.sudo().mart369_return_ids.mapped('refunded'))
        return total

    def _mart369_paid_amount(self):
        """What the customer paid. Recorded when the payment lands; an order
        paid online before that was recorded (or made by a demo seeder) falls
        back to its total. Cash on delivery counts only once collected."""
        self.ensure_one()
        if self.mart369_paid:
            return self.mart369_paid
        method = self.mart369_method or ''
        if method and method != 'cod' and self.mart369_state not in (False, 'draft'):
            return self.amount_total
        return 0.0

    def _mart369_refundable(self):
        """What the customer paid and has not had back yet."""
        self.ensure_one()
        return self.currency_id.round(max(0.0, self._mart369_paid_amount() - self._mart369_refunded()))

    def _mart369_refund_to_wallet(self, amount, title):
        """Put up to `amount` back in the customer's 369 Wallet - never more
        than they are still owed. Returns what was paid out."""
        self.ensure_one()
        amount = min(self.currency_id.round(amount or 0.0), self._mart369_refundable())
        if amount <= 0:
            return 0.0
        card = self.env['loyalty.card'].sudo()._mart369_wallet(self.partner_id)
        card._mart369_move(amount, 'refund', title, sub=_('Order #%s', self.mart369_ref or ''), order=self)
        return amount

    def _mart369_credit_note(self, amount, reason):
        """A posted credit note for `amount` against the order's invoice.

        Swallowed like the invoice itself (order_place.py): the customer has
        their money already, and a credit note that failed is finance's to
        raise, not a reason to take the refund back.
        """
        self.ensure_one()
        invoice = self.invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted')[:1]
        if not invoice or amount <= 0:
            return self.env['account.move']
        try:
            with self.env.cr.savepoint():
                credited = sum(self.invoice_ids.filtered(
                    lambda m: m.move_type == 'out_refund' and m.state == 'posted').mapped('amount_total'))
                currency = self.currency_id
                if not credited and currency.compare_amounts(amount, invoice.amount_total) >= 0:
                    note = invoice._reverse_moves([{
                        'ref': reason, 'invoice_date': fields.Date.context_today(self)}])
                else:
                    line = invoice.invoice_line_ids.filtered(lambda l: l.display_type == 'product')[:1]
                    note = self.env['account.move'].sudo().create({
                        'move_type': 'out_refund',
                        'partner_id': invoice.partner_id.id,
                        'invoice_origin': invoice.invoice_origin or self.name,
                        'reversed_entry_id': invoice.id,
                        'ref': reason,
                        'invoice_date': fields.Date.context_today(self),
                        'invoice_line_ids': [(0, 0, {
                            'name': reason,
                            'quantity': 1,
                            'price_unit': amount,
                            'account_id': line.account_id.id,
                            'tax_ids': [(6, 0, [])],
                        })],
                    })
                note.filtered(lambda m: m.state == 'draft').action_post()
                # The wallet refund was booked first; match the two now.
                self._mart369_reconcile_wallet_refunds()
                return note
        except Exception:  # noqa: BLE001
            _logger.exception('369 Mart: credit note for %s on %s failed', amount, self.mart369_ref)
            return self.env['account.move']
