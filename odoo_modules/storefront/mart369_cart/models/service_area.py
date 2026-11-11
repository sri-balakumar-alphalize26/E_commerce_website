"""Where 369 Mart delivers, and how fast.

Replaces `demoCheck` in components/home/LocationPicker.jsx, which is a regex:

    if (!/^6[789]\\d{4}$/.test(pin)) return { ok: false, error: "..." };
    return { ok: true, quick: pin.startsWith("68") || pin.startsWith("69"), eta: "13 mins" };

That is "Kerala is servicable, everywhere else is not", with one ETA for every
address in the state. Here a pincode - or a run of them - is a record an
operator can add without a developer, and the ETA belongs to the area.

Matching is longest-prefix: an entry for 6820 beats an entry for 68, so a city
can have its own promise inside a region that already has one.
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .postcode import CREDIT, clean_pincode, is_pincode


class Mart369ServiceArea(models.Model):
    _name = 'mart369.service.area'
    _description = '369 Mart Service Area'
    _order = 'pincode'
    _rec_name = 'pincode'

    pincode = fields.Char(
        string='Pincode', required=True, index=True,
        help="A full pincode (682016) or the start of one (68), which covers "
             "every pincode beginning with it.")
    name = fields.Char(
        string='Area', help="What to call this area in 369ai. The app never "
                            "shows it.")
    quick = fields.Boolean(
        string='Quick delivery', default=True,
        help="On: 10-minute groceries reach this area. Off: Express only.")
    express = fields.Boolean(
        string='Express delivery', default=True,
        help="On: items that ship over days reach this area.")
    eta = fields.Char(
        string='Delivery promise', default='13 mins',
        help="What the app tells a customer here, e.g. 13 mins.")
    active = fields.Boolean(default=True)

    _pincode_uniq = models.Constraint(
        'unique (pincode)',
        'That pincode is already covered by another area.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'pincode' in vals:
                vals['pincode'] = clean_pincode(vals['pincode'])
        return super().create(vals_list)

    def write(self, vals):
        if 'pincode' in vals:
            vals = dict(vals, pincode=clean_pincode(vals['pincode']))
        return super().write(vals)

    @api.constrains('pincode')
    def _check_pincode(self):
        # Letters too: UK SW1A1AA, Canada K1A0B1, Netherlands 1012AB.
        for area in self:
            if not is_pincode(area.pincode or ''):
                raise ValidationError(self.env._(
                    "A pincode is letters and numbers only, up to 10. '%s' is not.",
                    area.pincode))

    # -------------------------------------------------------------- lookup

    @api.model
    def _mart369_match(self, pin):
        """The most specific area covering this pincode, or nothing.

        Longest prefix wins, so 6820 beats 68 and an exact pincode beats both.
        """
        pin = clean_pincode(pin)
        if not is_pincode(pin):
            return self.browse()
        prefixes = [pin[:n] for n in range(len(pin), 0, -1)]
        areas = self.sudo().search([('pincode', 'in', prefixes)])
        if not areas:
            return self.browse()
        return max(areas, key=lambda a: len(a.pincode or ''))

    @api.model
    def _mart369_check(self, pin):
        """Exactly the answer `demoCheck` gives, so the picker is unchanged:
        {ok: True, quick: bool, eta: str} or {ok: False, error: str}."""
        pin = clean_pincode(pin)
        if not (is_pincode(pin) and len(pin) >= 3):
            return {'ok': False, 'error': self.env._('Enter a valid pincode.')}
        area = self._mart369_match(pin)
        if not area or not (area.quick or area.express):
            return {'ok': False,
                    'error': self.env._("We don't deliver to this pincode yet.")}
        if self.env['stock.warehouse']._mart369_any_ready():
            # Quick is measured from the branch now; a pincode has no
            # distance. Say we deliver, and ask for the location.
            return {'ok': True, 'quick': False, 'eta': area.eta or '', 'needPin': True}
        return {'ok': True, 'quick': area.quick, 'eta': area.eta or ''}

    # ------------------------------------------------------ one switch

    @api.model
    def _mart369_switch_values(self, deliver, area=None):
        """The one "We deliver here" switch, as the two old fields.

        Off: both off - customers there are told we don't deliver yet. On:
        an area that already delivers keeps what it had (a shop with no
        branch set up still reads its Quick switch), one that did not gets
        both on. With branches set up, distance decides Quick anyway."""
        if not deliver:
            return {'quick': False, 'express': False}
        if area and (area.quick or area.express):
            return {}
        return {'quick': True, 'express': True}

    # -------------------------------------------------- pincodes we know

    @api.model
    def mart369_admin_known_pincodes(self):
        """The pincodes the shop already knows, grouped by nearest branch, for
        ticking instead of typing.

        From customers' saved addresses, the branches' own addresses, and the
        postcodes found on the map around each branch (postcode.py). Each
        pincode goes under the branch nearest its map pins, and is ticked
        (`near`) when it lies inside that branch's farthest reach. Pincodes
        with no pin anywhere, and ones an area already covers, are listed
        apart. Read-only; the editor's group, like every delivery screen.

        {'groups': [{'branch', 'reach', 'pincodes': [row]}],
         'far': [row + 'branch'], 'noPin': [row], 'covered': [pincode]}
        'far' is past every branch's reach, with the nearest branch named.
        row = {'pincode', 'place', 'addresses', 'km', 'near'}; 'addresses' is 0
        for one found only on the map. 'credit' names the map sources.
        """
        from .branch import EDITOR_GROUP, has_pin, haversine_km
        if not self.env.user.has_group(EDITOR_GROUP):
            raise AccessError(self.env._('You do not have access to this.'))
        Partner = self.env['res.partner'].sudo().with_context(active_test=True)
        found = {}
        for p in Partner.search_read(
                [('zip', '!=', False), ('is_company', '=', False)],
                ['zip', 'city', 'partner_latitude', 'partner_longitude'], limit=50000):
            pin = clean_pincode(p['zip'])
            if not (is_pincode(pin) and len(pin) >= 3):
                continue
            row = found.setdefault(pin, {'pincode': pin, 'places': {}, 'addresses': 0,
                                         'points': []})
            row['addresses'] += 1
            if p['city']:
                row['places'][p['city']] = row['places'].get(p['city'], 0) + 1
            if has_pin(p['partner_latitude'], p['partner_longitude']):
                row['points'].append((p['partner_latitude'], p['partner_longitude']))
        branches = [b for b in self.env['stock.warehouse'].sudo().search([])
                    if has_pin(b.mart369_lat, b.mart369_lng)]
        for b in branches:
            zip_code = clean_pincode(b.partner_id.zip)
            if is_pincode(zip_code) and len(zip_code) >= 3:
                row = found.setdefault(zip_code, {'pincode': zip_code, 'places': {},
                                                  'addresses': 0, 'points': []})
                row['points'].append((b.mart369_lat, b.mart369_lng))
            # The postcodes found on the map around the branch, within its
            # reach - only once someone pressed "Find pincodes" on it, so one
            # branch is worked on at a time.
            if not b.mart369_pincodes_found:
                continue
            reach = max(b.mart369_maybe_km, b.mart369_quick_km) or 5.0
            for rec, __ in self.env['mart369.postcode']._mart369_near(
                    b.mart369_lat, b.mart369_lng, reach):
                row = found.setdefault(rec.postcode, {'pincode': rec.postcode, 'places': {},
                                                      'addresses': 0, 'points': []})
                if rec.place:
                    row['places'].setdefault(rec.place, 0)
                row['points'].append((rec.lat, rec.lng))
        covered = sorted(pin for pin in found if self._mart369_match(pin))
        groups = {b.id: {'branch': b.name, 'reach': max(b.mart369_maybe_km, b.mart369_quick_km),
                         'pincodes': []} for b in branches}
        no_pin, far = [], []
        for pin in sorted(found):
            if pin in covered:
                continue
            row = found[pin]
            out = {'pincode': pin, 'addresses': row['addresses'],
                   'place': max(row['places'], key=row['places'].get) if row['places'] else '',
                   'km': None, 'near': False}
            if not (row['points'] and branches):
                no_pin.append(out)
                continue
            lat = sum(x for x, __ in row['points']) / len(row['points'])
            lng = sum(y for __, y in row['points']) / len(row['points'])
            km, branch = min(((haversine_km(lat, lng, b.mart369_lat, b.mart369_lng), b)
                              for b in branches), key=lambda pair: pair[0])
            group = groups[branch.id]
            out['km'] = round(km, 1) if km < 100 else round(km)
            out['near'] = bool(group['reach'] and km <= group['reach'])
            if out['near']:
                group['pincodes'].append(out)
            else:
                # Past every branch's reach: listed apart, unticked, so a
                # branch's group only shows what really is around it.
                out['branch'] = branch.name
                far.append(out)
        for group in groups.values():
            group['pincodes'].sort(key=lambda r: (r['km'], r['pincode']))
        far.sort(key=lambda r: (r['km'], r['pincode']))
        return {'groups': [g for g in groups.values() if g['pincodes']],
                'far': far, 'noPin': no_pin, 'covered': covered, 'credit': CREDIT}

    # -------------------------------------------------------- the console

    @api.model
    def mart369_admin_add_many(self, pincodes, values=None):
        """Add several areas in one go, all with the same switches and promise.

        `pincodes` is what the operator pasted: "624001, 624002" or one per
        line. A pincode that already has an area is left alone and reported,
        so pasting a list twice is harmless. Every new pincode is checked
        before any is saved, so one typo saves nothing.

        Both screens call this: the desk in Odoo through the ORM, the console
        through POST /369mart/admin/delivery/areas with `pincodes`.
        Returns {'added': [pincode], 'skipped': [pincode]}.
        """
        if isinstance(pincodes, (list, tuple)):
            raw = ','.join(str(p) for p in pincodes)
        else:
            raw = str(pincodes or '')
        seen, wanted = set(), []
        for chunk in raw.replace(';', ',').replace('\n', ',').split(','):
            pin = clean_pincode(chunk)    # "682 016" from a spreadsheet, "sw1a 1aa"
            if pin and pin not in seen:
                seen.add(pin)
                wanted.append(pin)
        if not wanted:
            raise ValidationError(self.env._('Type at least one pincode.'))
        bad = [pin for pin in wanted if not is_pincode(pin)]
        if bad:
            raise ValidationError(self.env._(
                "A pincode is letters and numbers only, up to 10. %s is not.",
                ', '.join(bad)))
        Area = self.with_context(active_test=False)
        taken = set(Area.search([('pincode', 'in', wanted)]).mapped('pincode'))
        values = dict(values or {})
        common = {key: values[key] for key in ('name', 'quick', 'express', 'eta', 'active')
                  if key in values}
        if 'deliver' in values:
            common.update(self._mart369_switch_values(bool(values['deliver'])))
        new = [pin for pin in wanted if pin not in taken]
        if new:
            # No name typed: each pincode is called by its own place, so
            # Dindigul and Palani added together are not both "Dindigul".
            places = {} if (common.get('name') or '').strip() else self._mart369_places(new)
            Area.create([dict(common, pincode=pin, name=common.get('name') or places.get(pin, ''))
                         for pin in new])
        return {'added': new, 'skipped': [pin for pin in wanted if pin in taken]}

    @api.model
    def _mart369_places(self, pincodes):
        """{pincode: place name} from the map's postcode list, else the town
        most of the customers with that pincode wrote."""
        places = {}
        for rec in self.env['mart369.postcode'].sudo().search([('postcode', 'in', pincodes)]):
            if rec.place and rec.postcode not in places:
                places[rec.postcode] = rec.place
        left = [pin for pin in pincodes if pin not in places]
        if left:
            counts = {}
            for p in self.env['res.partner'].sudo().search_read(
                    [('zip', '!=', False), ('city', '!=', False)], ['zip', 'city'], limit=50000):
                pin = clean_pincode(p['zip'])
                if pin in left:
                    town = counts.setdefault(pin, {})
                    town[p['city']] = town.get(p['city'], 0) + 1
            for pin, town in counts.items():
                places[pin] = max(town, key=town.get)
        return places

    def _mart369_admin_row(self):
        """One area as the admin console draws it.

        `_mart369_check` above answers a customer's question - can you reach
        me, and how fast - and deliberately says nothing about which record
        answered it. This says which record, and everything on it.
        """
        self.ensure_one()
        return {
            'id': self.id,
            'pincode': self.pincode or '',
            'name': self.name or '',
            'quick': self.quick,
            'express': self.express,
            # The one switch the screens show: we deliver here, or not.
            'delivers': bool(self.quick or self.express),
            'eta': self.eta or '',
            'active': self.active,
        }
