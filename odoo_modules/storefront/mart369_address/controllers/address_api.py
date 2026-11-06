"""Delivery addresses for the signed-in customer, and reverse geocoding.

Same shape as mart369_auth's routes: type='http' answering bare JSON, called
by the storefront's own server rather than straight from a browser.

The one rule that matters here: a customer may only ever touch an address that
hangs off their own partner. Every route goes through _own() to get there, and
_own() returns nothing for anyone else's id - so guessing ids gets a 404, not
somebody else's home address.

What an address must contain, and how an edit to one an order has used is kept
away from that order, lives on res.partner (models/address_rules.py): the staff
routes and the Odoo dialog save addresses through the same methods.
"""

import json
import logging

from odoo import http
from odoo.http import request

from odoo.addons.mart369_address.models.res_partner import ADDRESS_TYPES

_logger = logging.getLogger(__name__)

_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'], 'csrf': False, 'sitemap': False}
_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'], 'csrf': False, 'sitemap': False}
_PATCH = {'type': 'http', 'auth': 'user', 'methods': ['PATCH'], 'csrf': False, 'sitemap': False}
_DELETE = {'type': 'http', 'auth': 'user', 'methods': ['DELETE'], 'csrf': False, 'sitemap': False}

# Geocoding is public: the app asks before anyone has signed in.
_GEO = {'type': 'http', 'auth': 'public', 'methods': ['POST'], 'csrf': False, 'sitemap': False}
_GET_PUBLIC = {'type': 'http', 'auth': 'public', 'methods': ['GET'], 'csrf': False, 'sitemap': False}


