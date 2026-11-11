"""Which branches do Quick delivery, and how far each one reaches.

A branch is a `stock.warehouse` - the shop already keeps one per company
(Ruwi, Sohar, Salalah), and each one's stock is its own. So Quick is not a
property of a category or even of a product: it is a question about *this*
basket going to *this* address. An item is Quick when a branch that does Quick
is within its reach of the customer's map pin and has the item on its shelf.
Anything else ships Express.

The pin is ours rather than the warehouse partner's `partner_latitude`: that
partner is the company's own address, which Odoo edits from the company form
for invoices, and moving it to fix an invoice must not quietly move where the
shop delivers from.

Distance is a straight line (haversine). Roads are longer, which is why the
reach is a number the shop sets and not a promise about the map.
"""

import math

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

EARTH_KM = 6371.0088
# The same group every delivery screen checks (controllers/admin_api.py).
EDITOR_GROUP = 'website.group_website_designer'

# The Quick time is worked out, never typed: packing, then the ride.
PACK_MINS = 10
MINS_PER_KM = 5
# What Quick on fills in when the boxes are still empty.
DEFAULT_QUICK_KM = 5.0
DEFAULT_MAYBE_KM = 15.0


def quick_minutes(km):
    """Minutes for a Quick delivery `km` away in a straight line: 10 to pack
    and 5 a km, rounded up to the next 5. 1 km -> 15, 3 km -> 25, 5 km -> 35."""
    raw = PACK_MINS + MINS_PER_KM * max(0.0, km or 0.0)
    return int(math.ceil(raw / 5.0 - 1e-9) * 5)


def quick_time_text(km):
    """The words a card shows: "25 mins", "1 hr", "1 hr 15 mins"."""
    mins = quick_minutes(km)
    if mins < 60:
        return '%d mins' % mins
    hours, rest = divmod(mins, 60)
    return '%d hr%s' % (hours, ' %d mins' % rest if rest else '')


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance between two points, in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def has_pin(lat, lng):
    """0/0 is how Odoo stores "no pin" - the same rule the address desk uses."""
    return bool(lat or lng)


