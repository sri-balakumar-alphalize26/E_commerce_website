"""The rules for a 369 Mart address, in one place.

The customer's app (controllers/address_api.py), the staff routes
(controllers/admin_api.py) and the Odoo dialog staff edit in
(wizard/address_wizard.py) all save addresses. They used to be one controller's
private helpers; now every door calls these, so an address is checked the same
way whoever types it.

The one rule that is new here: **an address an order has shipped to is never
edited in place.** Flipkart and Amazon keep the address an order was placed
with; so does 369 Mart. Editing such an address makes a fresh copy for the
customer to use from now on and archives the old one, which the orders keep.
"""

import json
import logging
import re

import requests

from odoo import api, models

from .res_partner import ADDRESS_TYPES

_logger = logging.getLogger(__name__)

# Changing any of these changes where a parcel goes, so an address already on
# an order is copied rather than rewritten. The label and the default flag are
# the customer's bookkeeping and never copy.
CONTENT_FIELDS = (
    'name', 'phone', 'mart369_alt_phone', 'street', 'street2', 'mart369_landmark',
    'city', 'zip', 'state_id', 'country_id',
)


def _plain(name):
    """'Jammu & Kashmir' and 'Jammu and Kashmir' are the same state; so are
    India Post's 'Chattisgarh' spellings once the letters are compared."""
    return re.sub(r'[^a-z]', '', (name or '').lower().replace('&', 'and'))