class Mart369AddressApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:
            data = None
        return data if isinstance(data, dict) else {}

    def _fail(self, error, field=None, status=400):
        payload = {'ok': False, 'error': error}
        if field:
            payload['field'] = field
        return self._json(payload, status=status)

    def _me(self):
        return request.env.user.partner_id

    def _mine(self):
        """Every address belonging to the signed-in customer."""
        return self._me().sudo()._mart369_book()

    def _own(self, pid):
        """One address, but only if it is this customer's. Anything else -
        another customer's address, a company, a made-up id - comes back empty
        and the caller answers 404."""
        empty = request.env['res.partner'].browse()
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return empty
        address = request.env['res.partner'].sudo().browse(pid).exists()
        if not address or address.parent_id != self._me() or address.type not in ADDRESS_TYPES:
            return empty
        return address

    def _values(self, body, address=None):
        """Map what the app sent onto partner fields. Returns (values, error)."""
        return request.env['res.partner'].sudo()._mart369_address_values(
            body, address=address, parent=self._me())

    def _list(self):
        mine = self._mine()
        selected = mine.filtered('mart369_default')[:1]
        return {
            'ok': True,
            'addresses': [a._mart369_serialize() for a in mine],
            'selected': selected.id if selected else None,
            'phone': request.env['res.partner']._mart369_phone_hint(partner=self._me()),
        }

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/addresses', **_GET)
    def index(self, **kwargs):
        return self._json(self._list())

    @http.route('/369mart/addresses', **_POST)
    def create(self, **kwargs):
        body = self._body()
        for required in ('name', 'line', 'phone'):
            body.setdefault(required, '')
        values, error = self._values(body)
        if error:
            return self._fail(error[0], error[1])
        address = self._me().sudo()._mart369_add_address(values)
        return self._json({'ok': True, 'address': address._mart369_serialize()}, status=201)

    @http.route('/369mart/addresses/<int:pid>', **_PATCH)
    def update(self, pid, **kwargs):
        address = self._own(pid)
        if not address:
            return self._fail('No such address.', status=404)
        values, error = self._values(self._body(), address=address)
        if error:
            return self._fail(error[0], error[1])
        # An address an order has used is copied, not rewritten; the answer
        # carries the address to use from now on, which may have a new id.
        address = address._mart369_revise(values)
        return self._json({'ok': True, 'address': address._mart369_serialize()})

    @http.route('/369mart/addresses/<int:pid>', **_DELETE)
    def remove(self, pid, **kwargs):
        address = self._own(pid)
        if not address:
            return self._fail('No such address.', status=404)
        was_default = address.mart369_default

        # Hand the crown over *before* archiving, not after. Doing it the other
        # way round meant `_mine()` - which has no `active_test=False` - could
        # no longer see this one, so the successor search ran against a list
        # that had already lost a member, and if this was the only address the
        # customer was left with none selected at all.
        successor = request.env['res.partner']
        if was_default:
            successor = self._mine().filtered(lambda a: a.id != address.id)[:1]

        # Archive rather than delete: orders already placed still point here.
        # `type` goes back to 'other' with it. Clearing `mart369_default` alone
        # left an archived record still typed 'delivery', so Odoo's own
        # `address_get('delivery')` kept resolving to the address the customer
        # had just removed - the app said nothing was selected while the shop
        # would have shipped there.
        address.write({'active': False, 'mart369_default': False, 'type': 'other'})

        if successor:
            successor._mart369_set_default()
        return self._json({'ok': True})

    @http.route('/369mart/addresses/<int:pid>/default', **_POST)
    def make_default(self, pid, **kwargs):
        address = self._own(pid)
        if not address:
            return self._fail('No such address.', status=404)
        address._mart369_set_default()
        return self._json(self._list())

    # ----------------------------------------------------------- the form

    @http.route('/369mart/addresses/form', **_GET)
    def form(self, country=None, **kwargs):
        """What the address form needs to draw itself for one country - the
        one picked (?country=IN), else where a new address starts. The form
        hard-codes none of it."""
        return self._json(request.env['res.partner']._mart369_form_meta(country, parent=self._me()))

    # ------------------------------------------------------- pincode lookup

    @http.route('/369mart/pincode/<string:pin>', **_GET_PUBLIC)
    def pincode(self, pin, **kwargs):
        """City, state and the post offices for an Indian pincode, so the form
        can fill itself in the way Flipkart's does."""
        return self._json(request.env['res.partner']._mart369_pincode_lookup(pin))

    # ------------------------------------------------------------- geocoding

    @http.route('/369mart/geocode/reverse', **_GEO)
    def reverse(self, **kwargs):
        """Turn a phone's GPS fix into something a delivery form can show.

        Uses Odoo's own base_geolocalize, which calls OpenStreetMap Nominatim -
        no API key. Nominatim asks for roughly one request a second, so answers
        are cached per rounded coordinate (about 100 m).
        """
        body = self._body()
        try:
            lat, lng = float(body.get('lat')), float(body.get('lng'))
        except (TypeError, ValueError):
            return self._fail('Send lat and lng.')

        key = 'mart369.geo.%.3f,%.3f' % (lat, lng)
        params = request.env['ir.config_parameter'].sudo()
        cached = params.get_param(key)
        if cached:
            return self._json(json.loads(cached))

        try:
            raw = request.env['base.geocoder'].sudo()._call_openstreetmap_reverse(lat, lng)
        except Exception as exc:  # noqa: BLE001 - offline, rate-limited, or disabled in tests
            _logger.info('reverse geocode failed: %s', exc)
            return self._fail("Couldn't find that location. Enter the address by hand.", status=502)

        address = (raw or {}).get('address') or {}
        city = (address.get('city') or address.get('town') or address.get('village')
                or address.get('city_district') or address.get('county') or '')
        area = ', '.join(p for p in (
            address.get('neighbourhood'), address.get('suburb'), address.get('city_district'),
        ) if p and p != city)
        code = (address.get('country_code') or '').upper()
        country = request.env['res.country'].search([('code', '=', code)], limit=1)
        state = request.env['res.country.state'].browse()
        if country and address.get('state'):
            state = request.env['res.country.state'].search([
                ('country_id', '=', country.id), ('name', '=ilike', address['state']),
            ], limit=1)

        payload = {
            'ok': True,
            'area': area or address.get('road') or '',
            'line': address.get('road') or '',
            'city': city,
            'state': state.name or address.get('state') or '',
            'state_id': state.id or False,
            'zip': address.get('postcode') or '',
            'country': country.name or address.get('country') or '',
        }
        params.set_param(key, json.dumps(payload))
        return self._json(payload)
