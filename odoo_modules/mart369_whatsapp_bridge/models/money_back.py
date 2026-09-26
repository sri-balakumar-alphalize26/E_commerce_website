"""Money back on WhatsApp orders, the way the website gives it.

Neither side refunded a paid WhatsApp order. Every cancel ends in
`sale.order._action_cancel`, and 369 Mart's override there only voids the
*unpaid* bill of a *website* order; the delivery stack's Refund button raised
a credit note that paid nobody; a returned parcel only went back on the shelf.
So a cancelled WhatsApp order kept a live bill, and a paid one kept the money.

From here a WhatsApp order is treated like a website order:

* cancelled unpaid - its bill is voided;
* cancelled, returned, or refunded from the Store screen after being paid -
  what was paid goes back to the customer's 369 Wallet, with a credit note,
  booked and matched (mart369_order/wallet_books.py), exactly once;
* the customer hears it in their own chat. A WhatsApp-only customer gets the
  wallet too - it waits on their customer record for the day they sign in to
  369 Mart with the same number.

A WhatsApp order still never passes `_mart369_set_state`.
"""

import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class SaleOrderMoneyBack(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------ what was paid

    def _mart369_wa_paid(self):
        """What a WhatsApp customer really paid: through the invoice, not the
        website's own payment fields (which a WhatsApp order never sets)."""
        self.ensure_one()
        invoices = self.invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
        # By the invoice's own verdict, as the stack's Refund button reads it:
        # "in payment" is money taken whose bank line is not matched yet, and a
        # bill reversed on cancel was never paid although it owes nothing.
        total = 0.0
        for invoice in invoices:
            if invoice.payment_state in ('paid', 'in_payment'):
                total += invoice.amount_total
            elif invoice.payment_state == 'partial':
                total += invoice.amount_total - invoice.amount_residual
        return self.currency_id.round(total)

    def _mart369_paid_amount(self):
        if self.mart369_channel == 'whatsapp':
            return self._mart369_wa_paid()
        return super()._mart369_paid_amount()

    def _mart369_refund_to_wallet(self, amount, title):
        """The website's refund, labelled with the order's own number: a
        WhatsApp order has no 369M- reference to show."""
        if self.mart369_channel != 'whatsapp':
            return super()._mart369_refund_to_wallet(amount, title)
        self.ensure_one()
        amount = min(self.currency_id.round(amount or 0.0), self._mart369_refundable())
        if amount <= 0:
            return 0.0
        card = self.env['loyalty.card'].sudo()._mart369_wallet(self.partner_id)
        card._mart369_move(amount, 'refund', title,
                           sub=_('Order %s', self.name), order=self)
        return amount

    # --------------------------------------------------------------- give it back

    def _mart369_wa_money_back(self, reason, returned=False):
        """Refund whatever of a WhatsApp order is still owed back. Safe to call
        from every trigger: the second finds nothing refundable."""
        done = 0.0
        for order in self.filtered(lambda o: o.mart369_channel == 'whatsapp'):
            try:
                with self.env.cr.savepoint():
                    order = order.sudo()
                    owed = order._mart369_refundable()
                    if owed <= 0:
                        continue
                    paid = order._mart369_refund_to_wallet(owed, reason)
                    if not paid:
                        continue
                    field = 'mart369_returned_refund' if returned else 'mart369_cancel_refund'
                    order[field] = (order[field] or 0.0) + paid
                    note = order._mart369_credit_note(paid, _('%(reason)s: %(order)s',
                                                              reason=reason, order=order.name))
                    order._mart369_wa_tell_refund(paid)
                    order.message_post(body=_(
                        '%(amount)s refunded to the 369 Wallet (%(reason)s).%(note)s',
                        amount=order.currency_id.format(paid), reason=reason,
                        note=(' ' + _('Credit note %s.', note[:1].name)) if note else ''))
                    done += paid
            except Exception:  # noqa: BLE001 - never block the cancel or return itself
                _logger.exception('bridge: could not refund WhatsApp order %s', order.name)
        return done

    def _mart369_wa_tell_refund(self, amount):
        """In the customer's own chat, through the delivery job."""
        self.ensure_one()
        job = self.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing').sorted('id')[:1]
        if not job:
            return False
        return job._sa_tell_customer(_(
            "\U0001F4B8 *%(amount)s* has been refunded to your 369 Wallet for "
            "order %(order)s.\n\nSign in to 369 Mart with this number to use it.",
            amount=self.currency_id.format(amount), order=self.name), unique=True)

    # ----------------------------------------------------------------- cancelling

    def _action_cancel(self):
        """A WhatsApp order's unpaid bill goes when it goes, as a website
        order's does; a paid one comes back to the wallet."""
        whatsapp = self.filtered(lambda o: o.mart369_channel == 'whatsapp')
        for order in whatsapp:
            order._mart369_void_unpaid_invoices()
        result = super()._action_cancel()
        whatsapp._mart369_wa_money_back(_('Order cancelled'))
        return result


class StockPickingMoneyBack(models.Model):
    _inherit = 'stock.picking'

    def write(self, vals):
        result = super().write(vals)
        if vals.get('sa_delivery_state') == 'returned' \
                and self.env.context.get('mart369_bridge') != 'push':
            # The parcel came back - delivered and returned, or turned away at
            # the door. Either way the customer paid for goods they do not have.
            self.sale_id._mart369_wa_money_back(_('Order returned'), returned=True)
        return result

    def sa_action_refund(self):
        """The Store screen's Refund, for a WhatsApp order: the wallet, with
        one credit note - never a second one beside an automatic refund."""
        whatsapp = self.filtered(lambda p: p.sale_id.mart369_channel == 'whatsapp')
        moves = self.env['account.move']
        for picking in whatsapp:
            order = picking.sale_id
            before = order.invoice_ids.filtered(lambda m: m.move_type == 'out_refund')
            if not order._mart369_wa_money_back(_('Refund')):
                picking.message_post(body=_(
                    'Nothing left to refund on %s: it was not paid, or it has '
                    'already been refunded to the 369 Wallet.', order.name))
                continue
            note = order.invoice_ids.filtered(lambda m: m.move_type == 'out_refund') - before
            if note:
                picking.sudo().sa_refund_move_id = note[:1].id
                moves |= note
        rest = self - whatsapp
        if rest:
            moves |= super(StockPickingMoneyBack, rest).sa_action_refund()
        return moves
