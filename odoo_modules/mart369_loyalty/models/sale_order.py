"""Points on a 369 Mart order: spending them, earning them, giving them back.

**Spending.** The bill prices the points (cart.py); placing the order writes
them as a `points` line, like a coupon, and *holds* them - a `redeemed` row on
the card - so the same points cannot go on a second basket. The order is still
an unpaid draft at that moment, so the hold is soft: placing again (going back
to change the slot) gives the points back first, and an hourly cron gives back
what a basket nobody paid for is still holding. If such a basket is paid for
after all, the points are taken again when it is placed.

**Earning.** At the step staff chose in Settings -> Loyalty. The order's own
`_mart369_set_state` is called once per real transition, so the step is
checked against the order's flow - Express is shipped where Quick is packed,
and both count as "packed". "After the return window" is not a step at all; a
daily cron earns those. The base is what the items cost after the coupon and
the points, without delivery: the counter earns on the sale, not the postage.

**Giving back.** Money refunded takes back the points it earned, in
proportion, never below zero on the card. Spent points come back only when the
order is cancelled or refunded in full: a partial return already refunds the
item at its full price, so handing back a share of the points as well would
pay the discount out twice.
"""

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Where each setting sits in an order's flow (mart369_order FLOW: index 1 is
# packed on Quick, shipped on Express).
EARN_INDEX = {'placed': 0, 'packed': 1, 'out': 2, 'delivered': 3}

