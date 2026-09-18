"""The order itself.

There is no `mart369.order` model. An order is a `sale.order` - the record Odoo
already knows how to invoice, deliver, refund and report on - carrying the few
extra things the app needs on top.

What the app used to do, and what happens instead:

    the browser invented the order number   ->  still does, but it is now a
                                                unique key on a real record, and
                                                placing twice with the same one
                                                places once
    the browser kept it in localStorage     ->  sale.order
    a timer moved placed -> delivered       ->  an operator moves it, and every
                                                move is stamped
    the delivery code was hash(order id)    ->  issued here, once, hashed

The status keys are the app's own six (components/home/orderState.js:9-22) and
not Odoo's `state`, because the app's screens are built around them and this
module adapts to the app rather than the other way round. Odoo's own `state`
still does its usual job underneath: a quotation until it is paid, confirmed
after.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# The app's six, plus a draft that exists only between "place" and "paid".
# The app never sees a draft: it has not been told the order exists yet.
STATE_CHOICES = [
    ('draft', 'Not paid for'),
    ('placed', 'Order placed'),
    ('packed', 'Packed'),
    ('shipped', 'Shipped'),
    ('out', 'Out for delivery'),
    ('delivered', 'Delivered'),
    ('cancelled', 'Cancelled'),
]

# Quick skips "shipped"; Express skips "packed". Straight out of STEPS in
# components/home/orderState.js:9-22, so the app's timeline and this agree.
FLOW = {
    'quick': ['placed', 'packed', 'out', 'delivered'],
    'all': ['placed', 'shipped', 'out', 'delivered'],
}

LIVE_STATES = ('placed', 'packed', 'shipped', 'out')

# Where the delivery code's key lives. The code is never stored in the clear, so
# a backup, a log or a careless read cannot hand someone a doorstep.
OTP_PARAM = 'mart369_order.otp_key'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------- the order

    mart369_ref = fields.Char(
        string='369 Mart order', copy=False, index=True,
        help="The order number the app shows, e.g. 369M-8412. Also the key "
             "that stops one basket being ordered twice.")
    mart369_state = fields.Selection(
        STATE_CHOICES, string='369 Mart status', copy=False, index=True,
        group_expand='_mart369_state_groups',
        help="Where the order is, in the words the customer's app uses.")
    mart369_mode = fields.Selection(
        [('quick', 'Quick'), ('all', 'Express')], string='Storefront',
        copy=False, index=True)
    mart369_placed_at = fields.Datetime(string='Placed', copy=False, readonly=True)

    # -------------------------------------------------------------- the slot

    mart369_slot_key = fields.Char(
        string='Slot', copy=False, index=True,
        help="Which delivery window this order booked.")
    mart369_slot_day = fields.Date(
        string='Slot day', copy=False, index=True,
        help="The day of that window. Capacity is counted per slot per day.")
    mart369_slot_label = fields.Char(string='Slot shown as', copy=False)
    mart369_eta = fields.Char(string='Promise', copy=False)

    # ------------------------------------------------------------ the extras

    mart369_instructions = fields.Char(string='Delivery note', copy=False)
    mart369_whatsapp = fields.Boolean(string='Updates on WhatsApp', copy=False)
    mart369_coupon_id = fields.Many2one(
        'mart369.coupon', string='Coupon', ondelete='restrict', copy=False)
    mart369_coupon_off = fields.Monetary(string='Coupon discount', copy=False)

    mart369_stamp_ids = fields.One2many(
        'mart369.order.stamp', 'order_id', string='Timeline', copy=False)
    mart369_return_ids = fields.One2many(
        'mart369.order.return', 'order_id', string='Returns', copy=False)
    mart369_return_count = fields.Integer(
        string='Returns', compute='_compute_mart369_returns', store=True,
        help="Stored so the board can filter on it: a computed field that is "
             "not stored cannot appear in a domain.")

    # ------------------------------------------------------------- the money

    mart369_paid = fields.Monetary(
        string='Paid', copy=False, readonly=True,
        help="What was actually settled. Set by the payment, never by the app.")
    mart369_wallet_used = fields.Monetary(string='From wallet', copy=False, readonly=True)
    mart369_txn = fields.Char(string='Transaction', copy=False, readonly=True)
    mart369_method = fields.Char(string='Paid by', copy=False, readonly=True)
    mart369_pay_note = fields.Char(string='Payment note', copy=False, readonly=True)

    # ---------------------------------------------------------- the doorstep

    mart369_otp_hash = fields.Char(
        string='Delivery code', copy=False, readonly=True, groups='base.group_system')
    mart369_otp_at = fields.Datetime(string='Code issued', copy=False, readonly=True)
    mart369_otp_used_at = fields.Datetime(string='Code used', copy=False, readonly=True)

    # ------------------------------------------------------- operator aids

    mart369_due_at = fields.Datetime(
        string='Due', copy=False, index=True,
        help="When this order was promised. What Late is measured against.")
    mart369_late = fields.Boolean(
        string='Late', compute='_compute_mart369_late', search='_search_mart369_late',
        help="Still on its way after the time it was promised.")

    _mart369_ref_uniq = models.Constraint(
        'unique (mart369_ref)',
        'That 369 Mart order number has already been used.',
    )

    # -------------------------------------------------------------- the board

    @api.model
    def _mart369_state_groups(self, states, domain):
        """Which columns the board shows, and in what order.

        Without this Odoo sorts kanban columns by the technical value, which
        reads "out, packed, placed, shipped" - so "Out for delivery" sat to the
        left of "Order placed" and the board told the day backwards.

        It also keeps every column on screen when it is empty, so an operator
        can see there is nothing to pack rather than wonder where the column
        went.
        """
        return [key for key, __ in STATE_CHOICES if key != 'draft']

    # -------------------------------------------------------------- computed

    @api.depends('mart369_return_ids')
    def _compute_mart369_returns(self):
        for order in self:
            order.mart369_return_count = len(order.mart369_return_ids)

    @api.depends('mart369_due_at', 'mart369_state')
    def _compute_mart369_late(self):
        now = fields.Datetime.now()
        for order in self:
            order.mart369_late = bool(
                order.mart369_state in LIVE_STATES
                and order.mart369_due_at and order.mart369_due_at < now)

    def _search_mart369_late(self, operator, value):
        """So the board's Late tile can filter on it.

        A computed boolean is not stored, so it needs its own domain. Late means
        all three at once: still on its way, promised a time, and that time gone.
        """
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(self.env._('Late can only be searched as true or false.'))
        now = fields.Datetime.now()
        wanted = (operator == '=') == value
        if wanted:
            return [
                ('mart369_state', 'in', list(LIVE_STATES)),
                ('mart369_due_at', '!=', False),
                ('mart369_due_at', '<', now),
            ]
        return [
            '|', '|',
            ('mart369_state', 'not in', list(LIVE_STATES)),
            ('mart369_due_at', '=', False),
            ('mart369_due_at', '>=', now),
        ]

    # -------------------------------------------------------------- the flow

    def _mart369_flow(self):
        self.ensure_one()
        return FLOW.get(self.mart369_mode or 'quick', FLOW['quick'])

    def _mart369_next_state(self):
        """The step after this one, or None at the end of the line."""
        self.ensure_one()
        flow = self._mart369_flow()
        if self.mart369_state not in flow:
            return None
        index = flow.index(self.mart369_state)
        return flow[index + 1] if index + 1 < len(flow) else None

    def _mart369_stamp(self, state, note=None):
        """Record that the order reached a state, once."""
        self.ensure_one()
        already = self.mart369_stamp_ids.filtered(lambda s: s.state == state)
        if already:
            return already[:1]
        return self.env['mart369.order.stamp'].sudo().create({
            'order_id': self.id,
            'state': state,
            'note': note or False,
        })

    def _mart369_set_state(self, state, note=None):
        """Move the order and stamp it.

        Idempotent, because a replayed webhook must not re-place an order: the
        state it is already in changes nothing and stamps nothing.
        """
        self.ensure_one()
        if self.mart369_state == state:
            return False
        self.write({'mart369_state': state})
        self._mart369_stamp(state, note=note)
        if state == 'delivered':
            self._mart369_on_delivered()
        return True

    def mart369_action_advance(self):
        """The board's one-click button: move each order on by one step."""
        for order in self:
            if order.mart369_state == 'cancelled':
                raise UserError(order.env._(
                    'Order %s was cancelled and cannot be moved on.',
                    order.mart369_ref or ''))
            nxt = order._mart369_next_state()
            if not nxt:
                raise UserError(order.env._(
                    'Order %s has already been delivered.', order.mart369_ref or ''))
            order._mart369_set_state(nxt)
        return True

    def _mart369_on_delivered(self):
        """Cash changes hands at the door, so this is where a cash payment is
        really collected - not an operator remembering to press a button."""
        self.ensure_one()
        if not self.mart369_ref:
            return
        transactions = self.env['payment.transaction'].sudo().search([
            ('mart369_order_ref', '=', self.mart369_ref),
            ('mart369_kind', '=', 'order'),
            ('state', '=', 'pending'),
        ])
        for tx in transactions:
            if tx.provider_id.mart369_is_cod:
                tx._mart369_mark_cod_collected()

    # ----------------------------------------------------------- the doorstep

    @api.model
    def _mart369_otp_key(self):
        params = self.env['ir.config_parameter'].sudo()
        key = params.get_param(OTP_PARAM)
        if not key:
            key = secrets.token_hex(32)
            params.set_param(OTP_PARAM, key)
        return key

    def _mart369_digest(self, code):
        self.ensure_one()
        return hmac.new(
            self._mart369_otp_key().encode(),
            ('%s:%s' % (self.id, (code or '').strip())).encode(),
            hashlib.sha256).hexdigest()

    def _mart369_issue_otp(self):
        """A fresh delivery code, returned once and stored only as a hash.

        The app derived it from the order id (orderState.js:82), so anyone
        holding an order number could work out the code for that doorstep
        without ever seeing the order.
        """
        self.ensure_one()
        code = '%06d' % secrets.randbelow(1000000)
        self.sudo().write({
            'mart369_otp_hash': self._mart369_digest(code),
            'mart369_otp_at': fields.Datetime.now(),
            'mart369_otp_used_at': False,
        })
        return code

    def _mart369_check_otp(self, code):
        """True once, for the right code. A used code is spent."""
        self.ensure_one()
        order = self.sudo()
        if not order.mart369_otp_hash or order.mart369_otp_used_at:
            return False
        if not hmac.compare_digest(self._mart369_digest(code), order.mart369_otp_hash):
            return False
        order.write({'mart369_otp_used_at': fields.Datetime.now()})
        return True

    # ------------------------------------------------------------ cancelling

    def _mart369_cancel(self, reason=None):
        """Cancel while it is still only placed, and give the money back."""
        self.ensure_one()
        if self.mart369_state != 'placed':
            raise UserError(self.env._(
                'This order has already been packed, so it can no longer be '
                'cancelled here.'))
        self._mart369_release_slot()
        self._mart369_release_coupon()
        transactions = self.env['payment.transaction'].sudo().search([
            ('mart369_order_ref', '=', self.mart369_ref or '-'),
            ('mart369_kind', '=', 'order'),
        ])
        for tx in transactions:
            if tx.state in ('draft', 'pending'):
                tx._set_canceled(
                    state_message=reason or self.env._('Cancelled by the customer.'))
                tx._post_process()
            elif tx.state == 'done':
                tx._mart369_refund_wallet_leg()
        self._mart369_set_state('cancelled', note=reason)
        if self.state != 'cancel':
            self.with_context(disable_cancel_warning=True).action_cancel()
        return True

    def _mart369_release_slot(self):
        """Give the window back, so the capacity it was holding is free."""
        self.ensure_one()
        self.write({'mart369_slot_key': False, 'mart369_slot_day': False})

    def _mart369_release_coupon(self):
        self.ensure_one()
        if self.mart369_coupon_id:
            coupon = self.mart369_coupon_id.sudo()
            coupon.write({'used_count': max(0, (coupon.used_count or 0) - 1)})

    # ------------------------------------------------------------ serializing

    def _mart369_serialize(self):
        """The order object the app already reads, field for field.

        Built from components/home/Checkout.jsx:617-631 - the shape onPlaced()
        is handed and every later screen consumes.
        """
        self.ensure_one()
        currency = self.currency_id
        lines = self._mart369_app_lines()
        placed = self.mart369_placed_at or self.create_date or fields.Datetime.now()
        return {
            'id': self.mart369_ref or str(self.id),
            'at': int(placed.timestamp() * 1000),
            'mode': self.mart369_mode or 'quick',
            'placed': self._mart369_placed_text(placed),
            'status': self.mart369_state or 'placed',
            'eta': self.mart369_eta or '',
            'items': [[str(tmpl_id), qty] for tmpl_id, qty, __ in lines],
            'snap': {
                str(tmpl_id): snap for tmpl_id, __, snap in lines
            },
            'total': currency.round(self.amount_total),
            'paid': currency.round(self.mart369_paid or 0.0),
            'walletUsed': currency.round(self.mart369_wallet_used or 0.0),
            'pay': self.mart369_pay_note or '',
            'method': self.mart369_method or '',
            'payNote': self.mart369_pay_note or '',
            'txn': self.mart369_txn or '',
            'coupon': self.mart369_coupon_id.code if self.mart369_coupon_id else None,
            'bill': self._mart369_bill_snapshot(),
            'address': (self.partner_shipping_id._mart369_serialize()
                        if self.partner_shipping_id else None),
            'slot': self.mart369_slot_label or '',
            'instructions': self.mart369_instructions or '',
            'whatsapp': bool(self.mart369_whatsapp),
            'timeline': [s._mart369_serialize() for s in self.mart369_stamp_ids],
            'returns': [r._mart369_serialize() for r in self.mart369_return_ids],
            'canCancel': self.mart369_state == 'placed',
        }

    def _mart369_app_lines(self):
        """[(template id, qty, {name, price})] for the basket lines only.

        Delivery, the priority fee and the coupon are lines on the order but
        were never basket items in the app, so they stay out of `items` and
        `snap` and appear in the bill instead.
        """
        self.ensure_one()
        out = []
        for line in self.order_line:
            if line.display_type or line.is_delivery or line.mart369_kind:
                continue
            tmpl = line.product_id.product_tmpl_id
            out.append((tmpl.id, int(line.product_uom_qty), {
                'name': line.name or line.product_id.display_name,
                'price': self.currency_id.round(line.price_unit),
            }))
        return out

    def _mart369_bill_snapshot(self):
        """The `bill` block the cart and the receipt print."""
        self.ensure_one()
        currency = self.currency_id
        items = fees = 0.0
        for line in self.order_line:
            if line.display_type or line.mart369_kind == 'coupon':
                continue
            if line.is_delivery or line.mart369_kind == 'fee':
                fees += line.price_subtotal
            else:
                items += line.price_subtotal
        return {
            'items': currency.round(items),
            'mrp': currency.round(self._mart369_mrp_total()),
            'fees': currency.round(fees),
            'couponOff': currency.round(self.mart369_coupon_off or 0.0),
            'total': currency.round(self.amount_total),
        }

    def _mart369_mrp_total(self):
        """What the basket would have cost at list price, for the "you saved"
        line the app prints."""
        self.ensure_one()
        total = 0.0
        for line in self.order_line:
            if line.display_type or line.is_delivery or line.mart369_kind:
                continue
            total += (line.mart369_mrp or line.price_unit) * line.product_uom_qty
        return total

    def _mart369_placed_text(self, when=None):
        """"Today, 4:05 pm" - what the app printed for itself."""
        self.ensure_one()
        when = fields.Datetime.context_timestamp(self, when or fields.Datetime.now())
        today = fields.Date.context_today(self)
        hour = when.hour % 12 or 12
        stamp = '%d:%02d %s' % (hour, when.minute, 'am' if when.hour < 12 else 'pm')
        if when.date() == today:
            return 'Today, %s' % stamp
        if when.date() == today - timedelta(days=1):
            return 'Yesterday, %s' % stamp
        return '%d %s, %s' % (when.day, when.strftime('%b'), stamp)

    @api.constrains('mart369_state', 'mart369_mode')
    def _check_mart369_state(self):
        for order in self:
            if not order.mart369_state or order.mart369_state in ('draft', 'cancelled'):
                continue
            if order.mart369_state not in order._mart369_flow():
                raise ValidationError(order.env._(
                    '%(state)s is not a step a %(mode)s order goes through.',
                    state=order.mart369_state, mode=order.mart369_mode or 'quick'))
