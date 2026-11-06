"""Who takes the parcel, and what happens when it does not get there.

**The rider.** Staff with the Rider role (mart369_roles) can be given an order;
the Orders screens show who has it, and so does the packing slip.

**Couldn't deliver.** Out for delivery and nobody answered, the address was
wrong, the customer refused it. The rider (or whoever is at the desk) says why,
then either:

* **Try again** - the order stays out for delivery, the attempt is counted, and
  the customer gets a fresh door code; or
* **Return to store** - the order is closed as returned. Everything the
  customer paid (gateway and wallet alike, less anything already refunded for
  an item taken out) goes to their **369 Wallet** at once; a cash order simply
  has nothing to collect. The slot and coupon are freed, as a cancel does.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

FAIL_REASONS = [
    'Customer not reachable',
    'Wrong address',
    'Customer refused the order',
    'Customer asked to come later',
    'Other',
]


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    mart369_rider_id = fields.Many2one(
        'res.users', string='Rider', copy=False, index=True,
        help='Who is taking this order to the door.')
    mart369_attempts = fields.Integer(
        string='Failed attempts', copy=False, readonly=True,
        help='How many times it went out and could not be delivered.')
    mart369_failed_reason = fields.Char(string='Last failed because', copy=False, readonly=True)
    mart369_failed_at = fields.Datetime(string='Last failed at', copy=False, readonly=True)
    mart369_returned = fields.Boolean(
        string='Returned to store', copy=False, readonly=True,
        help='Went out, could not be delivered, and came back.')
    mart369_returned_refund = fields.Monetary(
        string='Refunded on return', copy=False, readonly=True, currency_field='currency_id')

    # ------------------------------------------------------------- riders

    @api.model
    def _mart369_riders(self):
        """Staff with the Rider role, A-Z."""
        group = self.env.ref('mart369_roles.group_rider', raise_if_not_found=False)
        if not group:
            return self.env['res.users']
        return self.env['res.users'].sudo().search(
            [('share', '=', False), ('group_ids', 'in', group.id)], order='name')

    def _mart369_set_rider(self, user):
        self.ensure_one()
        if user and user not in self._mart369_riders():
            raise UserError(_('%s does not have the Rider role. Give it under Staff & roles.', user.name))
        if self.mart369_state in ('delivered', 'cancelled'):
            raise UserError(_('This order is closed.'))
        self.sudo().mart369_rider_id = user
        self.message_post(body=_('Rider: %s', user.name) if user else _('Rider removed.'))

    # --------------------------------------------------- couldn't deliver

    def _mart369_failed(self, reason, then):
        """A delivery that did not happen. `then` is 'retry' or 'return'."""
        self.ensure_one()
        if self.mart369_state != 'out':
            raise UserError(_('Only an order out for delivery can fail at the door.'))
        if then not in ('retry', 'return'):
            raise UserError(_('Try again, or return it to the store.'))
        reason = reason or _('Other')
        order = self.sudo()
        order.write({
            'mart369_attempts': order.mart369_attempts + 1,
            'mart369_failed_reason': reason,
            'mart369_failed_at': fields.Datetime.now(),
        })
        if then == 'retry':
            # A fresh code: the last one may have been read out to somebody.
            order._mart369_issue_otp()
            order.message_post(body=_(
                'Could not deliver (%(reason)s). Attempt %(n)s failed - going out again.',
                reason=reason, n=order.mart369_attempts))
            return 0.0
        return order._mart369_return_to_store(reason)

    def _mart369_return_to_store(self, reason):
        """Close an order that came back. Returns what went to the wallet."""
        self.ensure_one()
        currency = self.currency_id

        self._mart369_release_slot()
        self._mart369_release_coupon()
        # Cash that was never collected: the payment is simply called off.
        pending = self.env['payment.transaction'].sudo().search([
            ('mart369_order_ref', '=', self.mart369_ref or '-'),
            ('mart369_kind', '=', 'order'),
            ('state', 'in', ('draft', 'pending')),
        ])
        for tx in pending:
            tx._set_canceled(state_message=_('Returned to store: %s', reason))
            tx._post_process()
        # Everything still owed, to the 369 Wallet, with a credit note
        # (order_refund.py).
        refund = self._mart369_refund_to_wallet(self._mart369_paid_amount(), _('Order returned to store'))
        if refund:
            self._mart369_credit_note(refund, _('Returned to store: %s', reason))

        self.write({'mart369_returned': True, 'mart369_returned_refund': refund})
        note = _('Returned to store: %s', reason)
        self._mart369_set_state('cancelled', note=note)
        if self.state != 'cancel':
            self.with_context(disable_cancel_warning=True).action_cancel()
        self.message_post(body=note + (
            ' ' + _('%s refunded to the 369 Wallet.', currency.format(refund)) if refund else ''))
        return refund

    # ------------------------------------------------------ the staff screens

    @api.model
    def mart369_admin_set_rider(self, ref, user_id=None):
        order = self._mart369_admin_find(ref)
        if not order:
            raise UserError(_('There is no such order.'))
        user = self.env['res.users'].sudo().browse(int(user_id)) if user_id else self.env['res.users']
        order._mart369_set_rider(user.exists())
        return order._mart369_admin_detail()

    @api.model
    def mart369_admin_failed(self, ref, reason=None, then=None):
        order = self._mart369_admin_find(ref)
        if not order:
            raise UserError(_('There is no such order.'))
        if reason not in FAIL_REASONS:
            raise UserError(_('Pick what went wrong at the door.'))
        refund = order._mart369_failed(reason, then)
        return {'order': order._mart369_admin_detail(), 'refund': refund}
