# -*- coding: utf-8 -*-
"""The delivery-partner API.

A thin skin over the model methods the Odoo buttons and the rider web page
already call. Nothing here writes a status column directly, so no client can
reach `delivered` without the customer's WhatsApp message going out and the
picking being validated.

Every response carries `status` and `allowed_actions`, decided by
`stock.picking._SA_FLOW`. The app renders buttons from that list and holds no
workflow of its own - a change to the flow needs no new release.
"""

import functools
import json
import logging

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

_PREFIX = '/api/delivery'

# Nothing a rider can still act on. They belong in /history, not in the list
# of work: left in /orders they sit on the screen for ever with an empty
# allowed_actions and no way to clear them.
_TERMINAL = ('delivered', 'returned', 'cancelled', 'failed')


def _json(payload, status=200):
    return request.make_json_response(payload, status=status)


def _fail(message, status=400, **extra):
    out = {'success': False, 'message': message}
    out.update(extra)
    return _json(out, status=status)


def _body():
    """Accept a JSON body or an ordinary form post, whichever the app sends."""
    try:
        raw = request.httprequest.get_data(as_text=True) or ''
        if raw.strip().startswith('{'):
            return json.loads(raw)
    except (ValueError, TypeError):
        pass
    return dict(request.httprequest.values)


def _dt(value):
    """A datetime the app can trust.

    Odoo stores every datetime as naive UTC. Handing that to a client bare -
    `2026-09-05T12:48:26` with no zone - invites it to be read as local time,
    which in Oman is four hours wrong in the direction that makes a rider late.
    The `Z` is the whole fix.
    """
    return (value.isoformat() + 'Z') if value else ''


def _money(amount, currency):
    """Rounded the way the currency actually works.

    OMR has three decimals, most have two, some have none. Sending a bare
    float and letting the app guess produces 1000.0 for a rial amount that
    should read 1000.000 - and a rider counting cash notices.
    """
    places = currency.decimal_places if currency else 2
    return round(amount or 0.0, places)


def _money_block(amount, currency):
    """{amount, formatted} - the number and how to print it."""
    return request.env['sa.delivery.partner'].sa_money_block(amount, currency)


def _currency_block(currency):
    return {
        'code': currency.name or '',
        'symbol': currency.symbol or '',
        'decimals': currency.decimal_places if currency else 2,
    }


def _test_otp(payload, code, picking, kind):
    """Put the code in the response, but only when told to.

    There is no way to read a code back otherwise - they are stored salted and
    hashed, which is right - so with no WhatsApp session connected the flow
    cannot be driven from Postman at all. This is the deliberate hole, closed
    by default and noisy when open.
    """
    settings = request.env['sa.delivery.settings'].sudo().get_settings()
    if not settings.otp_test_mode or not code:
        return payload
    payload['otp_debug'] = code
    payload['otp_debug_warning'] = (
        'TEST MODE: this code is only in the response because '
        '"Return OTPs in the API" is on in Delivery Settings. Turn it off '
        'before anyone real uses this.')
    _logger.warning("Delivery API: OTP TEST MODE returned a %s code for job "
                    "%s - this must be off outside testing", kind,
                    getattr(picking, 'sa_ref_code', False) or picking.display_name)
    return payload


def _bearer():
    """The token, from the Authorization header or the body."""
    header = request.httprequest.headers.get('Authorization') or ''
    if header.lower().startswith('bearer '):
        return header[7:].strip()
    data = _body()
    return (data.get('token') or '').strip()


def _rider_from_request():
    """Who is calling, by either way in.

    Two are supported on purpose:

    * **Odoo's own JSON-RPC session.** The app logs in at
      `/web/session/authenticate` exactly as any Odoo client does, keeps the
      session cookie, and the rider is the `sa.delivery.partner` linked to that
      user. Standard Odoo, standard record rules, nothing invented.
    * **A bearer token** from `/api/delivery/auth/verify-code`, for riders who
      are not Odoo users - freelance couriers and third-party partners, who
      should not hold a login at all.

    The bearer token is checked first so a token always beats whatever session
    cookie happens to be lying around in the app's HTTP client.
    """
    token = _bearer()
    if token:
        rider = request.env['sa.delivery.token'].sudo()._rider_from_token(token)
        if rider:
            return rider
    if request.session.uid:
        return request.env['sa.delivery.partner'].sudo().search(
            [('user_id', '=', request.session.uid), ('active', '=', True)],
            limit=1)
    return request.env['sa.delivery.partner']


def _coords(data):
    """(lat, lng, accuracy) from a request body. Both spellings are taken:
    latitude / longitude (the contract) and lat / lng / lon - a body with the
    short names used to be answered "success" and silently dropped."""
    def num(*keys):
        for key in keys:
            try:
                value = data.get(key)
                if value not in (None, ''):
                    return float(value)
            except (TypeError, ValueError):
                continue
        return None
    lat, lng = num('latitude', 'lat'), num('longitude', 'lng', 'lon', 'long')
    if lat is None or lng is None or not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None, None, num('accuracy', 'acc')
    return lat, lng, num('accuracy', 'acc')


def _token_row():
    """The app session row of the bearer token in use (empty for an Odoo
    session login - there is no device row to hang a push token on)."""
    token = _bearer()
    Tok = request.env['sa.delivery.token'].sudo()
    if not token:
        return Tok
    return Tok.search([('token_hash', '=', Tok._hash(token)),
                       ('revoked', '=', False)], limit=1)


