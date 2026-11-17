# -*- coding: utf-8 -*-
"""The office live map (6 Oct 2026, "live tracking for every role"): every
rider on one map, coloured free / on a run / no signal, each run's stops in
order with minutes to each, a 30-minute trail, the shops and the orders
waiting for a rider. One method, `sa_fleet_snapshot(shop_id)`, drawn by the
Delivery > Fleet > Live Map screen and by the Shop Queue's "Live map" (that
one filtered to the shop). Read only: it changes nothing."""
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)
_ON_ROAD = ('picked', 'dispatched', 'out_for_delivery')
_WAITING = ('ready', 'to_assign', 'offered')


class StockPickingFleetMap(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def _sa_fleet_extra_shops(self, shops, shop_id=None):
        """More places to draw as shops on the live map, as dicts shaped like
        `shops` plus 'extra': True. None here; the storefront adds its
        branches."""
        return []

    @api.model
    def sa_fleet_snapshot(self, shop_id=None, trail_minutes=30):
        """{riders, shops, waiting, at}. Riders: on duty, or off duty but
        still holding a parcel; a shop filter keeps the riders allowed at
        that shop (no shop restriction = every shop) and that shop's orders."""
        now = fields.Datetime.now()
        Ping = self.env['sa.delivery.ping'].sudo()
        Rider = self.env['sa.delivery.partner'].sudo()
        shop_id = int(shop_id or 0) or None
        shops = self.env['sa.delivery.shop'].sudo().search([])
        if shop_id:
            shops = shops.filtered(lambda s: s.id == shop_id)
        on_road = self.sudo().search([('sa_delivery_state', 'in', _ON_ROAD), ('sa_delivery_partner_id', '!=', False)]
                                     + ([('sa_shop_id', '=', shop_id)] if shop_id else []))
        riders = Rider.search(['|', ('on_duty', '=', True), ('id', 'in', on_road.mapped('sa_delivery_partner_id').ids)])
        if shop_id:
            riders = riders.filtered(lambda r: not r.shop_ids or shop_id in r.shop_ids.ids)
        since = now - timedelta(minutes=trail_minutes)

        sos_ids = set(Rider._sa_sos_open_ids()) if hasattr(Rider, '_sa_sos_open_ids') else set()
        # Unpinned places are shown where the customer's tracking page already
        # looked them up (cached), never looked up again on every refresh.
        cached = self.with_context(sa_geo_cache_only=True)
        out_riders = []
        for r in riders:
            jobs = on_road.filtered(lambda j: j.sa_delivery_partner_id.id == r.id)
            # position: the freshest of the rider's own last fix and the job's
            lat, lng, fix = r.last_lat, r.last_lng, r.last_fix_on
            heading = None
            for j in jobs:
                if j.sa_rider_lat and j.sa_rider_fix_on and (not fix or j.sa_rider_fix_on > fix):
                    lat, lng, fix = j.sa_rider_lat, j.sa_rider_lng, j.sa_rider_fix_on
                    heading = j.sa_rider_heading or None
            age = int((now - fix).total_seconds()) if fix else None
            has_pos = bool(lat and lng)
            if r.id in sos_ids:
                state = 'sos'                       # outranks everything: somebody must go
            elif jobs:
                state = 'run' if (has_pos and age is not None and age <= 600) else 'no_signal'
            elif not r.on_duty:
                state = 'off'
            else:
                state = 'free' if (has_pos and age is not None and age <= 600) else 'no_signal'
            stops, trail = [], []
            if jobs:
                ordered = jobs[0]._sa_run_jobs().filtered(lambda j: j.id in jobs.ids) if len(jobs) > 1 else jobs
                speed = jobs[0]._sa_recent_speed_kmh() if has_pos else 20.0
                plat, plng, minutes = (lat, lng, 0.0) if has_pos else (None, None, None)
                for n, j in enumerate(ordered, 1):
                    clat, clng = j._sa_customer_position()
                    approx = False
                    if not (clat and clng):
                        clat, clng, approx = cached.browse(j.id)._sa_track_drop_fallback()
                    km = None
                    if plat and clat:
                        km = round(Ping._sa_metres(plat, plng, clat, clng) * 1.3 / 1000.0, 1)
                        minutes = (minutes or 0) + km / speed * 60
                        plat, plng = clat, clng
                    elif clat:
                        plat, plng = clat, clng
                    stops.append({
                        'job_id': j.id, 'ref': j.sa_ref_code or j.name, 'customer': j.partner_id.name or '',
                        'latitude': clat, 'longitude': clng, 'approximate': bool(approx and clat),
                        'stop_no': n, 'state': j.sa_delivery_state,
                        'km': km, 'minutes': int(round(minutes)) if (km is not None and minutes is not None) else None,
                        'kind': j.sa_delivery_kind or 'quick', 'paid': not j.sa_amount_due(),
                        'current': bool(j.sa_run_current) or (n == 1),
                    })
                pings = Ping.search([('picking_id', 'in', jobs.ids), ('create_date', '>=', since)], order='id asc', limit=300)
                trail = [[p.latitude, p.longitude] for p in pings]
            out_riders.append({
                'id': r.id, 'name': r.name, 'phone': r.phone or '', 'state': state, 'on_duty': bool(r.on_duty),
                'latitude': lat if has_pos else None, 'longitude': lng if has_pos else None,
                # degrees from north, clockwise; None = the map works it out
                # from the rider's last move
                'heading': heading if has_pos else None,
                'age_seconds': age, 'where': r.address_short or '', 'vehicle': getattr(r, 'vehicle', '') or '',
                'stops': stops, 'trail': trail,
                'shop_ids': r.shop_ids.ids,
            })
        order = {'sos': -1, 'run': 0, 'free': 1, 'no_signal': 2, 'off': 3}
        out_riders.sort(key=lambda x: (order.get(x['state'], 9), x['name'] or ''))

        out_shops = []
        for s in shops:
            slat, slng = s._sa_position()
            approx = False
            if not (slat and slng):
                slat, slng = cached._sa_track_lookup(cached._sa_address_texts(s._sa_address()))
                approx = bool(slat)
            out_shops.append({'id': s.id, 'name': s.name, 'latitude': slat, 'longitude': slng,
                              'approximate': approx})
        out_shops += self._sa_fleet_extra_shops(out_shops, shop_id)
        waiting = self.sudo().search([('sa_delivery_state', 'in', _WAITING)]
                                     + ([('sa_shop_id', '=', shop_id)] if shop_id else []), order='id asc')
        out_waiting = []
        for j in waiting:
            clat, clng = j._sa_customer_position()
            approx = False
            if not (clat and clng):
                clat, clng, approx = cached.browse(j.id)._sa_track_drop_fallback()
            slat, slng = j.sa_shop_position()
            km = round(Ping._sa_metres(slat, slng, clat, clng) / 1000.0, 1) if (slat and clat and not approx) else None
            out_waiting.append({
                'job_id': j.id, 'ref': j.sa_ref_code or j.name, 'customer': j.partner_id.name or '',
                'latitude': clat, 'longitude': clng, 'approximate': bool(approx and clat),
                'km': km, 'shop': j.sa_shop_id.name or '',
                'shop_id': j.sa_shop_id.id, 'state': j.sa_delivery_state, 'kind': j.sa_delivery_kind or 'quick',
                'offered_to': j.sa_delivery_partner_id.name if j.sa_delivery_state == 'offered' else '',
                'missed_by': ', '.join(j.sa_declined_partner_ids.mapped('name')),
                'waiting_min': getattr(j, 'sa_waiting_minutes', 0) or 0,
            })
        return {'riders': out_riders, 'shops': [s for s in out_shops if s.get('latitude') or not s.get('extra')],
                'waiting': out_waiting,
                'at': now.replace(microsecond=0).isoformat() + 'Z',
                'counts': {'riders': len([r for r in out_riders if r['state'] != 'off']),
                           'waiting': len(out_waiting)}}
