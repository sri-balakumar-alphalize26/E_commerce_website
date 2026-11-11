"""Where each postcode is on the map, so a branch can find the ones around it.

Two sources, because no free list covers every country:

* **GeoNames** (download.geonames.org/export/zip) - one file per country, about
  120 countries (India, UAE, UK, US, Malaysia ...). Downloaded once, then read
  offline. Credit: "Postcodes from GeoNames".
* **OpenStreetMap** (Nominatim) for everywhere else - Oman, Saudi Arabia and
  the rest. A background job asks "what is the postcode here?" at points every
  2 km around the branch, one a second as their rules ask. Credit:
  "(c) OpenStreetMap contributors".

A country with no postcodes at all simply finds none: a customer's map pin and
the branch distance already decide delivery, and service areas never block an
order.

Nothing here is ever shown to a shopper; it only fills the tick list the
delivery screens offer when adding service areas.
"""

import io
import json
import logging
import math
import time
import zipfile

import requests

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.modules import module as odoo_module

from .branch import EDITOR_GROUP, has_pin, haversine_km

_logger = logging.getLogger(__name__)

GEONAMES_URL = 'https://download.geonames.org/export/zip/%s.zip'
# The countries GeoNames has a postcode file for (its export/zip listing).
GEONAMES_COUNTRIES = frozenset((
    'AD AE AI AL AM AR AS AT AU AX AZ BD BE BG BM BR BY CA CC CH CL CN CO CR CX '
    'CY CZ DE DK DO DZ EC EE ES FI FK FM FO FR GB GF GG GI GL GP GS GT GU HK HM '
    'HN HR HT HU ID IE IM IN IO IS IT JE JP KE KR LI LK LT LU LV MA MC MD MH MK '
    'MN MO MP MQ MT MW MX MY NC NF NL NO NR NU NZ PA PE PF PH PK PL PM PN PR PT '
    'PW PY RE RO RS RU SE SG SI SJ SK SM TC TH TR UA US UY VA VI WF WS YT ZA'
).split())
NOMINATIM_URL = 'https://nominatim.openstreetmap.org/reverse'
NOMINATIM_SEARCH_URL = 'https://nominatim.openstreetmap.org/search'
# Nominatim asks for a name for the app; a generic one, no personal details.
USER_AGENT = '369Mart-delivery/1.0'
GRID_KM = 2.0           # one OpenStreetMap question every 2 km
BATCH = 50              # points per cron run, about a minute at 1 a second
CREDIT = 'Postcodes from GeoNames and © OpenStreetMap contributors'


def clean_pincode(value):
    """One way to write a postcode everywhere: no spaces or dashes, letters
    upper-case. "sw1a 1aa" -> "SW1A1AA", "100-0001" -> "1000001"."""
    return ''.join(str(value or '').replace('-', ' ').split()).upper()


def is_pincode(value):
    """Letters and digits only, 1 to 10 of them (a prefix like 62 counts)."""
    return bool(value) and len(value) <= 10 and value.isascii() and value.isalnum()