def authenticated(func):
    """Resolve the rider once, and refuse everything else.

    The single gate. Every endpoint below is scoped to the rider this returns,
    so rider A cannot reach rider B's job even by guessing its id - which is
    tested by calling every endpoint with the wrong rider's token.
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        rider = _rider_from_request()
        if not rider:
            return _fail(_("Not signed in."), status=401, code='unauthorized')
        return func(self, rider, *args, **kwargs)
    return wrapper


class SaDeliveryApi(http.Controller):

    # ==================================================================
    # Authentication
    # ==================================================================
    @http.route('%s/auth/request-code' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    def request_code(self, **kw):
        data = _body()
        phone = (data.get('mobile') or data.get('phone') or '').strip()
        Rider = request.env['sa.delivery.partner'].sudo()
        rider = Rider._sa_by_phone(phone)
        # The same answer either way: telling a stranger which numbers are
        # riders is a list worth having.
        body = {'success': True,
                'message': _("If that number is registered, a code has been "
                             "sent to it on WhatsApp.")}
        # Always present, for a rider or not: the app times its "Resend"
        # button from this, and returning it only for real riders would say
        # which numbers are riders.
        body['retry_after_seconds'] = 60
        if not rider:
            _logger.info("Delivery API: login code asked for unknown %r", phone)
            return _json(body)
        mismatch = rider.sa_kind_mismatch(data.get('kind'))
        if mismatch:
            # the app chose the other role: no code goes out
            return _fail(mismatch.pop('message'), status=403, **mismatch)

        Login = request.env['sa.delivery.login.code'].sudo()
        waiting = Login._cooldown_left(rider)
        if waiting:
            # A code went out moments ago and is still valid. Issuing another
            # would kill the one the rider is about to type.
            _logger.info("Delivery API: login code for %s asked again after "
                         "%ss - not reissuing", rider.phone,
                         60 - waiting)
            body['retry_after_seconds'] = waiting
            return _json(body)
        code = Login._issue(rider)
        # Same switch as the delivery codes: with no WhatsApp session there is
        # otherwise no way to sign in at all from Postman.
        _test_otp(body, code, rider, 'login')
        answer = _json(body)
        picking = request.env['stock.picking'].sudo().search(
            [('sa_delivery_partner_id', '=', rider.id)], limit=1)
        session = (picking._sa_session() if picking else
                   request.env['whatsapp.session'].sudo().search(
                       [('active', '=', True)], limit=1))
        if session:
            try:
                session.send_message(rider.phone, _(
                    "\U0001F510 Your delivery app code is *%(code)s*.\n\n"
                    "It expires in 10 minutes. Do not share it.", code=code))
            except Exception as err:  # noqa: BLE001
                _logger.warning("Delivery API: login code to %s failed: %s",
                                rider.phone, err)
        return answer

    @http.route('%s/auth/verify-code' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    def verify_code(self, **kw):
        data = _body()
        phone = (data.get('mobile') or data.get('phone') or '').strip()
        rider = request.env['sa.delivery.partner'].sudo()._sa_by_phone(phone)
        if not rider:
            # The same answer as a wrong code, and carrying the same `code`
            # field every other endpoint sends, so the app has one thing to
            # branch on.
            return _fail(_("Invalid or expired code."), status=401,
                         code='unauthorized')
        mismatch = rider.sa_kind_mismatch(data.get('kind'))
        if mismatch:
            return _fail(mismatch.pop('message'), status=403, **mismatch)
        ok, message = request.env['sa.delivery.login.code'].sudo()._verify(
            rider, data.get('code'))
        if not ok:
            return _fail(message, status=401, code='unauthorized')
        token, refresh = request.env['sa.delivery.token'].sudo()._issue(
            rider, data.get('device') or '')
        # Read the lifetime off the row that was just written rather than
        # repeating the constant here, so the two can never drift apart.
        row = request.env['sa.delivery.token'].sudo().search(
            [('partner_id', '=', rider.id)], order='id desc', limit=1)
        expires_in = int((row.expires_on - fields.Datetime.now()
                          ).total_seconds()) if row else 0
        return _json({
            'success': True,
            'token': token,
            'refresh_token': refresh,
            'expires_in': max(0, expires_in),
            'rider': {'id': rider.id, 'name': rider.name,
                      'mobile': rider.phone, 'kind': rider.kind,
                      'on_duty': rider.on_duty,
                      'duty_since': _dt(rider.duty_since)},
        })

    @http.route('%s/auth/refresh' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    def refresh(self, **kw):
        data = _body()
        pair = request.env['sa.delivery.token'].sudo()._refresh(
            (data.get('refresh_token') or '').strip(),
            data.get('device') or '')
        if not pair:
            return _fail(_("Please sign in again."), status=401,
                         code='unauthorized')
        token, refresh = pair
        return _json({'success': True, 'token': token,
                      'refresh_token': refresh})

    @http.route('%s/auth/logout' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    def logout(self, **kw):
        request.env['sa.delivery.token'].sudo()._revoke(_bearer())
        if request.session.uid:
            request.session.logout(keep_db=True)
        return _json({'success': True})

    @http.route('%s/auth/me' % _PREFIX, type='http', auth='public',
                methods=['GET', 'POST'], csrf=False)
    def me(self, **kw):
        """Who does the server think is calling?

        The first call an app should make after logging in either way. It says
        whether the credentials worked *and* whether that user is actually a
        rider - a valid Odoo login that is not linked to a delivery partner is
        a real and confusing failure otherwise.
        """
        rider = _rider_from_request()
        if not rider:
            hint = (_("Signed in to 369ai, but this user is not linked to a "
                      "delivery partner. Ask the office to set the 369ai User "
                      "on the rider's record.")
                    if request.session.uid
                    else _("Not signed in."))
            return _fail(hint, status=401, code='unauthorized')
        return _json({
            'success': True,
            'rider': {
                'id': rider.id, 'name': rider.name,
                'mobile': rider.phone, 'kind': rider.kind,
                'on_duty': rider.on_duty,
                'duty_since': _dt(rider.duty_since),
            },
            # Every datetime this API emits is UTC with a trailing Z. This is
            # the zone to *display* them in - the app converts, Odoo does not.
            'push': {'platform': row.push_platform or '',
                     'registered': bool(row.push_token)} if (row := _token_row())
            else {'platform': '', 'registered': False},
            # false = Delivery Partners are paused (no new offers); own riders
            # are never affected
            'third_party_enabled': bool(request.env['sa.delivery.settings'].sudo()
                                        .get_settings().third_party_enabled),
            # branch = the counter presses Dispatch and reads the code out
            'pickup_handover': request.env['stock.picking'].sudo().sa_pickup_mode(),
            'hide_customer_until_pickup': bool(request.env['sa.delivery.settings'].sudo()
                                               .get_settings().hide_customer_until_pickup),
            # the server marks Rider Near Customer itself from the positions
            'auto_near_customer': (lambda st: {
                'enabled': bool(st.auto_near_customer),
                'radius_m': st.near_radius_m or 150,
                'dwell_seconds': st.near_dwell_seconds or 0,
            })(request.env['sa.delivery.settings'].sudo().get_settings()),
            # ONE zone for every rider: the company's (the app names photos in it)
            'timezone': request.env['sa.delivery.partner'].sudo()._sa_company_tz(),
            'rider_timezone': rider.tz or '',
            'currency': _currency_block(request.env.company.currency_id),
            # 'bearer' rather than 'token': it names the scheme the app
            # actually sends, and it is the word the contract uses.
            'auth': 'session' if (request.session.uid and not _bearer())
                    else 'bearer',
        })

    # ==================================================================
    # Orders
    # ==================================================================
    def _jobs(self, rider, states=None):
        domain = [('sa_delivery_partner_id', '=', rider.id),
                  ('sa_delivery_state', 'not in', ('none', False))]
        if states:
            domain.append(('sa_delivery_state', 'in', states))
        return request.env['stock.picking'].sudo().search(
            domain, order='sa_offered_on desc, id desc')

    def _shop_block(self, shop, picking=None):
        """The shop as an object, so the offer screen needs no second call.

        `shop` used to be a bare name. The app accepts either, so this can
        change without waiting for a release.
        """
        if not shop:
            # Every job carries a pickup point: no shop on the job -> the
            # warehouse the goods leave from.
            wh = picking.picking_type_id.warehouse_id if picking else None
            if not wh:
                return None
            wp = wh.partner_id
            return {
                'id': None, 'name': wh.name or '', 'image_url': None,
                'latitude': (wp.partner_latitude or None) if wp else None,
                'longitude': (wp.partner_longitude or None) if wp else None,
                'address': ', '.join(filter(None, [wp.street, wp.city])) if wp else '',
                'phone': (wp.phone or '') if wp else '',
                'is_warehouse': True,
            }
        contact = shop.partner_id or shop.warehouse_id.partner_id
        # The app fetches this from a phone, so it needs the public
        # address rather than whatever identifies us to the WhatsApp panel.
        base = request.env['stock.picking'].sudo()._sa_public_base()
        image = ''
        if contact and contact.image_128:
            image = '%s/web/image/res.partner/%s/image_512' % (base, contact.id)
        return {
            'id': shop.id,
            'name': shop.name or '',
            'image_url': image or None,
            # the shop's own map pin first, then its address contact
            'latitude': shop._sa_position()[0] or None,
            'longitude': shop._sa_position()[1] or None,
            'address': (', '.join(filter(None, [contact.street, contact.city]))
                        if contact else '') or shop.address_short or '',
            'phone': shop.phone or (contact.phone if contact else '') or '',
        }

    def _brief_raw(self, picking):
        partner = picking.partner_id
        moves = picking.move_ids
        units = sum(moves.mapped('product_uom_qty'))
        return {
            'delivery_order_id': picking.id,
            'delivery_order_name': picking.name,
            'job_code': picking.sa_ref_code or '',
            'sales_order': picking.sale_id.name or '',
            'customer_name': partner.name or '',
            'customer_mobile': partner.phone or '',
            'delivery_address': ', '.join(filter(None, [
                partner.street, partner.street2, partner.city, partner.zip,
                partner.country_id.name])),
            'shop': self._shop_block(picking.sa_shop_id, picking),
            'items_summary': _("%(lines)s item(s) - %(units)s unit(s)",
                               lines=len(moves),
                               units=int(units) if float(units).is_integer()
                               else units),
            'products': [{
                'name': move.product_id.name,
                'quantity': move.product_uom_qty,
                'uom': move.product_uom.name or '',
            } for move in moves],
            # Both read from the invoice, so a customer who paid after the
            # job was created is not asked for the money a second time.
            'payment_status': 'cod' if picking.sa_amount_due() else 'paid',
            'amount_to_collect': _money(picking.sa_amount_due(),
                                        picking.sa_currency_id),
            'currency': _currency_block(picking.sa_currency_id),
            'delivery_status': picking.sa_delivery_state,
            'offer_expires_at': _dt(picking.sa_offer_expires_on)
            if picking.sa_delivery_state == 'offered' else '',
            'offer_round': picking.sa_offer_round or 0,
            'customer_latitude': picking.partner_id.partner_latitude or None,
            'customer_longitude': picking.partner_id.partner_longitude or None,
            # contact | whatsapp (the customer's own pin) | geocoded (approximate)
            'customer_pin_source': picking.sa_pin_source or '',
            'shop_to_customer_m': picking.sa_trip_m or None,
            'rider_earning': _money(picking.sa_rider_fee, picking.sa_currency_id)
            if picking.sa_rider_fee else None,
            'delivery_note': picking.sa_delivery_note or '',
            # one free-text answer from the customer lands in delivery_note;
            # landmark and door are reserved for when the question is split
            'landmark': '',
            'door': '',
            # the drop pin, in list rows as well as in the detail
            'latitude': picking.partner_id.partner_latitude or None,
            'longitude': picking.partner_id.partner_longitude or None,
            'location_source': picking.sa_location_source(),
            'rider_fee': _money_block(picking.sa_rider_fee, picking.sa_currency_id)
            if picking.sa_rider_fee else None,
            # cash jobs only: the chat's own pay link, to show as a QR
            'pay_url': picking.sa_pay_url_for_rider() or None,
            'delivery_type': picking.sa_delivery_kind or '',
            'promised_by': _dt(picking.sa_promised_on),
            'allowed_actions': picking.sa_allowed_actions(),
        }

    # What the rider may not know before the pickup code is verified
    # (Delivery Settings > "Show the customer's location only after pickup").
    _LOCKED_BLANK = {
        'delivery_address': '', 'customer_mobile': '', 'delivery_note': '',
        'customer_latitude': None, 'customer_longitude': None,
        'customer_pin_source': '', 'latitude': None, 'longitude': None,
        'location_source': None, 'pay_url': None,
    }

    def _brief(self, picking):
        out = self._brief_raw(picking)
        locked = not picking.sa_customer_revealed()
        out.update({
            'customer_location_locked': locked,
            'customer_area': picking.sa_customer_area(),
            'pickup_handover': picking.sa_pickup_mode(),
            'arrived_at_shop': _dt(picking.sa_arrived_shop_on),
            'pickup_code_ready': bool(picking.sa_pickup_code_shown)
            and picking.sa_delivery_state == 'accepted',
            # Rider Near Customer: when, and whether the server set it from
            # the rider's position (true) or somebody pressed the button
            'near_customer_at': _dt(picking.sa_out_on),
            'near_customer_auto': bool(picking.sa_near_auto),
            # where the parcel changed hands - on the job only; the
            # customer's address and pin are never changed by a delivery
            'handover': picking.sa_handover_block(),
            'photo_counts': {'pickup': len(picking.sa_pickup_photo_ids),
                             'delivery': len(picking.sa_delivery_photo_ids)},
        })
        if locked:
            out.update(self._LOCKED_BLANK)
        return self._overlay(out, picking)

    def _viewer(self):
        """The rider asking, once per request."""
        rider = getattr(request, '_sa_viewer', None)
        if rider is None:
            rider = _rider_from_request() or request.env['sa.delivery.partner'].sudo()
            try:
                request._sa_viewer = rider
            except Exception:  # noqa: BLE001
                pass
        return rider

    def _overlay(self, out, picking):
        """Problem follow-ups laid over the job: wait timer, a drop point for
        this job only, and the two sides of a rider-to-rider handover."""
        out.update(picking.sa_problem_overlay(self._viewer()))
        if out.get('pickup_from', {}).get('kind') == 'shop' and out.get('shop'):
            out['pickup_from'] = dict(out['shop'], kind='shop')
        if out.get('customer_location_locked'):
            out.update(self._LOCKED_BLANK)
            out['drop_point'] = None
            if 'pin_source' in out:
                out['pin_source'] = ''
        return out

    def _one_relay(self, rider, order_id):
        """A job another rider is handing over to this rider."""
        job = request.env['stock.picking'].sudo().browse(int(order_id or 0))
        if not job.exists() or job.sa_relay_to_id != rider \
                or job.sa_relay_state not in ('offered', 'accepted'):
            return None
        return job

    def _relay_jobs(self, rider):
        return request.env['stock.picking'].sudo().search(
            [('sa_relay_to_id', '=', rider.id), ('sa_relay_state', 'in', ('offered', 'accepted'))])

    def _full(self, picking):
        out = self._brief(picking)
        partner = picking.partner_id
        revealed = picking.sa_customer_revealed()
        out.update({
            # null, not 0.0. No address in this database is geocoded yet, and
            # 0,0 is a real place in the Atlantic - an app that trusts it drops
            # the customer's pin off the coast of Ghana.
            'latitude': (partner.partner_latitude or None) if revealed else None,
            'longitude': (partner.partner_longitude or None) if revealed else None,
            'pin_source': (picking.sa_pin_source or '') if revealed else '',
            'tracking': {'enabled': picking.sa_tracking_enabled()},
            # parcel photos of both ends; fetch each `url` with the same headers
            'photos': picking.sa_photos_block('%s/proof' % _PREFIX),
            # every report the rider made on this job, oldest first
            'reports': picking.sa_reports_block('%s/proof' % _PREFIX),
            'photos_missing': picking.sa_photos_missing_list(),
            'timestamps': {
                'offered': _dt(picking.sa_offered_on),
                'accepted': _dt(picking.sa_accepted_on),
                'picked_up': _dt(picking.sa_picked_on),
                'dispatched': _dt(picking.sa_dispatched_on),
                'out_for_delivery': _dt(picking.sa_out_on),
                'delivered': _dt(picking.sa_delivered_on),
            },
        })
        return self._overlay(out, picking)

    @http.route('%s/orders' % _PREFIX, type='http', auth='public',
                methods=['GET', 'POST'], csrf=False)
    @authenticated
    def orders(self, rider, **kw):
        # Everything, so the counts can still say how many were delivered -
        # then the finished ones are dropped from the list itself.
        try:
            request.env['stock.picking'].sudo()._sa_expire_offers()   # lazy timeout
        except Exception as err:  # noqa: BLE001
            _logger.warning("Delivery API: expiring offers failed: %s", err)
        jobs = self._jobs(rider)
        counts = {'assigned': 0, 'picked_up': 0, 'out_for_delivery': 0,
                  'delivered': 0}
        for job in jobs:
            state = job.sa_delivery_state
            if state in ('offered', 'accepted'):
                counts['assigned'] += 1
            elif state in ('picked', 'dispatched'):
                counts['picked_up'] += 1
            elif state == 'out_for_delivery':
                counts['out_for_delivery'] += 1
            elif state == 'delivered':
                counts['delivered'] += 1
        # Was `!= 'delivered'`, which left returned, cancelled and failed
        # jobs in the list for ever - the app team found three of them still
        # showing with an empty allowed_actions and nothing to tap.
        open_jobs = jobs.filtered(
            lambda p: p.sa_delivery_state not in _TERMINAL)
        return _json({
            'success': True,
            # `delivered` is all time; the dated ones are in the rider's timezone
            'counts': dict(counts, **rider.sudo().sa_delivered_counts()),
            'on_duty': rider.on_duty,
            # ONE zone for every rider: the company's (the app names photos in it)
            'timezone': request.env['sa.delivery.partner'].sudo()._sa_company_tz(),
            'rider_timezone': rider.tz or '',
            'server_time': _dt(fields.Datetime.now()),
            # + a parcel another rider is handing over to this rider
            'orders': [self._brief(job) for job in (open_jobs | self._relay_jobs(rider))],
        })

    @http.route('%s/orders/<int:order_id>' % _PREFIX, type='http',
                auth='public', methods=['GET', 'POST'], csrf=False)
    @authenticated
    def order_detail(self, rider, order_id, **kw):
        job = self._one(rider, order_id) or self._one_relay(rider, order_id)
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        # Both shapes. The contract assumed the order sat flat in the
        # envelope and the code nested it under `order`; sending both costs
        # a few hundred bytes and spares an app release either way.
        full = self._full(job)
        out = {'success': True, 'order': full}
        out.update(full)
        return _json(out)

    def _one(self, rider, order_id):
        """A job, but only if it is this rider's."""
        job = request.env['stock.picking'].sudo().browse(int(order_id or 0))
        if not job.exists() or job.sa_delivery_partner_id != rider:
            return None
        return job

    @http.route('%s/duty' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def duty(self, rider, **kw):
        """Clock on or off.

        Clocking on picks up whatever was waiting because nobody was on duty,
        and says how many - so the app can show "3 jobs were waiting for you"
        rather than a list that silently grew.
        """
        data = _body()
        wanted = data.get('on_duty')
        if isinstance(wanted, str):
            wanted = wanted.strip().lower() in ('1', 'true', 'yes', 'on')
        def _num(key):
            try:
                return float(data.get(key))
            except (TypeError, ValueError):
                return None
        lat, lng, _acc = _coords(data)
        taken = rider.sudo().sa_set_duty(bool(wanted), lat, lng)
        return _json({
            'success': True,
            'on_duty': rider.on_duty,
            'duty_since': _dt(rider.duty_since),
            'jobs_picked_up': taken or 0,
            'address_short': rider.address_short or '',
            'fleet_state': rider.fleet_state or '',
            'message': (_("You are on duty. %(n)s job(s) were waiting.",
                          n=taken or 0) if rider.on_duty
                        else _("You are off duty. Jobs already accepted are "
                               "still yours.")),
        })

    @http.route('%s/history' % _PREFIX, type='http', auth='public',
                methods=['GET', 'POST'], csrf=False)
    @authenticated
    def history(self, rider, **kw):
        """This rider's finished work, newest first."""
        data = _body()
        try:
            limit = int(data.get('limit') or 20)
            offset = int(data.get('offset') or 0)
        except (TypeError, ValueError):
            limit, offset = 20, 0
        # Capped server-side: a client asking for everything at once would
        # pull a year of rows down a phone connection.
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        domain = [('sa_delivery_partner_id', '=', rider.id),
                  ('sa_delivery_state', 'in',
                   ('delivered', 'returned', 'cancelled'))]
        Picking = request.env['stock.picking'].sudo()
        total = Picking.search_count(domain)
        jobs = Picking.search(domain, order='id desc',
                              limit=limit, offset=offset)

        rows = []
        for job in jobs:
            finished = (job.sa_delivered_on or job.sa_returned_on
                        or job.sa_cancelled_on)
            rows.append({
                'delivery_order_id': job.id,
                'job_code': job.sa_ref_code or '',
                'delivery_order_name': job.name,
                'sales_order': job.sale_id.name or '',
                'status': job.sa_delivery_state,
                'customer_name': job.partner_id.name or '',
                'city': job.partner_id.city or '',
                'shop': job.sa_shop_id.name or '',
                'finished_at': _dt(finished),
                # What was actually taken at the door - zero on anything that
                # did not complete, whatever the order was worth.
                'collected': _money(
                    job.sa_cod_amount
                    if job.sa_delivery_state == 'delivered' else 0.0,
                    job.sa_currency_id),
                # Zero by decision, not by omission: there is no fee
                # model yet. The field is here from the start so adding one
                # later needs no app release.
                # What the rider earned: the job's pay once delivered, zero
                # on anything that did not complete.
                'earnings': _money(job.sa_rider_fee if job.sa_delivery_state == 'delivered'
                                   else 0.0, job.sa_currency_id),
                'rider_fee': _money_block(job.sa_rider_fee if job.sa_delivery_state == 'delivered'
                                          else 0.0, job.sa_currency_id),
                'photo_counts': {'pickup': len(job.sa_pickup_photo_ids),
                                 'delivery': len(job.sa_delivery_photo_ids)},
                'photos': job.sa_photos_block('%s/proof' % _PREFIX),
                'currency': _currency_block(job.sa_currency_id),
            })
        return _json({
            'success': True,
            'total': total,            # stays: the app pages on it
            # every delivered job of this rider, not only this page
            # Delivery Partners: today / week / month / total; own riders
            # are on salary, so every figure is zero for them
            'earnings': rider.sudo().sa_earnings_by_period(),
            'counts': rider.sudo().sa_delivered_counts(),
            'limit': limit,
            'offset': offset,
            # ONE zone for every rider: the company's (the app names photos in it)
            'timezone': request.env['sa.delivery.partner'].sudo()._sa_company_tz(),
            'rider_timezone': rider.tz or '',
            'history': rows,
        })

    # ==================================================================
    # Moving the job along
    # ==================================================================
    def _advance(self, rider, order_id, action, otp_kind=None, code=None):
        """Validate, then call the same model method Odoo's buttons call."""
        job = self._one(rider, order_id)
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')

        wanted_from, wanted_to = job._SA_ACTION_STATE[action]
        if job.sa_delivery_state not in wanted_from:
            return _fail(
                _("This delivery is %(state)s - that is not possible now.",
                  state=job.sa_delivery_state),
                status=409, code='wrong_state',
                status_name=job.sa_delivery_state,
                allowed_actions=job.sa_allowed_actions())

        if action == 'accept' and job.sa_offer_expires_on \
                and fields.Datetime.now() > job.sa_offer_expires_on:
            job.sudo()._sa_expire_one()
            return _fail(_("This offer has expired - it went to another rider."),
                         status=409, code='offer_expired',
                         status_name=job.sa_delivery_state, allowed_actions=[])
        blocked = job.sa_action_blocked(action)
        if blocked:
            # a wait timer is running, or the parcel is being handed over
            return _fail(blocked.pop('message'), status=409,
                         status_name=job.sa_delivery_state,
                         allowed_actions=job.sa_allowed_actions(), **blocked)
        if otp_kind:
            ok, message = job.sa_verify_otp(otp_kind, code)
            if not ok:
                return _fail(message, status=400, code='bad_otp',
                             status_name=job.sa_delivery_state,
                             allowed_actions=job.sa_allowed_actions())

        branch_pickup = action == 'pickup' and job.sa_pickup_mode() == 'branch'
        if branch_pickup:
            job.sa_finish_branch_pickup()          # picked -> dispatched in one go
        else:
            job.sa_set_state(wanted_to)
        if action == 'accept':
            job.sudo().write({'sa_offer_expires_on': False})
            job.sudo()._sa_call_log_add(_("%s accepted", rider.name))
        out = {
            'success': True,
            'status': job.sa_delivery_state,
            'allowed_actions': job.sa_allowed_actions(),
            'tracking': {'enabled': job.sa_tracking_enabled()},
            'message': _("Done."),
        }
        if action == 'pickup':
            # the customer's location is unlocked now: hand it over at once
            out['order'] = self._full(job)
            if branch_pickup:
                out['message'] = _("Code verified. The parcel is yours - deliver to the address shown.")
        return _json(out)

    @http.route('%s/rider/location' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def rider_location(self, rider, **kw):
        """Where the rider is while waiting, with no job in hand.

        Different from `/location`, which is per-order and feeds the
        customer's tracking link. This one carries no order and exists so
        waiting work can be offered to whoever is nearest.

        The cadence is ours to set, not the app's: `poll_after_seconds` comes
        back on every call, so it can be tuned without a release. Continuous
        GPS is the largest battery cost in a shift-long app, so a rider
        holding nothing is asked for a fix far less often.
        """
        data = _body()
        if not rider.on_duty:
            # The app stops its location service on this and shows Start Duty.
            return _fail(_("You are no longer on duty."), status=409,
                         code='off_duty', on_duty=False)

        def _number(key):
            try:
                return float(data.get(key))
            except (TypeError, ValueError):
                return None

        lat, lng, _acc = _coords(data)
        vals = {'last_fix_on': fields.Datetime.now()}
        if lat is not None and lng is not None:
            vals.update({'last_lat': lat, 'last_lng': lng})
        battery = _number('battery')
        if battery is not None:
            vals['last_battery'] = battery
        rider.sudo().write(vals)
        rider.sudo()._sa_geocode(max_age_minutes=10)
        if lat is not None and lng is not None:
            # every job in hand follows the rider, so the tracking page moves
            # even when the app runs only this one loop (3 Oct 2026)
            Ping = request.env['sa.delivery.ping'].sudo()
            for job in self._jobs(rider, ['accepted', 'picked', 'dispatched',
                                          'out_for_delivery']):
                Ping._sa_record(job, lat, lng, _number('accuracy') or 0.0)

        held = self._jobs(rider, ['accepted', 'picked', 'dispatched',
                                  'out_for_delivery'])
        waiting = self._jobs(rider, ['offered'])
        return _json({
            'success': True,
            'on_duty': True,
            # Holding a parcel is worth a fix every half minute; waiting for
            # one is not.
            'poll_after_seconds': 30 if held else 120,
            # Saves the app a GET /orders every time round the loop.
            'has_new_offer': bool(waiting),
        })

    @http.route('%s/arrived' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def arrived(self, rider, **kw):
        """"Reached Pickup" and "Reached Customer", one endpoint.

        It records the arrival and, at the customer's door, sends them the
        completion code. Issuing it here rather than when the rider leaves the
        shop is the point of the endpoint: the code is then live for the few
        minutes it is needed instead of the whole journey.

        No geofence. There is nothing to measure against - no customer address
        in this database is geocoded - so a distance check would refuse honest
        arrivals. `422 too_far` is therefore never returned.
        """
        data = _body()
        job = self._one(rider, data.get('delivery_order_id'))
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')

        point = (data.get('point') or 'shop').strip().lower()
        if point not in ('shop', 'customer'):
            return _fail(_("Say whether you reached the shop or the "
                           "customer."), status=400, code='bad_point')

        # Arrival at the customer is only meaningful once the rider is on
        # the road: issuing the completion code at `dispatched` left a live
        # code on a job that /complete/verify-otp would still refuse.
        allowed = (('accepted',) if point == 'shop'
                   else ('out_for_delivery',))
        if job.sa_delivery_state not in allowed:
            return _fail(
                _("This delivery is %(state)s - that is not possible now.",
                  state=job.sa_delivery_state),
                status=409, code='wrong_state',
                status_name=job.sa_delivery_state,
                allowed_actions=job.sa_allowed_actions())

        stamp = fields.Datetime.now()
        out = {'success': True, 'arrived_at': _dt(stamp),
               'tracking': {'enabled': job.sa_tracking_enabled()}}

        if point == 'shop':
            job.sudo().write({'sa_arrived_shop_on': stamp})
            out['pickup_handover'] = job.sa_pickup_mode()
            if out['pickup_handover'] == 'branch':
                # The branch makes the code (Dispatch on its screen); the
                # rider only says "I am here".
                out['message'] = job.sa_rider_at_shop()
                out['otp_sent'] = False
                out['waiting_for_branch'] = True
            else:
                ok, message, code = job.sa_issue_pickup_otp()
                out['message'] = message
                out['otp_sent'] = bool(ok)
                _test_otp(out, code, job, 'pickup')
        else:
            job.sudo().write({'sa_arrived_customer_on': stamp})
            ok, message, code = job.sa_issue_delivery_otp()
            out['message'] = message
            out['otp_sent'] = bool(ok)
            _test_otp(out, code, job, 'delivery')

        out['status'] = job.sa_delivery_state
        out['allowed_actions'] = job.sa_allowed_actions()
        return _json(out)

    @http.route('%s/pickup/request-otp' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def pickup_request_otp(self, rider, **kw):
        job = self._one(rider, _body().get('delivery_order_id'))
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        if job.sa_delivery_state != 'accepted':
            return _fail(_("Not ready for pickup."), status=409,
                         code='wrong_state',
                         status_name=job.sa_delivery_state)
        if job.sa_pickup_mode() == 'branch':
            # No code from here: it rings the counter again and says so.
            return _json({'success': True, 'otp_sent': False,
                          'waiting_for_branch': True,
                          'pickup_handover': 'branch',
                          'pickup_code_ready': bool(job.sa_pickup_code_shown),
                          'message': job.sa_rider_at_shop(),
                          'status': job.sa_delivery_state,
                          'allowed_actions': job.sa_allowed_actions()})
        ok, message, code = job.sa_issue_pickup_otp()
        out = {'success': ok, 'message': message,
               'status': job.sa_delivery_state,
               'allowed_actions': job.sa_allowed_actions()}
        _test_otp(out, code, job, 'pickup')
        return _json(out)

    @http.route('%s/pickup/verify-otp' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def pickup_verify(self, rider, **kw):
        data = _body()
        return self._advance(rider, data.get('delivery_order_id'), 'pickup',
                             otp_kind='pickup', code=data.get('otp'))

    @http.route('%s/pickup' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def pickup(self, rider, **kw):
        """Kept for the shape in the spec. The OTP call already moved the job,
        so this only reports where it stands rather than skipping the code."""
        job = self._one(rider, _body().get('delivery_order_id'))
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        if job.sa_delivery_state == 'accepted':
            return _fail(_("Verify the pickup code first."), status=409,
                         code='otp_required',
                         status_name=job.sa_delivery_state,
                         allowed_actions=job.sa_allowed_actions())
        return _json({'success': True, 'status': job.sa_delivery_state,
                      'allowed_actions': job.sa_allowed_actions()})

    @http.route('%s/accept' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def accept(self, rider, **kw):
        relay = self._one_relay(rider, _body().get('delivery_order_id'))
        if relay:
            # taking a parcel over from a rider with a vehicle problem
            try:
                relay.sa_relay_accept(rider)
            except UserError as err:
                return _fail(str(err), status=409, code='offer_expired', allowed_actions=[])
            full = self._full(relay)
            return _json({'success': True, 'status': full.get('delivery_status'), 'is_relay': True,
                          'allowed_actions': full.get('allowed_actions'), 'order': full,
                          'message': _("Accepted. Ride to the rider shown and ask for the handover code.")})
        return self._advance(rider, _body().get('delivery_order_id'), 'accept')

    @http.route('%s/dispatch' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def dispatch(self, rider, **kw):
        job = self._one(rider, _body().get('delivery_order_id'))
        if job and job.sa_delivery_state == 'dispatched':
            # the pickup code already moved it (branch dispatch): not an error
            return _json({'success': True, 'status': job.sa_delivery_state,
                          'allowed_actions': job.sa_allowed_actions(),
                          'tracking': {'enabled': job.sa_tracking_enabled()},
                          'message': _("Already collected.")})
        return self._advance(rider, _body().get('delivery_order_id'),
                             'dispatch')

    @http.route('%s/start' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def start(self, rider, **kw):
        # The customer's code is issued by /arrived point=customer (Reached
        # Customer Location), not here - so nothing to echo in test mode.
        job = self._one(rider, _body().get('delivery_order_id'))
        if job and job.sa_delivery_state == 'out_for_delivery':
            # the server (or the counter) already marked it: not an error
            return _json({'success': True, 'status': job.sa_delivery_state,
                          'allowed_actions': job.sa_allowed_actions(),
                          'tracking': {'enabled': job.sa_tracking_enabled()},
                          'near_customer_at': _dt(job.sa_out_on),
                          'near_customer_auto': bool(job.sa_near_auto),
                          'message': _("Already near the customer")})
        return self._advance(rider, _body().get('delivery_order_id'),
                             'start_delivery')

    @http.route('%s/complete/verify-otp' % _PREFIX, type='http',
                auth='public', methods=['POST'], csrf=False)
    @authenticated
    def complete(self, rider, **kw):
        data = _body()
        result = self._advance(rider, data.get('delivery_order_id'),
                               'complete', otp_kind='delivery',
                               code=data.get('otp'))
        job = self._one(rider, data.get('delivery_order_id'))
        if job and job.sa_delivery_state == 'delivered':
            return _json({
                'success': True, 'status': 'delivered', 'allowed_actions': [],
                'tracking': {'enabled': False},
                'message': _("Delivery completed successfully"),
                'delivered_at': _dt(job.sa_delivered_on),
            })
        return result

    @http.route('%s/return' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def return_to_shop(self, rider, **kw):
        """Refused at the door, nobody home, wrong address.

        The rider says the parcel is coming back; only the shop says it
        arrived. Splitting the two is what stops goods being written back onto
        the shelf from the roadside.
        """
        data = _body()
        job = self._one(rider, data.get('delivery_order_id'))
        if job:
            job.sudo().sa_cancel_reason = (data.get('reason') or '')[:250]
        return self._advance(rider, data.get('delivery_order_id'),
                             'return_to_shop')

    @http.route('%s/return/confirm' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def return_confirm(self, rider, **kw):
        return self._advance(rider, _body().get('delivery_order_id'),
                             'confirm_return')

    # ==================================================================
    # Position and problems
    # ==================================================================
    @http.route('%s/location' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def location(self, rider, **kw):
        data = _body()
        job = self._one(rider, data.get('delivery_order_id'))
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        if not job.sa_tracking_enabled():
            # The app must stop its service on this. A delivered job is over,
            # and a rider's evening is their own.
            return _json({'success': False, 'stop': True,
                          'status': job.sa_delivery_state,
                          'message': _("Tracking is not active for this "
                                       "delivery.")})
        lat, lng, acc = _coords(data)
        if lat is None:
            # never "success" for a fix that cannot be stored
            return _fail(_("latitude and longitude are required (numbers)."),
                         status=400, code='bad_request', stop=False,
                         status_name=job.sa_delivery_state)
        request.env['sa.delivery.ping'].sudo()._sa_record(job, lat, lng, acc or 0.0)
        # the fleet view follows too
        rider.sudo().write({'last_lat': lat, 'last_lng': lng,
                            'last_fix_on': fields.Datetime.now()})
        return _json({'success': True, 'stop': False,
                      'status': job.sa_delivery_state,
                      # how soon to send the next fix: the customer is watching
                      # closely once the rider is near
                      'poll_after_seconds': 10 if (job.sa_delivery_state == 'out_for_delivery'
                                                   or (job.sa_near_pin_m() or 10 ** 6) <= 600) else 20})

    @http.route('%s/issue' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def issue(self, rider, **kw):
        data = _body()
        job = self._one(rider, data.get('delivery_order_id'))
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        reason = (data.get('reason') or data.get('message') or '').strip()[:250]
        kind = (data.get('type') or data.get('kind') or '').strip().lower()
        items = data.get('items') or data.get('missing_items') or []
        if isinstance(items, str):
            items = [x.strip() for x in items.split(',') if x.strip()]
        if reason.lower().startswith('item_missing'):
            # the app's own wording: "item_missing: <product> x<qty>; ..."
            reason = (_("Item missing") + reason[len('item_missing'):])[:250]
            kind = kind or 'item_missing'
        if not kind and ('missing' in reason.lower() or items):
            kind = 'item_missing'
        if items:
            names = ', '.join(str(i.get('name') if isinstance(i, dict) else i) for i in items)[:200]
            reason = (_("Item missing: %s", names) + ((' - ' + reason) if reason and 'missing' not in reason.lower() else ''))[:250]
        from odoo.addons.sales_automation_delivery.models.sa_rider_problems import REASONS
        legacy_note = ''
        if reason.lower().startswith('other:'):
            # an older app build sent the rider's words inside the reason
            legacy_note, reason = reason[6:].strip(), 'other'
        code = reason.lower() if reason.lower() in REASONS else (kind if kind in REASONS else '')
        if code:
            # A reason with a next step (5 Oct 2026): the customer is messaged,
            # a timer runs, the return unlocks, or the parcel goes to another rider.
            upload = request.httprequest.files.get('file') or request.httprequest.files.get('photo')
            payload = upload.read() if upload else None
            if payload and len(payload) > 8 * 1024 * 1024:
                return _fail(_("The photo is larger than 8 MB - send a smaller one."),
                             status=413, code='too_large', max_bytes=8 * 1024 * 1024)
            note = (data.get('note') or data.get('details') or data.get('comment')
                    or (data.get('message') if reason.lower() in REASONS else '')
                    or legacy_note or '').strip()[:500]
            res = job.sudo().sa_report_problem(rider, code, note, payload,
                                               upload.filename if upload else '')
            _logger.info("Delivery API: %s reported %s on job %s -> %s", rider.name, code,
                         job.sa_ref_code, res['next'].get('kind'))
            if res.get('released'):
                return _json({'success': True, 'status': 'released', 'reason': code,
                              'message': res['message'], 'next': res['next'], 'allowed_actions': []})
            full = self._full(job)
            return _json({'success': True, 'status': full.get('delivery_status'), 'reason': code,
                          'message': res['message'], 'next': res['next'],
                          'allowed_actions': full.get('allowed_actions'), 'order': full})
        # kept on the job, red on the Shop Queue card, rings the counter
        job.sudo().with_context(
            sa_note=(data.get('note') or data.get('details') or data.get('comment') or '').strip()[:500]
        ).sa_rider_report(rider, kind or 'issue', reason or _("a problem"))
        _logger.info("Delivery API: %s reported %r on job %s", rider.name,
                     reason[:40], job.sa_ref_code)
        return _json({'success': True, 'status': job.sa_delivery_state,
                      'allowed_actions': job.sa_allowed_actions(),
                      'next': {'kind': 'none'},
                      'message': _("Reported. Someone will follow up.")})

    # ---- rider-to-rider handover (vehicle problem with the parcel on board) ----
    @http.route('%s/heading' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def heading(self, rider, **kw):
        """The rider is heading to this customer now (Express runs: the
        customer's page switches to live for the next stop)."""
        job = self._one(rider, _body().get('delivery_order_id'))
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        info = job.sudo().sa_action_heading(rider)
        if info is None:
            return _fail(_("This delivery is %(state)s - that is not possible now.", state=job.sa_delivery_state),
                         status=409, code='wrong_state', status_name=job.sa_delivery_state,
                         allowed_actions=job.sa_allowed_actions())
        return _json({'success': True, 'stop_no': info['stop_no'], 'stops_total': info['stops_total'],
                      'status': job.sa_delivery_state})

    @http.route('%s/app/crash' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def app_crash(self, rider, **kw):
        """Crash reports kept on the rider's phone, up to 20 a call."""
        data = _body()
        reports = data.get('reports')
        if isinstance(reports, str):
            try:
                reports = json.loads(reports)
            except ValueError:
                reports = []
        if not isinstance(reports, list):
            return _fail(_("Send {reports: [...]}."), status=400, code='bad_request')
        saved = request.env['sa.app.crash'].sudo().sa_store_reports(rider, reports)
        return _json({'success': True, 'saved': saved})

    @http.route('%s/sos' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def sos(self, rider, **kw):
        """The rider held SOS: store it, alert the office at once. A repeat
        of the same rider + `at` is the same alert (the app retries)."""
        data = _body()
        if isinstance(data.get('contacts'), str):
            try:
                data['contacts'] = json.loads(data['contacts'])
            except ValueError:
                data['contacts'] = []
        alert = request.env['sa.sos.alert'].sudo().sa_raise(rider, data)
        return _json({'success': True, 'alert_id': alert.id, 'office_notified': bool(alert.notified_on),
                      'whatsapp_sent': bool(alert.whatsapp_sent)})

    @http.route('%s/customer-code/resend' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def customer_code_resend(self, rider, **kw):
        """The customer's code again, with a true answer: sent or not, and
        how long to wait before the next one."""
        job = self._one(rider, _body().get('delivery_order_id'))
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        res = job.sa_resend_customer_code(rider)
        code = res.pop('code', None)
        out = {'success': True, 'status': job.sa_delivery_state, 'allowed_actions': job.sa_allowed_actions()}
        out.update(res)
        if res.get('sent'):
            _test_otp(out, code, job, 'delivery')
        return _json(out)

    @http.route('%s/handover/verify' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def handover_verify(self, rider, **kw):
        """The second rider types the code the first rider shows."""
        data = _body()
        job = self._one_relay(rider, data.get('delivery_order_id'))
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        ok, message = job.sa_relay_verify(rider, data.get('code') or data.get('otp') or '')
        if not ok:
            return _fail(message, status=400, code='bad_otp', status_name='accepted',
                         allowed_actions=['verify_handover', 'decline', 'report_issue'])
        full = self._full(job)
        return _json({'success': True, 'status': full.get('delivery_status'), 'message': message,
                      'allowed_actions': full.get('allowed_actions'), 'order': full})

    @http.route('%s/handover/cancel' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def handover_cancel(self, rider, **kw):
        """The rider with the parcel can go on after all."""
        job = self._one(rider, _body().get('delivery_order_id'))
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        if not job.sa_relay_cancel(rider):
            return _fail(_("No handover is open for this delivery."), status=409, code='wrong_state',
                         status_name=job.sa_delivery_state, allowed_actions=job.sa_allowed_actions())
        full = self._full(job)
        return _json({'success': True, 'status': full.get('delivery_status'),
                      'allowed_actions': full.get('allowed_actions'), 'order': full,
                      'message': _("Handover cancelled. Continue the delivery.")})

    @http.route('%s/handover/new-code' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def handover_new_code(self, rider, **kw):
        job = self._one(rider, _body().get('delivery_order_id'))
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        try:
            code = job.sa_relay_new_code()
        except UserError as err:
            return _fail(str(err), status=409, code='wrong_state', status_name=job.sa_delivery_state)
        return _json({'success': True, 'handover_code': code, 'status': 'handover_waiting'})

    @http.route('%s/decline' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def decline(self, rider, **kw):
        """The rider refuses an offered job. It goes back to To Dispatch and
        is offered to the next on-duty rider who has not declined it."""
        data = _body()
        relay = self._one_relay(rider, data.get('delivery_order_id'))
        if relay:
            relay.sa_relay_decline(rider, (data.get('reason') or '').strip()[:250])
            return _json({'success': True, 'status': 'declined', 'is_relay': True,
                          'allowed_actions': [], 'message': _("Declined.")})
        job = self._one(rider, data.get('delivery_order_id'))
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        if job.sa_delivery_state not in ('offered', 'accepted'):
            return _fail(_("This delivery is %(state)s - that is not possible now.",
                           state=job.sa_delivery_state),
                         status=409, code='wrong_state',
                         status_name=job.sa_delivery_state,
                         allowed_actions=job.sa_allowed_actions())
        try:
            job.sudo().sa_action_decline(rider, (data.get('reason') or '').strip()[:250])
        except UserError as err:
            return _fail(str(err.args[0] if err.args else err), status=409,
                         code='wrong_state', status_name=job.sa_delivery_state)
        job.invalidate_recordset()
        return _json({'success': True, 'status': job.sa_delivery_state,
                      'reassigned_to': job.sa_delivery_partner_id.name or '',
                      'allowed_actions': [],
                      'message': _("Declined. The job is being offered to another rider.")})

    @http.route('%s/push/register' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def push_register(self, rider, **kw):
        """Keep the device's push token on this app session. Nothing is
        sent to it yet; the app can read it back in /auth/me."""
        data = _body()
        platform = (data.get('platform') or '').strip().lower()
        token = (data.get('token') or data.get('push_token') or '').strip()
        if platform not in ('android', 'ios', 'web') or not token:
            return _fail(_("platform (android | ios | web) and token are required."),
                         code='bad_request')
        row = _token_row()
        if not row:
            return _fail(_("No app session - sign in with the phone code first."),
                         status=409, code='no_device')
        row.write({'push_platform': platform, 'push_token': token[:512]})
        return _json({'success': True, 'push': {'platform': platform, 'registered': True}})

    @http.route('%s/push/unregister' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def push_unregister(self, rider, **kw):
        row = _token_row()
        if row:
            row.write({'push_platform': False, 'push_token': False})
        return _json({'success': True, 'push': {'platform': '', 'registered': False}})

    @http.route('%s/proof' % _PREFIX, type='http', auth='public',
                methods=['POST'], csrf=False)
    @authenticated
    def proof(self, rider, **kw):
        """A photo at the door, stored against the delivery."""
        data = _body()
        job = self._one(rider, data.get('delivery_order_id'))
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        upload = request.httprequest.files.get('file')
        payload = upload.read() if upload else None
        if not payload:
            return _fail(_("No file received."), status=400, code='bad_request')
        if len(payload) > 8 * 1024 * 1024:
            return _fail(_("The photo is larger than 8 MB - send a smaller one."),
                         status=413, code='too_large', max_bytes=8 * 1024 * 1024)
        # Parcel photos at both ends (5 Oct 2026): `stage` = pickup | delivery,
        # the app's own file name is kept, 4 at most per stage, and the same
        # file sent twice is one photo.
        res = job.sa_add_proof_photo(data.get('stage') or kw.get('stage'),
                                     upload.filename, payload)
        if res.get('error'):
            return _fail(res.get('message') or _("Not possible now."), status=409,
                         code=res['error'], status_name=job.sa_delivery_state,
                         count=res.get('count'), max=res.get('max'))
        return _json({'success': True, 'message': _("Proof saved."),
                      'attachment_id': res['attachment_id'], 'size': len(payload),
                      'stage': res['stage'], 'name': res['name'],
                      'count': res['count'], 'duplicate': res['duplicate'],
                      'status': job.sa_delivery_state,
                      # the server never blocks a step on a photo
                      'required': False})

    @http.route('%s/proof/<int:attachment_id>' % _PREFIX, type='http', auth='public',
                methods=['GET'], csrf=False)
    @authenticated
    def proof_get(self, rider, attachment_id, **kw):
        """One parcel photo of one of this rider's jobs."""
        att = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        job = request.env['stock.picking'].sudo().browse(att.res_id) \
            if att and att.res_model == 'stock.picking' else None
        if not job or job.sa_delivery_partner_id != rider or not job.sa_photo_for(att.id):
            return _fail(_("Not found."), status=404, code='not_found')
        return request.make_response(att.raw or b'', headers=[
            ('Content-Type', att.mimetype or 'image/jpeg'),
            ('Content-Disposition', 'inline; filename="%s"' % (att.name or 'photo.jpg')),
            ('Cache-Control', 'private, max-age=86400')])
