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
        out_riders = []
        for r in riders:
            jobs = on_road.filtered(lambda j: j.sa_delivery_partner_id.id == r.id)
            # position: the freshest of the rider's own last fix and the job's
            lat, lng, fix = r.last_lat, r.last_lng, r.last_fix_on
            for j in jobs:
                if j.sa_rider_lat and j.sa_rider_fix_on and (not fix or j.sa_rider_fix_on > fix):
                    lat, lng, fix = j.sa_rider_lat, j.sa_rider_lng, j.sa_rider_fix_on
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
                    km = None
                    if plat and clat:
                        km = round(Ping._sa_metres(plat, plng, clat, clng) * 1.3 / 1000.0, 1)
                        minutes = (minutes or 0) + km / speed * 60
                        plat, plng = clat, clng
                    elif clat:
                        plat, plng = clat, clng
                    stops.append({
                        'job_id': j.id, 'ref': j.sa_ref_code or j.name, 'customer': j.partner_id.name or '',
                        'latitude': clat, 'longitude': clng, 'stop_no': n, 'state': j.sa_delivery_state,
                        'km': km, 'minutes': int(round(minutes)) if (km is not None and minutes is not None) else None,
                        'kind': j.sa_delivery_kind or 'quick', 'paid': not j.sa_amount_due(),
                        'current': bool(j.sa_run_current) or (n == 1),
                    })
                pings = Ping.search([('picking_id', 'in', jobs.ids), ('create_date', '>=', since)], order='id asc', limit=300)
                trail = [[p.latitude, p.longitude] for p in pings]
            out_riders.append({
                'id': r.id, 'name': r.name, 'phone': r.phone or '', 'state': state, 'on_duty': bool(r.on_duty),
                'latitude': lat if has_pos else None, 'longitude': lng if has_pos else None,
                'age_seconds': age, 'where': r.address_short or '', 'vehicle': getattr(r, 'vehicle', '') or '',
                'stops': stops, 'trail': trail,
                'shop_ids': r.shop_ids.ids,
            })
        order = {'sos': -1, 'run': 0, 'free': 1, 'no_signal': 2, 'off': 3}
        out_riders.sort(key=lambda x: (order.get(x['state'], 9), x['name'] or ''))

        out_shops = [{'id': s.id, 'name': s.name, 'latitude': s._sa_position()[0], 'longitude': s._sa_position()[1]}
                     for s in shops]
        waiting = self.sudo().search([('sa_delivery_state', 'in', _WAITING)]
                                     + ([('sa_shop_id', '=', shop_id)] if shop_id else []), order='id asc')
        out_waiting = []
        for j in waiting:
            clat, clng = j._sa_customer_position()
            slat, slng = j.sa_shop_position()
            km = round(Ping._sa_metres(slat, slng, clat, clng) / 1000.0, 1) if (slat and clat) else None
            out_waiting.append({
                'job_id': j.id, 'ref': j.sa_ref_code or j.name, 'customer': j.partner_id.name or '',
                'latitude': clat, 'longitude': clng, 'km': km, 'shop': j.sa_shop_id.name or '',
                'shop_id': j.sa_shop_id.id, 'state': j.sa_delivery_state, 'kind': j.sa_delivery_kind or 'quick',
                'offered_to': j.sa_delivery_partner_id.name if j.sa_delivery_state == 'offered' else '',
                'missed_by': ', '.join(j.sa_declined_partner_ids.mapped('name')),
                'waiting_min': getattr(j, 'sa_waiting_minutes', 0) or 0,
            })
        return {'riders': out_riders, 'shops': out_shops, 'waiting': out_waiting,
                'at': now.replace(microsecond=0).isoformat() + 'Z',
                'counts': {'riders': len([r for r in out_riders if r['state'] != 'off']),
                           'waiting': len(out_waiting)}}
