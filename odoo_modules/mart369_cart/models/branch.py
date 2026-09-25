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

    @api.constrains('mart369_quick_km', 'mart369_lat', 'mart369_lng')
    def _check_mart369_quick(self):
        for branch in self:
            if branch.mart369_quick_km < 0:
                raise ValidationError(self.env._('The Quick reach cannot be negative.'))
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

    def _mart369_has_stock(self, product, qty):
        """Can this branch hand over `qty` of this template right now?

        An untracked product has nothing to run out of, so any branch has it -
        the same answer the storefront gives (`_mart369_free_qty` -> None).
        """
        self.ensure_one()
        if 'is_storable' in product._fields and not product.is_storable:
            return True
        variants = product.sudo().product_variant_ids.with_company(
            self.company_id).with_context(warehouse_id=self.id)
        return sum(variants.mapped('free_qty')) >= qty

    # -------------------------------------------------------- the console

    @api.model
    def mart369_admin_save(self, branch_id, values):
        """Save one branch's Quick settings from either screen.

        The desk in Odoo calls this through the ORM and the console's PATCH
        route calls it too, so both refuse the same things in the same words.
        Only the four Quick fields: a branch's name, company and stock are
        Inventory's business, and a delivery screen must not rename one.

        sudo after the group check, because the branches belong to other
        companies and a delivery editor is not an Inventory manager.
        """
        if not self.env.user.has_group(EDITOR_GROUP):
            raise AccessError(self.env._('You do not have access to this.'))
        branch = self.sudo().browse(int(branch_id)).exists()
        if not branch:
            raise UserError(self.env._('There is no such branch.'))
        vals = {}
        if 'quick' in values:
            vals['mart369_quick'] = bool(values['quick'])
        for key, field, what in (('quickKm', 'mart369_quick_km', self.env._('The reach')),
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
        branch.write(vals)
        branch.flush_recordset()
        return branch._mart369_admin_row()

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
            'lat': self.mart369_lat if pinned else None,
            'lng': self.mart369_lng if pinned else None,
            # Quick is on but it cannot actually reach anyone - the screens
            # warn about this rather than let a switch look like it works.
            'unready': bool(self.mart369_quick and not self._mart369_ready()),
        }
