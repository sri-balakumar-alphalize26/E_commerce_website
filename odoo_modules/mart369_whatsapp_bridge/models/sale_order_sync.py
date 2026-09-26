"""One order, two state machines, kept honestly in step.

The website's ladder lives on `sale.order.mart369_state`; the WhatsApp
delivery's lives on the picking's `sa_delivery_state`. Neither is replaced.
The bridge maps between them and keeps a single rule about direction:

* **push** - the console moved a *website* order, so the delivery job is
  driven to match (the shop is told, the rider is paged);
* **pull** - the shop or the rider moved a *job*, so the order is brought up
  to where the parcel really is.

One context key, ``mart369_bridge``, marks which of the two is running, and
each refuses to fire under the other - that is the whole loop-safety story.

**A WhatsApp order never goes through `_mart369_set_state`.** That method's
override chain pays referrals, mints scratch cards, earns loyalty points and
sends the website's own WhatsApp message - all of it for website customers.
A WhatsApp order is mirrored with a plain write plus the side-effect-free
`_mart369_stamp`, so the board and the timeline work and nothing else fires.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Job stage -> mart369 state, per storefront mode. Two columns because the
# website's constraint refuses `packed` on an Express order and `shipped` on a
# Quick one (sale_order.py, _check_mart369_state).
#                          quick        all (Express)
_MAP = {
    'awaiting_shop':      ('placed',    'placed'),
    'preparing':          ('placed',    'placed'),
    'to_assign':          (None,        'placed'),   # quick: depends on ready
    'ready':              ('packed',    'placed'),
    'offered':            ('packed',    'placed'),
    'accepted':           ('packed',    'placed'),
    'picked':             ('out',       'shipped'),
    'dispatched':         ('out',       'shipped'),
    'out_for_delivery':   ('out',       'out'),
    'returning':          ('out',       'out'),
    'delivered':          ('delivered', 'delivered'),
    'cancelled':          ('cancelled', 'cancelled'),
    'returned':           ('cancelled', 'cancelled'),
    'failed':             ('cancelled', 'cancelled'),
}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------ the job

    def _mart369_bridge_job(self):
        """The delivery job carrying this order, if there is one.

        Read from the picking, not from the order's related copy: the related
        field is not stored, reads only the first picking, and cannot be
        searched. Sudo'd, because the console's staff have no rights on
        stock.picking and must not need any to move an order along - every
        write the callers make is deliberate and goes through sudo anyway.
        """
        self.ensure_one()
        jobs = self.sudo().picking_ids.filtered(
            lambda p: p.picking_type_id.code == 'outgoing'
            and p.state != 'cancel'
            and p.sa_delivery_state not in (False, 'none'))
        return jobs.sorted('id', reverse=True)[:1]

    @api.model
    def _mart369_bridge_map(self, mode, picking):
        """Where the website's ladder says an order is, given its job."""
        stage = picking.sa_delivery_state
        if picking.sale_id.state == 'cancel':
            return 'cancelled'
        pair = _MAP.get(stage)
        if not pair:
            return None
        state = pair[1] if mode == 'all' else pair[0]
        if state is None:
            # Quick + to_assign: packed once the shop said Ready, otherwise
            # the shop still has it.
            state = 'packed' if picking.sa_shop_ready_on else 'placed'
        return state

    # -------------------------------------------------- mirroring (pull, WA)

    def _mart369_bridge_mirror(self):
        """Bring a WhatsApp order's board fields up to where the job is."""
        for order in self:
            if order.mart369_channel != 'whatsapp':
                continue
            job = order._mart369_bridge_job()
            mode = 'all' if (job and job.sa_delivery_kind == 'express') else 'quick'
            state = (order._mart369_bridge_map(mode, job) if job
                     else ('cancelled' if order.state == 'cancel' else 'placed'))
            if not state:
                continue
            vals = {}
            if order.mart369_mode != mode:
                vals['mart369_mode'] = mode
            if order.mart369_state != state:
                vals['mart369_state'] = state
            if not order.mart369_placed_at:
                vals['mart369_placed_at'] = order.date_order
            if job and job.sa_promised_on and order.mart369_due_at != job.sa_promised_on:
                vals['mart369_due_at'] = job.sa_promised_on
            # 'cod' is the only value the website's Cash tab looks for. Never
            # any other word: `_mart369_paid_amount` treats a non-cod method
            # as paid, which a WhatsApp order has its own books for.
            method = 'cod' if (job and job.sa_cod_amount) else False
            if order.mart369_method != method:
                vals['mart369_method'] = method
            if vals:
                order.sudo().with_context(mart369_bridge='pull').write(vals)
            if 'mart369_state' in vals:
                order._mart369_stamp(state)
        return True

    # --------------------------------------------- console actions, WhatsApp

    def mart369_action_advance(self):
        """The console's one button drives the real delivery for a WhatsApp
        order, instead of only recolouring a card."""
        wa = self.filtered(lambda o: o.mart369_channel == 'whatsapp')
        rest = self - wa
        if rest:
            super(SaleOrder, rest).mart369_action_advance()
        for order in wa:
            order._mart369_bridge_advance()
        return True

    def _mart369_bridge_advance(self):
        self.ensure_one()
        if self.mart369_state == 'cancelled':
            raise UserError(_('Order %s was cancelled and cannot be moved on.',
                              self.name))
        nxt = self._mart369_next_state()
        if not nxt:
            raise UserError(_('Order %s has already been delivered.', self.name))
        if nxt == 'delivered':
            raise UserError(_('Order %s is out for delivery. Enter the '
                              'delivery code to close it.', self.name))
        job = self._mart369_bridge_job()
        if not job:
            raise UserError(_('Order %s has no delivery job yet. Confirm it '
                              'in Odoo first.', self.name))
        job = job.sudo().with_context(mart369_bridge='push')
        if nxt in ('packed', 'shipped'):
            if job.sa_delivery_state == 'awaiting_shop':
                job.sa_shop_accept()
            if job.sa_delivery_state in ('awaiting_shop', 'preparing'):
                # Ready is what pages the rider (sales_automation_store).
                job.sa_shop_ready()
            if nxt == 'shipped' and job.sa_delivery_state in (
                    'ready', 'to_assign', 'offered', 'accepted', 'picked'):
                job.sa_set_state('dispatched')
        elif nxt == 'out':
            # The stack sends its own door code to the WhatsApp customer here.
            job.sa_set_state('out_for_delivery')
        self._mart369_bridge_mirror()
        return True

    def mart369_action_deliver(self, code):
        """A WhatsApp order closes with the stack's own door code."""
        if self.mart369_channel != 'whatsapp':
            return super().mart369_action_deliver(code)
        self.ensure_one()
        if self.mart369_state == 'cancelled':
            raise UserError(_('Order %s was cancelled.', self.name))
        if self.mart369_state == 'delivered':
            raise UserError(_('Order %s is already delivered.', self.name))
        if self.mart369_state != 'out':
            raise UserError(_('Order %s is not out for delivery yet.', self.name))
        job = self._mart369_bridge_job()
        if not job:
            raise UserError(_('Order %s has no delivery job.', self.name))
        ok, __ = job.sudo().sa_verify_otp('delivery', code)
        if not ok:
            # The console's controller matches "not right" for its 400.
            raise UserError(_('That delivery code is not right.'))
        job.sudo().with_context(mart369_bridge='push').sa_set_state('delivered')
        self._mart369_bridge_mirror()
        return True

    def _mart369_cancel(self, reason=None):
        """Cancelling a WhatsApp order is the stack's cancel.

        `action_cancel` (sales_automation_delivery) cancels the job and tells
        the customer and the rider; the money comes back to the customer's
        369 Wallet with a credit note on the way out (money_back.py).
        """
        if self.mart369_channel != 'whatsapp':
            return super()._mart369_cancel(reason=reason)
        self.ensure_one()
        job = self._mart369_bridge_job()
        if job and job.sa_delivery_state not in job._SA_CANCELLABLE:
            raise UserError(_('This order is already on the doorstep - it can '
                              'no longer be cancelled here.'))
        self.sudo().with_context(
            sa_cancel_reason=reason or '',
            disable_cancel_warning=True,
            mart369_bridge='push',
        ).action_cancel()
        self._mart369_bridge_mirror()
        self._mart369_stamp('cancelled', note=reason)
        return True

    def _mart369_failed(self, reason, then):
        """A failed doorstep on a WhatsApp order stays the stack's business."""
        if self.mart369_channel != 'whatsapp':
            return super()._mart369_failed(reason, then)
        self.ensure_one()
        if self.mart369_state != 'out':
            raise UserError(_('Only an order out for delivery can fail at the door.'))
        if then not in ('retry', 'return'):
            raise UserError(_('Try again, or return it to the store.'))
        job = self._mart369_bridge_job()
        if not job:
            raise UserError(_('Order %s has no delivery job.', self.name))
        order = self.sudo()
        order.write({
            'mart369_attempts': order.mart369_attempts + 1,
            'mart369_failed_reason': reason or _('Other'),
            'mart369_failed_at': fields.Datetime.now(),
        })
        job = job.sudo().with_context(mart369_bridge='push')
        if then == 'retry':
            job.sa_issue_delivery_otp()
            return 0.0
        job.sa_set_state('returning')
        self._mart369_bridge_mirror()
        return 0.0

    # --------------------------------------------------- confirm (both ways)

    def action_confirm(self):
        """A WhatsApp order steps onto the board the moment it is confirmed.

        By now the delivery stack has already made the job (its own
        `action_confirm` override ran in the super chain), so the mirror has
        something to read.
        """
        result = super().action_confirm()
        wa = self.filtered(lambda o: o.mart369_channel == 'whatsapp'
                           and o.state in ('sale', 'done'))
        if wa:
            try:
                wa._mart369_bridge_mirror()
            except Exception:  # noqa: BLE001 - never block a confirmation
                _logger.exception('bridge: could not mirror %s onto the board',
                                  wa.mapped('name'))
        return result

    # ------------------------------------------------- pushing website moves

    def _mart369_set_state(self, state, note=None):
        """After a website order really moved, drive its job to match.

        Inside a savepoint, and never blocking: the suite's rule is that a
        message or a job failing is not a reason for an order to stop moving.
        Skipped under `pull` - that is the job telling *us* where it is.
        """
        moved = super()._mart369_set_state(state, note=note)
        if not moved or self.mart369_channel == 'whatsapp':
            return moved
        if self.env.context.get('mart369_bridge') == 'pull':
            return moved
        job = self._mart369_bridge_job()
        if not job:
            return moved
        try:
            with self.env.cr.savepoint():
                self._mart369_bridge_push(job.sudo().with_context(
                    mart369_bridge='push'), state)
        except Exception as err:  # noqa: BLE001
            _logger.exception('bridge: could not move job %s to match %s (%s)',
                              job.sa_ref_code, self.mart369_ref, state)
            job.sudo().sa_last_error = str(err)[:180]
        return moved

    def _mart369_bridge_push(self, job, state):
        self.ensure_one()
        stage = job.sa_delivery_state
        if state in ('packed', 'shipped'):
            if stage == 'awaiting_shop':
                job.sa_shop_accept()
            if job.sa_delivery_state in ('awaiting_shop', 'preparing'):
                job.sa_shop_ready()
            if state == 'shipped' and job.sa_delivery_state in (
                    'ready', 'to_assign', 'offered', 'accepted', 'picked'):
                job.sa_set_state('dispatched')
        elif state == 'out':
            if job.sa_delivery_state in (
                    'awaiting_shop', 'preparing', 'ready', 'to_assign',
                    'offered', 'accepted', 'picked', 'dispatched'):
                job.sa_set_state('out_for_delivery')
        elif state == 'delivered':
            if job.sa_delivery_state not in ('delivered',):
                job.sa_set_state('delivered')
        # cancelled needs nothing: the website's cancel already calls
        # `action_cancel`, and the stack's override cancels the job there.
        return True

    # ------------------------------------------------------------- the rider

    def _mart369_set_rider(self, user):
        """Assigning a rider on the console also hands the real job over."""
        result = super()._mart369_set_rider(user)
        job = self._mart369_bridge_job()
        if not job or not user:
            return result
        rider = self.env['sa.delivery.partner'].sudo()._mart369_bridge_for(user)
        if not rider:
            # No phone, no rider app - the console assignment stands on its
            # own, exactly as it did before the bridge existed.
            _logger.info('bridge: %s has no phone, so job %s is not handed '
                         'to the rider app', user.name, job.sa_ref_code)
            return result
        holder = job.sa_delivery_partner_id
        if (holder and holder != rider
                and job.sa_delivery_state in ('accepted', 'picked',
                                              'dispatched', 'out_for_delivery',
                                              'delivered')):
            # Somebody else is carrying the parcel right now. Naming a rider
            # on a job nobody holds yet - or re-naming the same one - is fine
            # at any stage; taking it out of another rider's hands is not.
            raise UserError(_('%s already has this delivery in hand - it is '
                              'too late to hand it to somebody else.',
                              holder.name))
        job = job.sudo().with_context(mart369_bridge='push')
        job.sa_delivery_partner_id = rider
        # Page them only once there is something to collect; a job still at
        # the counter is offered by the shop's own Ready button.
        if (job.sa_delivery_state in ('to_assign', 'offered', 'ready')
                and (job.sa_shop_ready_on or job.sa_delivery_state == 'ready')):
            job.with_context(sa_shop_done=True,
                             sa_force_offer=True).sa_action_offer()
        return result


class SaDeliveryPartner(models.Model):
    _inherit = 'sa.delivery.partner'

    @api.model
    def _mart369_bridge_for(self, user):
        """The stack's rider record for a console rider, made if missing.

        The console's riders are res.users with the Rider role; the stack's
        are `sa.delivery.partner` rows keyed on a WhatsApp number. Linked by
        `user_id` first, then by phone, and only then created - so one person
        never becomes two riders.
        """
        rider = self.sudo().search([('user_id', '=', user.id)], limit=1)
        if rider:
            return rider
        phone = (user.partner_id.phone or '').strip()
        rider = self._sa_by_phone(phone) if phone else self.browse()
        if rider:
            rider.user_id = user
            return rider
        if not phone:
            return self.browse()
        return self.sudo().create({
            'name': user.name,
            'phone': phone,
            'user_id': user.id,
            'partner_id': user.partner_id.id,
            'kind': 'own',
            'on_duty': True,
        })
