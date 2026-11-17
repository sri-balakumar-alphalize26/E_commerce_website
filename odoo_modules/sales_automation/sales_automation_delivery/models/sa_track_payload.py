# -*- coding: utf-8 -*-
"""The customer's tracking page, decided on the server (app team's "Track my
order" asks, 6 Oct 2026): who may see the rider (Quick: live from pickup;
Express: route only until this customer is the next stop), the stop order
of a run, a road route and an arrival time, "last seen" and the end of
sharing - all in one method, `sa_track_payload()`, that the WhatsApp page
and any other customer app read."""
import logging
import math
from datetime import timedelta

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)
_UA = 'sales_automation_delivery/19 (tracking)'
_ON_ROAD = ('picked', 'dispatched', 'out_for_delivery')
_ENDED = ('delivered', 'failed', 'returned', 'cancelled')


def _encode_polyline(points):
    """Google's encoded polyline, from [(lat, lng), ...]."""
    out = []
    last_lat = last_lng = 0
    for lat, lng in points:
        for value, last in ((int(round(lat * 1e5)), last_lat), (int(round(lng * 1e5)), last_lng)):
            d = value - last
            d = ~(d << 1) if d < 0 else (d << 1)
            while d >= 0x20:
                out.append(chr((0x20 | (d & 0x1f)) + 63))
                d >>= 5
            out.append(chr(d + 63))
        last_lat, last_lng = int(round(lat * 1e5)), int(round(lng * 1e5))
    return ''.join(out)


class SaDeliverySettingsTrack(models.Model):
    _inherit = 'sa.delivery.settings'

    route_provider = fields.Selection([
        ('none', 'Straight line only'),
        ('osrm', 'Road route (OSRM public server, no key)'),
    ], 'Road route for the tracking page', default='osrm', required=True,
        help="Worked out once when the parcel leaves the shop and kept on the "
             "job. The straight line is used whenever the road service does "
             "not answer.")
    track_stale_seconds = fields.Integer(
        'Rider position counts as stale after (seconds)', default=120,
        help="The customer's page greys the dot and says 'Last seen ...'.")


class SaDeliveryPartnerVehicle(models.Model):
    _inherit = 'sa.delivery.partner'

    vehicle = fields.Char('Vehicle', help="Shown to the customer, e.g. 'Bike · TN 57 AK 4821'.")


