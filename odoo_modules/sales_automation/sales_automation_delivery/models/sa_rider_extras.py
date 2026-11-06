# -*- coding: utf-8 -*-
"""What the rider-app live test asked the backend for (3 Oct 2026):
the customer's map pin (a WhatsApp location pin, a geocoded address, or where
the last delivery was handed over), what the rider earns for the job, a
delivery note / landmark, a pay link for cash jobs, the rider's heading, and
the rider's "item missing" report shown at the shop counter."""
import logging
import math
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)


class SaDeliverySettingsRiderPay(models.Model):
    _inherit = 'sa.delivery.settings'

    third_party_enabled = fields.Boolean(
        'Use third-party riders', default=True,
        help="On: Delivery Partners (riders of kind 'Delivery Partner') can be "
             "given jobs and are paid per trip by the rates below. Off: they "
             "can still sign in and see their past trips and pay, but get no "
             "new offers. Own riders are on salary: they never get a per-trip "
             "fee, only delivery counts.")
    rider_fee_base = fields.Float(
        'Rider pay per job', default=0.0,
        help="What a rider earns for one delivery, shown on the offer in the "
             "rider app. 0 with 0 per km = pay is not shown.")
    rider_fee_per_km = fields.Float(
        'Rider pay per km (shop to customer)', default=0.0,
        help="Added for every kilometre between the shop's pin and the "
             "customer's pin, after the kilometres included in the base pay.")
    rider_fee_free_km = fields.Float(
        'Kilometres included in the base pay', default=0.0,
        help="The per-km pay starts after this distance. Example: base 30, "
             "8 per km after 2 km, Express bonus 10 -> a 3.5 km Express trip "
             "pays 30 + 1.5 x 8 + 10 = 52.")
    rider_fee_express_bonus = fields.Float(
        'Extra rider pay for an Express job', default=0.0)

    # ---- pickup at the branch (3 Oct 2026) ----
    pickup_handover = fields.Selection([
        ('branch', 'Branch dispatches: staff press Dispatch, the code shows on the branch screen, the rider types it'),
        ('rider_request', 'Rider asks: the code is sent to the shop on WhatsApp, the rider types it'),
        ('rider_shows', 'Rider shows: the code is sent to the rider, the shop types it'),
    ], 'Pickup handover', default='branch', required=True,
        help="Who starts the handover of the parcel at the branch.\n"
             "Branch dispatches: the rider signals arrival; the branch staff "
             "press Dispatch; a 6-digit code pops up on the branch screen; "
             "staff tell the rider; the rider types it in the app; the job "
             "becomes Collected by Rider. Nothing is sent on WhatsApp.")
    hide_customer_until_pickup = fields.Boolean(
        "Show the customer's location only after pickup", default=True,
        help="On: until the pickup code is verified the rider sees only the "
             "customer's area (city, pincode) and the distance - not the "
             "street address, map pin, phone or delivery note.")

    # ---- "Rider Near Customer" set by the server (5 Oct 2026) ----
    auto_near_customer = fields.Boolean(
        'Mark "Rider near customer" automatically', default=True,
        help="On: when the rider's position stays within the radius of the "
             "customer's map pin for the time below, the job moves to Rider "
             "Near Customer by itself - the same as the rider (or the counter) "
             "pressing the button, including the WhatsApp message to the "
             "customer. Only for a real pin (WhatsApp location, contact, last "
             "delivery) - never for an address that was only looked up.")
    near_radius_m = fields.Integer('Near the customer within (m)', default=300)
    near_hits_needed = fields.Integer(
        'Or after this many readings inside', default=2,
        help="Rider Near Customer is also set when this many positions in a "
             "row are inside the radius, even before the seconds above have "
             "passed. The radius is widened by the reading's GPS accuracy "
             "(at most 100 m).")
    # ---- parcel photos (5 Oct 2026) ----
    proof_photos_min = fields.Integer(
        'Parcel photos needed at each end', default=2,
        help="The rider app takes photos of the parcel after the pickup code "
             "and again after the customer's code. A job whose rider uses the "
             "app is marked 'Photos missing' when an end has fewer than this. "
             "0 = never marked.")
    proof_photos_max = fields.Integer(
        'Parcel photos allowed at each end', default=4,
        help="A further photo for the same end is refused.")
    near_dwell_seconds = fields.Integer(
        'For at least (seconds)', default=20,
        help="How long the rider must stay inside the radius, so one wrong "
             "GPS reading cannot trigger it. 0 = the first reading inside.")

    def _sa_rider_fee_for(self, metres, kind):
        self.ensure_one()
        if not (self.rider_fee_base or self.rider_fee_per_km or self.rider_fee_express_bonus):
            return 0.0
        km = max(0.0, (metres or 0) / 1000.0 - (self.rider_fee_free_km or 0.0))
        fee = (self.rider_fee_base or 0.0) + (self.rider_fee_per_km or 0.0) * km
        if kind == 'express':
            fee += self.rider_fee_express_bonus or 0.0
        return fee


def _sa_map_url(lat, lng):
    if not (lat and lng):
        return False
    return 'https://www.google.com/maps?q=%.7f,%.7f' % (lat, lng)


