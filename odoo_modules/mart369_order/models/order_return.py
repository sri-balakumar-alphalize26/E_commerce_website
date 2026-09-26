"""Returns and replacements.

In the app a return was a patch in localStorage and its photos were a counter -
`OrderTrack.jsx:361` counted how many the customer picked and then dropped them.
Here a return is a record and the photos are real attachments.

The refund is the whole amount, straight to the customer's 369 Wallet, however
they paid - UPI and card included - with a credit note against the invoice
(order_refund.py). Never more than they are still owed: an item already taken
out or an earlier return is not refunded twice.

The four steps are the app's own RETURN_STEPS (orderState.js:27-32), so the
tracking screen's progress bar reads this without changing.
"""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

RETURN_STATES = [
    ('requested', 'Return requested'),
    ('pickup', 'Pickup scheduled'),
    ('picked', 'Picked up'),
    ('done', 'Refund issued'),
    ('refused', 'Refused'),
]

RETURN_FLOW = ['requested', 'pickup', 'picked', 'done']

KIND_CHOICES = [
    ('refund', 'Refund'),
    ('replace', 'Replacement'),
]


class Mart369OrderReturn(models.Model):
    _name = 'mart369.order.return'
    _description = '369 Mart Return'
    _order = 'create_date desc, id desc'
    _rec_name = 'order_ref'

    order_id = fields.Many2one(
        'sale.order', string='Order', required=True, ondelete='cascade', index=True)
    order_ref = fields.Char(related='order_id.mart369_ref', store=True, string='Order number')
    partner_id = fields.Many2one(
        related='order_id.partner_id', store=True, string='Customer', index=True)
    currency_id = fields.Many2one(related='order_id.currency_id')

    kind = fields.Selection(KIND_CHOICES, string='Wants', required=True, default='refund')
    state = fields.Selection(
        RETURN_STATES, string='Status', required=True, default='requested', index=True,
        group_expand='_mart369_return_groups')
    reason = fields.Char(string='Reason', required=True)
    detail = fields.Text(string='What happened')
    amount = fields.Monetary(string='Refund', help="What goes back to the customer.")
    refunded = fields.Monetary(
        string='Refunded to wallet', readonly=True, copy=False,
        help='What actually went to the 369 Wallet when the refund was issued.')
    return_picking_id = fields.Many2one(
        'stock.picking', string='Stock return', readonly=True, copy=False,
        help="The goods coming back into stock, made when the refund is issued.")

    photo_ids = fields.Many2many(
        'ir.attachment', string='Photos',
        help="What the customer sent with the request.")
    photo_count = fields.Integer(compute='_compute_photo_count')

    @api.model
    def _mart369_return_groups(self, states, domain):
        """Columns in the order a return really moves, not alphabetically by
        the technical value - which put "Picked up" before "Pickup scheduled"."""
        return [key for key, __ in RETURN_STATES]

    @api.depends('photo_ids')
    def _compute_photo_count(self):
        for record in self:
            record.photo_count = len(record.photo_ids)

    # ----------------------------------------------------------------- flow

    def _mart369_next_state(self):
        self.ensure_one()
        if self.state not in RETURN_FLOW:
            return None
        index = RETURN_FLOW.index(self.state)
        return RETURN_FLOW[index + 1] if index + 1 < len(RETURN_FLOW) else None

    def mart369_action_advance(self):
        """Move a return on a step; issuing the refund is the last one."""
        for record in self:
            nxt = record._mart369_next_state()
            if not nxt:
                raise UserError(record.env._('This return is already finished.'))
            record.state = nxt
            if nxt == 'done':
                record._mart369_refund()
                record._mart369_restock()
        return True

    def mart369_action_refuse(self):
        for record in self:
            if record.state == 'done':
                raise UserError(record.env._(
                    'That refund has already been issued.'))
            record.state = 'refused'
        return True

    def _mart369_refund(self):
        """The whole refund, to the customer's 369 Wallet, and a credit note.

        Once per return: `refunded` records it, so moving a finished return on
        again cannot pay twice.
        """
        self.ensure_one()
        if self.refunded:
            return False
        order = self.order_id.sudo()
        paid = order._mart369_refund_to_wallet(
            self.amount or order.amount_total, self.env._('Return refund'))
        self.sudo().refunded = paid
        if paid:
            order._mart369_credit_note(paid, self.env._('Return: %s', self.reason or ''))
        return True

    def _mart369_restock(self):
        """Put the returned goods back in stock, with Odoo's own return.

        At the refund rather than at pickup, so money and stock move together
        and a return refused after pickup - the goods go back to the customer -
        never touches stock. A return is always the whole order, and Odoo's
        "return all" counts only what earlier returns have not already brought
        back, so a second return on one order restocks nothing. Swallowed and
        logged: the refund has been issued, and a stock error is the
        warehouse's to fix, not a reason to take it back.
        """
        self.ensure_one()
        if self.return_picking_id:
            return False
        order = self.order_id.sudo()
        delivered = order.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state == 'done')
        for picking in delivered:
            try:
                with self.env.cr.savepoint():
                    wizard = self.env['stock.return.picking'].sudo().with_context(
                        active_id=picking.id, active_model='stock.picking',
                    ).create({'picking_id': picking.id})
                    action = wizard.action_create_returns_all()
                    back = self.env['stock.picking'].sudo().browse(action['res_id'])
                    order._mart369_picking_done(back)
                    self.sudo().return_picking_id = back
            except UserError:
                # Nothing left to return: an earlier return brought it all back.
                continue
            except Exception:  # noqa: BLE001 - see the docstring
                _logger.exception('mart369: could not restock return %s of %s',
                                  self.id, self.order_ref)
        return bool(self.return_picking_id)

    def _mart369_serialize(self):
        self.ensure_one()
        return {
            'id': str(self.id),
            'kind': self.kind,
            'state': self.state,
            'reason': self.reason or '',
            'detail': self.detail or '',
            'amount': self.currency_id.round(self.amount or 0.0),
            # Where the money went once the refund was issued.
            'refunded': self.currency_id.round(self.refunded or 0.0),
            'refundTo': 'wallet',
            'photos': len(self.photo_ids),
            'at': int(self.create_date.timestamp() * 1000) if self.create_date else None,
        }