class StockPickingTrack(models.Model):
    _inherit = 'stock.picking'

    sa_run_current = fields.Boolean(
        'Current Stop', copy=False, readonly=True,
        help="The rider's app said the rider is heading to this customer now.")
    sa_run_sequence = fields.Integer(
        'Run Order', default=0, copy=False,
        help="The office's stop order on a multi-parcel run (1, 2, 3 ...). "
             "0 = not set: the nearest open drop is taken as next.")
    sa_route_polyline = fields.Text('Route (encoded polyline)', copy=False, readonly=True)
    sa_route_km = fields.Float('Route (km)', copy=False, readonly=True)
    sa_route_approx = fields.Boolean('Route is Approximate', copy=False, readonly=True)
    sa_route_on = fields.Datetime(copy=False, readonly=True)
    sa_next_told = fields.Boolean(copy=False, readonly=True)

    # ------------------------------------------------------------------
    # The run: which stop is next
    # ------------------------------------------------------------------
    def _sa_run_jobs(self):
        """The rider's parcels on the road, in stop order: the one the rider
        said they are heading to, then the office's run order, then nearest
        first from the rider's last position."""
        self.ensure_one()
        rider = self.sa_delivery_partner_id
        if not rider:
            return self
        jobs = self.env['stock.picking'].sudo().search(
            [('sa_delivery_partner_id', '=', rider.id), ('sa_delivery_state', 'in', _ON_ROAD)])
        if not jobs:
            return self.sudo()
        lat, lng = rider.last_lat, rider.last_lng
        Ping = self.env['sa.delivery.ping'].sudo()

        def key(j):
            clat, clng = j._sa_customer_position()
            dist = Ping._sa_metres(lat, lng, clat, clng) if (lat and lng and clat and clng) else 1e9
            return (0 if j.sa_run_current else 1,
                    0 if j.sa_run_sequence else 1, j.sa_run_sequence or 0,
                    0 if j.sa_delivery_state == 'out_for_delivery' else 1,
                    dist, j.id)
        return jobs.sorted(key)

    def sa_run_info(self):
        self.ensure_one()
        run = self._sa_run_jobs()
        ids = run.ids
        no = ids.index(self.id) + 1 if self.id in ids else 1
        return {'stop_no': no, 'stops_total': max(1, len(ids)), 'stops_before': max(0, no - 1),
                'is_current_stop': no == 1}

    def sa_action_heading(self, rider=None):
        """The rider's app: 'I am heading to this customer now'."""
        self.ensure_one()
        job = self.sudo()
        if job.sa_delivery_state not in _ON_ROAD:
            return None
        others = self.env['stock.picking'].sudo().search(
            [('sa_delivery_partner_id', '=', job.sa_delivery_partner_id.id),
             ('sa_run_current', '=', True), ('id', '!=', job.id)])
        others.write({'sa_run_current': False})
        if not job.sa_run_current:
            job.write({'sa_run_current': True})
        info = job.sa_run_info()
        if job.sa_delivery_kind == 'express' and not job.sa_next_told and info['stops_total'] > 1:
            link = job.sudo().sa_track_url or ''
            try:
                job._sa_tell_customer(_(
                    "\U0001F6F5 You're next! Order *#%(ref)s* is the rider's next stop.%(tail)s",
                    ref=job.sa_ref_code or '-', tail=(_("\n\nTrack your rider live:\n%s", link) if link else '')))
            except Exception as err:  # noqa: BLE001
                _logger.warning("Tracking: 'you're next' for %s failed: %s", job.sa_ref_code, err)
            job.write({'sa_next_told': True})
        _logger.info("Tracking: %s is heading to %s (stop %s of %s)", job.sa_delivery_partner_id.name,
                     job.sa_ref_code, info['stop_no'], info['stops_total'])
        return info

    # ------------------------------------------------------------------
    # The road route, once, when the parcel leaves
    # ------------------------------------------------------------------
    def sa_compute_route(self):
        """Shop -> drop pin. OSRM when allowed and answering, else the straight
        line (approximate). Never raises."""
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        Ping = self.env['sa.delivery.ping'].sudo()
        for job in self.sudo():
            try:
                slat, slng = job.sa_shop_position()
                dlat, dlng = job._sa_customer_position()
                if not (slat and slng and dlat and dlng):
                    job.write({'sa_route_polyline': False, 'sa_route_km': 0.0, 'sa_route_approx': True,
                               'sa_route_on': fields.Datetime.now()})
                    continue
                approx_pin = job.sa_pin_source in ('geocoded', 'door') and not (job.sa_drop_lat and job.sa_drop_lng)
                poly, km, approx = None, 0.0, True
                if (settings.route_provider or 'osrm') == 'osrm':
                    try:
                        r = requests.get(
                            'https://router.project-osrm.org/route/v1/driving/%.6f,%.6f;%.6f,%.6f'
                            % (slng, slat, dlng, dlat),
                            params={'overview': 'full', 'geometries': 'polyline'},
                            headers={'User-Agent': _UA}, timeout=4)
                        data = r.json() if r.status_code == 200 else {}
                        route = (data.get('routes') or [None])[0]
                        if route and route.get('geometry'):
                            poly = route['geometry']
                            km = round((route.get('distance') or 0.0) / 1000.0, 2)
                            approx = approx_pin
                    except Exception as err:  # noqa: BLE001
                        _logger.info("Tracking: road route for %s not available (%s) - straight line", job.sa_ref_code, err)
                if not poly:
                    poly = _encode_polyline([(slat, slng), (dlat, dlng)])
                    km = round(Ping._sa_metres(slat, slng, dlat, dlng) * 1.3 / 1000.0, 2)
                    approx = True
                job.write({'sa_route_polyline': poly, 'sa_route_km': km, 'sa_route_approx': approx,
                           'sa_route_on': fields.Datetime.now()})
            except Exception as err:  # noqa: BLE001
                _logger.warning("Tracking: route for %s failed: %s", job.name, err)
        return True

    def sa_set_state(self, state):
        res = super().sa_set_state(state)
        if state == 'dispatched':
            self.sa_compute_route()
        return res

    def _sa_set_drop_point(self, lat, lng, label):
        res = super()._sa_set_drop_point(lat, lng, label)
        if self.sa_delivery_state in _ON_ROAD:
            self.sa_compute_route()
        return res

    # ------------------------------------------------------------------
    # Speed and arrival
    # ------------------------------------------------------------------
    def _sa_recent_speed_kmh(self):
        """From the job's positions of the last 5 minutes; 20 km/h when
        unknown; never below 15, never above 60."""
        self.ensure_one()
        since = fields.Datetime.now() - timedelta(minutes=5)
        pings = self.env['sa.delivery.ping'].sudo().search(
            [('picking_id', '=', self.id), ('create_date', '>=', since)], order='id asc')
        if len(pings) >= 2:
            Ping = self.env['sa.delivery.ping'].sudo()
            metres = sum(Ping._sa_metres(a.latitude, a.longitude, b.latitude, b.longitude)
                         for a, b in zip(pings, pings[1:]))
            secs = (pings[-1].create_date - pings[0].create_date).total_seconds()
            if secs > 20 and metres > 30:
                return max(15.0, min(60.0, metres / secs * 3.6))
        return 20.0

    # ------------------------------------------------------------------
    # Where the customer's map puts things (display only)
    # ------------------------------------------------------------------
    # The real positions - sa_shop_position() and _sa_customer_position() -
    # decide the route, the arrival time, the rider's pay and who is called.
    # They stay exactly as they are. The map only needs *something* to show
    # while those are still empty (an order being packed has no customer pin
    # yet, a database may never have pinned its shop), so these fill the gap
    # for the picture alone and say when they are approximate.

    @staticmethod
    def _sa_address_texts(partner, city_only=False):
        """Address lines to look a partner up by, most precise first."""
        if not partner:
            return []
        p = partner.sudo()
        if city_only:
            texts = [', '.join(filter(None, [p.city, p.zip, p.state_id.name, p.country_id.name])),
                     ', '.join(filter(None, [p.state_id.name, p.country_id.name]))]
        else:
            texts = [', '.join(filter(None, [p.street, p.street2, p.city, p.zip, p.state_id.name, p.country_id.name])),
                     ', '.join(filter(None, [p.street2 or p.street, p.city, p.zip, p.country_id.name]))]
        out = []
        for text in texts:
            if text and len(text) >= 4 and text not in out:
                out.append(text)
        return out

    def _sa_track_lookup(self, texts):
        """(lat, lng) of the first text the address service finds, cached."""
        Geo = self.env['sa.geocode.cache'].sudo()
        for text in texts:
            lat, lng = Geo.sa_forward(text)
            if lat and lng:
                return lat, lng
        return None, None

    def _sa_track_shop_fallback(self):
        """(lat, lng, approximate) for the shop pin when the job has none."""
        self.ensure_one()
        job = self.sudo()
        partners = [job.sa_shop_id._sa_address() if job.sa_shop_id else None,
                    job.picking_type_id.warehouse_id.partner_id, job.company_id.partner_id]
        partners = [p for p in partners if p]
        for p in partners:
            if p.partner_latitude and p.partner_longitude:
                return p.partner_latitude, p.partner_longitude, False
        texts = []
        for p in partners:
            texts += [t for t in self._sa_address_texts(p) if t not in texts]
        lat, lng = self._sa_track_lookup(texts)
        return lat, lng, True

    def _sa_track_drop_fallback(self):
        """(lat, lng, approximate) for the customer pin when the job has none:
        the typed address looked up, never written onto the contact."""
        self.ensure_one()
        lat, lng = self._sa_track_lookup(self._sa_address_texts(self.sudo().partner_id))
        return lat, lng, True

    def _sa_track_center(self):
        """(lat, lng) to centre an empty map on: the customer's town, else the shop's."""
        self.ensure_one()
        job = self.sudo()
        texts = self._sa_address_texts(job.partner_id, city_only=True)
        for p in (job.sa_shop_id._sa_address() if job.sa_shop_id else None,
                  job.picking_type_id.warehouse_id.partner_id, job.company_id.partner_id):
            texts += [t for t in self._sa_address_texts(p, city_only=True) if t not in texts]
        return self._sa_track_lookup(texts)

    def _sa_track_places(self):
        """{'shop', 'dropoff', 'center'} for the customer's map. Never raises."""
        self.ensure_one()
        job = self.sudo()

        def block(lat, lng, approx):
            return {'latitude': lat or None, 'longitude': lng or None, 'approximate': bool(approx and lat)}

        try:
            slat, slng = job.sa_shop_position()
            s_approx = False
            if not (slat and slng):
                slat, slng, s_approx = job._sa_track_shop_fallback()
            dlat, dlng = job._sa_customer_position()
            d_approx = bool(dlat and job.sa_pin_source in ('geocoded', 'door')
                            and not (job.sa_drop_lat and job.sa_drop_lng))
            if not (dlat and dlng):
                dlat, dlng, d_approx = job._sa_track_drop_fallback()
            center = None
            if not (slat and slng) and not (dlat and dlng):
                clat, clng = job._sa_track_center()
                if clat and clng:
                    center = {'latitude': clat, 'longitude': clng}
            return {'shop': block(slat, slng, s_approx), 'dropoff': block(dlat, dlng, d_approx), 'center': center}
        except Exception:  # noqa: BLE001 - the page always shows
            _logger.exception("Tracking: map places for %s failed", job.sa_ref_code or job.id)
            slat, slng = job.sa_shop_position()
            dlat, dlng = job._sa_customer_position()
            return {'shop': block(slat, slng, False), 'dropoff': block(dlat, dlng, False), 'center': None}

    # ------------------------------------------------------------------
    # The one answer
    # ------------------------------------------------------------------
    def sa_track_payload(self):
        """Everything the customer's page draws. Public: the WhatsApp page
        and a customer app read the same dict (the caller does the token
        or sign-in check)."""
        self.ensure_one()
        job = self.sudo()
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        state = job.sa_delivery_state or 'none'
        kind = job.sa_delivery_kind or 'quick'
        rider = job.sa_delivery_partner_id
        ended = state in _ENDED
        on_road = state in _ON_ROAD
        run = job.sa_run_info() if on_road and rider else {'stop_no': 1, 'stops_total': 1, 'stops_before': 0,
                                                            'is_current_stop': on_road}
        relaying = bool(getattr(job, 'sa_relay_state', False))
        show = bool(on_road and rider and rider.on_duty and not relaying
                    and (kind != 'express' or run['is_current_stop']))
        now = fields.Datetime.now()
        pos = job.sa_live_position() if show else {}
        rider_block = None
        if show and pos.get('lat'):
            age = int((now - pos['fix_on']).total_seconds()) if pos.get('fix_on') else None
            rider_block = {'latitude': pos['lat'], 'longitude': pos['lng'],
                           'heading': job.sa_rider_heading or None,
                           'fix_at': (pos['fix_on'].replace(microsecond=0).isoformat() + 'Z') if pos.get('fix_on') else '',
                           'age_seconds': age,
                           'stale': bool(age is not None and age > max(30, settings.track_stale_seconds or 120))}
        slat, slng = job.sa_shop_position()
        dlat, dlng = job._sa_customer_position()
        Ping = self.env['sa.delivery.ping'].sudo()
        eta = {'minutes': None, 'window_from': None, 'window_to': None}
        if show and rider_block and dlat and dlng:
            left_km = Ping._sa_metres(rider_block['latitude'], rider_block['longitude'], dlat, dlng) * 1.3 / 1000.0
            eta['minutes'] = max(1, int(round(left_km / job._sa_recent_speed_kmh() * 60)))
        elif not ended and job.sa_promised_on:
            eta['window_to'] = job.sa_promised_on.replace(microsecond=0).isoformat() + 'Z'
            if kind == 'express':
                eta['window_from'] = (job.sa_promised_on - timedelta(hours=2)).replace(microsecond=0).isoformat() + 'Z'
        if on_road and not job.sa_route_polyline and slat and dlat:
            job.sa_compute_route()
        near = bool(show and rider_block and dlat and
                    Ping._sa_metres(rider_block['latitude'], rider_block['longitude'], dlat, dlng) <= 600)
        places = job._sa_track_places()
        return {
            'kind': kind, 'state': state, 'ended': ended, 'show_rider': show,
            'rider': rider_block,
            'rider_name': (rider.name or '') if rider and (on_road or state == 'accepted') else '',
            'vehicle': (getattr(rider, 'vehicle', '') or '') if rider and (on_road or state == 'accepted') else '',
            'run': run if on_road else None,
            'eta': eta,
            'route': ({'polyline': job.sa_route_polyline, 'km': job.sa_route_km or 0.0,
                       'approximate': bool(job.sa_route_approx)}
                      if job.sa_route_polyline and (on_road or state in ('ready', 'offered', 'accepted', 'to_assign'))
                      and (kind != 'express' or state in _ON_ROAD or state == 'accepted') else None),
            # What the map shows: the real pins when known, else approximate
            # ones, else a town to centre on (see _sa_track_places).
            'shop': places['shop'],
            'dropoff': places['dropoff'],
            'center': places['center'],
            'show_code': bool(state == 'out_for_delivery' and job.sa_arrived_customer_on),
            'next_poll_seconds': 60 if ended else (10 if (state == 'out_for_delivery' or near) else 20),
        }

    def sa_problem_overlay(self, viewer):
        out = super().sa_problem_overlay(viewer)
        if self.sa_delivery_state in _ON_ROAD and self.sa_delivery_partner_id:
            info = self.sudo().sa_run_info()
            out.update({'run_stop_no': info['stop_no'], 'run_stops_total': info['stops_total'],
                        'is_current_stop': info['is_current_stop']})
        else:
            out.update({'run_stop_no': None, 'run_stops_total': None, 'is_current_stop': False})
        return out
