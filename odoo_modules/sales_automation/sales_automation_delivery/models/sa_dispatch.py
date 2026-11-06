# -*- coding: utf-8 -*-
"""Call a Rider (3 Oct 2026, the senior's spec).

Priority 1  the shop picks an on-duty rider by hand.
Priority 2  the nearest free rider to the shop (Haversine, radius), longest
            idle first among near-equal distances.
Priority 3  exact ties -> random.choice.
Rule 0      one rider at a time, never a broadcast: the offer carries a
            timeout; no answer or a decline -> the next candidate.

Also here: reverse / forward geocoding (Nominatim, or Google with a key) with
a small cache, and the FCM HTTP v1 push to the one chosen rider's devices.
"""
import base64
import json
import logging
import random
import time
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)

_UA = 'sales_automation_delivery/1.0 (Odoo; contact the shop admin)'
_FCM_TOKEN = {}          # dbname -> (access_token, expires_at_epoch)
_BUSY_STATES = ('accepted', 'picked', 'dispatched', 'out_for_delivery', 'returning')


# ======================================================================
# Geocoding
# ======================================================================
class SaGeocodeCache(models.Model):
    _name = 'sa.geocode.cache'
    _description = 'Geocoding cache'
    _rec_name = 'key'

    key = fields.Char(required=True, index=True)
    short = fields.Char('Short address')
    full = fields.Char('Full address')
    lat = fields.Float(digits=(10, 7))
    lng = fields.Float(digits=(10, 7))

    def _settings(self):
        return self.env['sa.delivery.settings'].sudo().get_settings()

    @api.model
    def _nominatim(self, path, params):
        r = requests.get('https://nominatim.openstreetmap.org/' + path, params=params,
                         headers={'User-Agent': _UA, 'Accept-Language': 'en'}, timeout=4)
        r.raise_for_status()
        return r.json()

    @api.model
    def sa_reverse(self, lat, lng):
        """(short, full) for a point. Cached to 4 decimals (~11 m). Never raises."""
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            return '', ''
        if not lat and not lng:
            return '', ''
        key = 'r:%.4f,%.4f' % (lat, lng)
        row = self.sudo().search([('key', '=', key)], limit=1)
        if row:
            return row.short or '', row.full or ''
        short = full = ''
        try:
            s = self._settings()
            if s.geocode_provider == 'google' and s.geocode_google_key:
                r = requests.get('https://maps.googleapis.com/maps/api/geocode/json',
                                 params={'latlng': '%s,%s' % (lat, lng), 'key': s.geocode_google_key,
                                         'language': 'en'}, timeout=4).json()
                res = (r.get('results') or [{}])[0]
                full = res.get('formatted_address') or ''
                comps = {t: c['long_name'] for c in res.get('address_components', []) for t in c.get('types', [])}
                area = comps.get('sublocality') or comps.get('neighborhood') or comps.get('sublocality_level_1') or ''
                city = comps.get('locality') or comps.get('administrative_area_level_2') or comps.get('administrative_area_level_1') or ''
                short = ', '.join(x for x in (area, city) if x)
            else:
                r = self._nominatim('reverse', {'format': 'jsonv2', 'lat': lat, 'lon': lng, 'zoom': 16})
                full = r.get('display_name') or ''
                a = r.get('address') or {}
                area = (a.get('suburb') or a.get('neighbourhood') or a.get('quarter') or a.get('village')
                        or a.get('hamlet') or a.get('residential') or a.get('road') or '')
                city = a.get('city') or a.get('town') or a.get('county') or a.get('state') or ''
                short = ', '.join(x for x in (area, city) if x and x != area or x == area and x) if area or city else ''
                short = ', '.join(dict.fromkeys(x for x in (area, city) if x))
        except Exception as err:  # noqa: BLE001 - an address is a nicety, never a blocker
            _logger.info("Geocode reverse %s,%s failed: %s", lat, lng, err)
            return '', ''
        if short or full:
            self.sudo().create({'key': key, 'short': short[:120], 'full': full[:400], 'lat': lat, 'lng': lng})
        return short, full

    @api.model
    def sa_forward(self, text):
        """(lat, lng) for an address text, or (None, None). Never raises."""
        text = (text or '').strip()
        if not text:
            return None, None
        key = 'f:' + text.lower()[:180]
        row = self.sudo().search([('key', '=', key)], limit=1)
        if row and row.lat:
            return row.lat, row.lng
        try:
            s = self._settings()
            if s.geocode_provider == 'google' and s.geocode_google_key:
                r = requests.get('https://maps.googleapis.com/maps/api/geocode/json',
                                 params={'address': text, 'key': s.geocode_google_key}, timeout=4).json()
                loc = ((r.get('results') or [{}])[0].get('geometry') or {}).get('location') or {}
                lat, lng = loc.get('lat'), loc.get('lng')
            else:
                r = self._nominatim('search', {'format': 'jsonv2', 'q': text, 'limit': 1})
                lat = float(r[0]['lat']) if r else None
                lng = float(r[0]['lon']) if r else None
        except Exception as err:  # noqa: BLE001
            _logger.info("Geocode forward %r failed: %s", text[:60], err)
            return None, None
        if lat and lng:
            self.sudo().create({'key': key, 'lat': lat, 'lng': lng})
            return lat, lng
        return None, None


