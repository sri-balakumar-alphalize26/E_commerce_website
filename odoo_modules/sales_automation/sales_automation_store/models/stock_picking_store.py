# -*- coding: utf-8 -*-
"""The shop's part of a delivery: accept it, pack it, call the rider."""

import logging
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# A date picked at the counter means "by the end of that day's trading", not
# midnight: a promise that only expires at 23:59 is never late in time for
# anybody to do anything about it.
_SA_PROMISE_HOUR = 18


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # ------------------------------------------------------------------
    # Two states that were missing
    # ------------------------------------------------------------------
    # A paid order used to page a rider straight away, so a rider could reach
    # the counter before anyone had taken the goods off the shelf. These sit
    # between the two: `awaiting_shop` is ringing on the shop's screen,
    # `preparing` is somebody packing it. The rider is called at `ready`,
    # which is the moment there is actually something to collect.
    sa_delivery_state = fields.Selection(
        selection_add=[
            ('awaiting_shop', 'Waiting for the Shop'),
            ('preparing', 'Being Packed'),
            ('ready', 'Ready for Pickup'),
        ],
        ondelete={'awaiting_shop': 'set default',
                  'preparing': 'set default',
                  'ready': 'set default'},
    )

    sa_shop_seen_on = fields.Datetime(
        'Accepted by the Shop', readonly=True, copy=False,
        help="When somebody at the counter took the order on. The alarm stops "
             "at this moment.")
    sa_shop_ready_on = fields.Datetime(
        'Packed', readonly=True, copy=False,
        help="When the shop said it was packed. The rider is called here, "
             "not when the customer paid.")
    sa_shop_user_id = fields.Many2one(
        'res.users', 'Packed By', readonly=True, copy=False)

    # ---- Nothing on any shelf: bought in for this order ----
    # A flag, not a new delivery state. `sa_delivery_state` already carries
    # fifteen values across two modules and a dozen places enumerate it
    # literally; adding a sixteenth means auditing every one of them again.
    sa_supply_waiting = fields.Boolean(
        'Waiting for Supplier Stock', index=True, copy=False,
        help="Accepted with nothing on the shelf: the goods are being bought "
             "in for this order. Cleared when somebody marks them arrived.")
    sa_supply_partner_id = fields.Many2one(
        'res.partner', 'Bought From', copy=False)
    sa_supply_cost = fields.Monetary(
        'We Pay', currency_field='sa_currency_id', copy=False,
        help="What this costs us from the supplier. The customer's price is "
             "already agreed and is not touched by this.")
    sa_supply_vendor_ids = fields.Many2many(
        'res.partner', 'sa_supply_asked_rel', 'picking_id', 'partner_id',
        string='Suppliers Asked', copy=False)
    sa_supply_asked_on = fields.Datetime(
        'Suppliers Asked On', readonly=True, copy=False)
    sa_supply_arrived_on = fields.Datetime(
        'Goods Arrived On', readonly=True, copy=False)
    sa_supply_reminded_on = fields.Datetime(
        'Last Morning Reminder', readonly=True, copy=False)

    # How long it has been ringing, so the screen can show the oldest first
    # and a supervisor can see what is being ignored.
    # The pickup code, kept in the clear for exactly one reader: the shop
    # screen, which shows it to the person handing the parcel over. The hash
    # in sa.delivery.otp is what is *checked*; this is what is *read out*.
    sa_last_pickup_code = fields.Char(
        'Pickup Code', copy=False, readonly=True, groups='base.group_system')

    # The delivery module lists the states a job may be cancelled from; the
    # three counter states are added so the shop can stop an order it has
    # not packed yet. The parent's own rule still decides what happens.
    _SA_CANCELLABLE = ('to_assign', 'offered', 'accepted', 'picked',
                       'dispatched', 'out_for_delivery',
                       'awaiting_shop', 'preparing', 'ready')

    sa_waiting_minutes = fields.Integer(
        'Waiting (min)', compute='_compute_sa_waiting_minutes')

    @api.depends('sa_delivery_state', 'sa_offered_on', 'sa_shop_seen_on')
    def _compute_sa_waiting_minutes(self):
        now = fields.Datetime.now()
        for picking in self:
            since = picking.sa_offered_on
            if picking.sa_delivery_state == 'preparing':
                since = picking.sa_shop_seen_on or since
            picking.sa_waiting_minutes = (
                int((now - since).total_seconds() // 60) if since else 0)

    # ------------------------------------------------------------------
    # What the shop may do, and from where
    # ------------------------------------------------------------------
    def sa_allowed_actions(self):
        """Riders get nothing to do while the shop still has the parcel."""
        self.ensure_one()
        if self.sa_delivery_state in ('awaiting_shop', 'preparing', 'ready'):
            return []
        return super().sa_allowed_actions()

    def sa_action_offer(self):
        """Hold the job at the counter instead of paging the rider.

        Intercepted here rather than after the fact because the parent both
        sets `offered` *and* sends the rider a WhatsApp message. Reversing the
        state afterwards left the rider already told to come, and left an
        `sa.outbox.guard` claim behind that silently swallowed the real offer
        when the shop finally pressed Packed - the job sat at `ready` for ever.

        `sa_shop_done` is how `sa_shop_ready` gets through.
        """
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        if self.env.context.get('sa_shop_done') or not settings.shop_confirms:
            return super().sa_action_offer()

        hold = self.filtered(
            lambda p: p.sa_delivery_state in ('none', False, 'to_assign')
            and not p.sa_shop_ready_on)
        if hold:
            hold.write({'sa_delivery_state': 'awaiting_shop'})
            hold._sa_store_notify()
            _logger.info("Store: holding %s at the shop",
                         ', '.join(hold.mapped('sa_ref_code')))
        rest = self - hold
        return super(StockPicking, rest).sa_action_offer() if rest else True

    # ------------------------------------------------------------------
    # The two buttons
    # ------------------------------------------------------------------
    def sa_shop_accept(self):
        """Somebody at the counter has taken this order on.

        The alarm is keyed on `awaiting_shop`, so this is what silences it -
        deliberately a separate step from packing, because acknowledging an
        order takes a second and packing does not.
        """
        for picking in self:
            if picking.sa_delivery_state != 'awaiting_shop':
                continue
            picking.write({
                'sa_delivery_state': 'preparing',
                'sa_shop_seen_on': fields.Datetime.now(),
                'sa_shop_user_id': self.env.user.id,
            })
            _logger.info("Store: %s accepted by %s", picking.sa_ref_code,
                         self.env.user.name)
            link = picking.sa_track_link_once()
            picking._sa_tell_customer(_(
                "✅ Order *#%(ref)s* approved.\n\n%(shop)s is packing it "
                "now. We will message you the moment it leaves.%(tail)s",
                ref=picking.sa_ref_code or '-',
                shop=picking.sa_shop_id.name or _("Our shop"),
                tail=(_("\n\nTrack it live here - this one link keeps "
                        "itself up to date:\n%(url)s", url=link)
                      if link else '')))
        self._sa_store_notify()
        return True

    def sa_shop_ready(self):
        """Packed. This is what calls the rider."""
        for picking in self:
            if picking.sa_delivery_state not in ('awaiting_shop', 'preparing'):
                continue
            picking.write({
                'sa_delivery_state': 'ready',
                'sa_shop_ready_on': fields.Datetime.now(),
                'sa_shop_user_id': (picking.sa_shop_user_id.id
                                    or self.env.user.id),
            })
            link = picking.sa_track_link_once()
            picking._sa_tell_customer(_(
                "📦 Order *#%(ref)s* is packed and ready.\n\n"
                "A rider is being called to collect it from %(shop)s.%(tail)s",
                ref=picking.sa_ref_code or '-',
                shop=picking.sa_shop_id.name or _("our shop"),
                tail=(_("\n\nTrack it here:\n%(url)s", url=link)
                      if link else '')))
            # Only now is there something to collect. Call a Rider (3 Oct
            # 2026): a rider set by hand on the job is called at once;
            # otherwise the counter presses Call a Rider - unless the setting
            # calls the nearest free rider by itself.
            settings = self.env['sa.delivery.settings'].sudo().get_settings()
            try:
                if picking.sa_delivery_partner_id:
                    picking.sa_action_call_rider(rider_id=picking.sa_delivery_partner_id.id)
                elif settings.auto_call_rider_on_packed:
                    picking.sa_action_call_rider()
                else:
                    _logger.info("Store: %s is packed - waiting for Call a Rider",
                                 picking.sa_ref_code)
            except UserError as err:
                picking.write({'sa_last_error': str(err.args[0] if err.args else err)[:250]})
                _logger.info("Store: %s packed, rider not called: %s", picking.sa_ref_code, err)
        self._sa_store_notify()
        return True

    def sa_shop_unaccept(self):
        """Put it back in the queue - taken on by mistake, or handed over."""
        for picking in self:
            if picking.sa_delivery_state != 'preparing':
                continue
            picking.write({
                'sa_delivery_state': 'awaiting_shop',
                'sa_shop_seen_on': False,
                'sa_shop_user_id': False,
            })
        self._sa_store_notify()
        return True

    def sa_issue_pickup_otp(self, to='shop'):
        """The code goes out (shop / rider / nobody) *and* onto the shop screen.

        A shop whose WhatsApp number is the business's own - or has none -
        still has to be able to read the code to the rider. The screen is
        the counter; it is where the person with the parcel is looking.
        """
        ok, message, code = super().sa_issue_pickup_otp(to=to)
        if code:
            self.sudo().write({'sa_last_pickup_code': code})
            self._sa_store_notify()
        return ok, message, code

    def sa_set_state(self, state):
        """Any move by the rider redraws the shop's screen.

        The card for a job the rider has just collected must leave the counter
        by itself; nobody at a till is going to press refresh.
        """
        result = super().sa_set_state(state)
        if state == 'picked':
            self.sudo().write({'sa_last_pickup_code': False})
        self._sa_store_notify()
        return result

    # ------------------------------------------------------------------
    # Which company's shelf
    # ------------------------------------------------------------------
    def _sa_store_candidate(self, product, company):
        """The record of `product` that belongs to `company`.

        A product with no company is everyone's. A product owned by another
        company is not available here even if the name matches - unless this
        company keeps its own record under the same name, which is how the
        catalogues on this database are set up.
        """
        if not product.company_id or product.company_id == company:
            return product
        return self.env['product.product'].sudo().search([
            ('name', '=', product.name), ('sale_ok', '=', True),
            '|', ('company_id', '=', company.id), ('company_id', '=', False),
        ], limit=1)

    @api.model
    def sa_store_company_options(self, job_id):
        """Every company, with what it could give this order from its shelf."""
        job = self.sudo().browse(int(job_id))
        if not job.exists():
            raise UserError(_("That order is no longer there."))
        Warehouse = self.env['stock.warehouse'].sudo()
        out = []
        for company in self.env['res.company'].sudo().search([]):
            wh = Warehouse.search([('company_id', '=', company.id)], limit=1)
            if not wh:
                continue
            lines, ok = [], True
            for move in job.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                cand = self._sa_store_candidate(move.product_id, company)
                have = 0.0
                if cand:
                    have = cand.with_company(company).with_context(
                        warehouse_id=wh.id).qty_available or 0.0
                need = move.product_uom_qty
                if not cand or have < need:
                    ok = False
                lines.append({'name': move.product_id.name, 'need': need,
                              'have': have, 'found': bool(cand)})
            out.append({
                'id': company.id, 'name': company.name,
                'warehouse': wh.name, 'lines': lines, 'ok': ok,
                'current': company == job.company_id,
            })
        # The one it is already booked against first, then the ones that can.
        out.sort(key=lambda c: (not c['current'], not c['ok'], c['name']))
        return out

    def _sa_store_move_to_company(self, company):
        """Re-point the delivery at `company`'s warehouse and products.

        Reservation is released first: the moves are holding units in the
        old warehouse, and a location change while reserved leaves quants
        pointing at stock that is no longer going anywhere.
        """
        self.ensure_one()
        wh = self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', company.id)], limit=1)
        if not wh:
            raise UserError(_("%s has no warehouse.", company.name))
        if self.company_id == company and self.location_id == wh.lot_stock_id:
            return True
        self.do_unreserve()
        for move in self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            cand = self._sa_store_candidate(move.product_id, company)
            if not cand:
                raise UserError(_(
                    "%(company)s does not sell %(product)s.",
                    company=company.name, product=move.product_id.name))
            vals = {'location_id': wh.lot_stock_id.id,
                    'picking_type_id': wh.out_type_id.id,
                    'company_id': company.id,
                    'warehouse_id': wh.id}
            if cand != move.product_id:
                vals['product_id'] = cand.id
            move.write(vals)
        self.write({'picking_type_id': wh.out_type_id.id,
                    'location_id': wh.lot_stock_id.id})
        shop = self.env['sa.delivery.shop'].sudo().search(
            [('warehouse_id', '=', wh.id)], limit=1)
        if shop:
            self.sa_shop_id = shop.id
        self.action_assign()
        _logger.info("Store: %s moved to %s (%s)", self.sa_ref_code,
                     company.name, wh.name)
        return True

    # ------------------------------------------------------------------
    # Telling the screen
    # ------------------------------------------------------------------
    def _sa_store_channel(self):
        """One channel per shop, so nobody sees another shop's customers.

        With several companies on one database that is not tidiness, it is the
        difference between a storekeeper seeing their own queue and seeing
        somebody else's customer addresses.
        """
        self.ensure_one()
        return 'sa_store_%s' % (self.sa_shop_id.id or 0)

    def _sa_store_notify(self):
        """Wake every screen watching this shop.

        Pushed rather than polled: a shop screen left open all day would
        otherwise ask the server for nothing, hundreds of times an hour, and
        still show a new order a few seconds late.
        """
        bus = self.env['bus.bus']
        for shop_id in set(self.mapped('sa_shop_id').ids + [0]):
            bus._sendone('sa_store_%s' % shop_id, 'sa_store/refresh',
                         {'shop_id': shop_id})
        return True

    # ------------------------------------------------------------------
    # What the screen reads
    # ------------------------------------------------------------------
    @api.model
    def _sa_store_sos(self, job):
        if 'sa.sos.alert' not in self.env:
            return None
        alert = self.env['sa.sos.alert'].sudo().sa_open_for_job(job)
        if not alert:
            return None
        return {'id': alert.id, 'rider': alert.rider_id.name or '', 'phone': alert.rider_id.phone or '',
                'at': fields.Datetime.context_timestamp(job, alert.at).strftime('%H:%M'),
                'map_url': alert.map_url or '', 'whatsapp_sent': bool(alert.whatsapp_sent)}

    def _sa_store_live(self, job):
        """One line for the card while the parcel is on the road (6 Oct 2026):
        stop x of y, km and minutes left, how fresh the position is."""
        if job.sa_delivery_state not in ('picked', 'dispatched', 'out_for_delivery') or not job.sa_delivery_partner_id:
            return None
        try:
            d = job.sudo().sa_track_payload()
        except Exception as err:  # noqa: BLE001 - the card must still draw
            _logger.warning("Store: live line for %s failed: %s", job.name, err)
            return None
        rider = d.get('rider') or {}
        run = d.get('run') or {}
        eta = d.get('eta') or {}
        route = d.get('route') or {}
        km = None
        if rider.get('latitude') and d.get('dropoff', {}).get('latitude'):
            km = round(self.env['sa.delivery.ping'].sudo()._sa_metres(
                rider['latitude'], rider['longitude'], d['dropoff']['latitude'], d['dropoff']['longitude']) * 1.3 / 1000.0, 1)
        elif route.get('km'):
            km = route['km']
        arrives_by = ''
        if not eta.get('minutes') and eta.get('window_to'):
            try:
                arrives_by = fields.Datetime.context_timestamp(job, job.sa_promised_on).strftime('%I:%M %p').lstrip('0')
            except Exception:  # noqa: BLE001
                arrives_by = ''
        return {
            'stop_no': run.get('stop_no') or 1, 'stops_total': run.get('stops_total') or 1,
            'km': km, 'minutes': eta.get('minutes'), 'arrives_by': arrives_by,
            'has_pos': bool(rider.get('latitude')), 'age': rider.get('age_seconds'),
            'stale': bool(rider.get('stale')), 'shown': bool(d.get('show_rider')),
            'at': fields.Datetime.now().replace(microsecond=0).isoformat() + 'Z',
        }

    def sa_store_queue(self, shop_id=None):
        """The shop's open work, newest need first.

        Returned as plain dictionaries rather than as records: the screen
        redraws on every push and does not want to fetch each order again.
        """
        # The rider's first two stages stay on the counter as well: the shop
        # needs to see that a rider has been called and, once one accepts,
        # the pickup code to read out to them.
        # ... and now the rest of the road too (owner, 30 Sep 2026): the
        # counter presses Pickup / Start / Delivered / Failed on the card.
        try:
            self.sudo()._sa_expire_offers()        # offers past their timeout move on
        except Exception as err:  # noqa: BLE001 - the screen must still draw
            _logger.warning("Store: expiring rider offers failed: %s", err)
        call_mode = self.env['sa.delivery.settings'].sudo().get_settings().call_rider_mode or 'ask'
        pickup_mode = self.sa_pickup_mode()
        domain = [('sa_delivery_state', 'in',
                   ('awaiting_shop', 'preparing', 'ready', 'to_assign',
                    'offered', 'accepted', 'picked', 'dispatched',
                    'out_for_delivery'))]
        if shop_id:
            domain.append(('sa_shop_id', '=', int(shop_id)))
        jobs = self.sudo().search(domain, order='sa_offered_on asc, id asc')

        rows = []
        for job in jobs:
            currency = job.sa_currency_id or job.company_id.currency_id
            order = job.sale_id
            invoice = order.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice'
                and m.state == 'posted')[:1]
            rows.append({
                'order_id': order.id,
                'order_name': order.name or '',
                'invoice_id': invoice.id,
                'invoice_name': invoice.name or '',
                'invoice_paid': invoice.payment_state in ('paid', 'in_payment')
                if invoice else False,
                'can_cancel': job.sa_delivery_state in job._SA_CANCELLABLE,
                'company': job.company_id.name or '',
                'id': job.id,
                'ref': job.sa_ref_code or '',
                'name': job.name,
                'sale': job.sale_id.name or '',
                'state': job.sa_delivery_state,
                'customer': job.partner_id.name or '',
                'address': ', '.join(filter(None, [
                    job.partner_id.street, job.partner_id.city])),
                'phone': job.partner_id.phone or '',
                'shop': job.sa_shop_id.name or '',
                'rider': job.sa_delivery_partner_id.name or '',
                'rider_id': job.sa_delivery_partner_id.id or 0,
                'riders': [{'id': r.id, 'name': r.name} for r in self.env['sa.delivery.partner'].sudo().search(
                    ['|', ('shop_ids', '=', False), ('shop_ids', 'in', [job.sa_shop_id.id] if job.sa_shop_id else [])],
                    order='on_duty desc, sequence, name', limit=20)],
                'reached_on': bool(job.sa_arrived_customer_on),
                'stage_text': job.sa_stage_text or '',
                'offer_left': job.sa_offer_seconds_left,
                'track_url': ('/wa/track/%s?token=%s' % (job.id, job.sudo().sa_track_token))
                if job.sudo().sa_track_token else '',
                'offer_round': job.sa_offer_round or 0,
                'call_mode': call_mode,
                'issue': (job.sa_issue_text or job.sa_issue_kind or '') if job.sa_issue_on else '',
                # the rider's own words, and when
                'issue_note': (job.sa_issue_note or '') if job.sa_issue_on and 'sa_issue_note' in job._fields else '',
                'issue_at': (fields.Datetime.context_timestamp(job, job.sa_issue_on).strftime('%H:%M')
                             if job.sa_issue_on else ''),
                # the photos of the open reports, for the red line on the card
                'issue_photos': ([{'id': a.id, 'name': a.name or '', 'url': '/web/image/%d' % a.id,
                                   'thumb': '/web/image/%d/120x120' % a.id}
                                  for r in job.sudo().sa_report_ids.filtered(lambda r: not r.handled_on).sorted('id')
                                  for a in r.photo_ids.sorted('id')]
                                 if job.sa_issue_on and 'sa_report_ids' in job._fields else []),
                'delivery_note': job.sa_delivery_note or '',
                # the live line: rider, stop x of y, km, minutes, freshness
                'live': self._sa_store_live(job),
                # the rider pressed SOS: red on the card until Handled (6 Oct 2026)
                'sos': self._sa_store_sos(job),
                # online order, pay link sent, not paid: Call a Rider waits (6 Oct 2026)
                'waiting_payment': job._sa_waiting_payment() if hasattr(job, '_sa_waiting_payment') else False,
                'missed_by': (', '.join(job.sa_declined_partner_ids.mapped('name'))
                              if job.sa_delivery_state in ('ready', 'to_assign') and not job.sa_delivery_partner_id else ''),
                'candidates': (job.sa_candidates_brief()
                               if job.sa_delivery_state in ('ready', 'to_assign', 'offered')
                               else []),
                'waiting': job.sa_waiting_minutes,
                'pickup_code': (job.sudo().sa_last_pickup_code or ''
                                if job.sa_delivery_state == 'accepted'
                                else ''),
                'rider_phone': job.sa_delivery_partner_id.phone or '',
                # packed before the payment: waiting, no alarm
                'unpaid_wait': bool(job.sa_packed_unpaid_on) and job.sa_delivery_state in ('ready', 'to_assign')
                and not job.sa_delivery_partner_id,
                'unpaid_wait_left': job.sa_packed_wait_left() if job.sa_packed_unpaid_on else 0,
                # branch-controlled pickup: the rider said "I am here"
                'pickup_handover': pickup_mode,
                'rider_arrived': bool(job.sa_arrived_shop_on) and job.sa_delivery_state == 'accepted',
                'rider_arrived_at': (fields.Datetime.context_timestamp(
                    job, job.sa_arrived_shop_on).strftime('%H:%M')
                    if job.sa_arrived_shop_on else ''),
                'supply_waiting': job.sa_supply_waiting,
                'supply_vendor': job.sa_supply_partner_id.name or '',
                'supply_cost': job.sa_supply_cost or 0.0,
                'supply_asked': len(job.sa_supply_vendor_ids),
                'promised': (fields.Datetime.context_timestamp(
                    job, job.sa_promised_on).strftime('%a %d %b')
                    if job.sa_promised_on else ''),
                'kind': job.sa_delivery_kind or '',
                # Rings only for the ones this morning's reminder named, so
                # the alarm is the reminder rather than a permanent noise.
                'reminded': bool(job.sa_supply_reminded_on
                                 and not job.sa_supply_arrived_on),
                'paid': not job.sa_amount_due(),
                'collect': job.sa_amount_due(),
                'currency': currency.symbol or currency.name or '',
                'lines': [{
                    'name': move.product_id.name,
                    'qty': move.product_uom_qty,
                    'uom': move.product_uom.name or '',
                } for move in job.move_ids],
            })
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        return {
            'rows': rows,
            'is_manager': self.env.user.has_group('sales_automation_delivery.group_sa_delivery_manager'),
            'ringing': sum(1 for r in rows
                           if (r['state'] == 'awaiting_shop'
                               and not r['supply_waiting'])
                           # packed, nobody called yet: the counter must press
                           # Call a Rider (3 Oct 2026)
                           or (r['state'] in ('ready', 'to_assign') and not r['rider']
                               and not r.get('unpaid_wait'))
                           # the rider is at the counter and nobody has
                           # pressed Dispatch yet (branch-controlled pickup)
                           or (r['pickup_handover'] == 'branch' and r['rider_arrived']
                               and not r['pickup_code'])
                           # the rider reported something (item missing ...)
                           or r.get('issue')
                           # a rider pressed SOS
                           or r.get('sos')),
            'packing': sum(1 for r in rows if r['state'] == 'preparing'
                           and not r['supply_waiting']),
            'waiting_supply': sum(1 for r in rows if r['supply_waiting']),
            'supply_ringing': sum(1 for r in rows
                                  if r['supply_waiting'] and r['reminded']),
            # The screen re-reads this on every refresh rather than caching it,
            # so changing the cadence in Settings takes effect without anybody
            # reloading the shop's browser.
            'repeat': max(3, settings.alarm_repeat_seconds or 10),
            'ring': max(3, settings.alarm_ring_seconds or 30),
        }

    # ------------------------------------------------------------------
    # Nothing on any shelf
    # ------------------------------------------------------------------
    @api.model
    def _sa_promise_at(self, day):
        """A date picked at the counter, as a UTC datetime.

        Stored at `_SA_PROMISE_HOUR` in the reader's own timezone. Naive UTC
        is what Odoo stores, and doing the conversion here is what keeps a
        20:00 local promise from being filed under tomorrow.
        """
        if not day:
            return False
        if isinstance(day, str):
            day = fields.Date.from_string(day)
        zone = pytz.timezone(self.env.user.tz or 'UTC')
        local = zone.localize(datetime.combine(day, time(_SA_PROMISE_HOUR, 0)))
        return local.astimezone(pytz.UTC).replace(tzinfo=None)

    @api.model
    def _sa_kind_for_date(self, promised):
        """`quick` when the promise falls today, `express` when it is later.

        Compared as LOCAL dates. In UTC an 18:00 promise in Muscat is already
        the next day for four hours of every evening, which would file a
        same-day job under Express.
        """
        if not promised:
            return 'quick'
        local = fields.Datetime.context_timestamp(self, promised)
        today = fields.Datetime.context_timestamp(
            self, fields.Datetime.now())
        return 'quick' if local.date() <= today.date() else 'express'

    def _sa_supply_vendors(self):
        """(suppliers worth asking, a line has no category).

        The category wiring is the one the enquiry desk uses, so a supplier
        added for a category is offered here too without being registered
        twice.

        When a line has NO category the whole field is offered instead, with
        the flag set so the screen can say why. `#DGB` is what taught this: a
        Dell laptop with no `categ_id` offered exactly one supplier - *iPhone
        Parts Supplier* - because `product.seller_ids` was all that was left
        to go on. A confident wrong answer is worse than a long list.
        """
        self.ensure_one()
        partners = self.env['res.partner']
        no_categ = False
        for move in self.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')):
            product = move.product_id
            category = product.categ_id
            if category:
                partners |= category._sa_vendors_for_sourcing()
            else:
                no_categ = True
            partners |= product.seller_ids.mapped('partner_id')
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        if no_categ or not partners:
            everyone = self.env['product.category'].sudo().search(
                []).mapped('sa_vendor_ids')
            partners |= everyone | settings.unlisted_vendor_ids
        return partners, no_categ

    @api.model
    def sa_store_supply_options(self, job_id):
        """The suppliers the shopkeeper may tick, shaped like the desk's."""
        job = self.sudo().browse(int(job_id))
        if not job.exists():
            raise UserError(_("That order is no longer there."))
        partners, no_categ = job._sa_supply_vendors()
        out = []
        for partner in partners:
            phone = (partner.phone or '').strip()
            out.append({'id': partner.id, 'name': partner.name or '',
                        'phone': phone,
                        # Shown but not tickable: a blank number would only
                        # log a failed send.
                        'ok': bool(phone)})
        out.sort(key=lambda v: (not v['ok'], v['name'].lower()))
        return {'vendors': out, 'no_categ': no_categ}

    @api.model
    def sa_store_supply_ask(self, job_id, vendor_ids):
        """Ask the ticked suppliers what they want for this, privately.

        The job's own code rides along so a human can tie the answer back,
        but nothing parses the reply: a vendor answering a *picking* is not
        an enquiry, and the shopkeeper types the agreed number in. Saying so
        here is better than pretending an automatic capture exists.
        """
        job = self.sudo().browse(int(job_id))
        if not job.exists():
            raise UserError(_("That order is no longer there."))
        wanted = [int(v) for v in (vendor_ids or []) if v]
        # Intersected with what was offered: the screen must not be able to
        # message a partner this job never showed.
        offered, _no_categ = job._sa_supply_vendors()
        chosen = offered.filtered(
            lambda p: p.id in wanted and (p.phone or '').strip())
        if not chosen:
            raise UserError(
                _("Choose at least one supplier with a phone number."))
        session = job._sa_session()
        if not session:
            raise UserError(_("No WhatsApp session is connected."))

        lines = '\n'.join(
            '\u2022 *%s* x %s' % (m.product_id.name, int(m.product_uom_qty))
            for m in job.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')))
        body = _("\U0001F50E *Price check* \u2014 *#%(ref)s*\n\n"
                 "%(lines)s\n\n"
                 "Best price *and delivery time* please.\n\n"
                 "\U0001F449 *Just reply with the amount* \u2014 like *450*\n"
                 "With the days if you can: *450 3 days*",
                 ref=job.sa_ref_code or job.name, lines=lines)

        guard = self.env['sa.outbox.guard'].sudo()
        sent = self.env['res.partner']
        for partner in chosen:
            if not guard.claim('supplyask|%s|%s' % (job.id, partner.phone),
                               3600):
                sent |= partner
                continue
            try:
                session.send_message(partner.phone, body)
                sent |= partner
            except Exception as err:  # noqa: BLE001 - one bad number is not
                _logger.warning(     # a reason to skip the rest
                    "Store: could not ask %s about %s: %s",
                    partner.name, job.sa_ref_code, err)
        job.write({'sa_supply_vendor_ids': [(4, p.id) for p in sent],
                   'sa_supply_asked_on': fields.Datetime.now()})
        _logger.info("Store: asked %d supplier(s) about %s",
                     len(sent), job.sa_ref_code)
        job._sa_store_notify()
        return self.sa_store_queue(job.sa_shop_id.id)

    @api.model
    def sa_store_supply_set(self, job_id, company_id=None, partner_id=None,
                            cost=None, promised_date=None):
        """Accept a job nothing can be picked for, and record the buy-in.

        Deliberately does NOT go through the company picker's stock rule:
        that rule is the whole reason this path exists. The customer's price
        is not touched - what is typed here is what we pay.
        """
        job = self.sudo().browse(int(job_id))
        if not job.exists():
            raise UserError(_("That order is no longer there."))
        try:
            amount = float(str(cost or 0).strip().replace(',', ''))
        except (TypeError, ValueError):
            raise UserError(_("Type the amount as a number, like 900."))
        if amount < 0:
            raise UserError(_("The amount cannot be negative."))

        if company_id:
            company = self.env['res.company'].sudo().browse(int(company_id))
            if company.exists():
                # Whose books it goes on. `action_assign` inside will reserve
                # nothing - there is nothing to reserve yet, which is the
                # point - and the moves stay waiting until the goods land.
                job._sa_store_move_to_company(company)

        promised = self._sa_promise_at(promised_date)
        vals = {
            'sa_supply_waiting': True,
            'sa_supply_cost': amount,
            'sa_supply_partner_id': int(partner_id) if partner_id else False,
        }
        if promised:
            vals['sa_promised_on'] = promised
            vals['sa_delivery_kind'] = self._sa_kind_for_date(promised)
        job.write(vals)
        if job.sa_delivery_state == 'awaiting_shop':
            job.sa_shop_accept()
        _logger.info("Store: %s bought in from %s at %s, promised %s (%s)",
                     job.sa_ref_code, job.sa_supply_partner_id.name or '-',
                     amount, promised or '-', job.sa_delivery_kind or '-')
        job._sa_store_notify()
        return self.sa_store_queue(job.sa_shop_id.id)

    @api.model
    def sa_store_supply_arrived(self, job_id):
        """The goods are in. Put the job back into the ordinary queue."""
        job = self.sudo().browse(int(job_id))
        if not job.exists():
            raise UserError(_("That order is no longer there."))
        job.write({'sa_supply_waiting': False,
                   'sa_supply_arrived_on': fields.Datetime.now()})
        # Now there is something to reserve.
        try:
            job.action_assign()
        except Exception as err:  # noqa: BLE001 - reservation is not the point
            _logger.warning("Store: could not reserve %s after arrival: %s",
                            job.sa_ref_code, err)
        _logger.info("Store: goods for %s marked arrived by %s",
                     job.sa_ref_code, self.env.user.name)
        job._sa_store_notify()
        return self.sa_store_queue(job.sa_shop_id.id)

    @api.model
    def _cron_sa_supply_remind(self):
        """Every morning, tell each shop what it is still waiting for.

        An order waiting on a supplier is invisible the next day: the counter
        screen shows today's work and nobody re-reads yesterday's. This is the
        only thing that chases it.

        Runs hourly and acts in the configured hour only, so the hour can be
        changed in Settings without touching the cron.
        """
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        hour = max(0, min(23, settings.supply_remind_hour or 9))
        now_local = fields.Datetime.context_timestamp(
            self, fields.Datetime.now())
        if now_local.hour != hour:
            return True

        domain = [('sa_supply_waiting', '=', True)]
        days = max(0, settings.supply_remind_days or 0)
        if days:
            # Stop chasing eventually: a line that has been read out every
            # morning for a fortnight is one nobody is reading any more.
            domain.append(('sa_supply_asked_on', '>=',
                           fields.Datetime.subtract(
                               fields.Datetime.now(), days=days)))
        waiting = self.sudo().search(domain, order='sa_promised_on asc, id asc')
        if not waiting:
            return True

        guard = self.env['sa.outbox.guard'].sudo()
        stamp = fields.Date.to_string(now_local.date())
        escalation = (self.env['sa.ai.settings'].sudo().get_settings(
            ).price_escalation_phone or '').strip()

        by_shop = {}
        for job in waiting:
            by_shop.setdefault(job.sa_shop_id, self.browse())
            by_shop[job.sa_shop_id] |= job

        for shop, jobs in by_shop.items():
            lines = []
            for job in jobs:
                due = ''
                if job.sa_promised_on:
                    local = fields.Datetime.context_timestamp(
                        self, job.sa_promised_on)
                    late = job.sa_promised_on < fields.Datetime.now()
                    due = _(" - due %(day)s%(late)s",
                            day=local.strftime('%a %d %b'),
                            late=_(" \u26A0 OVERDUE") if late else '')
                lines.append('*#%s* %s%s' % (
                    job.sa_ref_code or job.name,
                    ', '.join('%s x %s' % (m.product_id.name,
                                           int(m.product_uom_qty))
                              for m in job.move_ids[:3]) or job.name,
                    due))
            body = _("\u23F0 *Still waiting for stock* \u2014 %(count)s "
                     "order(s)\n\n%(lines)s\n\n"
                     "Mark them arrived on the Store screen once the goods "
                     "are in.",
                     count=len(jobs), lines='\n'.join(lines))

            phone = ((shop.phone or '').strip() if shop else '') or escalation
            if not phone:
                _logger.info("Store: %s has no number for the morning stock "
                             "reminder - the screen has it anyway",
                             shop.name if shop else '(no shop)')
            elif guard.claim('supplyremind|%s|%s' % (shop.id if shop else 0,
                                                     stamp), 86400):
                session = jobs[0]._sa_session()
                if session:
                    try:
                        session.send_message(phone, body)
                        _logger.info("Store: told %s about %d waiting "
                                     "order(s)", phone, len(jobs))
                    except Exception as err:  # noqa: BLE001
                        _logger.warning("Store: morning reminder to %s "
                                        "failed: %s", phone, err)
            jobs.write({'sa_supply_reminded_on': fields.Datetime.now()})
            jobs._sa_store_notify()
        return True

    @api.model
    def sa_store_shops(self):
        """Shops this user may watch."""
        shops = self.env['sa.delivery.shop'].sudo().search([])
        return [{'id': s.id, 'name': s.name} for s in shops]

    @api.model
    def sa_store_act(self, job_id, action, reason='', company_id=None,
                     **kwargs):
        """One entry point for the screen's buttons."""
        job = self.sudo().browse(int(job_id))
        if not job.exists():
            raise UserError(_("That order is no longer there."))
        # Handled before the ordinary branches: these are the paths for a
        # job that has no stock anywhere, which is exactly what the company
        # picker below refuses to let through.
        if action == 'supply_ask':
            return self.sa_store_supply_ask(job.id, kwargs.get('vendor_ids'))
        if action == 'supply_set':
            return self.sa_store_supply_set(
                job.id, company_id=kwargs.get('company_id') or company_id,
                partner_id=kwargs.get('partner_id'),
                cost=kwargs.get('cost'),
                promised_date=kwargs.get('promised_date'))
        if action == 'supply_arrived':
            return self.sa_store_supply_arrived(job.id)

        if action == 'accept' and company_id:
            company = self.env['res.company'].sudo().browse(int(company_id))
            if company.exists():
                job._sa_store_move_to_company(company)
        if action == 'cancel':
            # The delivery module decides what a cancel means for where the
            # parcel is - on the shelf it cancels the picking, with a rider it
            # becomes a return - and tells the customer and the rider. The
            # invoice is not touched: money moves from the Delivery form's
            # Refund button, on purpose, by a person.
            job.sa_action_cancel(reason=reason or _("Cancelled at the shop"))
            job._sa_store_notify()
        elif action == 'accept':
            job.sa_shop_accept()
        elif action == 'ready':
            job.sa_shop_ready()
        elif action == 'call_rider':
            ids = kwargs.get('rider_ids') or ([kwargs.get('rider_id')] if kwargs.get('rider_id') else [])
            # "Call anyway" on an unpaid online order: delivery managers only
            force = bool(kwargs.get('force')) and self.env.user.has_group('sales_automation_delivery.group_sa_delivery_manager')
            if force:
                job.message_post(body=_("Rider called before the payment by %s (manager).", self.env.user.name))
            job.with_context(sa_force_call=force).sa_action_call_rider(rider_ids=[int(x) for x in ids] or None)
        elif action == 'next_rider':
            job.sa_action_next_rider()
        elif action == 'issue_seen':
            job.sa_action_issue_seen()
        elif action == 'sos_handled':
            alert = self.env['sa.sos.alert'].sudo().browse(int(kwargs.get('sos_id') or 0)).exists()
            if alert:
                alert.with_user(self.env.user).sudo().action_handled()
        elif action == 'unaccept':
            job.sa_shop_unaccept()
        elif action == 'branch_dispatch':
            # Dispatch in branch mode: the code for the staff to read out.
            res = job.sa_action_branch_dispatch()
            data = self.sa_store_queue(job.sa_shop_id.id)
            data['branch_code'] = res
            return data
        elif action == 'gen_pickup_otp':
            # The rider gets it on WhatsApp; the screen shows it too.
            ok, message, code = job.sa_issue_pickup_otp(to='rider')
            job._sa_store_notify()
            data = self.sa_store_queue(job.sa_shop_id.id)
            data['otp_message'] = message
            data['otp_code'] = code
            return data
        elif action in ('pickup_otp', 'dispatch_otp'):
            job.sa_action_dispatch_with_otp(kwargs.get('code') or '',
                                            rider_id=kwargs.get('rider_id'))
        elif action in ('start', 'near'):
            job.sa_action_rider_near()
        elif action == 'reached':
            job.sa_action_reached_customer()
            job._sa_store_notify()
        elif action == 'deliver_otp':
            job.sa_action_deliver_with_otp(kwargs.get('code') or '')
        elif action == 'fail':
            job.sa_action_fail(reason or _("Failed at the counter"))
            job._sa_store_notify()
        else:
            raise UserError(_("Unknown action %s.", action))
        return self.sa_store_queue(job.sa_shop_id.id)