class Mart369Branch(models.Model):
    _inherit = 'stock.warehouse'

    mart369_quick = fields.Boolean(
        string='Quick delivery', default=False,
        help="On: this branch delivers Quick to customers within its reach.")
    mart369_quick_km = fields.Float(
        string='Quick reach (km)', default=0.0,
        help="How far from the branch Quick reaches, in a straight line. "
             "0 means nowhere.")
    mart369_lat = fields.Float(string='Latitude', digits=(10, 7))
    mart369_lng = fields.Float(string='Longitude', digits=(10, 7))
    # Used once the hub rules are on (hub_rule.py); until then nothing reads them.
    mart369_maybe_km = fields.Float(
        string='Quick if possible up to (km)', default=0.0,
        help="Past the Quick reach and up to here, the customer is promised "
             "Express, and it comes Quick when a rider is free. 0 means off.")
    # No longer read: the Quick time is worked out from the customer's
    # distance (quick_time_text). Kept so nothing typed into it is lost.
    mart369_quick_eta = fields.Char(
        string='Quick promise (old)',
        help="Not used any more: the shop works the Quick time out from how "
             "far the customer is.")

    # Which country the pin is in, learnt once from OpenStreetMap when the
    # branch first looks for the pincodes around it (postcode.py).
    mart369_country_code = fields.Char(string='Pin country', size=2)
    mart369_country_pin = fields.Char(
        help="The pin the country was worked out for, so moving the pin asks again.")
    # Someone pressed "Find pincodes around this branch": only then does the
    # Service areas list offer the map's pincodes around it, so one branch at
    # a time is worked on, never every branch in the country at once.
    mart369_pincodes_found = fields.Boolean(string='Pincodes looked up')

    # A hub's own delivery charges, for the part of a basket it ships. Off:
    # the shop's Quick and Express fees apply, as everywhere else.
    mart369_own_fees = fields.Boolean(
        string='Own delivery fees',
        help="On: what this branch ships is charged the fees below instead of "
             "the shop's.")
    mart369_quick_fee = fields.Float(string='Quick fee', default=0.0)
    mart369_express_fee = fields.Float(string='Express fee', default=0.0)
    mart369_free_above = fields.Float(
        string='Free delivery above', default=0.0,
        help="Items from this branch worth more than this ship free. 0 means "
             "delivery is never free.")

    @api.constrains('mart369_quick_km', 'mart369_maybe_km', 'mart369_lat', 'mart369_lng',
                    'mart369_quick_fee', 'mart369_express_fee', 'mart369_free_above')
    def _check_mart369_quick(self):
        for branch in self:
            if branch.mart369_quick_km < 0 or branch.mart369_maybe_km < 0:
                raise ValidationError(self.env._('The Quick reach cannot be negative.'))
            if min(branch.mart369_quick_fee, branch.mart369_express_fee,
                   branch.mart369_free_above) < 0:
                raise ValidationError(self.env._('Delivery amounts cannot be negative.'))
            if branch.mart369_maybe_km and branch.mart369_maybe_km < branch.mart369_quick_km:
                raise ValidationError(self.env._(
                    '"Quick if possible up to" must be at least the Quick reach.'))
            if not -90 <= branch.mart369_lat <= 90 or not -180 <= branch.mart369_lng <= 180:
                raise ValidationError(self.env._(
                    'That is not a place on the map: latitude is -90 to 90, '
                    'longitude -180 to 180.'))

    # ------------------------------------------------------------ the rule

    def _mart369_ready(self):
        """Quick on, a pin, and somewhere to reach. Anything less is off."""
        self.ensure_one()
        return bool(self.mart369_quick and self.mart369_quick_km > 0
                    and has_pin(self.mart369_lat, self.mart369_lng))

    @api.model
    def _mart369_any_ready(self):
        """Is any branch set up for Quick (on, pinned, with a reach)? Then
        distance decides Quick, not a pincode's switch."""
        return any(b._mart369_ready()
                   for b in self.sudo().search([('mart369_quick', '=', True)]))

    @api.model
    def _mart369_quick_branches(self, lat, lng):
        """[(branch, km)] that reach this pin, nearest first.

        sudo: every branch is its own company, and a shopper - or a staff
        member working in one company - must still be measured against all of
        them.
        """
        if not has_pin(lat, lng):
            return []
        found = []
        for branch in self.sudo().search([('mart369_quick', '=', True)]):
            if not branch._mart369_ready():
                continue
            km = haversine_km(lat, lng, branch.mart369_lat, branch.mart369_lng)
            if km <= branch.mart369_quick_km:
                found.append((branch, km))
        found.sort(key=lambda pair: pair[1])
        return found

    def _mart369_has_stock(self, product, qty, variant=None):
        """Can this branch hand over `qty` of this template right now?

        With `variant` (the colour or size the customer picked) only that
        variant's stock counts, not its siblings'.

        An untracked product has nothing to run out of, so any branch has it -
        the same answer the storefront gives (`_mart369_free_qty` -> None).
        """
        self.ensure_one()
        if 'is_storable' in product._fields and not product.is_storable:
            return True
        variants = (variant or product.product_variant_ids).sudo().with_company(
            self.company_id).with_context(warehouse_id=self.id)
        return sum(variants.mapped('free_qty')) >= qty

    # -------------------------------------------------------- the console

    @api.model
    def mart369_admin_save(self, branch_id, values):
        """Save one branch's Quick settings from either screen.

        The desk in Odoo calls this through the ORM and the console's PATCH
        route calls it too, so both refuse the same things in the same words.
        Only the Quick fields: a branch's name, company and stock are
        Inventory's business, and a delivery screen must not rename one.

        sudo after the group check, because the branches belong to other
        companies and a delivery editor is not an Inventory manager.
        """
        if not self.env.user.has_group(EDITOR_GROUP):
            raise AccessError(self.env._('You do not have access to this.'))
        branch = self.sudo().browse(int(branch_id)).exists()
        if not branch:
            raise UserError(self.env._('There is no such branch.'))
        values = dict(values)
        if 'pin' in values:
            # One box: "10.3673, 77.9803" as Google Maps copies it. Empty
            # takes the pin away.
            raw = str(values.pop('pin') or '').strip()
            parts = [p.strip() for p in raw.split(',')] if raw else ['', '']
            if len(parts) != 2:
                raise UserError(self.env._(
                    'Paste the location as two numbers with a comma between, '
                    'e.g. 10.3673, 77.9803.'))
            values['lat'], values['lng'] = parts
        vals = {}
        if 'quick' in values:
            vals['mart369_quick'] = bool(values['quick'])
        if 'ownFees' in values:
            vals['mart369_own_fees'] = bool(values['ownFees'])
        for key, field, what in (('quickKm', 'mart369_quick_km', self.env._('The reach')),
                                 ('quickFee', 'mart369_quick_fee', self.env._('The Quick fee')),
                                 ('expressFee', 'mart369_express_fee',
                                  self.env._('The Express fee')),
                                 ('freeAbove', 'mart369_free_above',
                                  self.env._('"Free delivery above"')),
                                 ('maybeKm', 'mart369_maybe_km',
                                  self.env._('"Quick if possible up to"')),
                                 ('lat', 'mart369_lat', self.env._('Latitude')),
                                 ('lng', 'mart369_lng', self.env._('Longitude'))):
            if key not in values:
                continue
            raw = values[key]
            try:
                vals[field] = float(raw) if raw not in (None, '') else 0.0
            except (TypeError, ValueError):
                raise UserError(self.env._('%s is a number.', what))  # noqa: B904
        if not vals:
            raise UserError(self.env._('Nothing to change.'))
        if vals.get('mart369_quick') and not branch.mart369_quick:
            # Switching Quick on with the boxes still empty: the usual
            # reaches, so one switch is enough to start.
            reach = vals.get('mart369_quick_km', branch.mart369_quick_km)
            if not reach:
                reach = vals['mart369_quick_km'] = DEFAULT_QUICK_KM
            if not vals.get('mart369_maybe_km', branch.mart369_maybe_km):
                vals['mart369_maybe_km'] = max(DEFAULT_MAYBE_KM, reach)
        branch.write(vals)
        branch.flush_recordset()
        return branch._mart369_admin_row()

    # ------------------------------------------- pincodes around the branch

    def _mart369_reach_km(self):
        """How far around the branch to look: its farthest reach, else 5."""
        self.ensure_one()
        return max(self.mart369_maybe_km, self.mart369_quick_km) or DEFAULT_QUICK_KM

    @api.model
    def mart369_admin_find_pincodes(self, branch_id):
        """The "Find pincodes around this branch" button.

        Works out the pin's country once (OpenStreetMap). Where GeoNames has a
        list, it is loaded (once) and the answer is ready at once. Anywhere
        else an OpenStreetMap lookup starts in the background, and the screen
        asks `mart369_admin_find_status` how it is going.

        Returns {'state', 'done', 'total', 'found', 'source', 'country',
        'message'} - `message` says it in plain words for the screen."""
        from .postcode import GEONAMES_COUNTRIES, editor_only
        editor_only(self.env)
        branch = self.sudo().browse(int(branch_id)).exists()
        if not branch:
            raise UserError(self.env._('There is no such branch.'))
        if not has_pin(branch.mart369_lat, branch.mart369_lng):
            raise UserError(self.env._(
                "Set the branch's location from Google Maps first, so we know "
                "where to look."))
        Postcode = self.env['mart369.postcode'].sudo()
        pin_key = '%.5f,%.5f' % (branch.mart369_lat, branch.mart369_lng)
        if not branch.mart369_country_code or branch.mart369_country_pin != pin_key:
            branch.write({
                'mart369_country_code': Postcode._mart369_country_at(
                    branch.mart369_lat, branch.mart369_lng) or False,
                'mart369_country_pin': pin_key})
        country = branch.mart369_country_code or ''
        km = branch._mart369_reach_km()
        branch.mart369_pincodes_found = True
        if country in GEONAMES_COUNTRIES:
            if not Postcode._mart369_has_geonames(country):
                Postcode._mart369_load_geonames(country)
            return branch._mart369_list_status(country, km)
        return self.env['mart369.postcode.scan']._mart369_start(
            branch, country, km)._mart369_status()

    @api.model
    def mart369_admin_find_status(self, branch_id):
        """How the last "Find pincodes" for this branch is going."""
        from .postcode import GEONAMES_COUNTRIES, editor_only
        editor_only(self.env)
        branch = self.sudo().browse(int(branch_id)).exists()
        if not branch:
            raise UserError(self.env._('There is no such branch.'))
        country = branch.mart369_country_code or ''
        if country in GEONAMES_COUNTRIES and \
                self.env['mart369.postcode']._mart369_has_geonames(country):
            return branch._mart369_list_status(country, branch._mart369_reach_km())
        scan = self.env['mart369.postcode.scan'].sudo().search(
            [('branch_id', '=', branch.id)], limit=1)
        if scan:
            return scan._mart369_status()
        return {'state': 'none', 'done': 0, 'total': 0, 'found': 0, 'source': '',
                'country': country, 'message': ''}

    def _mart369_list_status(self, country, km):
        """The answer when the country's list is loaded: ready at once."""
        self.ensure_one()
        found = len(self.env['mart369.postcode']._mart369_near(
            self.mart369_lat, self.mart369_lng, km))
        name = self.env['res.country'].sudo().search(
            [('code', '=', country)], limit=1).name or country
        if found:
            message = self.env._(
                "Found %(found)s within %(km)s km of %(branch)s, from the postcode "
                "list for %(country)s. They're ticked for you in Service areas, Add.",
                found=self.env._('1 pincode') if found == 1 else
                self.env._('%s pincodes', found),
                km='%g' % km, branch=self.name, country=name)
        else:
            message = self.env._(
                "No pincodes found within %(km)s km of %(branch)s. Try a bigger "
                "reach, or type them in Service areas.", km='%g' % km, branch=self.name)
        return {'state': 'done', 'done': 1, 'total': 1, 'found': found,
                'source': 'geonames', 'country': country, 'message': message}

    def _mart369_admin_row(self):
        self.ensure_one()
        pinned = has_pin(self.mart369_lat, self.mart369_lng)
        return {
            'id': self.id,
            'name': self.name or '',
            'code': self.code or '',
            'company': self.company_id.name or '',
            'quick': self.mart369_quick,
            'quickKm': round(self.mart369_quick_km or 0.0, 2),
            'maybeKm': round(self.mart369_maybe_km or 0.0, 2),
            # The longest Quick time, at the edge of the reach: what the
            # screens show beside the reach, worked out, never typed.
            'quickUpTo': quick_time_text(self.mart369_quick_km) if self.mart369_quick_km else '',
            'ownFees': self.mart369_own_fees,
            'quickFee': round(self.mart369_quick_fee or 0.0, 3),
            'expressFee': round(self.mart369_express_fee or 0.0, 3),
            'freeAbove': round(self.mart369_free_above or 0.0, 3),
            'lat': self.mart369_lat if pinned else None,
            'lng': self.mart369_lng if pinned else None,
            # Quick is on but it cannot actually reach anyone - the screens
            # warn about this rather than let a switch look like it works.
            'unready': bool(self.mart369_quick and not self._mart369_ready()),
        }