# ======================================================================
# Settings: push (FCM HTTP v1)
# ======================================================================
def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


class SaDeliverySettingsPush(models.Model):
    _inherit = 'sa.delivery.settings'

    def _sa_fcm_account(self):
        self.ensure_one()
        raw = (self.fcm_service_account_json or '').strip()
        if not raw:
            return None
        try:
            acc = json.loads(raw)
        except ValueError:
            return None
        if not acc.get('client_email') or not acc.get('private_key') or not acc.get('project_id'):
            return None
        return acc

    def _sa_fcm_access_token(self):
        """OAuth2 token for FCM v1, signed with the service-account key
        (cryptography ships with Odoo; no google library needed)."""
        acc = self._sa_fcm_account()
        if not acc:
            return None
        cached = _FCM_TOKEN.get(self.env.cr.dbname)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        now = int(time.time())
        header = _b64url(json.dumps({'alg': 'RS256', 'typ': 'JWT'}).encode())
        claims = _b64url(json.dumps({
            'iss': acc['client_email'], 'sub': acc['client_email'],
            'aud': acc.get('token_uri') or 'https://oauth2.googleapis.com/token',
            'scope': 'https://www.googleapis.com/auth/firebase.messaging',
            'iat': now, 'exp': now + 3600}).encode())
        signing_input = ('%s.%s' % (header, claims)).encode()
        key = serialization.load_pem_private_key(acc['private_key'].encode(), password=None,
                                                 backend=default_backend())
        sig = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        assertion = '%s.%s' % (signing_input.decode(), _b64url(sig))
        r = requests.post(acc.get('token_uri') or 'https://oauth2.googleapis.com/token',
                          data={'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                                'assertion': assertion}, timeout=8)
        r.raise_for_status()
        tok = r.json()
        _FCM_TOKEN[self.env.cr.dbname] = (tok['access_token'], time.time() + int(tok.get('expires_in', 3600)))
        return tok['access_token']

    def _sa_push(self, rider, data, title, body):
        """Send one push to every registered device of `rider`. Returns the
        number of devices reached. Never raises; the last error is kept on
        the settings form."""
        self.ensure_one()
        acc = self._sa_fcm_account()
        if not acc:
            return 0
        Tok = self.env['sa.delivery.token'].sudo()
        rows = Tok.search([('partner_id', '=', rider.id), ('revoked', '=', False),
                           ('push_token', '!=', False),
                           ('expires_on', '>', fields.Datetime.now())])
        if not rows:
            return 0
        try:
            access = self._sa_fcm_access_token()
        except Exception as err:  # noqa: BLE001
            self.sudo().write({'fcm_last_error': ('token: %s' % err)[:250]})
            _logger.warning("FCM: could not get an access token: %s", err)
            return 0
        url = 'https://fcm.googleapis.com/v1/projects/%s/messages:send' % acc['project_id']
        sent = 0
        payload_data = {k: str(v) for k, v in (data or {}).items() if v is not None}
        for row in rows:
            msg = {'message': {
                'token': row.push_token,
                'notification': {'title': title, 'body': body},
                'data': payload_data,
                'android': {'priority': 'high', 'notification': {'channel_id': 'sa_delivery_offers',
                                                                 'sound': 'default'}},
                'apns': {'headers': {'apns-priority': '10'},
                         'payload': {'aps': {'sound': 'default', 'content-available': 1}}},
            }}
            try:
                r = requests.post(url, json=msg, timeout=8,
                                  headers={'Authorization': 'Bearer ' + access,
                                           'Content-Type': 'application/json'})
                if r.status_code == 200:
                    sent += 1
                    continue
                text = r.text[:300]
                if r.status_code in (404, 410) or 'UNREGISTERED' in text or 'NOT_FOUND' in text:
                    row.write({'push_token': False})      # dead device token
                self.sudo().write({'fcm_last_error': ('%s: %s' % (r.status_code, text))[:250]})
                _logger.warning("FCM: %s -> %s %s", rider.name, r.status_code, text)
            except Exception as err:  # noqa: BLE001
                self.sudo().write({'fcm_last_error': str(err)[:250]})
                _logger.warning("FCM: send to %s failed: %s", rider.name, err)
        if sent:
            self.sudo().write({'fcm_last_error': False})
        return sent


# ======================================================================
# The job: candidates, ranking, Call a Rider, the timeout cascade
# ======================================================================
class StockPickingDispatch(models.Model):
    _inherit = 'stock.picking'

    _SA_CALL_FROM = ('ready', 'to_assign', 'offered')

    sa_offer_expires_on = fields.Datetime('Offer Expires', copy=False, readonly=True)
    sa_offer_round = fields.Integer('Riders Tried', copy=False, readonly=True, default=0)
    sa_call_log = fields.Text('Call Log', copy=False, readonly=True,
                              help="Who was called for this job, when, and why.")
    sa_offer_seconds_left = fields.Integer(compute='_compute_sa_offer_seconds_left')
    sa_call_pool_ids = fields.Many2many(
        'sa.delivery.partner', 'sa_picking_call_pool_rel', 'picking_id', 'partner_id',
        string='Riders Chosen', copy=False,
        help="Manual mode: the riders the shop ticked for this job. They are "
             "called one at a time, in rank order; nobody else is called.")

    def _compute_sa_offer_seconds_left(self):
        now = fields.Datetime.now()
        for p in self:
            if p.sa_delivery_state == 'offered' and p.sa_offer_expires_on:
                p.sa_offer_seconds_left = max(0, int((p.sa_offer_expires_on - now).total_seconds()))
            else:
                p.sa_offer_seconds_left = 0

    def _sa_call_log_add(self, line):
        self.ensure_one()
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d %b %H:%M:%S')
        old = self.sa_call_log or ''
        self.write({'sa_call_log': ((old + '\n') if old else '') + '%s  %s' % (stamp, line)})

    # ------------------------------------------------------------------
    def sa_shop_position(self):
        self.ensure_one()
        shop = self.sa_shop_id
        if shop:
            return shop._sa_position()
        wh = self.picking_type_id.warehouse_id.partner_id
        if wh and wh.partner_latitude and wh.partner_longitude:
            return wh.partner_latitude, wh.partner_longitude
        return None, None

    def sa_candidates(self, exclude=None, include_busy=True, include_off=False):
        """Every rider the dialog may show, with distance / idle / busy."""
        self.ensure_one()
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        Rider = self.env['sa.delivery.partner'].sudo()
        riders = Rider.search([('on_duty', '=', True)] if not include_off else [])
        if self.sa_shop_id:
            riders = riders.filtered(lambda r: not r.shop_ids or self.sa_shop_id in r.shop_ids)
        skip = (self.sa_declined_partner_ids | (exclude or Rider)).sudo()
        riders = riders - skip
        # distances are from the shop - or, for a rider-to-rider handover, from
        # wherever the parcel is (context `sa_origin`)
        lat0, lng0 = self.env.context.get('sa_origin') or self.sa_shop_position()
        now = fields.Datetime.now()
        max_age = timedelta(minutes=max(1, settings.position_max_age_minutes or 30))
        Ping = self.env['sa.delivery.ping'].sudo()
        # an open SOS makes the rider unavailable whatever else is true (6 Oct 2026)
        sos_ids = set(Rider._sa_sos_open_ids()) if hasattr(Rider, '_sa_sos_open_ids') else set()
        out = []
        for r in riders:
            busy = bool(r.is_busy)
            if busy and not include_busy:
                continue
            fresh = bool(r.last_fix_on and r.last_lat and r.last_lng and (now - r.last_fix_on) <= max_age)
            dist = None
            if fresh and lat0 and lng0:
                dist = Ping._sa_metres(lat0, lng0, r.last_lat, r.last_lng)
            since = r.duty_since or now
            done = [j.sa_delivered_on for j in r.job_ids if j.sa_delivered_on and j.sa_delivered_on > since]
            idle_from = max(done) if done else since
            idle_min = int((now - idle_from).total_seconds() // 60) if r.on_duty else 0
            out.append({
                'rider': r, 'id': r.id, 'name': r.name, 'phone': r.phone or '',
                'on_duty': bool(r.on_duty), 'busy': busy, 'sos': r.id in sos_ids,
                'distance_m': int(dist) if dist is not None else None,
                'distance_km': round(dist / 1000.0, 1) if dist is not None else None,
                'fix_age_min': int((now - r.last_fix_on).total_seconds() // 60) if r.last_fix_on else None,
                'fresh': fresh, 'idle_min': idle_min,
                'address_short': r.address_short or '',
                'in_hand': ', '.join(j.sa_ref_code or j.name for j in r.job_ids
                                     if j.sa_delivery_state in _BUSY_STATES) if busy else '',
                'sequence': r.sequence,
            })
        return out

    def sa_rank_candidates(self, cands, strict_radius=False):
        """Free riders in call order. Tier 1: fresh fix inside the radius,
        nearest first (50 m bands), longest idle breaks the band; exact ties
        -> random. Tier 2: fresh fix outside the radius, same rule. Tier 3:
        no usable fix, longest idle first, then sequence.
        `strict_radius` (mode "only within the radius"): tier 1 only."""
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        radius_m = (settings.dispatch_radius_km or 0.0) * 1000.0
        free = [c for c in cands if not c['busy'] and c['on_duty'] and not c.get('sos')]
        near = [c for c in free if c['distance_m'] is not None and (not radius_m or c['distance_m'] <= radius_m)]
        far = [c for c in free if c['distance_m'] is not None and radius_m and c['distance_m'] > radius_m]
        blind = [c for c in free if c['distance_m'] is None]

        def by_distance(group):
            group = sorted(group, key=lambda c: (c['distance_m'] // 50, -c['idle_min']))
            if len(group) > 1:
                k0 = (group[0]['distance_m'] // 50, -group[0]['idle_min'])
                tied = [c for c in group if (c['distance_m'] // 50, -c['idle_min']) == k0]
                if len(tied) > 1:
                    first = random.choice(tied)      # Priority 3: the tie-breaker
                    group = [first] + [c for c in group if c is not first]
            return group

        def by_idle(group):
            group = sorted(group, key=lambda c: (-c['idle_min'], c['sequence']))
            if len(group) > 1:
                tied = [c for c in group if c['idle_min'] == group[0]['idle_min']]
                if len(tied) > 1:
                    first = random.choice(tied)
                    group = [first] + [c for c in group if c is not first]
            return group

        if strict_radius:
            return by_distance(near)
        return by_distance(near) + by_distance(far) + by_idle(blind)

    def sa_candidates_brief(self):
        """For the counter screen / shop API: JSON-safe, ranked, busy and
        declined riders included but flagged."""
        self.ensure_one()
        # Off-duty riders are listed too (5 Oct 2026): the counter sees two
        # lists - who can be called now, and who cannot and why.
        cands = self.sa_candidates(include_busy=True, include_off=True)
        ranked = self.sa_rank_candidates(cands)          # on duty and free only
        order = {c['id']: i for i, c in enumerate(ranked)}

        def group(c):
            return 0 if c['id'] in order else (1 if (c['busy'] or c.get('sos')) else 2)

        rows = []
        for c in sorted(cands, key=lambda c: (group(c), order.get(c['id'], 999), c['name'] or '')):
            row = {k: v for k, v in c.items() if k != 'rider'}
            row['rank'] = order.get(c['id'])
            row['declined'] = False
            row['available'] = c['id'] in order
            row['reason'] = '' if row['available'] else ('sos' if c.get('sos') else 'busy' if c['busy'] else 'off_duty')
            rows.append(row)
        declined = self.sa_declined_partner_ids
        for r in declined:
            rows.append({'id': r.id, 'name': r.name, 'phone': r.phone or '', 'on_duty': bool(r.on_duty),
                         'busy': bool(r.is_busy), 'distance_m': None, 'distance_km': None, 'fix_age_min': None,
                         'fresh': False, 'idle_min': 0, 'address_short': r.address_short or '', 'in_hand': '',
                         'sequence': r.sequence, 'rank': None, 'declined': True,
                         'available': False, 'reason': 'declined'})
        return rows

    @api.model
    def _sa_reason_label(self, row):
        """Why a rider is in the "not available" list, in words."""
        if row.get('reason') == 'sos':
            return _("SOS open - not until it is handled")
        if row.get('reason') == 'busy':
            return _("On a delivery %s", row.get('in_hand') or '').strip()
        if row.get('reason') == 'declined':
            return _("Did not answer / declined this job")
        return _("Off duty")

    # ------------------------------------------------------------------
    def sa_action_call_rider(self, rider_id=None, rider_ids=None):
        """Call a Rider. `rider_id` / `rider_ids` = the shop's own choice
        (manual mode: several riders may be ticked - they are called ONE at a
        time, in rank order, and nobody else); nothing = automatic (nearest
        free rider, random tie-break; mode "only within the radius" never
        leaves the radius). One rider, one offer, with a timeout; returns the
        rider or empty."""
        self.ensure_one()
        Rider = self.env['sa.delivery.partner'].sudo()
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        if self.sa_delivery_state not in self._SA_CALL_FROM:
            raise UserError(_("Job #%(ref)s is %(state)s - a rider cannot be called now.",
                              ref=self.sa_ref_code, state=self.sa_delivery_state))
        mode = settings.call_rider_mode or 'ask'
        cascade = bool(self.env.context.get('sa_cascade'))
        previous = self.sa_delivery_partner_id if self.sa_delivery_state == 'offered' else Rider
        if rider_id and not rider_ids:
            rider_ids = [rider_id]
        pool = Rider
        if rider_ids:
            pool = Rider.browse([int(r) for r in rider_ids if r]).exists()
            if not pool:
                raise UserError(_("Choose at least one rider."))
            off = pool.filtered(lambda r: not r.on_duty)
            if off and off == pool:
                raise UserError(_("%s - off duty, they cannot be given a job.",
                                  ', '.join(off.mapped('name'))))
            pool -= off
            sos = pool.filtered(lambda r: getattr(r, 'sa_sos_open', False))
            if sos and sos == pool:
                raise UserError(_("%s - SOS open, no job until it is marked handled.", ', '.join(sos.mapped('name'))))
            pool -= sos
            if len(pool) == 1 and previous and previous == pool and self.sa_offer_seconds_left > 0:
                raise UserError(_("Job #%(ref)s is already offered to %(name)s (%(left)s s left).",
                                  ref=self.sa_ref_code, name=pool.name, left=self.sa_offer_seconds_left))
            # a rider picked by hand may be asked again even after a miss
            self.write({'sa_call_pool_ids': [(6, 0, pool.ids)],
                        'sa_declined_partner_ids': [(3, r.id) for r in pool]})
        elif cascade and self.sa_call_pool_ids:
            pool = self.sa_call_pool_ids.sudo()
        elif not cascade and self.sa_call_pool_ids:
            self.write({'sa_call_pool_ids': [(5, 0, 0)]})
        chosen, how = Rider, ''
        if pool:
            skip = self.sa_declined_partner_ids.ids + (previous.ids if previous and not rider_ids else [])
            cands = [c for c in self.sa_candidates(include_busy=True)
                     if c['id'] in pool.ids and c['id'] not in skip]
            order = self.sa_rank_candidates(cands) + sorted(
                [c for c in cands if c['busy']],
                key=lambda c: c['distance_m'] if c['distance_m'] is not None else 10 ** 9)
            if order:
                c = order[0]
                chosen = c['rider']
                how = _("chosen by %s", self.env.user.name) if rider_ids else _("next of the chosen riders")
                if len(pool) > 1:
                    how += _(" (%(n)s riders chosen: %(names)s)", n=len(pool),
                             names=', '.join(pool.mapped('name')))
                if c['distance_km'] is not None:
                    how += _(", %s km away", c['distance_km'])
                if chosen.is_busy:
                    how += _(" (override: %s still has %s in hand)", chosen.name,
                             ', '.join(j.sa_ref_code or j.name for j in chosen.job_ids
                                       if j.sa_delivery_state in _BUSY_STATES) or '-')
        else:
            cands = self.sa_candidates(include_busy=False)
            ranked = self.sa_rank_candidates(cands, strict_radius=(mode == 'auto_radius'))
            if ranked:
                c = ranked[0]
                chosen = c['rider']
                if c['distance_m'] is not None:
                    how = _("auto: nearest, %(km)s km away, idle %(idle)s min", km=c['distance_km'], idle=c['idle_min'])
                else:
                    how = _("auto: no position known, idle %(idle)s min", idle=c['idle_min'])
                if len(ranked) > 1 and ranked[1]['distance_m'] is not None and c['distance_m'] is not None \
                        and ranked[1]['distance_m'] // 50 == c['distance_m'] // 50 \
                        and ranked[1]['idle_min'] == c['idle_min']:
                    how += _(" (tie with %s, picked at random)", ranked[1]['name'])
        if previous and previous != chosen:
            # the previous rider never answered: remembered, not asked again
            self.write({'sa_declined_partner_ids': [(4, previous.id)]})
            self._sa_call_log_add(_("%s did not answer - replaced", previous.name))
        if not chosen:
            if pool:
                why = _("None of the chosen riders answered (%s)", ', '.join(pool.mapped('name')))
            elif mode == 'auto_radius':
                why = _("No free rider within %s km of the shop", settings.dispatch_radius_km or 0)
            else:
                why = _("No rider available - %s on duty",
                        len([c for c in self.sa_candidates(include_busy=True)]))
            vals = {'sa_delivery_state': 'to_assign', 'sa_delivery_partner_id': False,
                    'sa_offer_expires_on': False, 'sa_last_error': why}
            self.write(vals)
            self._sa_call_log_add(_("%s - waiting for the counter", why))
            self.message_post(body=_("Call a Rider: %s. The job waits under To Dispatch.", why))
            if hasattr(self, '_sa_store_notify'):
                try:
                    self._sa_store_notify()
                except Exception:  # noqa: BLE001
                    pass
            return Rider
        timeout = max(15, settings.offer_timeout_seconds or 60)
        self.write({'sa_delivery_partner_id': chosen.id,
                    'sa_offer_expires_on': fields.Datetime.now() + timedelta(seconds=timeout),
                    'sa_offer_round': (self.sa_offer_round or 0) + 1,
                    'sa_accepted_on': False})
        if hasattr(self, '_sa_apply_rider_fee'):
            self._sa_apply_rider_fee(chosen)        # per-trip pay: Delivery Partners only
        self._sa_call_log_add(_("round %(n)s -> %(name)s - %(how)s - %(t)s s to answer",
                                n=self.sa_offer_round, name=chosen.name, how=how, t=timeout))
        self.message_post(body=_("Call a Rider: offered to %(name)s (%(how)s).", name=chosen.name, how=how))
        # the WhatsApp link (one rider) - the shop already packed, no second hold
        self.with_context(sa_force_offer=True, sa_shop_done=True).sa_action_offer()
        if self.sa_delivery_state != 'offered':
            # No WhatsApp session / the nudge could not go: the offer still
            # stands - the rider app reads it from /orders and gets the push.
            self.write({'sa_delivery_state': 'offered', 'sa_offered_on': fields.Datetime.now()})
        self._sa_push_offer()
        return chosen

    def sa_action_next_rider(self):
        """The counter gives up on the current offer: next candidate now."""
        self.ensure_one()
        if self.sa_delivery_state != 'offered':
            raise UserError(_("Job #%s is not waiting for a rider's answer.", self.sa_ref_code))
        self.write({'sa_offer_expires_on': fields.Datetime.now() - timedelta(seconds=1)})
        return self._sa_expire_one()

    def _sa_expire_one(self):
        """This offer timed out: remember the rider, call the next one."""
        self.ensure_one()
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        rider = self.sa_delivery_partner_id
        if rider:
            self.write({'sa_declined_partner_ids': [(4, rider.id)]})
            self._sa_call_log_add(_("%s did not answer in time", rider.name))
            try:
                settings._sa_push(rider, {'type': 'job_offer_expired', 'delivery_order_id': self.id,
                                          'job_code': self.sa_ref_code or ''},
                                  _("Offer expired"), _("Job #%s went to another rider.", self.sa_ref_code or ''))
            except Exception:  # noqa: BLE001
                pass
        self.write({'sa_delivery_state': 'to_assign', 'sa_delivery_partner_id': False,
                    'sa_offer_expires_on': False, 'sa_accepted_on': False})
        cap = max(1, settings.max_offer_rounds or 5)
        if (self.sa_offer_round or 0) >= cap:
            self.write({'sa_last_error': _("No rider answered after %s tries", cap)})
            self._sa_call_log_add(_("%s riders tried - stopped, waiting for the counter", cap))
            self.message_post(body=_("Call a Rider: %s riders did not answer. Pick one by hand or press Call a Rider again.", cap))
            if hasattr(self, '_sa_store_notify'):
                try:
                    self._sa_store_notify()
                except Exception:  # noqa: BLE001
                    pass
            return self.env['sa.delivery.partner']
        # cascade: stays inside the riders the shop ticked, when it ticked any
        return self.with_context(sa_cascade=True).sa_action_call_rider()

    @api.model
    def _sa_expire_offers(self):
        """Cron (every minute) and lazy hook: offers past their timeout move
        on to the next rider. Each job in its own savepoint."""
        now = fields.Datetime.now()
        jobs = self.sudo().search([('sa_delivery_state', '=', 'offered'),
                                   ('sa_offer_expires_on', '!=', False),
                                   ('sa_offer_expires_on', '<', now)])
        n = 0
        for job in jobs:
            try:
                with self.env.cr.savepoint():
                    job._sa_expire_one()
                    n += 1
            except Exception as err:  # noqa: BLE001
                _logger.warning("Call a Rider: expiring job %s failed: %s", job.sa_ref_code, err)
        if n:
            _logger.info("Call a Rider: %s offer(s) timed out and moved on", n)
        return n

    def _sa_push_offer(self):
        self.ensure_one()
        rider = self.sa_delivery_partner_id
        if not rider:
            return 0
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        partner = self.partner_id
        area = ', '.join(filter(None, [partner.city, partner.zip])) or partner.street or ''
        data = {
            'type': 'job_offer', 'delivery_order_id': self.id, 'job_code': self.sa_ref_code or '',
            'shop': self.sa_shop_id.name or '', 'customer_area': area,
            'amount_to_collect': round(self.sa_amount_due() or 0.0, 3),
            'promised_by': (self.sa_promised_on.isoformat() + 'Z') if self.sa_promised_on else '',
            'expires_at': (self.sa_offer_expires_on.isoformat() + 'Z') if self.sa_offer_expires_on else '',
            'round': self.sa_offer_round or 1,
        }
        if 'sa_rider_fee' in self._fields:
            data['shop_to_customer_m'] = self.sa_trip_m or 0
            if self.sa_rider_fee:                   # Delivery Partners only
                data.update({'rider_earning': round(self.sa_rider_fee, 3),
                             'rider_fee': round(self.sa_rider_fee, 3)})
        try:
            return settings._sa_push(rider, data, _("New delivery #%s", self.sa_ref_code or ''),
                                     _("%(shop)s -> %(area)s. Accept within %(s)s s.",
                                       shop=self.sa_shop_id.name or _("the shop"), area=area or '-',
                                       s=self.sa_offer_seconds_left))
        except Exception as err:  # noqa: BLE001
            _logger.warning("Call a Rider: push for %s failed: %s", self.sa_ref_code, err)
            return 0

    def action_sa_open_call_rider(self):
        self.ensure_one()
        mode = self.env['sa.delivery.settings'].sudo().get_settings().call_rider_mode or 'ask'
        if mode in ('auto', 'auto_radius'):
            # automatic mode: no dialog, the system picks
            self.sa_action_call_rider()
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        return {'type': 'ir.actions.act_window', 'name': _('Call a Rider'),
                'res_model': 'sa.delivery.call.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_picking_id': self.id}}


# ======================================================================
# The wizard behind the Call a Rider button
# ======================================================================
class SaDeliveryCallWizard(models.TransientModel):
    _name = 'sa.delivery.call.wizard'
    _description = 'Call a Rider'

    picking_id = fields.Many2one('stock.picking', required=True)
    call_mode = fields.Char(compute='_compute_call_mode')
    mode = fields.Selection([('auto', 'Auto - the nearest free rider (random on a tie)'),
                             ('pick', 'I choose the riders')],
                            default=lambda self: 'pick' if (
                                self.env['sa.delivery.settings'].sudo().get_settings().call_rider_mode == 'manual')
                            else 'auto', required=True)
    available_rider_ids = fields.Many2many('sa.delivery.partner', compute='_compute_available_rider_ids')
    rider_ids = fields.Many2many('sa.delivery.partner', string='Available riders',
                                 domain="[('id', 'in', available_rider_ids)]",
                                 help="Only riders who can be called now: on duty, not on a delivery, "
                                      "and not already tried for this job. Tick one or several; they are "
                                      "called one at a time, nearest first; nobody else is called.")

    @api.depends('picking_id')
    def _compute_available_rider_ids(self):
        for w in self:
            rows = w.picking_id.sudo().sa_candidates_brief() if w.picking_id else []
            w.available_rider_ids = [(6, 0, [r['id'] for r in rows if r.get('available')])]
    candidates_html = fields.Html(compute='_compute_candidates_html', sanitize=False)

    def _compute_call_mode(self):
        mode = self.env['sa.delivery.settings'].sudo().get_settings().call_rider_mode or 'ask'
        for w in self:
            w.call_mode = mode

    @api.depends('picking_id')
    def _compute_candidates_html(self):
        for w in self:
            rows = w.picking_id.sudo().sa_candidates_brief() if w.picking_id else []
            free = [r for r in rows if r.get('available')]
            rest = [r for r in rows if not r.get('available')]
            esc = html_escape
            html = ['<h5 class="mt-2">Available (%s)</h5>' % len(free)]
            if free:
                html.append('<table class="table table-sm"><tr><th>#</th><th>Rider</th><th>Distance</th><th>Idle</th><th>Position</th></tr>')
                for r in free:
                    html.append('<tr><td>%s</td><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                        (r['rank'] + 1) if r.get('rank') is not None else '-', esc(r['name'] or ''),
                        ('%s km' % r['distance_km']) if r['distance_km'] is not None else 'no position',
                        '%s min' % r['idle_min'],
                        esc(r['address_short'] or '-') + ((' (%s min ago)' % r['fix_age_min']) if r['fix_age_min'] is not None else '')))
                html.append('</table>')
            else:
                html.append('<p class="text-muted">No rider can be called right now.</p>')
            if rest:
                html.append('<h5 class="mt-3 text-muted">Not available (%s) - cannot be called</h5>' % len(rest))
                html.append('<table class="table table-sm text-muted"><tr><th>Rider</th><th>Why</th><th>Position</th></tr>')
                for r in rest:
                    html.append('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                        esc(r['name'] or ''), esc(w.picking_id._sa_reason_label(r)),
                        esc(r['address_short'] or '-') + ((' (%s min ago)' % r['fix_age_min']) if r['fix_age_min'] is not None else '')))
                html.append('</table>')
            w.candidates_html = ''.join(html)

    def action_call(self):
        self.ensure_one()
        if self.mode == 'pick' and not self.rider_ids:
            raise UserError(_("Tick at least one rider."))
        self.picking_id.sudo().sa_action_call_rider(
            rider_ids=self.rider_ids.ids if self.mode == 'pick' else None)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
