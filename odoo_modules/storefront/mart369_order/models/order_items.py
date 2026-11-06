"""Taking one item out of an order because the store ran out of it.

What JioMart and Flipkart do instead of cancelling the whole basket: the rest
goes out, and the missing item's money comes back at once.

* The line stays on the order at quantity 0, marked removed with the reason and
  how many were taken out - the order's history keeps it, and both screens and
  the customer's order page show it struck through.
* Paid orders: the item's price goes to the customer's **369 Wallet** straight
  away, however they paid - the shop's choice, so a refund never waits on a
  gateway. Cash on delivery: nothing was paid, so nothing is refunded; the cash
  to collect at the door drops instead.
* The invoice already posted for the order gets a credit note for the line.

Only before the parcel leaves, and never the last item - that is a cancel.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Still in the store: an item can be taken out and the rest still packed.
REMOVABLE_STATES = ('placed', 'packed', 'shipped')


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    mart369_removed_qty = fields.Float(
        string='Removed', copy=False, readonly=True,
        help='How many were taken out of the order because the store ran out.')
    mart369_removed_reason = fields.Char(string='Removed because', copy=False, readonly=True)
    mart369_removed_refund = fields.Monetary(
        string='Refunded to wallet', copy=False, readonly=True, currency_field='currency_id')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _mart369_item_lines(self):
        """The basket's product lines still in it."""
        self.ensure_one()
        return self.order_line.filtered(
            lambda l: not l.display_type and not l.is_delivery and not l.mart369_kind
            and l.product_uom_qty > 0)

    def _mart369_removed_lines(self):
        """[{name, qty, reason, refund}] for what was taken out."""
        self.ensure_one()
        return [{
            'name': line.name or line.product_id.display_name,
            'qty': int(line.mart369_removed_qty),
            'reason': line.mart369_removed_reason or '',
            'refund': self.currency_id.round(line.mart369_removed_refund or 0.0),
        } for line in self.order_line if line.mart369_removed_qty]

    def _mart369_can_remove(self):
        self.ensure_one()
        return self.mart369_state in REMOVABLE_STATES and len(self._mart369_item_lines()) > 1

    def _mart369_remove_line(self, line, reason):
        """Take `line` out of the order. Returns the amount refunded."""
        self.ensure_one()
        if line.order_id != self or line not in self._mart369_item_lines():
            raise UserError(_('That item is not in this order any more.'))
        if self.mart369_state not in REMOVABLE_STATES:
            raise UserError(_('The order has left the store - an item can no longer be taken out.'))
        if len(self._mart369_item_lines()) < 2:
            raise UserError(_('That is the last item. Cancel the order instead.'))

        currency = self.currency_id
        qty = line.product_uom_qty
        value = currency.round(line.price_total)
        cash = (self.mart369_method or '') == 'cod'
        refund = 0.0 if cash else value
        name = line.product_id.display_name

        order = self.sudo()
        line = line.sudo()
        line.write({
            'product_uom_qty': 0,
            'mart369_removed_qty': qty,
            'mart369_removed_reason': reason or _('Out of stock'),
            'mart369_removed_refund': refund,
        })

        if refund:
            card = self.env['loyalty.card'].sudo()._mart369_wallet(order.partner_id)
            card._mart369_move(
                refund, 'refund', _('Item removed - %s', name),
                sub=_('Order #%s', order.mart369_ref), order=order)
        else:
            # What the rider is told to collect follows the new total.
            # Cash payments are tied to the order by its number, not by
            # Odoo's own transaction link (payment_transaction.py).
            pending = self.env['payment.transaction'].sudo().search([
                ('mart369_order_ref', '=', order.mart369_ref), ('state', '=', 'pending')])
            if pending:
                pending.write({'amount': order.amount_total})

        order._mart369_credit_removed()
        order.message_post(body=_(
            'Removed %(qty)s x %(name)s (%(reason)s). %(money)s',
            qty='%g' % qty, name=name, reason=reason or _('Out of stock'),
            money=(_('%s refunded to the 369 Wallet.', currency.format(refund)) if refund
                   else _('Cash to collect is now %s.', currency.format(order.amount_total)))))
        return refund

    def _mart369_credit_removed(self):
        """A credit note for what was taken out of an invoiced order.

        Odoo's own rule: a line invoiced for more than is now ordered is
        credited by the next invoice run. Swallowed like the invoice itself
        (order_place.py) - the refund to the customer has already happened,
        and a failed credit note is finance's to redo, not a reason to take
        the refund back.
        """
        self.ensure_one()
        if not self.invoice_ids.filtered(lambda m: m.state == 'posted'):
            return
        try:
            with self.env.cr.savepoint():
                credit = self._create_invoices(final=True)
                credit.filtered(lambda m: m.state == 'draft').action_post()
                self._mart369_reconcile_wallet_refunds()
        except Exception:  # noqa: BLE001
            _logger.exception('369 Mart: credit note for a removed item on %s failed', self.mart369_ref)

    # ------------------------------------------------------ the staff screens

    @api.model
    def mart369_admin_remove_line(self, ref, line_id, reason=None):
        order = self._mart369_admin_find(ref)
        if not order:
            raise UserError(_('There is no such order.'))
        line = order.order_line.filtered(lambda l: l.id == int(line_id or 0))
        refund = order._mart369_remove_line(line, reason)
        return {'order': order._mart369_admin_detail(), 'refund': refund}