def _text(body, key):
    value = body.get(key)
    return value.strip() if isinstance(value, str) else ''


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ------------------------------------------------------------ countries

    @api.model
    def _mart369_india(self):
        return self.env['res.country'].search([('code', '=', 'IN')], limit=1)

    @api.model
    def _mart369_default_country(self, parent=None):
        """Where a new address starts: the customer's own country, else India
        - the shop's customers are Indian even where the company sits
        elsewhere - else the company's."""
        return ((parent and parent.country_id) or self._mart369_india()
                or self.env.company.country_id)

    @api.model
    def _mart369_find_country(self, value):
        """A country from what the app sent: an id, or a code like 'IN'."""
        Country = self.env['res.country']
        if not value:
            return Country
        if isinstance(value, str) and not value.isdigit():
            return Country.search([('code', '=', value.upper())], limit=1)
        try:
            return Country.browse(int(value)).exists()
        except (TypeError, ValueError):
            return Country

    @api.model
    def _mart369_pin_length(self, country):
        """India's pincodes are always six digits; elsewhere anything from
        three (Oman) to ten is let through."""
        return 6 if (country.code or '').upper() == 'IN' else 0

    # --------------------------------------------------------- the form meta

    @api.model
    def _mart369_form_meta(self, country=None, parent=None):
        """What an address form needs to draw itself for one country: the phone
        prefix, the pincode length, the states, and every country for the
        picker, the likely ones first."""
        country = self._mart369_find_country(country) or self._mart369_default_country(parent)
        suggested = []
        for near in (self._mart369_default_country(parent), self._mart369_india(),
                     self.env.company.country_id):
            if near.code and near.code not in suggested:
                suggested.append(near.code)
        return {
            'ok': True,
            'suggested': suggested,
            'country': {'id': country.id, 'code': country.code or '', 'name': country.name or ''},
            'countries': [{'id': c.id, 'code': c.code, 'name': c.name,
                           'dial': '+%s' % c.phone_code if c.phone_code else ''}
                          for c in self.env['res.country'].search([], order='name')],
            'phone': self._mart369_phone_hint(region=country.code),
            'pin_length': self._mart369_pin_length(country),
            'pin_lookup': (country.code or '').upper() == 'IN',
            'states': [{'id': s.id, 'name': s.name, 'code': s.code}
                       for s in country.state_ids.sorted('name')],
        }

    # ------------------------------------------------------- pincode lookup

    @api.model
    def _mart369_pincode_lookup(self, pin):
        """City, state and the post offices for an Indian pincode.

        Asks India Post's free API (no key) and keeps each answer: a pincode's
        district does not move. Anything that goes wrong answers ok:false and
        the form stays manual.
        """
        india = self._mart369_india()
        if not india or not re.fullmatch(r'\d{6}', pin or ''):
            return {'ok': False}
        key = 'mart369.pin.%s' % pin
        params = self.env['ir.config_parameter'].sudo()
        cached = params.get_param(key)
        if cached:
            return json.loads(cached)
        try:
            # India Post hangs up on the default python-requests agent.
            reply = requests.get('https://api.postalpincode.in/pincode/%s' % pin, timeout=5,
                                 headers={'User-Agent': 'Mozilla/5.0 (369 Mart address form)'})
            reply.raise_for_status()
            found = (reply.json() or [{}])[0]
        except Exception as exc:  # noqa: BLE001 - offline, slow, or blocked in tests
            _logger.info('pincode lookup failed for %s: %s', pin, exc)
            return {'ok': False}
        offices = (found.get('PostOffice') or []) if found.get('Status') == 'Success' else []
        if not offices:
            return {'ok': False}
        first = offices[0]
        wanted = _plain(first.get('State'))
        state = india.state_ids.filtered(lambda s: _plain(s.name) == wanted)[:1]
        areas = []
        for office in offices:
            name = (office.get('Name') or '').strip()
            if name and name not in areas:
                areas.append(name)
        payload = {
            'ok': True,
            'pin': pin,
            'town': first.get('District') or first.get('Block') or '',
            'state_id': state.id or False,
            'state': state.name or first.get('State') or '',
            'areas': areas,
        }
        params.set_param(key, json.dumps(payload))
        return payload

    # ---------------------------------------------------- what was sent -> fields

    @api.model
    def _mart369_address_values(self, body, address=None, parent=None):
        """Map an address form onto partner fields. Returns (values, error),
        error being (message, field).

        Creating needs every line a rider reads off the parcel: name, mobile,
        flat, area, town, pincode and - where the country has them - state.
        Editing only touches the keys sent, but may not blank a required one.
        """
        address = address or self.browse()
        parent = parent or address.parent_id
        if 'country_id' in body and not self._mart369_find_country(body.get('country_id')):
            return None, ('Pick a country.', 'country')
        country = (self._mart369_find_country(body.get('country_id'))
                   or address.country_id or self._mart369_default_country(parent))
        creating = not address
        # An address saved before countries were asked has none: filling it in
        # is not a move, and must not suddenly demand a state.
        moved = bool(address) and bool(address.country_id) and address.country_id != country
        # The phone rule follows the address's country, not the customer's:
        # a Chennai address booked from Muscat still wants a +91 number.
        holder = self.new({'country_id': country.id})
        values = {}

        if 'label' in body:
            values['mart369_label'] = _text(body, 'label') or 'Home'
        for key, field, message in (
            ('name', 'name', 'Enter the name this is delivered to.'),
            ('line', 'street', 'Enter the house no., building or apartment.'),
            ('area', 'street2', 'Enter the road name, area or colony.'),
        ):
            if (creating or key in body) and not _text(body, key):
                return None, (message, key)
            if key in body:
                values[field] = _text(body, key)
        if 'landmark' in body:
            values['mart369_landmark'] = _text(body, 'landmark')

        # Town and pincode arrive apart from the new form; older callers still
        # send them joined as `city` ("Dindigul 624003").
        joined = 'city' in body and 'town' not in body and 'pin' not in body
        if joined:
            town, pin = self._mart369_split_city(body.get('city'))
        else:
            town, pin = _text(body, 'town'), _text(body, 'pin')
        if creating or joined or 'town' in body:
            if not town:
                return None, ('Enter the city, district or town.', 'town')
            values['city'] = town
        if creating or joined or 'pin' in body:
            length = self._mart369_pin_length(country)
            if not pin:
                return None, ('Enter the pincode.', 'pin')
            if not re.fullmatch(r'\d{%d}' % length if length else r'\d{3,10}', pin):
                return None, ('Enter a %d-digit pincode.' % length if length
                              else 'Enter a valid pincode.', 'pin')
            values['zip'] = pin

        has_states = bool(country.state_ids)
        if 'state_id' in body or ((creating or moved) and has_states):
            state = self.env['res.country.state']
            try:
                state = state.browse(int(body.get('state_id') or 0)).exists()
            except (TypeError, ValueError):
                state = state.browse()
            if state and state.country_id != country:
                state = state.browse()
            if not state and has_states:
                return None, ('Pick a state.', 'state')
            values['state_id'] = state.id or False
        if (creating or moved or not address.country_id) and country:
            values['country_id'] = country.id
            if moved and 'state_id' not in body:
                values['state_id'] = False

        if 'phone' in body:
            ok, phone = self._mart369_check_mobile(body.get('phone'), partner=holder, required=True)
            if not ok:
                return None, (phone, 'phone')
            values['phone'] = phone
        if 'alt' in body:
            ok, alt = self._mart369_check_mobile(body.get('alt'), partner=holder, required=False)
            if not ok:
                return None, (alt, 'alt')
            values['mart369_alt_phone'] = alt
        for key, field in (('lat', 'partner_latitude'), ('lng', 'partner_longitude')):
            if body.get(key):
                try:
                    values[field] = float(body[key])
                except (TypeError, ValueError):
                    pass
        return values, None

    # ---------------------------------------------------------- the address book

    def _mart369_book(self, active_test=True):
        """Every address hanging off this customer, the default first."""
        self.ensure_one()
        return self.with_context(active_test=active_test).search([
            ('parent_id', '=', self.id),
            ('type', 'in', ADDRESS_TYPES),
        ], order='mart369_default desc, id asc')

    def _mart369_add_address(self, values):
        """Add an address under this customer; the first one becomes the
        default, as does one added while none is."""
        self.ensure_one()
        address = self.create(dict(values, parent_id=self.id, type='other'))
        if not self._mart369_book().filtered('mart369_default'):
            address._mart369_set_default()
        return address

    # ------------------------------------------------ an order's address stays put

    def _mart369_in_use(self):
        """Has an order shipped (or is one about to ship) to this address?
        Nothing here knows about orders; mart369_order answers for real."""
        self.ensure_one()
        return False

    def _mart369_revise(self, values):
        """Apply an edit and return the address to use from now on.

        In place, unless the edit changes where a parcel goes *and* an order
        already points here - then the order keeps this record (archived) and
        the customer carries on with a copy that has the new lines.
        """
        self.ensure_one()
        moving = any(
            field in values and self._fields[field].convert_to_write(self[field], self) != values[field]
            # Giving an old address the country it never had moves nothing.
            and not (field == 'country_id' and not self.country_id)
            for field in CONTENT_FIELDS
        )
        if not moving or not self._mart369_in_use():
            self.write(values)
            return self
        was_default = self.mart369_default
        # The name is passed on purpose: res.partner.copy() would otherwise
        # hand the customer "Ravi Kumar (copy)".
        fresh = self.copy(dict(values, name=values.get('name', self.name), type='other',
                               mart369_default=False, parent_id=self.parent_id.id))
        # Archived exactly as a removed address is: orders keep pointing here,
        # and Odoo's own address_get('delivery') no longer lands on it.
        self.write({'active': False, 'mart369_default': False, 'type': 'other'})
        if was_default:
            fresh._mart369_set_default()
        return fresh