class Mart369Postcode(models.Model):
    _name = 'mart369.postcode'
    _description = '369 Mart Postcode on the Map'
    _order = 'country_code, postcode'
    _rec_name = 'postcode'

    country_code = fields.Char(string='Country', size=2, required=True, index=True)
    postcode = fields.Char(string='Postcode', required=True, index=True)
    place = fields.Char(string='Place')
    lat = fields.Float(string='Latitude', digits=(10, 7), index=True)
    lng = fields.Float(string='Longitude', digits=(10, 7))
    source = fields.Selection(
        [('geonames', 'GeoNames'), ('osm', 'OpenStreetMap')], required=True)

    _country_postcode_uniq = models.Constraint(
        'unique (country_code, postcode)',
        'That postcode is already on the map for this country.',
    )

    # ---------------------------------------------------------- the network
    # Small methods of their own so tests can stand in for the internet.

    @api.model
    def _mart369_get(self, url, params=None, timeout=30):
        response = requests.get(url, params=params, timeout=timeout,
                                headers={'User-Agent': USER_AGENT})
        response.raise_for_status()
        return response

    @api.model
    def _mart369_pause(self, seconds):
        time.sleep(seconds)

    @api.model
    def _mart369_reverse(self, lat, lng, zoom=16):
        """OpenStreetMap's answer for one point: {'country', 'postcode',
        'place'}, any of them empty. Raises on a network problem."""
        data = self._mart369_get(NOMINATIM_URL, params={
            'format': 'jsonv2', 'lat': '%.6f' % lat, 'lon': '%.6f' % lng,
            'zoom': zoom, 'addressdetails': 1}, timeout=20).json() or {}
        address = data.get('address') or {}
        place = (address.get('suburb') or address.get('town') or address.get('city')
                 or address.get('village') or address.get('county') or '')
        return {'country': (address.get('country_code') or '').upper(),
                'postcode': clean_pincode(address.get('postcode')),
                'place': place}

    @api.model
    def _mart369_country_at(self, lat, lng):
        """The country a map pin is in, from OpenStreetMap ('' at sea)."""
        try:
            return self._mart369_reverse(lat, lng, zoom=3)['country']
        except (requests.RequestException, ValueError) as exc:
            raise UserError(self.env._(
                "We couldn't reach OpenStreetMap to see which country the branch "
                "is in. Check the internet and try again. (%s)", exc)) from exc

    @api.model
    def _mart369_search(self, params):
        """OpenStreetMap's best match for an address: (lat, lng), or None when
        it knows no such place. Raises on a network problem."""
        data = self._mart369_get(NOMINATIM_SEARCH_URL, params=dict(
            params, format='jsonv2', limit=1), timeout=20).json() or []
        if not data:
            return None
        return float(data[0]['lat']), float(data[0]['lon'])

    @api.model
    def _mart369_locate(self, partner):
        """Where an address is on the map, for "Find from the address".

        Tries the street, then the pincode, then the town: the first one
        OpenStreetMap knows answers. A pincode already on our own list answers
        without the internet. Nothing is saved here - the screen fills its
        boxes and Save keeps them.

        Returns {'found', 'lat', 'lng', 'level', 'message', 'name',
        'country'}; `level` is street, pincode or town, and `message` says in
        plain words how close it is. With no address at all, `found` is False
        and the screen asks for one in place."""
        name = partner.display_name or self.env._('This branch')
        street = ', '.join(filter(None, [partner.street, partner.street2]))
        city = (partner.city or '').strip()
        zip_code = (partner.zip or '').strip()
        state = partner.state_id.name or ''
        country = partner.country_id
        only_in = {'countrycodes': country.code.lower()} if country.code else {}
        if not (street or city or zip_code):
            return {'found': False, 'lat': None, 'lng': None, 'level': '',
                    'name': name, 'country': country.name or '',
                    'message': self.env._(
                        "%(name)s has no street, town or pincode in Odoo yet. "
                        "Type it below and we'll look it up, or use Pick on map.",
                        name=name)}
        written = ', '.join(filter(None, [street, city, zip_code, state, country.name]))
        tries = []
        if street:
            tries.append(('street', {'q': written}))
        if zip_code:
            tries.append(('pincode', dict(only_in, postalcode=zip_code)))
        if city:
            tries.append(('town', dict(only_in, city=city, **({'state': state} if state else {}))))
        asked = False
        for level, params in tries:
            spot = None
            if level == 'pincode':
                listed = self._mart369_spot(zip_code)
                if listed['known']:
                    spot = (listed['lat'], listed['lng'])
            if spot is None:
                if asked:
                    self._mart369_pause(1)   # Nominatim asks for one a second
                asked = True
                try:
                    spot = self._mart369_search(params)
                except (requests.RequestException, ValueError) as exc:
                    raise UserError(self.env._(
                        "We couldn't reach OpenStreetMap to look up the address. "
                        "Check the internet and try again, or use Pick on map. (%s)",
                        exc)) from exc
            if spot:
                messages = {
                    'street': self.env._(
                        "Found %(address)s on the map. Check it with Pick on map, "
                        "then Save.", address=written),
                    'pincode': self.env._(
                        "Found the pincode %(zip)s but not the street, so this is "
                        "the middle of that area. Use Pick on map to put it on the "
                        "branch's door, then Save.", zip=zip_code),
                    'town': self.env._(
                        "Found the town %(city)s but not the street, so this is its "
                        "middle. Use Pick on map to put it on the branch's door, "
                        "then Save.", city=city),
                }
                return {'found': True, 'lat': round(spot[0], 6), 'lng': round(spot[1], 6),
                        'level': level, 'message': messages[level], 'name': name,
                        'country': country.name or ''}
        raise UserError(self.env._(
            "OpenStreetMap couldn't find %(address)s. Use Pick on map, or paste "
            "the location from Google Maps.", address=written))

    # ------------------------------------------------------------ GeoNames

    @api.model
    def _mart369_has_geonames(self, country):
        return bool(self.sudo().search_count(
            [('country_code', '=', country), ('source', '=', 'geonames')], limit=1))

    @api.model
    def _mart369_load_geonames(self, country, data=None):
        """Read one country's GeoNames file into the table, once. `data` is the
        zip itself when it was uploaded; otherwise it is downloaded.

        Several rows share a postcode (one per post office): their points are
        averaged and the first place name kept. Returns how many postcodes."""
        country = (country or '').upper()
        if country not in GEONAMES_COUNTRIES:
            raise UserError(self.env._('GeoNames has no postcode list for %s.', country))
        if data is None:
            try:
                data = self._mart369_get(GEONAMES_URL % country, timeout=120).content
            except requests.RequestException as exc:
                raise UserError(self.env._(
                    "We couldn't download the postcode list for %s. Check the "
                    "internet, or upload the file from download.geonames.org. (%s)",
                    country, exc)) from exc
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                name = next((n for n in archive.namelist()
                             if n.upper() == '%s.TXT' % country), None)
                if not name:
                    raise UserError(self.env._('That file has no %s.txt inside.', country))
                text = archive.read(name).decode('utf-8', errors='replace')
        except zipfile.BadZipFile as exc:
            raise UserError(self.env._('That is not a GeoNames zip file.')) from exc
        rows = {}
        for line in text.splitlines():
            parts = line.split('\t')
            if len(parts) < 11:
                continue
            code = clean_pincode(parts[1])
            try:
                lat, lng = float(parts[9]), float(parts[10])
            except ValueError:
                continue
            if not is_pincode(code) or not has_pin(lat, lng):
                continue
            row = rows.setdefault(code, [parts[2].strip(), 0.0, 0.0, 0])
            row[1] += lat
            row[2] += lng
            row[3] += 1
        Table = self.sudo()
        Table.search([('country_code', '=', country), ('source', '=', 'geonames')]).unlink()
        # OpenStreetMap rows for the same country step aside for the list.
        Table.search([('country_code', '=', country),
                      ('postcode', 'in', list(rows))]).unlink()
        values = [{'country_code': country, 'postcode': code, 'place': r[0],
                   'lat': r[1] / r[3], 'lng': r[2] / r[3], 'source': 'geonames'}
                  for code, r in rows.items()]
        for start in range(0, len(values), 2000):
            Table.create(values[start:start + 2000])
        return len(values)

    # ---------------------------------------------------------- the lookup

    MISMATCH_KM = 30.0

    @api.model
    def _mart369_spot(self, pincode):
        """A pincode's rough spot, for opening a map there."""
        code = clean_pincode(pincode)
        rec = self.sudo().search([('postcode', '=', code)], limit=1) if is_pincode(code) else None
        if not rec:
            return {'known': False}
        return {'known': True, 'lat': rec.lat, 'lng': rec.lng, 'place': rec.place or ''}

    @api.model
    def _mart369_pin_check(self, pincode, lat, lng):
        """Do a typed pincode and a map pin point to the same place?

        {'known': False} when the pincode is not on the map list (another
        country, or never loaded): nothing to say. Otherwise {'known': True,
        'match': bool, 'km', 'place'} - a match when the pincode's spot is
        within 30 km of the pin. The list's spots are averages of post
        offices, so 30 km leaves room for that; this only ever warns."""
        code = clean_pincode(pincode)
        if not (is_pincode(code) and has_pin(lat, lng)):
            return {'known': False}
        rows = self.sudo().search([('postcode', '=', code)])
        if not rows:
            return {'known': False}
        km, rec = min(((haversine_km(lat, lng, r.lat, r.lng), r) for r in rows),
                      key=lambda pair: pair[0])
        return {'known': True, 'match': km <= self.MISMATCH_KM,
                'km': round(km) if km >= 10 else round(km, 1), 'place': rec.place or ''}

    @api.model
    def _mart369_near(self, lat, lng, km):
        """[(postcode record, km)] within `km` of a pin, nearest first."""
        if not (has_pin(lat, lng) and km > 0):
            return []
        dlat = km / 111.0
        dlng = km / max(1e-6, 111.0 * math.cos(math.radians(lat)))
        found = []
        for rec in self.sudo().search([('lat', '>=', lat - dlat), ('lat', '<=', lat + dlat),
                                       ('lng', '>=', lng - dlng), ('lng', '<=', lng + dlng)]):
            dist = haversine_km(lat, lng, rec.lat, rec.lng)
            if dist <= km:
                found.append((rec, dist))
        found.sort(key=lambda pair: pair[1])
        return found