class StockPickingRiderExtras(models.Model):
    _inherit = 'stock.picking'

    sa_rider_fee = fields.Monetary(
        'Rider Pay', currency_field='sa_currency_id', copy=False,
        help="What the rider earns for this job. Filled from Delivery Settings "
             "when a rider is called; can be typed by hand. Not changed once "
             "the job is delivered.")
    sa_trip_m = fields.Integer('Shop to Customer (m)', copy=False, readonly=True)
    sa_delivery_note = fields.Char(
        'Delivery Note / Landmark', copy=False,
        help="Flat, gate, landmark - what the customer answered on WhatsApp, "
             "or typed here. Shown to the rider in the app.")
    sa_pin_source = fields.Selection([
        ('contact', 'On the contact'), ('whatsapp', 'WhatsApp location pin'),
        ('door', 'Where the rider delivered last time'),
        ('geocoded', 'Looked up from the address (approximate)'),
    ], 'Customer Pin', copy=False, readonly=True)
    sa_issue_kind = fields.Char('Rider Report', copy=False, readonly=True)
    sa_issue_text = fields.Char('Rider Report Text', copy=False, readonly=True)
    sa_issue_on = fields.Datetime('Rider Reported On', copy=False, readonly=True)
    sa_rider_heading = fields.Float('Rider Heading (deg)', copy=False, readonly=True)
    sa_pay_url_cache = fields.Char(copy=False, readonly=True)
    # Where the parcel actually changed hands (the rider's position when
    # Delivered was confirmed). Kept on the job; the customer's own address
    # and pin are never changed by a delivery (rider-app report, 5 Oct 2026).
    sa_handover_lat = fields.Float('Handover Latitude', digits=(10, 7), copy=False, readonly=True)
    sa_handover_lng = fields.Float('Handover Longitude', digits=(10, 7), copy=False, readonly=True)
    sa_handover_on = fields.Datetime('Handed Over On', copy=False, readonly=True)
    sa_handover_m = fields.Integer(
        'Handover Distance from the Pin (m)', copy=False, readonly=True,
        help="How far from the customer's map pin the parcel was handed over. "
             "0 when the customer has no pin.")
    # The handover spot in words (reverse lookup when Delivered is confirmed),
    # shown next to the address the customer gave so a different place stands out.
    sa_handover_address = fields.Char('Handover Address', copy=False, readonly=True)
    sa_customer_address = fields.Char('Customer Address', compute='_compute_sa_address_section')
    sa_customer_lat = fields.Float('Customer Latitude', digits=(10, 7), compute='_compute_sa_address_section')
    sa_customer_lng = fields.Float('Customer Longitude', digits=(10, 7), compute='_compute_sa_address_section')
    sa_customer_map_url = fields.Char('Customer on the Map', compute='_compute_sa_address_section')
    sa_handover_map_url = fields.Char('Handover on the Map', compute='_compute_sa_address_section')
    sa_handover_far = fields.Boolean(compute='_compute_sa_address_section')

    _SA_HANDOVER_FAR_M = 200

    @api.depends('partner_id', 'partner_id.street', 'partner_id.street2', 'partner_id.city',
                 'partner_id.zip', 'partner_id.state_id', 'partner_id.country_id',
                 'partner_id.partner_latitude', 'partner_id.partner_longitude',
                 'sa_handover_lat', 'sa_handover_lng', 'sa_handover_m', 'sa_handover_on')
    def _compute_sa_address_section(self):
        for job in self:
            p = job.partner_id
            lines = (p._display_address(without_company=True) or '').splitlines() if p else []
            job.sa_customer_address = ', '.join(x.strip() for x in lines if x.strip()) or False
            clat, clng = job._sa_customer_position() if p else (None, None)
            job.sa_customer_lat = clat or 0.0
            job.sa_customer_lng = clng or 0.0
            job.sa_customer_map_url = _sa_map_url(clat, clng)
            job.sa_handover_map_url = _sa_map_url(job.sa_handover_lat, job.sa_handover_lng)
            job.sa_handover_far = bool(clat and job.sa_handover_on and job.sa_handover_m > self._SA_HANDOVER_FAR_M)

    # How long each leg took, from the stamps the states already leave. Steps
    # can be skipped and a reset can leave stamps out of order, so a leg with
    # a missing end or a negative span is simply not shown.
    sa_ride_minutes = fields.Integer(
        'Pickup to Delivered (min)', compute='_compute_sa_ride_minutes', store=True,
        help="Minutes from the rider picking the parcel up (or the branch dispatching it) "
             "to Delivered.")
    sa_time_ride = fields.Char('Pickup to Delivered', compute='_compute_sa_times')
    sa_time_answer = fields.Char('Rider Answered the Offer', compute='_compute_sa_times')
    sa_time_to_shop = fields.Char('Reached the Shop', compute='_compute_sa_times')
    sa_time_collect = fields.Char('Collected at the Shop', compute='_compute_sa_times')
    sa_time_door = fields.Char("At the Customer's Door", compute='_compute_sa_times')
    sa_time_total = fields.Char('Whole Job (Offer to Delivered)', compute='_compute_sa_times')

    @staticmethod
    def _sa_span_seconds(start, end):
        if not (start and end) or end < start:
            return None
        return (end - start).total_seconds()

    @staticmethod
    def _sa_span_text(seconds):
        if seconds is None:
            return False
        minutes = int(seconds // 60)
        if minutes < 1:
            return _("less than 1 min")
        if minutes < 60:
            return _("%(m)s min", m=minutes)
        hours, minutes = divmod(minutes, 60)
        if hours < 24:
            return _("%(h)s h %(m)02d min", h=hours, m=minutes)
        days, hours = divmod(hours, 24)
        return _("%(d)s d %(h)s h", d=days, h=hours)

    @api.depends('sa_picked_on', 'sa_dispatched_on', 'sa_delivered_on')
    def _compute_sa_ride_minutes(self):
        for job in self:
            secs = self._sa_span_seconds(job.sa_picked_on or job.sa_dispatched_on, job.sa_delivered_on)
            job.sa_ride_minutes = int(secs // 60) if secs is not None else 0

    @api.depends('sa_offered_on', 'sa_accepted_on', 'sa_arrived_shop_on', 'sa_picked_on',
                 'sa_dispatched_on', 'sa_arrived_customer_on', 'sa_delivered_on')
    def _compute_sa_times(self):
        span, text = self._sa_span_seconds, self._sa_span_text
        for job in self:
            pickup = job.sa_picked_on or job.sa_dispatched_on
            job.sa_time_ride = text(span(pickup, job.sa_delivered_on))
            job.sa_time_answer = text(span(job.sa_offered_on, job.sa_accepted_on))
            job.sa_time_to_shop = text(span(job.sa_accepted_on, job.sa_arrived_shop_on or job.sa_picked_on))
            job.sa_time_collect = text(span(job.sa_accepted_on, job.sa_picked_on))
            job.sa_time_door = text(span(job.sa_arrived_customer_on, job.sa_delivered_on))
            job.sa_time_total = text(span(job.sa_offered_on, job.sa_delivered_on))

    def _sa_fill_handover_address(self):
        """Look the handover spot up in words. Never raises; empty when the
        lookup service gives nothing."""
        Geo = self.env['sa.geocode.cache'].sudo()
        for job in self:
            if not (job.sa_handover_lat and job.sa_handover_lng):
                continue
            short, full = Geo.sa_reverse(job.sa_handover_lat, job.sa_handover_lng)
            if full or short:
                job.sudo().write({'sa_handover_address': full or short})

    def action_sa_lookup_handover_address(self):
        self._sa_fill_handover_address()
        if not self.filtered('sa_handover_address'):
            raise UserError(_("The address lookup gave nothing for this spot. Check Delivery "
                              "Settings ▸ Address lookup, or try again in a minute."))
        return True

    def sa_near_pin_m(self):
        """Metres from the rider's last fix to the customer's pin, or None."""
        self.ensure_one()
        clat, clng = self._sa_customer_position()
        if not clat or not (self.sa_rider_lat and self.sa_rider_lng):
            return None
        return int(self.env['sa.delivery.ping'].sudo()._sa_metres(clat, clng, self.sa_rider_lat, self.sa_rider_lng))

    def sa_handover_block(self):
        """For the apps: where this job was handed over, or None."""
        self.ensure_one()
        if not (self.sa_handover_lat and self.sa_handover_lng):
            return None
        return {'latitude': self.sa_handover_lat, 'longitude': self.sa_handover_lng,
                'at': (self.sa_handover_on.replace(microsecond=0).isoformat() + 'Z') if self.sa_handover_on else '',
                'metres_from_pin': self.sa_handover_m or None,
                'address': self.sa_handover_address or ''}
    sa_pay_url_amount = fields.Float(copy=False, readonly=True)

    # ------------------------------------------------------------------
    def _sa_customer_position(self):
        """(lat, lng) of the customer, or (None, None)."""
        self.ensure_one()
        p = self.partner_id
        if p and p.partner_latitude and p.partner_longitude:
            return p.partner_latitude, p.partner_longitude
        return None, None

    def sa_location_source(self):
        """For the rider app: 'customer_pin' (a real pin), 'geocoded'
        (approximate) or None (no pin at all)."""
        self.ensure_one()
        lat, _lng = self._sa_customer_position()
        if not lat:
            return None
        # 'door' pins were copied from an earlier handover spot (before
        # 5 Oct 2026) - a corner or an office as easily as the house
        return 'geocoded' if self.sa_pin_source in ('geocoded', 'door') else 'customer_pin'

    def _sa_ensure_customer_pin(self):
        """No pin on the contact: look the typed address up once (Nominatim /
        Google). Approximate - a WhatsApp location pin replaces it. Never raises."""
        Geo = self.env['sa.geocode.cache'].sudo()
        for job in self:
            p = job.partner_id.sudo()
            if not p:
                continue
            if p.partner_latitude and p.partner_longitude:
                if not job.sa_pin_source:
                    job.sa_pin_source = 'contact'
                continue
            tries = [
                ', '.join(filter(None, [p.street, p.street2, p.city, p.zip, p.state_id.name, p.country_id.name])),
                ', '.join(filter(None, [p.street2 or p.street, p.city, p.zip, p.country_id.name])),
                ', '.join(filter(None, [p.city, p.zip, p.state_id.name, p.country_id.name])),
            ]
            for text in tries:
                if not text or len(text) < 4:
                    continue
                try:
                    lat, lng = Geo.sa_forward(text)
                except Exception:  # noqa: BLE001
                    lat = lng = None
                if lat and lng:
                    p.write({'partner_latitude': lat, 'partner_longitude': lng})
                    job.sa_pin_source = 'geocoded'
                    _logger.info("Delivery: customer pin for %s looked up from %r", job.sa_ref_code, text[:60])
                    break
        return True

    def _sa_prepare_trip(self):
        """Pin, shop-to-customer distance, the rider's pay and the customer's
        note, before a rider is called. Never raises."""
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        Ping = self.env['sa.delivery.ping'].sudo()
        for job in self:
            try:
                job._sa_ensure_customer_pin()
                lat, lng = job._sa_customer_position()
                slat, slng = job.sa_shop_position()
                metres = 0
                if lat and lng and slat and slng:
                    metres = int(Ping._sa_metres(slat, slng, lat, lng))
                vals = {'sa_trip_m': metres}
                if metres > 150000 and job.sa_pin_source == 'geocoded':
                    # A looked-up address that lands 150 km+ from the shop is
                    # the wrong place (same street name elsewhere): no pin is
                    # better than a wrong one, and it must not set the pay.
                    job.partner_id.sudo().write({'partner_latitude': 0.0, 'partner_longitude': 0.0})
                    vals.update({'sa_trip_m': 0, 'sa_pin_source': False})
                    metres = 0
                    _logger.info("Delivery: looked-up pin for %s dropped - too far from the shop", job.sa_ref_code)
                # (the per-trip fee is set when the job goes to a Delivery
                # Partner - see _sa_apply_rider_fee - not here)
                if not job.sa_delivery_note:
                    partner = job.partner_id
                    note = (partner.sa_delivery_note if 'sa_delivery_note' in partner._fields else '') or partner.street2
                    if note:
                        vals['sa_delivery_note'] = note[:120]
                job.write(vals)
            except Exception as err:  # noqa: BLE001
                _logger.warning("Delivery: preparing the trip for %s failed: %s", job.name, err)
        return True

    sa_rider_fee_locked = fields.Boolean(
        'Pay typed by hand', copy=False,
        help="Tick to keep the Rider Pay typed here; otherwise it is worked "
             "out from the rates whenever the job goes to a Delivery Partner.")

    def _sa_apply_rider_fee(self, rider):
        """Per-trip pay is for Delivery Partners (third party) only; own
        riders are on salary. Set when the job goes to a rider, frozen once
        delivered."""
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        for job in self:
            if job.sa_delivery_state in ('delivered', 'returned', 'cancelled', 'failed'):
                continue
            if not rider or rider.kind != 'third_party' or not settings.third_party_enabled:
                if job.sa_rider_fee:
                    job.write({'sa_rider_fee': 0.0})
                continue
            if job.sa_rider_fee_locked and job.sa_rider_fee:
                continue
            job.write({'sa_rider_fee': settings._sa_rider_fee_for(job.sa_trip_m, job.sa_delivery_kind)})
        return True

    def sa_candidates(self, exclude=None, include_busy=True, include_off=False):
        cands = super().sa_candidates(exclude=exclude, include_busy=include_busy, include_off=include_off)
        if not self.env['sa.delivery.settings'].sudo().get_settings().third_party_enabled:
            cands = [c for c in cands if c['rider'].kind != 'third_party']
        return cands

    def sa_action_call_rider(self, rider_id=None, rider_ids=None):
        self._sa_prepare_trip()
        ids = list(rider_ids or ([rider_id] if rider_id else []))
        if ids and not self.env['sa.delivery.settings'].sudo().get_settings().third_party_enabled:
            Rider = self.env['sa.delivery.partner'].sudo()
            partners = Rider.browse([int(i) for i in ids if i]).exists().filtered(
                lambda r: r.kind == 'third_party')
            if partners:
                keep = [int(i) for i in ids if i and int(i) not in partners.ids]
                if not keep:
                    raise UserError(_("%s - third-party riders are switched off in Delivery Settings.",
                                      ', '.join(partners.mapped('name'))))
                rider_id, rider_ids = None, keep
        return super().sa_action_call_rider(rider_id=rider_id, rider_ids=rider_ids)

    def sa_action_dispatch_with_otp(self, code, rider_id=None):
        res = super().sa_action_dispatch_with_otp(code, rider_id=rider_id)
        for job in self:
            job._sa_apply_rider_fee(job.sa_delivery_partner_id)      # the counter picked the rider
        return res

    # ------------------------------------------------------------------
    def sa_set_customer_pin(self, lat, lng, source='whatsapp'):
        """A location pin the customer sent: on the contact and on the job."""
        for job in self:
            job.partner_id.sudo().write({'partner_latitude': lat, 'partner_longitude': lng})
            vals = {'sa_pin_source': source}
            if job.sa_delivery_state in ('awaiting_shop', 'preparing', 'ready', 'to_assign'):
                # nobody has been offered this job yet: the pay follows the
                # real distance, not the approximate one
                vals['sa_rider_fee'] = 0.0
            job.write(vals)
            job._sa_prepare_trip()
        return True

    # ------------------------------------------------------------------
    # Pickup at the branch (3 Oct 2026): the rider signals arrival, the
    # branch presses Dispatch, the code shows on the branch screen, the rider
    # types it, and only then the customer's location is given to the rider.
    # ------------------------------------------------------------------
    _SA_REVEALED_STATES = ('picked', 'dispatched', 'out_for_delivery', 'delivered',
                           'failed', 'returning', 'returned')

    sa_pickup_handover = fields.Char(compute='_compute_sa_pickup_handover')
    sa_near_since = fields.Datetime('Inside the Near Radius Since', copy=False, readonly=True)
    sa_near_hits = fields.Integer('Readings Inside the Near Radius', copy=False, readonly=True)
    sa_near_auto = fields.Boolean(
        'Near Customer Set Automatically', copy=False, readonly=True,
        help="Rider Near Customer was set by the server from the rider's "
             "position, not by a button.")

    def _sa_check_auto_near(self, lat, lng, accuracy=0.0):
        """A position of the rider came in: is a collected job now close
        enough to the customer, for long enough, to be Rider Near Customer?
        True when this call moved the job."""
        self.ensure_one()
        if self.sa_delivery_state != 'dispatched':
            return False
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        if not settings.auto_near_customer:
            return False
        clat, clng = self._sa_customer_position()
        if not clat or self.sa_pin_source in ('geocoded', 'door'):
            return False                    # no pin, or only an approximate one
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            return False
        radius = max(20, settings.near_radius_m or 300)
        # A vague reading is not thrown away: the radius is widened by its
        # accuracy (at most 100 m). 0 / missing = unknown, taken as is.
        try:
            accuracy = float(accuracy or 0)
        except (TypeError, ValueError):
            accuracy = 0.0
        slack = min(max(accuracy, 0.0), 100.0)
        metres = self.env['sa.delivery.ping'].sudo()._sa_metres(clat, clng, lat, lng)
        now = fields.Datetime.now()
        inside = metres <= radius + slack
        job = self.sudo()
        if not inside:
            if job.sa_near_since or job.sa_near_hits:
                job.write({'sa_near_since': False, 'sa_near_hits': 0})
            _logger.info("Auto near: job %s d=%dm acc=%.0f radius=%d+%d inside=no hits=0",
                         job.sa_ref_code, metres, accuracy, radius, slack)
            return False
        since = job.sa_near_since or now
        hits = (job.sa_near_hits or 0) + 1
        job.write({'sa_near_since': since, 'sa_near_hits': hits})
        dwell = max(0, settings.near_dwell_seconds or 0)
        need = max(1, settings.near_hits_needed or 2)
        waited = (now - since).total_seconds()
        fire = hits >= need or waited >= dwell
        _logger.info("Auto near: job %s d=%dm acc=%.0f radius=%d+%d inside=yes hits=%d/%d inside_for=%ds/%ds -> %s",
                     job.sa_ref_code, metres, accuracy, radius, slack, hits, need, waited, dwell,
                     'NEAR' if fire else 'wait')
        if not fire:
            return False
        job.write({'sa_near_auto': True})
        job.sa_action_rider_near()
        job.message_post(body=_("Rider Near Customer set automatically: %(rider)s is %(m)s m from the customer's pin.",
                                rider=job.sa_delivery_partner_id.name or '-', m=int(metres)))
        try:
            settings._sa_push(job.sa_delivery_partner_id,
                              {'type': 'near_customer_auto', 'delivery_order_id': job.id,
                               'job_code': job.sa_ref_code or '', 'status': 'out_for_delivery'},
                              _("Near the customer - #%s", job.sa_ref_code or ''),
                              _("Marked near automatically. At the door, press Reached."))
        except Exception as err:  # noqa: BLE001
            _logger.warning("Auto near: push for %s failed: %s", job.sa_ref_code, err)
        return True

    def _compute_sa_pickup_handover(self):
        mode = self.sa_pickup_mode()
        for job in self:
            job.sa_pickup_handover = mode

    @api.model
    def sa_pickup_mode(self):
        return self.env['sa.delivery.settings'].sudo().get_settings().pickup_handover or 'branch'

    def sa_customer_revealed(self):
        """May the rider see where the customer is? Always once the parcel
        is in the rider's hands; before that only when the setting allows."""
        self.ensure_one()
        if not self.env['sa.delivery.settings'].sudo().get_settings().hide_customer_until_pickup:
            return True
        return self.sa_delivery_state in self._SA_REVEALED_STATES

    def sa_customer_area(self):
        """City and pincode - what the rider may know before pickup."""
        self.ensure_one()
        p = self.partner_id
        return ', '.join(filter(None, [p.city, p.zip])) if p else ''

    def sa_branch_wait_message(self):
        self.ensure_one()
        if self.sa_pickup_code_shown:
            return _("The counter has your pickup code. Ask them to read it to you, then type it here.")
        return _("Tell the counter you are here. They will press Dispatch and read you the pickup code.")

    def sa_rider_at_shop(self):
        """The rider signalled arrival (or asked again): ring the counter.
        No code is made here - the branch makes it by pressing Dispatch."""
        self.ensure_one()
        if not self.sa_arrived_shop_on:
            self.sudo().write({'sa_arrived_shop_on': fields.Datetime.now()})
        if hasattr(self, '_sa_store_notify'):
            try:
                self._sa_store_notify()
            except Exception:  # noqa: BLE001
                pass
        return self.sa_branch_wait_message()

    def sa_action_branch_dispatch(self):
        """The branch's Dispatch button: make the pickup code and show it on
        the branch screen only. Returns what the popup needs."""
        self.ensure_one()
        rider = self.sa_delivery_partner_id
        if self.sa_delivery_state != 'accepted' or not rider:
            raise UserError(_("Job #%(ref)s is %(state)s - Dispatch shows the pickup code once a rider "
                              "has accepted the job.", ref=self.sa_ref_code or self.name,
                              state=dict(self._fields['sa_delivery_state']._description_selection(self.env))
                              .get(self.sa_delivery_state, self.sa_delivery_state)))
        _ok, _msg, code = self.sa_issue_pickup_otp(to='none')
        self.write({'sa_pickup_code_shown': code})
        otp = self.env['sa.delivery.otp'].sudo().search(
            [('picking_id', '=', self.id), ('kind', '=', 'pickup'), ('active', '=', True)],
            order='id desc', limit=1)
        self.message_post(body=_("Dispatch pressed by %(user)s - pickup code shown at the branch for rider %(rider)s%(arr)s.",
                                 user=self.env.user.name, rider=rider.name,
                                 arr='' if self.sa_arrived_shop_on else _(" (the rider has not signalled arrival yet)")))
        try:
            self.env['sa.delivery.settings'].sudo().get_settings()._sa_push(
                rider, {'type': 'pickup_code_ready', 'delivery_order_id': self.id,
                        'job_code': self.sa_ref_code or ''},
                _("Pickup code ready - #%s", self.sa_ref_code or ''),
                _("Ask the counter for the 6-digit code and type it in the app."))
        except Exception as err:  # noqa: BLE001
            _logger.warning("Branch dispatch: push for %s failed: %s", self.sa_ref_code, err)
        if hasattr(self, '_sa_store_notify'):
            self._sa_store_notify()
        return {'code': code, 'rider': rider.name or '',
                'expires_at': (otp.expires_on.isoformat() + 'Z') if otp and otp.expires_on else '',
                'arrived': bool(self.sa_arrived_shop_on)}

    def sa_action_branch_dispatch_button(self):
        """Job form: Dispatch (the code appears in the Pickup Code box)."""
        self.ensure_one()
        self.sa_action_branch_dispatch()
        return True

    def sa_finish_branch_pickup(self):
        """The rider typed the right code: the parcel is theirs -> Collected
        by Rider (dispatched), with one customer message."""
        self.ensure_one()
        for st in ('picked', 'dispatched'):
            if self.sa_delivery_state != st:
                self.with_context(sa_quiet=(st != 'dispatched')).sa_set_state(st)
        self.write({'sa_pickup_code_shown': False})
        self.message_post(body=_("Collected by rider %s - the rider typed the pickup code shown at the branch.",
                                 self.sa_delivery_partner_id.name or '-'))
        return True

    def _compute_sa_stage_text(self):
        super()._compute_sa_stage_text()
        if self.sa_pickup_mode() != 'branch':
            return
        for p in self:
            if p.sa_delivery_state != 'accepted':
                continue
            rider = p.sa_delivery_partner_id.name or _("the rider")
            if p.sa_pickup_code_shown:
                p.sa_stage_text = _("Pickup code shown - read it to %s; waiting for the rider to type it", rider)
            elif p.sa_arrived_shop_on:
                p.sa_stage_text = _("%s is at the counter - next: press Dispatch and read the code to the rider", rider)
            else:
                p.sa_stage_text = _("%s accepted and is coming - when the rider arrives, press Dispatch", rider)

    def sa_set_state(self, state):
        if state in ('offered', 'accepted'):
            # a new rider (or a new try): yesterday's arrival and code are not theirs
            vals = {'sa_arrived_shop_on': False}
            if self.sa_pickup_mode() == 'branch':
                vals['sa_pickup_code_shown'] = False
                if 'sa_last_pickup_code' in self._fields:      # the counter screen's copy
                    vals['sa_last_pickup_code'] = False
            self.sudo().write(vals)
        if state == 'dispatched':
            # a fresh trip to the customer: nothing is "near" yet
            self.sudo().write({'sa_near_since': False, 'sa_near_auto': False, 'sa_near_hits': 0})
        res = super().sa_set_state(state)
        if state == 'delivered':
            # Where the parcel changed hands is kept ON THE JOB. It is not the
            # customer's address: the bike may have stopped at the corner, or
            # the customer was at the office that day. The customer's street
            # and pin stay exactly as the customer (or the office) gave them.
            for job in self:
                try:
                    if job.sa_rider_lat and job.sa_rider_lng and job.sa_rider_fix_on \
                            and (fields.Datetime.now() - job.sa_rider_fix_on) <= timedelta(minutes=10):
                        clat, clng = job._sa_customer_position()
                        metres = 0
                        if clat and clng:
                            metres = int(self.env['sa.delivery.ping'].sudo()._sa_metres(
                                clat, clng, job.sa_rider_lat, job.sa_rider_lng))
                        job.sudo().write({'sa_handover_lat': job.sa_rider_lat, 'sa_handover_lng': job.sa_rider_lng,
                                          'sa_handover_on': fields.Datetime.now(), 'sa_handover_m': metres,
                                          'sa_handover_address': False})
                        job._sa_fill_handover_address()
                except Exception as err:  # noqa: BLE001
                    _logger.warning("Delivery: handover spot for %s not kept: %s", job.name, err)
        return res

    def sa_pay_url_for_rider(self):
        """The same pay link the WhatsApp chat sends, for a cash job, so the
        rider can show it as a QR at the door. '' when nothing is due."""
        self.ensure_one()
        due = self.sa_amount_due() or 0.0
        order = self.sale_id
        if due <= 0 or not order or 'sa.group.request' not in self.env:
            return ''
        if self.sa_pay_url_cache and abs((self.sa_pay_url_amount or 0.0) - due) < 0.005:
            return self.sa_pay_url_cache
        try:
            url = self.env['sa.group.request'].sudo()._sa_pay_url(order.sudo()) or ''
        except Exception as err:  # noqa: BLE001
            _logger.warning("Delivery: pay link for %s failed: %s", self.name, err)
            return ''
        if url.startswith('http'):
            self.sudo().write({'sa_pay_url_cache': url, 'sa_pay_url_amount': due})
            return url
        return ''

    def sa_rider_report(self, rider, kind, text):
        """The rider's report from the app (item missing, customer not
        answering ...): kept on the job, shown red at the counter, rings."""
        self.ensure_one()
        self.write({'sa_issue_kind': (kind or 'issue')[:40], 'sa_issue_text': (text or '')[:250],
                    'sa_issue_on': fields.Datetime.now(), 'sa_last_error': (text or '')[:250]})
        self.message_post(body=_("Rider %(rider)s reported: %(text)s",
                                 rider=rider.name if rider else _("the rider"), text=text or kind or _("a problem")))
        if hasattr(self, '_sa_store_notify'):
            try:
                self._sa_store_notify()
            except Exception:  # noqa: BLE001
                pass
        return True

    def sa_action_issue_seen(self):
        """The counter has dealt with the rider's report."""
        for job in self:
            if job.sa_issue_on:
                job.message_post(body=_("Rider report handled by %s.", self.env.user.name))
        self.write({'sa_issue_kind': False, 'sa_issue_text': False, 'sa_issue_on': False})
        return True


class StockPickingProofPhotos(models.Model):
    """Parcel photos at both ends: after the pickup code at the shop and
    after the customer's code at the door, kept apart on the job."""
    _inherit = 'stock.picking'

    sa_pickup_photo_ids = fields.Many2many(
        'ir.attachment', 'sa_picking_pickup_photo_rel', 'picking_id', 'attachment_id',
        string='Pickup Photos', copy=False)
    sa_delivery_photo_ids = fields.Many2many(
        'ir.attachment', 'sa_picking_delivery_photo_rel', 'picking_id', 'attachment_id',
        string='Delivery Photos', copy=False)
    sa_photos_html = fields.Html(compute='_compute_sa_photos', sanitize=False)
    sa_photos_missing = fields.Char('Photos Missing', compute='_compute_sa_photos')

    _SA_PHOTO_CLOSED = ('none', 'awaiting_shop', 'preparing', 'ready', 'to_assign', 'offered', 'cancelled')
    _SA_PHOTO_FINISHED = ('delivered', 'returned', 'failed')

    def _sa_photo_limits(self):
        st = self.env['sa.delivery.settings'].sudo().get_settings()
        return max(0, st.proof_photos_min or 0), max(1, st.proof_photos_max or 4)

    def sa_photos_missing_list(self):
        """['pickup', 'delivery'] - the ends that have too few photos. Only
        for a rider who uses the app (a counter-only job has no photos)."""
        self.ensure_one()
        low, _high = self._sa_photo_limits()
        rider = self.sa_delivery_partner_id
        if not low or not rider:
            return []
        uses_app = self.env['sa.delivery.token'].sudo().search_count(
            [('partner_id', '=', rider.id), ('revoked', '=', False)], limit=1)
        if not uses_app:
            return []
        out = []
        if self.sa_delivery_state in ('dispatched', 'out_for_delivery', 'delivered') \
                and len(self.sa_pickup_photo_ids) < low:
            out.append('pickup')
        if self.sa_delivery_state == 'delivered' and len(self.sa_delivery_photo_ids) < low:
            out.append('delivery')
        return out

    @api.depends('sa_pickup_photo_ids', 'sa_delivery_photo_ids', 'sa_delivery_state', 'sa_delivery_partner_id')
    def _compute_sa_photos(self):
        low, _high = self._sa_photo_limits()
        for job in self:
            tz = self.env['sa.delivery.partner']._sa_company_tz(job.company_id or self.env.company)
            parts = []
            for group, label, photos in (('pickup', _("Pickup photos"), job.sa_pickup_photo_ids),
                                         ('delivery', _("Delivery photos"), job.sa_delivery_photo_ids)):
                if not photos:
                    continue
                # `o_sa_photo` + data-group: photo_lightbox.js opens these in
                # a popup on the same page (ctrl-click still opens a tab).
                thumbs = ''.join(
                    '<a href="/web/image/%d" class="o_sa_photo" data-group="%s" title="%s" style="display:inline-block;margin:0 8px 8px 0;text-align:center;font-size:11px;color:#64748b">'
                    '<img src="/web/image/%d/160x160" style="width:120px;height:120px;object-fit:cover;border:1px solid #cbd5e1;border-radius:6px"/><br/>%s<br/><span style="color:#0f172a">%s</span></a>'
                    % (a.id, group, html_escape(a.name or ''), a.id, html_escape(a.name or ''),
                       fields.Datetime.context_timestamp(job.with_context(tz=tz), a.create_date).strftime('%d %b %H:%M:%S') if a.create_date else '')
                    for a in photos.sorted('id'))
                parts.append('<div style="margin-bottom:6px"><b>%s (%d)</b></div><div>%s</div>'
                             % (html_escape(label), len(photos), thumbs))
            job.sa_photos_html = ''.join(parts) or False
            missing = job.sa_photos_missing_list() if job.sa_delivery_state not in ('none', False) else []
            names = {'pickup': _("pickup %(n)s of %(m)s", n=len(job.sa_pickup_photo_ids), m=low),
                     'delivery': _("delivery %(n)s of %(m)s", n=len(job.sa_delivery_photo_ids), m=low)}
            job.sa_photos_missing = ', '.join(names[k] for k in missing) or False

    def sa_photo_refusal(self):
        """'' when the rider may still send photos for this job, else why not."""
        self.ensure_one()
        state = self.sa_delivery_state or 'none'
        if state in self._SA_PHOTO_CLOSED:
            return _("This delivery is not open for photos.")
        if state in self._SA_PHOTO_FINISHED:
            done = self.sa_delivered_on or self.sa_returned_on or self.write_date
            if done and (fields.Datetime.now() - done) > timedelta(hours=24):
                return _("Photos can be sent for 24 hours after the delivery is finished.")
        return ''

    def sa_add_proof_photo(self, stage, filename, payload):
        """Keep one photo. Returns a dict for the API: attachment_id, stage,
        name, count, duplicate - or {'error': code, 'message': ...}."""
        self.ensure_one()
        import base64
        import re
        job = self.sudo()
        stage = (stage or '').strip().lower()
        if stage not in ('pickup', 'delivery'):
            # an older app build sends no stage: before the door it is pickup
            stage = 'delivery' if job.sa_delivery_state in ('out_for_delivery', 'delivered') else 'pickup'
        refusal = job.sa_photo_refusal()
        if refusal:
            return {'error': 'wrong_state', 'message': refusal}
        field = 'sa_pickup_photo_ids' if stage == 'pickup' else 'sa_delivery_photo_ids'
        photos = job[field]
        name = re.sub(r'[^A-Za-z0-9._ -]+', '_', (filename or '').replace('\\', '/').split('/')[-1]).strip(' .')[:120]
        if not name:
            name = 'proof-%s-%s.jpg' % (job.sa_ref_code or job.id, fields.Datetime.now().strftime('%Y%m%d-%H%M%S'))
        same = photos.filtered(lambda a: a.name == name)[:1]
        if same:
            # the same photo sent again after a lost reply: not a second copy
            return {'attachment_id': same.id, 'stage': stage, 'name': same.name,
                    'count': len(photos), 'duplicate': True}
        _low, high = job._sa_photo_limits()
        if len(photos) >= high:
            return {'error': 'too_many_photos', 'count': len(photos), 'max': high,
                    'message': _("%(n)s photos are already saved for %(stage)s - that is the most.",
                                 n=len(photos), stage=stage)}
        att = self.env['ir.attachment'].sudo().create({
            'name': name, 'res_model': 'stock.picking', 'res_id': job.id,
            'datas': base64.b64encode(payload),
            'description': 'Parcel photo - %s' % stage,
        })
        job.write({field: [(4, att.id)]})
        job._sa_check_photo_name_time(att)
        return {'attachment_id': att.id, 'stage': stage, 'name': name,
                'count': len(photos) + 1, 'duplicate': False}

    def _sa_check_photo_name_time(self, att, minutes=10):
        """The app names a photo <order>_<DDMMYY>_<HHmmss> in the company's
        zone. A name time far from the received time means a wrong clock or
        zone on the phone: say so on the job, at once."""
        import re
        from datetime import datetime
        self.ensure_one()
        m = re.search(r'_(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.', att.name or '')
        if not m:
            return False
        try:
            tz = self.env['sa.delivery.partner']._sa_company_tz(self.company_id or self.env.company)
            received = fields.Datetime.context_timestamp(self.with_context(tz=tz), att.create_date or fields.Datetime.now())
            d, mo, y, h, mi, sec = (int(x) for x in m.groups())
            named = received.replace(year=2000 + y, month=mo, day=d, hour=h, minute=mi, second=sec, microsecond=0)
            gap = (received - named).total_seconds() / 60.0
        except (ValueError, OverflowError):
            return False
        if abs(gap) > minutes:
            self.message_post(body=_(
                "Photo %(name)s: the time in its name is %(gap)s minutes %(way)s the time it reached the server "
                "(%(recv)s %(tz)s). The phone's clock or time zone is probably wrong.",
                name=att.name, gap=int(abs(gap)), way=_("before") if gap > 0 else _("after"),
                recv=received.strftime('%d %b %H:%M:%S'), tz=tz))
            _logger.info("Parcel photo %s on %s: name time is %.0f min from the received time (%s)",
                         att.name, self.sa_ref_code or self.name, gap, tz)
            return True
        return False

    def sa_photos_block(self, prefix):
        """For the apps: the photos of both ends, with a link each
        (`prefix` + the attachment id; fetched with the same headers)."""
        self.ensure_one()

        tz = self.env['sa.delivery.partner']._sa_company_tz(self.company_id or self.env.company)

        def rows(photos):
            return [{'id': a.id, 'name': a.name or '', 'url': '%s/%d' % (prefix, a.id),
                     'size': a.file_size or 0,
                     'at': (a.create_date.replace(microsecond=0).isoformat() + 'Z') if a.create_date else '',
                     # the same moment in the company's zone, to compare with the name
                     'at_local': (fields.Datetime.context_timestamp(self.with_context(tz=tz), a.create_date)
                                  .strftime('%Y-%m-%d %H:%M:%S')) if a.create_date else ''}
                    for a in photos.sudo().sorted('id')]
        return {'timezone': tz, 'pickup': rows(self.sa_pickup_photo_ids), 'delivery': rows(self.sa_delivery_photo_ids)}

    def sa_photo_for(self, attachment_id):
        """The attachment, only when it is one of this job's parcel photos."""
        self.ensure_one()
        att = (self.sudo().sa_pickup_photo_ids | self.sudo().sa_delivery_photo_ids).filtered(
            lambda a: a.id == int(attachment_id or 0))[:1]
        return att


class SaDeliveryPartnerNumbers(models.Model):
    _inherit = 'sa.delivery.partner'

    @api.model
    def sa_money_block(self, amount, currency):
        """{amount, formatted}: the number and how to print it."""
        places = currency.decimal_places if currency else 2
        value = round(amount or 0.0, places)
        symbol = (currency.symbol or currency.name or '') if currency else ''
        text = '{:,.{p}f}'.format(value, p=places)
        if currency and currency.position == 'after':
            text = ('%s %s' % (text, symbol)).strip()
        else:
            text = '%s%s' % (symbol, text)
        return {'amount': value, 'formatted': text}

    def sa_period_starts(self):
        """Start of today / this week (Monday) / this month in the rider's
        own timezone, as naive UTC datetimes for searching."""
        self.ensure_one()
        import pytz
        from datetime import datetime
        tz = pytz.timezone(self.tz or self.env.company.partner_id.tz or 'UTC')
        now = datetime.now(pytz.utc).astimezone(tz)
        day = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        week = day - timedelta(days=day.weekday())
        month = day.replace(day=1)

        def utc(d):
            return tz.localize(d).astimezone(pytz.utc).replace(tzinfo=None)
        return {'today': utc(day), 'week': utc(week), 'month': utc(month)}

    def _sa_delivered_domain(self, since=None):
        dom = [('sa_delivery_partner_id', '=', self.id), ('sa_delivery_state', '=', 'delivered')]
        if since:
            dom.append(('sa_delivered_on', '>=', since))
        return dom

    def sa_delivered_counts(self):
        """delivered_today / delivered_week / delivered_month for the app."""
        self.ensure_one()
        Picking = self.env['stock.picking'].sudo()
        return {'delivered_%s' % k: Picking.search_count(self._sa_delivered_domain(v))
                for k, v in self.sa_period_starts().items()}

    def sa_earnings_by_period(self):
        """What a Delivery Partner earned: today, this week, this month and
        in total. Own riders are on salary - all zero."""
        self.ensure_one()
        Picking = self.env['stock.picking'].sudo()
        cur = self.env.company.currency_id
        paid = self.kind == 'third_party'

        def total(since=None):
            if not paid:
                return 0.0
            return sum(Picking.search(self._sa_delivered_domain(since)).mapped('sa_rider_fee'))
        out = self.sa_money_block(total(), cur)                 # amount / formatted = all time
        for key, since in self.sa_period_starts().items():
            out[key] = self.sa_money_block(total(since), cur)
        out['total'] = self.sa_money_block(total(), cur)
        return out


class SaDeliveryPingHeading(models.Model):
    _inherit = 'sa.delivery.ping'

    @api.model
    def _sa_record(self, picking, lat, lng, accuracy=0.0):
        """Also keep which way the rider is heading (0 = north, clockwise),
        from the last stored fix to this one."""
        old_lat, old_lng = picking.sa_rider_lat, picking.sa_rider_lng
        res = super()._sa_record(picking, lat, lng, accuracy)
        try:
            new_lat, new_lng = picking.sa_rider_lat, picking.sa_rider_lng
            if old_lat and old_lng and (old_lat, old_lng) != (new_lat, new_lng):
                p1, p2 = math.radians(old_lat), math.radians(new_lat)
                dl = math.radians(new_lng - old_lng)
                y = math.sin(dl) * math.cos(p2)
                x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
                picking.sudo().write({'sa_rider_heading': (math.degrees(math.atan2(y, x)) + 360.0) % 360.0})
        except Exception:  # noqa: BLE001
            pass
        try:
            # every position, moved or not: the dwell time is counted on them
            picking._sa_check_auto_near(lat, lng, accuracy)
        except Exception as err:  # noqa: BLE001 - a position must never fail over this
            _logger.warning("Auto near: check for %s failed: %s", picking.name, err)
        return res