# A basket nobody paid for keeps its points this long.
HOLD_HOURS = 24
# "After the return window" only looks this far back past the window, so
# switching the setting on does not pay out for every order ever delivered.
SETTLE_LOOKBACK_DAYS = 30


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    mart369_kind = fields.Selection(
        selection_add=[('points', 'Loyalty points')], ondelete={'points': 'set null'})


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    mart369_loyalty_card_id = fields.Many2one(
        'pos.loyalty.card', string='Loyalty card', copy=False, ondelete='set null')
    mart369_points_spent = fields.Float(string='Points spent', copy=False, readonly=True)
    mart369_points_off = fields.Monetary(string='Points discount', copy=False, readonly=True)
    mart369_points_credited = fields.Float(
        string='Spent points given back', copy=False, readonly=True)
    mart369_points_earned = fields.Float(string='Points earned', copy=False, readonly=True)
    mart369_points_base = fields.Monetary(
        string='Earned on', copy=False, readonly=True,
        help="The amount the points were earned on - what the items cost after "
             "the coupon and the points, without delivery.")
    mart369_points_reversed = fields.Float(
        string='Earned points taken back', copy=False, readonly=True)

    # ============================================================ spending

    @api.model
    def _mart369_place(self, partner, body):
        # One savepoint, so a basket that is refused leaves its holds where
        # they were: the route turns the refusal into a 400 and still commits.
        with self.env.cr.savepoint():
            self._mart369_points_release(partner)
            order = super(SaleOrder, self.with_context(
                mart369_partner_id=partner.id,
                mart369_use_points=bool(body.get('usePoints')),
            ))._mart369_place(partner, body)
            if order.mart369_state == 'draft':
                order._mart369_points_hold()
        return order.with_context(mart369_partner_id=None, mart369_use_points=None)

    def _mart369_write_lines(self, items, bill, coupon):
        super()._mart369_write_lines(items, bill, coupon)
        points = bill.get('points') or {}
        vals = {'mart369_points_spent': 0.0, 'mart369_points_off': 0.0}
        if points.get('off'):
            self.env['sale.order.line'].sudo().create(self._mart369_charge_line(
                _('Loyalty points (%s)', '%g' % points['spend']),
                -points['off'], 'points', self._mart369_tax()))
            vals = {'mart369_points_spent': points['spend'],
                    'mart369_points_off': points['off']}
        self.sudo().write(vals)

    @api.model
    def _mart369_charge_product(self, kind):
        if kind != 'points':
            return super()._mart369_charge_product(kind)
        template = self.env.ref('mart369_loyalty.product_points', raise_if_not_found=False)
        product = template.sudo().product_variant_id if template else None
        if not product:
            raise UserError(_('The loyalty points product is missing. '
                              'Reinstall 369 Mart Loyalty Points.'))
        return product

    def _mart369_points_hold_rows(self):
        return self.env['pos.loyalty.history'].sudo().search([
            ('sale_order_id', 'in', self.ids), ('type', '=', 'redeemed')])

    def _mart369_points_hold(self):
        """Take the points this basket is spending off the card."""
        self.ensure_one()
        spend = self.mart369_points_spent
        if not spend:
            return
        Card = self.env['pos.loyalty.card'].sudo()
        card = Card._mart369_card_for(self.partner_id)
        if not card or card.state != 'active':
            raise UserError(_('Your loyalty card cannot be used right now.'))
        card._mart369_lock()
        if card.total_points + 1e-6 < spend:
            # Spent somewhere else between the bill and now.
            raise UserError(_('Your points balance has just changed. '
                              'Please check the bill again.'))
        card._mart369_write(spend, 'redeemed', _('Points used'),
                            sub=_('Order #%s', self._mart369_points_ref()),
                            order=self, amount=self.mart369_points_off)
        self.sudo().mart369_loyalty_card_id = card

    @api.model
    def _mart369_points_release(self, partner):
        """Give back what this customer's unpaid baskets are holding."""
        drafts = self.sudo().search([
            ('partner_id', '=', partner.id), ('mart369_state', '=', 'draft'),
            ('mart369_points_spent', '>', 0)])
        # Deleted, not reversed: nothing was ever bought with them, and a
        # "given back" row would read to the customer like a refund.
        drafts._mart369_points_hold_rows().unlink()

    def _mart369_points_retake(self):
        """A basket whose hold was released, paid for after all."""
        self.ensure_one()
        spend = self.mart369_points_spent
        if not spend or self._mart369_points_hold_rows():
            return
        Card = self.env['pos.loyalty.card'].sudo()
        card = self.mart369_loyalty_card_id or Card._mart369_card_for(self.partner_id)
        if not card:
            _logger.warning('mart369 loyalty: %s spent %s points but has no card',
                            self.mart369_ref, spend)
            return
        card._mart369_lock()
        take = round(min(spend, max(0.0, card.total_points)), 2)
        if take < spend:
            _logger.warning('mart369 loyalty: %s spent %s points, only %s were left to take',
                            self.mart369_ref, spend, take)
        card._mart369_write(take, 'redeemed', _('Points used'),
                            sub=_('Order #%s', self._mart369_points_ref()),
                            order=self, amount=self.mart369_points_off)
        self.sudo().write({'mart369_points_spent': take, 'mart369_loyalty_card_id': card.id})

    @api.model
    def _mart369_loyalty_release_cron(self):
        cutoff = fields.Datetime.now() - timedelta(hours=HOLD_HOURS)
        drafts = self.sudo().search([
            ('mart369_state', '=', 'draft'), ('mart369_points_spent', '>', 0),
            ('write_date', '<', cutoff)])
        rows = drafts._mart369_points_hold_rows()
        if rows:
            _logger.info('mart369 loyalty: giving back points held by %s unpaid baskets',
                         len(rows.mapped('sale_order_id')))
            rows.unlink()

    # ============================================================= earning

    def _mart369_set_state(self, state, note=None):
        moved = super()._mart369_set_state(state, note=note)
        if not moved:
            return moved
        try:
            with self.env.cr.savepoint():
                if state == 'placed':
                    self._mart369_points_retake()
                if state == 'cancelled':
                    self._mart369_points_undo()
                elif self._mart369_points_due(state):
                    self._mart369_points_earn()
        except Exception:  # noqa: BLE001
            # Points are not worth failing an order over - the order moving on
            # is the thing that must not be lost.
            _logger.exception('mart369 loyalty: points for %s on %s failed',
                              self.mart369_ref, state)
        return moved

    def _mart369_points_due(self, state):
        """Whether reaching `state` is when this order earns."""
        self.ensure_one()
        earn_on = self.env['mart369.config'].sudo()._get().loyalty_earn_on or 'delivered'
        if earn_on not in EARN_INDEX:
            return False
        flow = self._mart369_flow()
        return state in flow and flow.index(state) >= EARN_INDEX[earn_on]

    def _mart369_points_base_now(self):
        """What the order earns on: items after the coupon and the points,
        without delivery, less whatever returns have already refunded."""
        self.ensure_one()
        lines = self.order_line.filtered(
            lambda l: not l.display_type and not l.is_delivery and l.mart369_kind != 'fee')
        base = sum(lines.mapped('price_total'))
        base -= sum(self.sudo().mart369_return_ids.mapped('refunded'))
        return self.currency_id.round(max(0.0, base))

    def _mart369_points_ref(self):
        """The number a customer knows the order by: the app's, or Odoo's."""
        self.ensure_one()
        return self.mart369_ref or self.name or ''

    def _mart369_points_live(self):
        """Whether the order is a real, standing sale: an app order that was
        paid for and not cancelled, or a confirmed order from Odoo's Sales."""
        self.ensure_one()
        if self.mart369_ref:
            return self.mart369_state not in (False, 'draft', 'cancelled')
        return self.state == 'sale'

    def _mart369_points_earn(self):
        self.ensure_one()
        if self.mart369_points_earned or not self._mart369_points_live():
            return
        Card = self.env['pos.loyalty.card'].sudo()
        if not Card._mart369_enabled():
            return
        rule = Card._mart369_rule()
        if not rule:
            return
        base = self._mart369_points_base_now()
        points = rule._mart369_points_for(base)
        if points <= 0:
            return
        card = Card._mart369_card_for(self.partner_id, create=True)
        if not card or card.state != 'active':
            return
        card._mart369_write(points, 'earned', _('Points earned'),
                            sub=_('Order #%s', self._mart369_points_ref()),
                            order=self, amount=base)
        self.sudo().write({
            'mart369_points_earned': points,
            'mart369_points_base': base,
            'mart369_loyalty_card_id': card.id,
        })

    @api.model
    def _mart369_loyalty_settle_cron(self):
        """Earn on orders whose return window has closed."""
        config = self.env['mart369.config'].sudo()._get()
        if config.loyalty_earn_on != 'settled':
            return
        now = fields.Datetime.now()
        cutoff = now - timedelta(days=max(1, config.loyalty_settle_days or 7))
        stamps = self.env['mart369.order.stamp'].sudo().search([
            ('state', '=', 'delivered'),
            ('at', '<=', cutoff),
            ('at', '>=', cutoff - timedelta(days=SETTLE_LOOKBACK_DAYS)),
            ('order_id.mart369_state', '=', 'delivered'),
            ('order_id.mart369_points_earned', '=', 0),
        ])
        orders = stamps.mapped('order_id').filtered(
            lambda o: not o.mart369_return_ids.filtered(
                # A return still open: wait for it to settle first.
                lambda r: r.state not in ('done', 'refused')))

        # Orders from Odoo's Sales have no stamps: their delivery is the day
        # the last outgoing picking was done.
        pickings = self.env['stock.picking'].sudo().search([
            ('picking_type_code', '=', 'outgoing'),
            ('state', '=', 'done'),
            ('date_done', '<=', cutoff),
            ('date_done', '>=', cutoff - timedelta(days=SETTLE_LOOKBACK_DAYS)),
            ('sale_id', '!=', False),
            ('sale_id.mart369_ref', '=', False),
            ('sale_id.mart369_points_earned', '=', 0),
        ])
        for order in pickings.mapped('sale_id'):
            last = order._mart369_points_delivered_at()
            if last and last <= cutoff:
                orders |= order

        for order in orders:
            try:
                with self.env.cr.savepoint():
                    order._mart369_points_earn()
            except Exception:  # noqa: BLE001
                _logger.exception('mart369 loyalty: settling %s failed',
                                  order._mart369_points_ref())

    # ================================================ orders from Odoo Sales

    def _mart369_points_delivered_at(self):
        """When everything this order ships had gone, or None while some of it
        is still to go. Cancelled pickings do not count either way."""
        self.ensure_one()
        outgoing = self.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel')
        if not outgoing or outgoing.filtered(lambda p: p.state != 'done'):
            return None
        return max(outgoing.mapped('date_done'))

    def _mart369_points_staff_step(self, step):
        """An order from Odoo's Sales reached `step`: 'placed' (confirmed) or
        'delivered' (its last outgoing picking done). Earn if that is the
        moment the shop chose. Packed and out for delivery are app steps a
        Sales order has no equivalent of, so they mean its delivery."""
        self.ensure_one()
        if self.mart369_ref:
            return
        earn_on = self.env['mart369.config'].sudo()._get().loyalty_earn_on or 'delivered'
        due = (earn_on == 'placed' and step in ('placed', 'delivered')) or \
              (earn_on in ('packed', 'out', 'delivered') and step == 'delivered')
        if not due:
            return
        try:
            with self.env.cr.savepoint():
                self._mart369_points_earn()
        except Exception:  # noqa: BLE001
            _logger.exception('mart369 loyalty: points for %s on %s failed', self.name, step)

    def action_confirm(self):
        result = super().action_confirm()
        for order in self.filtered(lambda o: not o.mart369_ref):
            order._mart369_points_staff_step('placed')
        return result

    def _action_cancel(self):
        result = super()._action_cancel()
        # App orders take their points back through `_mart369_set_state`.
        for order in self.filtered(lambda o: not o.mart369_ref):
            try:
                with self.env.cr.savepoint():
                    order._mart369_points_undo()
            except Exception:  # noqa: BLE001
                _logger.exception('mart369 loyalty: undoing points on %s failed', order.name)
        return result

    # ========================================================= giving back

    def _mart369_refund_to_wallet(self, amount, title):
        # Every caller records the refund only after this returns (the
        # return's `refunded`, the cancel's `mart369_cancel_refund`), so what
        # is still owed afterwards is what was owed before, less this.
        before = self._mart369_refundable()
        paid = super()._mart369_refund_to_wallet(amount, title)
        if paid:
            self._mart369_points_after_refund(paid, left=before - paid)
        return paid

    def _mart369_remove_line(self, line, reason):
        # Priced before it goes: the line is at quantity 0 afterwards. Cash on
        # delivery refunds nothing but still earns on less. The removal
        # records its own refund, so what is owed is read afterwards.
        value = line.price_total
        refund = super()._mart369_remove_line(line, reason)
        self._mart369_points_after_refund(value, left=self._mart369_refundable())
        return refund

    def _mart369_points_after_refund(self, value, left):
        try:
            with self.env.cr.savepoint():
                self._mart369_points_take_back(value)
                if self.currency_id.compare_amounts(left, 0.0) <= 0 \
                        and self._mart369_paid_amount() > 0:
                    self._mart369_points_give_spent()
        except Exception:  # noqa: BLE001
            _logger.exception('mart369 loyalty: giving back points on %s failed',
                              self.mart369_ref)

    def _mart369_points_take_back(self, value, everything=False):
        """Take back the points `value` of this order had earned."""
        self.ensure_one()
        earned = self.mart369_points_earned
        left = round(earned - (self.mart369_points_reversed or 0.0), 2)
        card = self.mart369_loyalty_card_id
        if not earned or left <= 0 or not card:
            return
        share = left if everything else (
            round(earned * value / self.mart369_points_base, 2)
            if self.mart369_points_base else left)
        card._mart369_lock()
        # Never below zero: points already spent at the counter stay spent.
        take = round(min(left, share, max(0.0, card.total_points)), 2)
        if take <= 0:
            return
        card._mart369_write(take, 'returned', _('Points taken back'),
                            sub=_('Order #%s', self._mart369_points_ref()), order=self)
        self.sudo().mart369_points_reversed = (self.mart369_points_reversed or 0.0) + take

    def _mart369_points_give_spent(self):
        """Return the points this order spent, once and in full."""
        self.ensure_one()
        spent = self.mart369_points_spent
        left = round(spent - (self.mart369_points_credited or 0.0), 2)
        if not spent or left <= 0 or not self._mart369_points_hold_rows():
            return
        card = self.mart369_loyalty_card_id
        if not card:
            return
        card._mart369_write(left, 'redeem_returned', _('Points given back'),
                            sub=_('Order #%s', self._mart369_points_ref()), order=self)
        self.sudo().mart369_points_credited = (self.mart369_points_credited or 0.0) + left

    def _mart369_points_undo(self):
        """A cancelled order keeps nothing it earned and loses nothing it spent."""
        self.ensure_one()
        self._mart369_points_take_back(0.0, everything=True)
        self._mart369_points_give_spent()

    # ========================================================= serializing

    def _mart369_serialize(self):
        data = super()._mart369_serialize()
        data['points'] = self._mart369_points_serialize()
        return data

    def _mart369_points_serialize(self):
        self.ensure_one()
        earned = round((self.mart369_points_earned or 0.0)
                       - (self.mart369_points_reversed or 0.0), 2)
        will = 0.0
        Card = self.env['pos.loyalty.card'].sudo()
        if not self.mart369_points_earned and self.mart369_state not in (False, 'cancelled') \
                and Card._mart369_enabled():
            rule = Card._mart369_rule()
            will = rule._mart369_points_for(self._mart369_points_base_now()) if rule else 0.0
        return {
            'spent': self.mart369_points_spent or 0.0,
            'off': self.currency_id.round(self.mart369_points_off or 0.0),
            'earned': max(0.0, earned),
            'willEarn': will,
            'earnOn': self.env['mart369.config'].sudo()._get().loyalty_earn_on or 'delivered',
            'returned': self.mart369_points_credited or 0.0,
        }

    def _mart369_bill_snapshot(self):
        """The points line is not an item: the base snapshot counts every line
        that is not a fee or a coupon, so take it back out and name it."""
        snap = super()._mart369_bill_snapshot()
        points = self.order_line.filtered(lambda l: l.mart369_kind == 'points')
        if points:
            snap['items'] = self.currency_id.round(
                snap['items'] - sum(points.mapped('price_subtotal')))
        snap['pointsOff'] = self.currency_id.round(self.mart369_points_off or 0.0)
        return snap