class Mart369PostcodeScan(models.Model):
    """One branch's OpenStreetMap lookup, worked through in the background.

    The points are a 2 km grid over the branch's farthest reach. A cron job
    takes them a batch at a time, one a second, and saves each answer as soon
    as it has it, so a stop part-way loses nothing."""
    _name = 'mart369.postcode.scan'
    _description = '369 Mart Postcode Lookup Around a Branch'
    _order = 'id desc'

    branch_id = fields.Many2one('stock.warehouse', required=True, ondelete='cascade')
    country_code = fields.Char(size=2)
    km = fields.Float()
    lat = fields.Float(digits=(10, 7))
    lng = fields.Float(digits=(10, 7))
    points = fields.Text(help='The grid still to visit, as JSON [[lat, lng], ...].')
    total = fields.Integer()
    done = fields.Integer()
    found = fields.Integer()
    tries = fields.Integer()
    state = fields.Selection([('running', 'Looking up'), ('done', 'Done'),
                              ('failed', 'Failed')], default='running', required=True)
    error = fields.Char()

    @api.model
    def _mart369_grid(self, lat, lng, km, step=GRID_KM):
        """Points every `step` km inside a circle of `km` around the pin."""
        points = [[lat, lng]]
        rings = int(km // step)
        dlat = step / 111.0
        dlng = step / max(1e-6, 111.0 * math.cos(math.radians(lat)))
        for i in range(-rings, rings + 1):
            for j in range(-rings, rings + 1):
                if i == j == 0:
                    continue
                plat, plng = lat + i * dlat, lng + j * dlng
                if haversine_km(lat, lng, plat, plng) <= km:
                    points.append([round(plat, 6), round(plng, 6)])
        return points

    @api.model
    def _mart369_start(self, branch, country, km):
        """A scan for this branch, reusing one already running for the same
        pin and reach; a new one starts the cron at once."""
        lat, lng = branch.mart369_lat, branch.mart369_lng
        cron = self.env.ref('mart369_cart.ir_cron_postcode_scan', raise_if_not_found=False)
        last = self.sudo().search([('branch_id', '=', branch.id)], limit=1)
        if last and last.km == km and (last.lat, last.lng) == (lat, lng):
            if last.state == 'failed':
                # Carry on from where it stopped.
                last.write({'state': 'running', 'tries': 0, 'error': False})
                if cron:
                    cron.sudo()._trigger()
            return last
        self.sudo().search([('branch_id', '=', branch.id), ('state', '=', 'running')]).write(
            {'state': 'failed', 'error': 'Replaced by a newer lookup.'})
        points = self._mart369_grid(lat, lng, km)
        scan = self.sudo().create({
            'branch_id': branch.id, 'country_code': country, 'km': km, 'lat': lat,
            'lng': lng, 'points': json.dumps(points), 'total': len(points)})
        if cron:
            cron.sudo()._trigger()
        return scan

    def _mart369_status(self):
        """Where the lookup is, with a sentence that says it in plain words."""
        self.ensure_one()
        found = self.env._('1 pincode') if self.found == 1 else \
            self.env._('%s pincodes', self.found)
        if self.state == 'running':
            left = max(0, self.total - self.done)
            mins = max(1, math.ceil(left * 1.3 / 60))
            message = self.env._(
                "Looking up pincodes on OpenStreetMap: checked %(done)s of %(total)s "
                "spots around %(branch)s, %(found)s found so far. About %(mins)s "
                "left. You can close this window; it carries on by itself.",
                done=self.done, total=self.total, branch=self.branch_id.name,
                found=found,
                mins=self.env._('1 minute') if mins == 1 else self.env._('%s minutes', mins))
        elif self.state == 'done' and self.found:
            message = self.env._(
                "Finished: checked all %(total)s spots and found %(found)s within "
                "%(km)s km of %(branch)s. They're ticked for you in Service areas, "
                "Add.", total=self.total, found=found, km=('%g' % self.km),
                branch=self.branch_id.name)
        elif self.state == 'done':
            message = self.env._(
                "Finished: no pincodes found around %s. This country may not use "
                "them. That's fine: the customer's map pin and the distance decide "
                "delivery.", self.branch_id.name)
        else:
            message = self.env._(
                "Stopped: OpenStreetMap didn't answer after several tries. Press "
                "the button again to carry on from where it stopped.")
        return {'state': self.state, 'done': self.done, 'total': self.total,
                'found': self.found, 'source': 'osm', 'country': self.country_code or '',
                'message': message}

    @api.model
    def _cron_postcode_scan(self, batch=BATCH):
        """Work through the running scans, `batch` points per run, then ask
        to be run again while any are left."""
        Postcode = self.env['mart369.postcode'].sudo()
        left = False
        for scan in self.sudo().search([('state', '=', 'running')], order='id'):
            points = json.loads(scan.points or '[]')
            for __ in range(min(batch, len(points))):
                lat, lng = points[0]
                try:
                    answer = Postcode._mart369_reverse(lat, lng)
                except (requests.RequestException, ValueError) as exc:
                    scan.tries += 1
                    if scan.tries >= 5:
                        scan.write({'state': 'failed', 'error': str(exc)[:200]})
                    break
                points.pop(0)
                values = {'points': json.dumps(points), 'done': scan.done + 1}
                code = answer['postcode']
                if is_pincode(code) and (not scan.country_code
                                         or answer['country'] in ('', scan.country_code)):
                    country = answer['country'] or scan.country_code
                    if not Postcode.search_count([('country_code', '=', country),
                                                  ('postcode', '=', code)]):
                        Postcode.create({'country_code': country, 'postcode': code,
                                         'place': answer['place'], 'lat': lat, 'lng': lng,
                                         'source': 'osm'})
                        values['found'] = scan.found + 1
                scan.write(values)
                self._mart369_save_progress()
                Postcode._mart369_pause(1.0)
            if scan.state == 'running':
                if points:
                    left = True
                else:
                    scan.state = 'done'
        if left:
            cron = self.env.ref('mart369_cart.ir_cron_postcode_scan', raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()

    @api.model
    def _mart369_save_progress(self):
        """Commit after each answer in a real cron run, so the screen sees the
        count climb and a stop loses nothing. Never inside a test."""
        if not odoo_module.current_test:
            self.env.cr.commit()


def editor_only(env):
    """The delivery screens' group, checked before anything here runs sudo."""
    if not env.user.has_group(EDITOR_GROUP):
        raise AccessError(env._('You do not have access to this.'))
