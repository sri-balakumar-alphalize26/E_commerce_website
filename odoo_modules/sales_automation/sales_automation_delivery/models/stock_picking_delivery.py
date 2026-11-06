# -*- coding: utf-8 -*-
"""The delivery job is the picking Odoo already made."""

import logging
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------
    sa_delivery_state = fields.Selection([
        ('none', 'Not a Delivery Job'),
        ('to_assign', 'To Dispatch'),
        ('offered', 'Offered'),
        ('accepted', 'Accepted'),
        ('picked', 'Picked Up'),
        ('dispatched', 'Collected by Rider'),
        ('out_for_delivery', 'Rider Near Customer'),
        ('delivered', 'Delivered'),
        ('returning', 'Coming Back'),
        ('returned', 'Returned to Shop'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ], string='Delivery Status', default='none', copy=False, index=True,
        tracking=True)

    sa_shop_id = fields.Many2one(
        'sa.delivery.shop', string='Shop', copy=False, index=True)
    sa_delivery_partner_id = fields.Many2one(
        'sa.delivery.partner', string='Rider / Courier', copy=False,
        index=True, tracking=True)
    sa_partner_kind = fields.Selection(
        related='sa_delivery_partner_id.kind', string='Carrier Kind',
        store=True)

    sa_ref_code = fields.Char(
        'Job Code', copy=False, index=True, readonly=True,
        help="Short code the rider can quote on WhatsApp - #D42 ACCEPT.")
    sa_access_token = fields.Char(
        'Job Token', copy=False, readonly=True, groups='base.group_user')

    sa_cod_amount = fields.Monetary(
        'Collect on Delivery', currency_field='sa_currency_id', copy=False,
        help="Zero when the order was already paid online.")
    sa_currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda s: s.env.company.currency_id)

    sa_offered_on = fields.Datetime('Offered On', copy=False, readonly=True)
    sa_accepted_on = fields.Datetime('Accepted On', copy=False, readonly=True)
    sa_picked_on = fields.Datetime('Picked Up On', copy=False, readonly=True)
    sa_dispatched_on = fields.Datetime('Dispatched On', copy=False,
                                       readonly=True)
    sa_out_on = fields.Datetime('Out for Delivery On', copy=False,
                                readonly=True)
    sa_delivered_on = fields.Datetime('Delivered On', copy=False, readonly=True)
    sa_last_error = fields.Char('Last Error', copy=False, readonly=True)
    sa_last_delivery_code = fields.Char(
        'Last Delivery Code', copy=False, readonly=True,
        groups='base.group_system',
        help="Only read back when the testing switch is on. Kept so a tester "
             "driving the flow from Postman can complete a delivery with no "
             "WhatsApp session connected.")
    # The stored values stay `quick` / `express` - existing rows and the
    # search filters depend on them. Only the words change, to the ones the
    # shop actually uses.
    sa_delivery_kind = fields.Selection([
        ('quick', 'Quick'),
        ('express', 'Express'),
    ], string='Delivery Type', copy=False, index=True,
        help="Quick when the shop can supply every line from what it "
             "holds and the promise falls today; Express when something has "
             "to come in from a supplier first, so it lands on a later day.")
    sa_arrived_shop_on = fields.Datetime(
        'Reached the Shop', readonly=True, copy=False,
        help="When the rider said they were at the counter. Recorded for the "
             "record only - collection is still proved by the shop's code.")
    sa_arrived_customer_on = fields.Datetime(
        'Reached the Customer', readonly=True, copy=False,
        help="When the rider said they were at the door. This is when the "
             "customer's completion code is sent, so it is live for the few "
             "minutes it is needed rather than the whole journey.")
    sa_promised_on = fields.Datetime(
        'Promised By', copy=False,
        help="What the customer was told. Set from the delivery settings at "
             "confirmation, and editable afterwards - a promise that changes "
             "should be visible, not silently recomputed.")

    sa_cancelled_on = fields.Datetime('Cancelled On', copy=False,
                                      readonly=True)
    sa_returned_on = fields.Datetime('Returned On', copy=False, readonly=True)
    sa_cancel_reason = fields.Char('Cancel / Return Reason', copy=False)
    sa_refund_move_id = fields.Many2one(
        'account.move', string='Refund', copy=False, readonly=True,
        help="The credit note raised when a paid order was cancelled or "
             "returned.")

    # ---- Live position ----
    sa_rider_lat = fields.Float('Rider Latitude', digits=(16, 6), copy=False,
                                readonly=True)
    sa_rider_lng = fields.Float('Rider Longitude', digits=(16, 6), copy=False,
                                readonly=True)
    sa_rider_fix_on = fields.Datetime('Position Updated', copy=False,
                                      readonly=True)
    sa_ping_ids = fields.One2many('sa.delivery.ping', 'picking_id',
                                  string='Position History')
    sa_track_token = fields.Char(
        'Tracking Token', copy=False, readonly=True, groups='base.group_user',
        help="The customer's own token. Separate from the rider's, so that "
             "sharing one link never hands over the other.")

    sa_job_url = fields.Char('Job Link', compute='_compute_sa_job_url')
    sa_track_url = fields.Char('Tracking Link', compute='_compute_sa_job_url')

    def sa_amount_due(self):
        """What the rider should collect at the door, as of now.

        Read from the invoice rather than from `sa_cod_amount`, which is a
        snapshot taken when the job was created. A customer who paid the link
        afterwards would otherwise still be asked for the full amount and pay
        it twice.

        `amount_residual` handles the awkward cases for free: a part payment
        leaves the remainder, a credit note reduces it, a refund puts it back.
        With no posted invoice yet there is nothing better than the snapshot.
        """
        self.ensure_one()
        invoices = self.sale_id.invoice_ids.filtered(
            lambda move: move.move_type in ('out_invoice', 'out_refund')
            and move.state == 'posted')
        if not invoices:
            return self.sa_cod_amount
        # Settled as far as the customer is concerned. `in_payment` is the
        # important one: the money has been taken and matched to the invoice,
        # and only the bank reconciliation is outstanding. The residual still
        # reads as the full amount until that happens, which is days away and
        # nothing to do with the person at the door.
        settled = ('paid', 'in_payment', 'reversed')
        due = 0.0
        for move in invoices:
            if move.payment_state in settled:
                continue
            due += (move.amount_residual if move.move_type == 'out_invoice'
                    else -move.amount_residual)
        currency = self.sa_currency_id or self.company_id.currency_id
        if currency and currency.is_zero(due):
            return 0.0
        return max(0.0, due)

    @api.model
    def _sa_public_base(self):
        """The address to put in a link somebody outside will tap.

        Deliberately not `web.base.url`. That one tells the WhatsApp panel
        which server we are, and the panel refuses a key it did not issue to
        that exact address - so it has to stay whatever the key was registered
        with, usually `http://localhost:8069`. A customer's phone can do
        nothing with that.

        Set `sa_delivery.public_base_url` to the tunnel or domain the outside
        world reaches, and only the links move. Unset, everything behaves as it
        did before.
        """
        params = self.env['ir.config_parameter'].sudo()
        return (params.get_param('sa_delivery.public_base_url')
                or params.get_param('web.base.url') or '')

    def _compute_sa_job_url(self):
        # Through the doorway, so a rider or a customer opening this on a
        # phone lands on the right database instead of a bare 404.
        link = self.env['wa.auto.reply'].sudo()._sa_public_link
        for picking in self:
            picking.sa_job_url = (
                link('/wa/delivery/%s?token=%s'
                     % (picking.id, picking.sa_access_token))
                if picking.id and picking.sa_access_token else '')
            picking.sa_track_url = (
                link('/wa/track/%s?token=%s'
                     % (picking.id, picking.sa_track_token))
                if picking.id and picking.sa_track_token else '')

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    def _sa_ensure_identity(self):
        """A short code and a token, made once and kept."""
        for picking in self:
            values = {}
            if not picking.sa_ref_code:
                values['sa_ref_code'] = 'D%s' % picking._sa_base36(picking.id)
            if not picking.sa_access_token:
                # Long enough that guessing is not worth anyone's time, and
                # never reused: the token is the only thing standing between
                # a stranger and a customer's home address.
                values['sa_access_token'] = secrets.token_urlsafe(24)
            if not picking.sa_track_token:
                # A different secret for the customer. One link must never be
                # able to act as the other: the rider's moves the job on, the
                # customer's only watches it.
                values['sa_track_token'] = secrets.token_urlsafe(18)
            if values:
                picking.write(values)
        return True

    @api.model
    def _sa_base36(self, number):
        if not number:
            return '0'
        out = ''
        while number:
            number, rest = divmod(number, 36)
            out = _ALPHABET[rest] + out
        return out

    @api.model
    def _sa_by_ref(self, code):
        """The job a `#D42` code names."""
        code = (code or '').strip().lstrip('#').upper()
        if not code:
            return self.browse()
        return self.sudo().search([('sa_ref_code', '=', code)], limit=1)

    # ------------------------------------------------------------------
    # Sending the job
    # ------------------------------------------------------------------
    def _sa_session(self):
        """Which WhatsApp number the job is sent from."""
        self.ensure_one()
        order = self.sale_id
        session = order.wa_employee_session_id.session_id if order else False
        if not session and order and order.sa_group_id:
            session = order.sa_group_id.session_id
        if not session:
            session = self.env['whatsapp.session'].sudo().search(
                [('active', '=', True)], limit=1)
        return session

    def _sa_job_body(self):
        """What the rider reads on their phone."""
        self.ensure_one()
        partner = self.partner_id
        lines = [_("\U0001F6F5 *Delivery #%(code)s*%(shop)s",
                   code=self.sa_ref_code or '-',
                   shop=(' - %s' % self.sa_shop_id.name)
                        if self.sa_shop_id else '')]

        items = []
        for move in self.move_ids[:6]:
            qty = move.product_uom_qty
            items.append('%s x %s' % (
                int(qty) if float(qty).is_integer() else qty,
                move.product_id.name))
        if items:
            lines.append('\U0001F4E6 %s' % '\n     '.join(items))

        where = ', '.join(filter(None, [
            partner.street, partner.street2, partner.city, partner.zip,
            partner.country_id.name]))
        revealed = self.sa_customer_revealed() if hasattr(self, 'sa_customer_revealed') else True
        if not revealed:
            where = self.sa_customer_area()
            if where:
                where = _("%s (full address after pickup)", where)
        if where:
            lines.append('\U0001F4CD %s' % where)
        if partner.phone and revealed:
            lines.append('\U0001F4DE %s' % partner.phone)

        # The same figure the app shows, read from the invoice rather than
        # the snapshot taken when the job was made. A customer who paid the
        # link afterwards must not be asked for it again at the door.
        due = self.sa_amount_due()
        if due:
            lines.append(_("\U0001F4B0 Collect *%(amount).3f %(cur)s* on "
                           "delivery.",
                           amount=due,
                           cur=self.sa_currency_id.name or ''))
        else:
            lines.append(_("\U0001F4B3 Already paid - nothing to collect."))

        if self.sa_job_url:
            lines.append('')
            lines.append(_("Open to accept:\n%s", self.sa_job_url))
            lines.append(_("(or reply *#%(code)s ACCEPT*)",
                           code=self.sa_ref_code or ''))
        return '\n'.join(lines)

    def sa_action_offer(self):
        """Send the job to the assigned rider.

        Guarded on the *picking*, not on the message. A `SERIALIZATION_FAILURE`
        rolls this transaction back while leaving the WhatsApp message sent, so
        a guard keyed on anything the rollback undoes lets the same job go out
        again - which is exactly how three private chats were opened for one
        order on 1 Sep before the handoff guard was re-keyed.
        """
        for picking in self:
            rider = picking.sa_delivery_partner_id
            if not rider or not rider.phone:
                picking.write({'sa_delivery_state': 'to_assign',
                               'sa_last_error': _("No rider assigned.")})
                continue
            picking._sa_ensure_identity()

            key = 'delivery|%s' % picking.id
            if self.env.context.get('sa_force_offer'):
                # A dispatcher pressing "Send again" means it, so the key is
                # made unique rather than the guard row being deleted.
                key = '%s|%s' % (key, fields.Datetime.now())
            if not self.env['sa.outbox.guard'].sudo().claim(key, 900):
                _logger.info("Delivery: job %s was already offered - not "
                             "sending it again", picking.sa_ref_code)
                continue
            # The claim commits on its own connection and outlives a rollback
            # of THIS request. On 10 Sep a concurrent update of the WhatsApp
            # session rolled the offer back; the retry then read "already
            # offered" and the job sat at Ready with no rider step at all.
            # Handing the claim back on rollback lets the retry offer it.
            self.env.cr.postrollback.add(
                lambda k=key: self.env['sa.outbox.guard'].sudo().release(k))

            session = picking._sa_session()
            if not session:
                picking.write({'sa_delivery_state': 'to_assign',
                               'sa_last_error': _("No WhatsApp session.")})
                continue
            try:
                session.send_message(rider.phone, picking._sa_job_body())
                picking.write({
                    'sa_delivery_state': 'offered',
                    'sa_offered_on': fields.Datetime.now(),
                    'sa_last_error': False,
                })
                _logger.info("Delivery: offered job %s to %s (%s)",
                             picking.sa_ref_code, rider.name, rider.phone)
            except Exception as err:  # noqa: BLE001 - a job is not lost over this
                # The WhatsApp message is a nudge, not the delivery mechanism:
                # the app polls `/orders` and will show this job regardless. So
                # a failed send records why and leaves the job offered, rather
                # than marking it `failed` and stranding a real parcel because
                # a gateway was down.
                picking.write({
                    'sa_delivery_state': 'offered',
                    'sa_offered_on': fields.Datetime.now(),
                    'sa_last_error': _("Assigned, but the WhatsApp nudge did "
                                       "not send: %(why)s", why=str(err)[:180]),
                })
                _logger.warning("Delivery: job %s is offered to %s but the "
                                "WhatsApp nudge failed: %s",
                                picking.sa_ref_code, rider.phone, err)
        return True

    def sa_action_reoffer(self):
        """Send it again, on purpose - a dispatcher pressing the button.

        Only while the job is still waiting for a rider's answer: offering
        writes the state back to Offered, which on 5 Oct 2026 took a job the
        rider had already collected back to Offered (and locked the
        customer's address again in the rider app)."""
        for picking in self:
            if picking.sa_delivery_state not in ('ready', 'to_assign', 'offered'):
                raise UserError(_(
                    "Job #%(ref)s is %(state)s - the job message can only be sent again "
                    "while it is waiting for a rider's answer.",
                    ref=picking.sa_ref_code or picking.name,
                    state=dict(picking._fields['sa_delivery_state']._description_selection(self.env))
                    .get(picking.sa_delivery_state, picking.sa_delivery_state)))
        return self.with_context(sa_force_offer=True).sa_action_offer()

    # ------------------------------------------------------------------
    # Moving it along
    # ------------------------------------------------------------------
    _SA_STAMP = {
        'accepted': 'sa_accepted_on',
        'picked': 'sa_picked_on',
        'dispatched': 'sa_dispatched_on',
        'out_for_delivery': 'sa_out_on',
        'delivered': 'sa_delivered_on',
    }

    # The whole workflow, in one place. The API returns the actions from this
    # table so the app never hard-codes a ladder of its own - a change here is
    # a change in every client at once, with no new release.
    _SA_FLOW = {
        'to_assign': [],
        'offered': ['accept', 'decline'],
        'accepted': ['arrived_shop', 'verify_pickup_otp', 'report_issue'],
        'picked': ['dispatch', 'return_to_shop', 'report_issue'],
        'dispatched': ['start_delivery', 'verify_delivery_otp', 'return_to_shop',
                       'report_issue'],
        'out_for_delivery': ['verify_delivery_otp', 'return_to_shop',
                             'report_issue'],
        # The parcel is with the rider and coming back. Only the shop closes
        # this, so a rider cannot mark goods returned from the roadside.
        'returning': ['confirm_return'],
        'returned': [],
        'cancelled': [],
        'delivered': [],
        'failed': [],
        'none': [],
    }

    # Which states an action may run from, and where it lands.
    _SA_ACTION_STATE = {
        'accept': (('offered',), 'accepted'),
        'pickup': (('accepted',), 'picked'),
        'dispatch': (('picked',), 'dispatched'),
        'start_delivery': (('dispatched',), 'out_for_delivery'),
        'complete': (('dispatched', 'out_for_delivery'), 'delivered'),
        # Refused at the door, nobody home, wrong address - the goods are on
        # the rider and have to get back to the shelf.
        'return_to_shop': (('picked', 'dispatched', 'out_for_delivery'),
                           'returning'),
        'confirm_return': (('returning',), 'returned'),
    }

    # Cancelling is a manager's or the customer's decision, not a rider's, so
    # it is not in `_SA_FLOW` - it comes from Odoo or from the WhatsApp cancel.
    _SA_CANCELLABLE = ('to_assign', 'offered', 'accepted', 'picked',
                       'dispatched', 'out_for_delivery')

    def sa_allowed_actions(self):
        """What this rider may do next, decided here and nowhere else."""
        self.ensure_one()
        return list(self._SA_FLOW.get(self.sa_delivery_state or 'none', []))

    _SA_TRACK_STATES = ('accepted', 'picked', 'dispatched', 'out_for_delivery')

    def sa_tracking_enabled(self):
        """The rider's position is wanted from the moment they accept until
        the parcel is delivered (3 Oct 2026: the tracking page is live for
        all of that, so the feed has to be too)."""
        self.ensure_one()
        return self.sa_delivery_state in self._SA_TRACK_STATES

    def sa_live_position(self):
        """Where the rider is, for the map: the job's own last fix, else the
        rider's last fix if it is recent. {} when unknown or not live."""
        self.ensure_one()
        if self.sa_delivery_state not in self._SA_TRACK_STATES:
            return {}
        if self.sa_rider_lat and self.sa_rider_lng:
            return {'lat': self.sa_rider_lat, 'lng': self.sa_rider_lng,
                    'fix_on': self.sa_rider_fix_on, 'source': 'job'}
        rider = self.sa_delivery_partner_id.sudo()
        if rider and rider.last_lat and rider.last_lng and rider.last_fix_on:
            age = (fields.Datetime.now() - rider.last_fix_on).total_seconds()
            if age <= 1800:
                return {'lat': rider.last_lat, 'lng': rider.last_lng,
                        'fix_on': rider.last_fix_on, 'source': 'rider'}
        return {}

    def action_sa_open_live_tracking(self):
        """Button: this order's live tracking page (map + timeline)."""
        self.ensure_one()
        self._sa_ensure_identity()
        token = self.sudo().sa_track_token
        if not token:
            raise UserError(_("There is no tracking page for %s yet.", self.name))
        # relative: the staff's browser is already on this server and database
        return {'type': 'ir.actions.act_url',
                'url': '/wa/track/%s?token=%s' % (self.id, token), 'target': 'new'}

    def sa_set_state(self, state):
        """Move the job on, and validate the picking once it is delivered."""
        self.ensure_one()
        if state not in dict(self._fields['sa_delivery_state'].selection):
            return False
        values = {'sa_delivery_state': state}
        stamp = self._SA_STAMP.get(state)
        if stamp and not self[stamp]:
            values[stamp] = fields.Datetime.now()
        self.write(values)
        self._sa_notify_customer(state)

        # Issued when the rider sets off, not when the job was created: a code
        # sitting in a customer's chat since breakfast is a code they have
        # already lost by the time somebody knocks.
        # (The customer's code is sent by "Reached Customer Location", not
        # here - owner's flow, 1 Oct 2026.)

        # The parcel is coming back: no code should still work, and the goods
        # only return to the shelf when the shop says they are on it.
        if state == 'returning':
            self._sa_void_codes()
        if state == 'returned':
            if self.state not in ('done', 'cancel'):
                self.action_cancel()
            if not self.sa_returned_on:
                self.sa_returned_on = fields.Datetime.now()

        if state == 'delivered' and self.state not in ('done', 'cancel'):
            # The stock has actually left the building, so Odoo should say so.
            # Odoo will not validate a transfer with nothing on it - "you're
            # not moving invisible goods around are you?" - and a rider who
            # says delivered has moved the whole line, so fill the quantities
            # in rather than leaving the picking stuck at `confirmed`.
            for move in self.move_ids.filtered(
                    lambda m: m.state not in ('done', 'cancel')):
                move.quantity = move.product_uom_qty
                if 'picked' in move._fields:
                    move.picked = True
            try:
                done = self.with_context(
                    skip_backorder=True,
                    picking_ids_not_to_backorder=self.ids)
                result = done.button_validate()
                # `button_validate` hands back a wizard action rather than
                # validating whenever `_pre_action_done_hook` wants a person to
                # confirm something - a backorder, a partial quantity. There is
                # nobody to ask: the rider has already put the parcel in the
                # customer's hands, and the whole line went with them. So the
                # transfer is completed directly when the button declines to.
                if isinstance(result, dict) or done.state != 'done':
                    done.with_context(cancel_backorder=True)._action_done()
                    _logger.info("Delivery: %s validated directly - "
                                 "button_validate wanted a wizard",
                                 self.sa_ref_code)
            except Exception as err:  # noqa: BLE001
                _logger.warning("Delivery: %s marked delivered but the "
                                "picking would not validate: %s",
                                self.sa_ref_code, err)
                self.sa_last_error = str(err)[:250]
        return True

    # ------------------------------------------------------------------
    # Cancel, return, refund
    # ------------------------------------------------------------------
    def sa_action_cancel(self, reason=''):
        """Stop a delivery that has not been handed over.

        Where the parcel is decides what happens. Still on the shelf: the
        picking is cancelled outright. Already with the rider: it cannot
        vanish because a manager pressed a button, so it goes to `returning`
        and somebody has to bring it back.
        """
        for picking in self:
            if picking.sa_delivery_state not in picking._SA_CANCELLABLE:
                continue
            with_rider = picking.sa_delivery_state in (
                'picked', 'dispatched', 'out_for_delivery')
            picking.write({
                'sa_delivery_state': 'returning' if with_rider else 'cancelled',
                'sa_cancel_reason': (reason or '')[:250],
                'sa_cancelled_on': fields.Datetime.now(),
            })
            picking._sa_void_codes()

            if with_rider:
                picking._sa_tell_rider(_(
                    "❌ *Delivery #%(ref)s is cancelled.*\n\n"
                    "Please bring the parcel back to %(shop)s.",
                    ref=picking.sa_ref_code or '-',
                    shop=picking.sa_shop_id.name or _("the shop")))
            else:
                if picking.state not in ('done', 'cancel'):
                    picking.action_cancel()
                picking._sa_tell_rider(_(
                    "❌ Delivery *#%(ref)s* is cancelled - no need to "
                    "collect it.", ref=picking.sa_ref_code or '-'))

            picking._sa_tell_customer(_(
                "❌ Your delivery has been cancelled.\n\n%(why)s"
                "Someone will be in touch.",
                why=('%s\n\n' % reason) if reason else ''), unique=True)
            _logger.info("Delivery: job %s cancelled (%s) - %s",
                         picking.sa_ref_code, picking.sa_delivery_state,
                         reason or 'no reason given')
        return True

    def sa_action_confirm_return(self):
        """The shop has the goods back on the shelf."""
        for picking in self:
            if picking.sa_delivery_state != 'returning':
                continue
            picking.write({'sa_delivery_state': 'returned',
                           'sa_returned_on': fields.Datetime.now()})
            # Never validated, so the stock never left as far as Odoo is
            # concerned. Cancelling the picking is what puts it back.
            if picking.state not in ('done', 'cancel'):
                picking.action_cancel()
            _logger.info("Delivery: job %s is back at %s",
                         picking.sa_ref_code,
                         picking.sa_shop_id.name or 'the shop')
        return True

    def sa_action_return_delivered(self):
        """A customer sending back something already delivered.

        Different from a failed delivery. There the parcel never left as far
        as Odoo is concerned and cancelling the picking is the whole story;
        here the stock moved, so it has to move back — and Odoo already has
        the flow for that. `stock.return.picking` is the same wizard the
        Return button on a done transfer opens, so the incoming picking, its
        moves and its valuation are exactly what a warehouse clerk would get.
        """
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_(
                "This delivery has not gone out yet. Cancel it instead."))
        wizard = self.env['stock.return.picking'].with_context(
            active_id=self.id, active_model='stock.picking').sudo().create({
                'picking_id': self.id})
        wizard.action_create_returns_all()
        back = self.sudo().search(
            [('return_id', '=', self.id)], order='id desc', limit=1) \
            if 'return_id' in self._fields else self.env['stock.picking']
        self.sudo().write({'sa_delivery_state': 'returned',
                           'sa_returned_on': fields.Datetime.now()})
        self._sa_tell_customer(_(
            "\U0001F501 Your return has been booked. We will confirm once the "
            "goods are back with us."), unique=True)
        _logger.info("Delivery: return booked for delivered job %s",
                     self.sa_ref_code)
        return back

    def sa_action_refund(self):
        """Credit what the customer actually paid.

        Only money that was taken is given back: an unpaid or cash-on-delivery
        order has nothing to refund, and raising a credit note for it would
        put a hole in the accounts for a parcel that never left.
        """
        moves = self.env['account.move']
        for picking in self:
            order = picking.sale_id
            invoices = order.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
            ) if order else self.env['account.move']
            paid = invoices.filtered(
                lambda m: m.payment_state in ('paid', 'in_payment', 'partial'))
            if not paid:
                _logger.info("Delivery: nothing to refund on %s - no paid "
                             "invoice", picking.sa_ref_code)
                continue
            refund = paid._reverse_moves(default_values_list=[{
                'invoice_origin': order.name,
                'ref': _("Refund for %(ref)s", ref=picking.sa_ref_code or
                         order.name),
            }] * len(paid))
            moves |= refund
            picking.sa_refund_move_id = refund[:1].id
            picking._sa_tell_customer(_(
                "\U0001F4B8 A refund of *%(amount).3f %(cur)s* has been "
                "raised for your order.\n\nIt will reach you through the way "
                "you paid.",
                amount=sum(paid.mapped('amount_total')),
                cur=order.currency_id.name or ''), unique=True)
            _logger.info("Delivery: refund %s raised for job %s",
                         refund[:1].name, picking.sa_ref_code)
        return moves

    def _sa_void_codes(self):
        """No live OTP survives a cancellation."""
        self.ensure_one()
        self.env['sa.delivery.otp'].sudo().search([
            ('picking_id', '=', self.id), ('used_on', '=', False),
        ]).write({'active': False})

    def _sa_tell_rider(self, body):
        """Message whoever is carrying this job."""
        self.ensure_one()
        rider = self.sa_delivery_partner_id
        session = self._sa_session()
        if not rider or not rider.phone or not session:
            return False
        try:
            session.send_message(rider.phone, body)
            return True
        except Exception as err:  # noqa: BLE001
            _logger.warning("Delivery: could not tell %s about job %s: %s",
                            rider.phone, self.sa_ref_code, err)
            return False

    # ------------------------------------------------------------------
    # One-time codes
    # ------------------------------------------------------------------
    def sa_issue_pickup_otp(self, to='shop'):
        """Issue the pickup code. `to`: 'shop' (the app flow - the counter
        reads it to the rider), 'rider' (the counter flow - the rider shows
        it and the shop types it), or 'none' (shown on screen only).

        Returns (sent_ok, message, code). The code is always issued even
        when nothing could be sent, so the wizard can show it.
        """
        self.ensure_one()
        shop = self.sa_shop_id
        rider = self.sa_delivery_partner_id
        code = self.env['sa.delivery.otp'].sudo()._issue(self, 'pickup')
        if to == 'none':
            return True, _("Code made, not sent."), code
        if to == 'rider':
            phone = (rider.phone or '').strip() if rider else ''
            if not phone:
                return False, _("No rider with a WhatsApp number is on this "
                                "job yet - assign one, or pass the code on "
                                "yourself."), code
            body = _("\U0001F511 *Your pickup code: %(code)s*\n\n"
                     "Delivery *#%(ref)s* for %(customer)s.\n"
                     "Show this code at the counter when you collect the "
                     "parcel. Valid 15 minutes.",
                     code=code, ref=self.sa_ref_code or '-',
                     customer=self.partner_id.name or '-')
            who = rider.name
        else:
            phone = (shop.phone or '').strip() if shop else ''
            if not phone:
                return False, _("This shop has no WhatsApp number, so a pickup "
                                "code cannot be sent."), code
            body = _("\U0001F511 *Pickup code %(code)s*\n\n"
                     "Delivery *#%(ref)s* for %(customer)s.\n"
                     "Rider: *%(rider)s*\n\n"
                     "Read this code out only when you hand the parcel over.",
                     code=code, ref=self.sa_ref_code or '-',
                     customer=self.partner_id.name or '-',
                     rider=rider.name or '-')
            who = shop.name
        session = self._sa_session()
        if not session:
            return False, _("No WhatsApp session is connected."), code
        try:
            session.send_message(phone, body)
        except Exception as err:  # noqa: BLE001
            _logger.warning("Delivery: pickup code for %s not sent: %s",
                            self.sa_ref_code, err)
            return False, _("Could not send the pickup code."), code
        self.env['sa.delivery.otp'].sudo().search(
            [('picking_id', '=', self.id), ('kind', '=', 'pickup'),
             ('active', '=', True)], limit=1).sent_to = phone
        return True, _("A pickup code has been sent to %(who)s.", who=who), code

    def sa_issue_delivery_otp(self, send=True):
        """Send the completion code to the customer, at the last moment."""
        self.ensure_one()
        code = self.env['sa.delivery.otp'].sudo()._issue(self, 'delivery')
        body = _("\U0001F4E6 Your order is arriving.\n\n"
                 "Give this code to the rider *after* you have the parcel:\n\n"
                 "*%(code)s*\n\n"
                 "Do not share it before you receive your order.", code=code)
        ok = self._sa_tell_customer(body, unique=True) if send else True
        self.sa_last_delivery_code = code
        if ok and send:
            phone = (self.partner_id.phone or '').strip()
            self.env['sa.delivery.otp'].sudo().search(
                [('picking_id', '=', self.id), ('kind', '=', 'delivery'),
                 ('active', '=', True)], limit=1).sent_to = phone
        return ok, (_("A code has been sent to the customer.") if ok and send
                    else _("Code made, not sent.") if not send
                    else _("Could not send the code to the customer.")), code

    def sa_verify_otp(self, kind, code):
        """(ok, message) - the only way an OTP is ever checked."""
        self.ensure_one()
        return self.env['sa.delivery.otp'].sudo()._verify(self, kind, code)

    def _sa_tell_customer(self, body, unique=False):
        """Message the customer on the number the order came from."""
        self.ensure_one()
        phone = (self.partner_id.phone or '').strip()
        order = self.sale_id
        if not phone and order and order.wa_conversation_id:
            phone = order.wa_conversation_id.phone or ''
        session = self._sa_session()
        if not phone or not session:
            return False
        # An OTP must never be swallowed as a duplicate: each one is different
        # from the last, but the guard keys on the opening words, which are
        # not. `unique` opts out of the dedupe for exactly that case.
        if not unique and not self.env['sa.outbox.guard'].sudo().claim(
                'track|%s|%s' % (self.id, body[:40]), 900):
            return False
        try:
            # the gateway answers False when it refused the message: say so,
            # the rider's "resend" relies on it (6 Oct 2026)
            return session.send_message(phone, body) is not False
        except Exception as err:  # noqa: BLE001 - the job matters more
            _logger.warning("Delivery: could not tell %s about job %s: %s",
                            phone, self.sa_ref_code, err)
            return False

    def sa_track_link_once(self):
        """The tracking URL the first time it is asked for, '' after that.

        The customer gets one link and the page keeps itself current, so a
        second message carrying the same URL is only noise - and on WhatsApp
        a repeated link is what makes a thread look like spam.
        """
        self.ensure_one()
        if not self.sa_track_url:
            return ''
        if self.env['sa.outbox.guard'].sudo().claim(
                'tracklink|%s' % self.id, 60 * 60 * 24 * 14):
            return self.sa_track_url
        return ''

    def _sa_notify_customer(self, state):
        """What the customer hears at each step.

        Only between accepted and delivered, and only ever this job - the
        customer follows their parcel, not the rider's day.
        """
        self.ensure_one()
        if self.env.context.get('sa_quiet'):
            return False
        name = self.sa_delivery_partner_id.name or _("Our rider")
        if state == 'returning':
            return self._sa_tell_customer(_(
                "\U0001F501 Your order could not be delivered and is going "
                "back to %(shop)s. Someone will be in touch.",
                shop=self.sa_shop_id.name or _("our shop")), unique=True)
        if state in ('returned', 'cancelled'):
            return False        # said once, by the cancel/return step itself
        link = self.sa_track_link_once()
        tail = _("\n\nFollow it live here:\n%(url)s", url=link) if link else ''
        if state == 'accepted':
            body = _("\U0001F6F5 *%(rider)s* is bringing your order.%(tail)s",
                     rider=name, tail=tail)
        elif state == 'picked':
            body = _("\U0001F4E6 Your order has been collected from "
                     "%(shop)s.%(tail)s",
                     shop=self.sa_shop_id.name or _("our shop"), tail=tail)
        elif state == 'dispatched':
            body = _("\U0001F69A *%(rider)s* has collected your order *#%(ref)s* "
                     "and is on the way.%(tail)s", rider=name,
                     ref=self.sa_ref_code or '', tail=tail)
        elif state == 'out_for_delivery':
            body = _("\U0001F6F5 *%(rider)s* is near your location with order "
                     "*#%(ref)s*. Please be ready to receive it.%(tail)s",
                     rider=name, ref=self.sa_ref_code or '', tail=tail)
        elif state == 'delivered':
            body = _("\u2705 Delivered. Thank you! \U0001F64F")
        else:
            return False
        return self._sa_tell_customer(body)

    def action_sa_accepted(self):
        for p in self:
            p.sa_set_state('accepted')
        return True

    # ---- the counter's buttons (owner, 30 Sep / 1 Oct 2026) ----
    _SA_DISPATCH_FROM = ('awaiting_shop', 'preparing', 'ready', 'to_assign',
                         'offered', 'accepted', 'picked')
    _SA_PICKUP_FROM = ('accepted', 'ready', 'offered')

    sa_stage_text = fields.Char(compute='_compute_sa_stage_text')
    sa_pickup_code_shown = fields.Char(
        'Pickup Code', copy=False,
        help="The current 6-digit pickup code, shown here (and sent to the "
             "rider) until the job is dispatched. Press Generate Pickup Code "
             "to make one; a new one replaces the old.")
    sa_is_paid = fields.Boolean(compute='_compute_sa_pay_text', string='Order Paid')
    sa_pay_text = fields.Char(compute='_compute_sa_pay_text', string='Payment')

    @api.depends('sale_id', 'sale_id.invoice_ids.payment_state',
                 'sale_id.transaction_ids.state', 'sa_cod_amount')
    def _compute_sa_pay_text(self):
        for p in self:
            order = p.sale_id
            paid = False
            if order:
                inv = order.invoice_ids.filtered(
                    lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
                if inv:
                    paid = all(m.payment_state in ('paid', 'in_payment') for m in inv)
                elif order.transaction_ids.filtered(lambda t: t.state == 'done'):
                    paid = True
            p.sa_is_paid = paid
            if not order:
                p.sa_pay_text = ''
            elif paid:
                p.sa_pay_text = _("Paid")
            else:
                p.sa_pay_text = _("Unpaid - collect %(cur)s %(amt).2f",
                                  cur=order.currency_id.symbol or '',
                                  amt=order._sa_amount_to_collect())

    def sa_refresh_cod(self):
        """Re-read what the rider must collect (a payment after the job
        was raised used to leave the old amount on the card)."""
        for p in self:
            if p.sale_id and p.sa_delivery_state not in ('none', False):
                amount = p.sale_id._sa_amount_to_collect()
                if abs((p.sa_cod_amount or 0.0) - amount) > 0.004:
                    p.write({'sa_cod_amount': amount})
        return True

    def sa_action_generate_pickup_code(self):
        """Button on the job form: make the pickup code, show it here, send
        it to the rider when the job has one."""
        self.ensure_one()
        if self.sa_delivery_state not in self._SA_DISPATCH_FROM:
            raise UserError(_("Job #%s is already dispatched.", self.sa_ref_code))
        ok, msg, code = self.sa_issue_pickup_otp(
            to='rider' if self.sa_delivery_partner_id else 'none')
        self.write({'sa_pickup_code_shown': code})
        self.message_post(body=_("Pickup code generated by %(user)s - %(msg)s",
                                 user=self.env.user.name, msg=msg))
        return True

    @api.depends('sa_delivery_state', 'sa_delivery_partner_id',
                 'sa_arrived_customer_on')
    def _compute_sa_stage_text(self):
        for p in self:
            rider = p.sa_delivery_partner_id.name or _("the rider")
            st = p.sa_delivery_state
            if st in ('none', False):
                p.sa_stage_text = ''
            elif st in ('ready', 'to_assign') and not p.sa_delivery_partner_id:
                p.sa_stage_text = _("Packed, no rider yet - next: press Call a Rider")
            elif st == 'offered':
                left = p.sa_offer_seconds_left if 'sa_offer_seconds_left' in p._fields else 0
                p.sa_stage_text = _("Offered to %(rider)s - waiting for the answer%(left)s",
                                    rider=rider, left=(_(" (%s s left)") % left) if left else '')
            elif st in p._SA_DISPATCH_FROM:
                p.sa_stage_text = _("Waiting at the shop - next: press Dispatch "
                                    "and type the rider's pickup code")
            elif st == 'dispatched':
                p.sa_stage_text = _("Collected by rider %s - next: press Rider "
                                    "Near Customer when close", rider)
            elif st == 'out_for_delivery' and not p.sa_arrived_customer_on:
                p.sa_stage_text = _("Rider %s near the customer - next: press "
                                    "Reached Customer Location", rider)
            elif st == 'out_for_delivery':
                p.sa_stage_text = _("Reached at %s - the customer has the code; "
                                    "next: press Delivered and type it",
                                    fields.Datetime.context_timestamp(
                                        p, p.sa_arrived_customer_on).strftime('%H:%M'))
            elif st == 'delivered':
                p.sa_stage_text = _("Delivered by %s", rider)
            else:
                p.sa_stage_text = dict(p._fields['sa_delivery_state'].selection).get(st, st)

    def sa_action_dispatch_with_otp(self, code, rider_id=None):
        """Dispatch: the rider (set here if missing) shows the pickup code,
        the shop types it, the parcel leaves -> Collected by Rider."""
        self.ensure_one()
        if self.sa_delivery_state not in self._SA_DISPATCH_FROM:
            raise UserError(_("Job #%(ref)s is %(state)s - it cannot be dispatched.",
                              ref=self.sa_ref_code, state=self.sa_delivery_state))
        if rider_id:
            rider = self.env['sa.delivery.partner'].sudo().browse(int(rider_id))
            if rider.exists():
                self.write({'sa_delivery_partner_id': rider.id})
        if not self.sa_delivery_partner_id:
            raise UserError(_("Pick the rider who is collecting job #%s.", self.sa_ref_code))
        ok, msg = self.sa_verify_otp('pickup', (code or '').strip())
        if not ok:
            raise UserError(msg or _("Wrong code."))
        for st in ('accepted', 'picked', 'dispatched'):
            if self.sa_delivery_state != st:
                # One customer message for the whole handover, at `dispatched`.
                quiet = self.with_context(sa_quiet=(st != 'dispatched'))
                quiet.sa_set_state(st)
        self.write({'sa_pickup_code_shown': False})       # used, gone
        self.message_post(body=_("Collected by rider %(rider)s - pickup code verified by %(user)s.",
                                 rider=self.sa_delivery_partner_id.name, user=self.env.user.name))
        return True

    def sa_action_rider_near(self):
        """The customer is told the rider is close - be ready."""
        self.ensure_one()
        if self.sa_delivery_state != 'dispatched':
            raise UserError(_("Job #%s is not with the rider yet.", self.sa_ref_code))
        self.sa_set_state('out_for_delivery')      # sends the "near" message
        return True

    def sa_action_reached_customer(self):
        """At the door: the customer gets the 6-digit code on WhatsApp."""
        self.ensure_one()
        if self.sa_delivery_state == 'dispatched':
            self.sa_set_state('out_for_delivery')
        if self.sa_delivery_state != 'out_for_delivery':
            raise UserError(_("Job #%s is not out with the rider.", self.sa_ref_code))
        self.write({'sa_arrived_customer_on': fields.Datetime.now()})
        ok, msg, code = self.sa_issue_delivery_otp()
        self.message_post(body=_("Reached the customer - delivery code %s.",
                                 _("sent to the customer") if ok else _("NOT sent: %s", msg)))
        if not ok:
            raise UserError(msg)
        return True

    def sa_action_pickup_with_otp(self, code):
        """Kept for the rider page / API: same as Dispatch with the job's rider."""
        return self.sa_action_dispatch_with_otp(code)

    _SA_DELIVER_FROM = ('dispatched', 'out_for_delivery')
    sa_declined_partner_ids = fields.Many2many(
        'sa.delivery.partner', 'sa_picking_declined_rider_rel', 'picking_id',
        'partner_id', string='Declined By', copy=False,
        help="Riders who refused this job from the app; it is not offered "
             "to them again.")

    def sa_action_decline(self, rider, reason=''):
        """The offered rider refuses (rider app). Back to To Dispatch, then
        offered to the next on-duty rider who has not declined it; nobody
        left = it waits under To Dispatch for the counter."""
        self.ensure_one()
        if self.sa_delivery_state not in ('offered', 'accepted'):
            raise UserError(_("Job #%(ref)s is %(state)s - it cannot be declined now.",
                              ref=self.sa_ref_code, state=self.sa_delivery_state))
        if rider and self.sa_delivery_partner_id and self.sa_delivery_partner_id != rider:
            raise UserError(_("Job #%(ref)s is not offered to %(name)s.",
                              ref=self.sa_ref_code, name=rider.name))
        who = rider.name if rider else _("the rider")
        self.message_post(body=_("Declined by %(rider)s - %(reason)s",
                                 rider=who, reason=reason or _("no reason given")))
        vals = {'sa_delivery_state': 'to_assign', 'sa_delivery_partner_id': False,
                'sa_accepted_on': False, 'sa_offer_expires_on': False,
                'sa_last_error': _("Declined by %s", who)}
        if rider:
            vals['sa_declined_partner_ids'] = [(4, rider.id)]
        self.write(vals)
        self._sa_call_log_add(_("%(who)s declined - %(why)s", who=who, why=reason or _("no reason given")))
        # one algorithm for every re-offer (Call a Rider, 3 Oct 2026)
        nxt = self.with_context(sa_cascade=True).sa_action_call_rider()
        _logger.info("Delivery: job %s declined by %s -> %s", self.sa_ref_code, who,
                     nxt.name if nxt else 'nobody')
        return True

    _SA_FAIL_FROM = ('picked', 'dispatched', 'out_for_delivery')

    def sa_action_pickup_with_otp(self, code):
        """Handover at the counter: the pickup code checked, then the job is
        picked AND dispatched in one go (the parcel leaves with the rider)."""
        self.ensure_one()
        if self.sa_delivery_state not in self._SA_PICKUP_FROM:
            raise UserError(_("Job #%(ref)s is %(state)s - pickup is not the next step.",
                              ref=self.sa_ref_code, state=self.sa_delivery_state))
        if not self.sa_delivery_partner_id:
            raise UserError(_("Assign a rider to job #%s first.", self.sa_ref_code))
        ok, msg = self.sa_verify_otp('pickup', (code or '').strip())
        if not ok:
            raise UserError(msg or _("Wrong code."))
        if self.sa_delivery_state != 'accepted':
            self.sa_set_state('accepted')
        self.sa_set_state('picked')
        self.sa_set_state('dispatched')
        self.message_post(body=_("Picked up at the counter - pickup code verified by %s.",
                                 self.env.user.name))
        return True

    def sa_action_start_delivery(self):
        self.ensure_one()
        if self.sa_delivery_state != 'dispatched':
            raise UserError(_("Job #%s is not dispatched yet.", self.sa_ref_code))
        self.sa_set_state('out_for_delivery')        # issues the customer code
        return True

    def sa_action_deliver_with_otp(self, code):
        """The customer's code checked, then delivered: stock validated, the
        order closed."""
        self.ensure_one()
        if self.sa_delivery_state not in self._SA_DELIVER_FROM:
            raise UserError(_("Job #%(ref)s is %(state)s - it is not out for delivery.",
                              ref=self.sa_ref_code, state=self.sa_delivery_state))
        ok, msg = self.sa_verify_otp('delivery', (code or '').strip())
        if not ok:
            raise UserError(msg or _("Wrong code."))
        self.sa_set_state('delivered')
        self.message_post(body=_("Delivered - customer code verified by %s.",
                                 self.env.user.name))
        return True

    def sa_action_fail(self, reason):
        """The parcel could not be delivered. The job stays open for a
        retry (Send Job Again) or a return."""
        self.ensure_one()
        if self.sa_delivery_state not in self._SA_FAIL_FROM:
            raise UserError(_("Job #%(ref)s is %(state)s - nothing to fail.",
                              ref=self.sa_ref_code, state=self.sa_delivery_state))
        self._sa_void_codes()
        self.write({'sa_delivery_state': 'failed', 'sa_cancel_reason': reason})
        self.message_post(body=_("Delivery failed: %s", reason))
        self._sa_tell_customer(_("\u26A0 We could not deliver your order *#%(ref)s* "
                                 "(%(reason)s). We will contact you to arrange it.",
                                 ref=self.sa_ref_code, reason=reason))
        self._sa_tell_rider(_("Job #%(ref)s marked as failed: %(reason)s. Please "
                              "bring the parcel back to the shop.",
                              ref=self.sa_ref_code, reason=reason))
        _logger.info("Delivery: job %s failed - %s", self.sa_ref_code, reason)
        return True

    def action_sa_open_otp_entry(self):
        """The Dispatch / Delivered buttons: open the code dialog."""
        self.ensure_one()
        kind = self.env.context.get('sa_otp_kind') or (
            'delivery' if self.sa_delivery_state in self._SA_DELIVER_FROM else 'pickup')
        return {'type': 'ir.actions.act_window', 'res_model': 'sa.delivery.otp.entry',
                'view_mode': 'form', 'target': 'new',
                'name': _('Dispatch - enter the pickup code') if kind == 'pickup' else _('Delivered - enter the customer code'),
                'context': {'default_picking_id': self.id, 'default_kind': kind,
                            'default_rider_id': self.sa_delivery_partner_id.id}}

    def action_sa_open_fail(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'sa.delivery.fail.wizard',
                'view_mode': 'form', 'target': 'new', 'name': _('Delivery failed'),
                'context': {'default_picking_id': self.id}}

    def _sa_force_guard(self, what):
        if not self.env.user.has_group('sales_automation_delivery.group_sa_delivery_manager'):
            raise UserError(_("Only a delivery manager may mark a job %s without the code. "
                              "Use the Pickup / Delivered buttons with the OTP.", what))

    def action_sa_picked(self):
        self._sa_force_guard(_("picked up"))
        for p in self:
            p.sa_set_state('picked')
            p.message_post(body=_("Forced to picked up WITHOUT the pickup code by %s.",
                                  self.env.user.name))
        return True

    def action_sa_delivered(self):
        self._sa_force_guard(_("delivered"))
        for p in self:
            p.sa_set_state('delivered')
            p.message_post(body=_("Forced to delivered WITHOUT the customer code by %s.",
                                  self.env.user.name))
        return True

    def action_sa_open_job(self):
        self.ensure_one()
        self._sa_ensure_identity()
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': self.sa_job_url}
