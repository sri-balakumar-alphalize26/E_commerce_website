"""How fast a product travels from one hub to another.

A hub is a branch (`stock.warehouse`), one per company: Ruwi, Sohar, Salalah.
Inside one hub, distance decides (branch.py: Quick up to its reach, "Quick if
possible" up to its second reach). Between two hubs, this table decides: one
row per pair, read as "a product in Sohar Hub, for a customer in Ruwi, arrives
next day".

Every row is Express - a van between cities is never Quick. `days` orders the
rows when several hubs have the item (fewest days wins); `arrives` is the words
the shop prints, and `cargo` adds the Cargo badge for long trips such as to or
from Salalah.

While the table is empty, nothing changes: the shop decides Quick and Express
exactly as it always has.
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .branch import has_pin, haversine_km


class Mart369HubRule(models.Model):
    _name = 'mart369.hub.rule'
    _description = '369 Mart Hub to Hub Delivery'
    _order = 'from_hub_id, to_hub_id'

    from_hub_id = fields.Many2one(
        'stock.warehouse', string='Product is in', required=True, ondelete='cascade',
        help="The hub that has the item on its shelf.")
    to_hub_id = fields.Many2one(
        'stock.warehouse', string='Customer is in', required=True, ondelete='cascade',
        help="The customer's hub: the one nearest to their delivery address.")
    days = fields.Integer(
        string='Days', default=1, required=True,
        help="Roughly how many days it takes. When several hubs have the item, "
             "the one with the fewest days is picked.")
    arrives = fields.Char(
        string='Arrives', default='Next day',
        help='What the shop says, e.g. "Next day" or "In 2-3 days".')
    cargo = fields.Boolean(
        string='Cargo badge',
        help="Show the Cargo badge on the product: a long trip, such as to or "
             "from Salalah.")
    active = fields.Boolean(default=True)
    auto = fields.Boolean(
        string='Worked out from distance', copy=False,
        help="Added by the automatic delivery setup from the straight-line "
             "distance between the two hubs. Check the days and the words; "
             "changing them makes the row yours.")

    _pair_uniq = models.Constraint(
        'unique (from_hub_id, to_hub_id)',
        'There is already a rule for these two hubs.',
    )

    @api.constrains('days', 'from_hub_id', 'to_hub_id')
    def _check_rule(self):
        for rule in self:
            if rule.days < 0:
                raise ValidationError(self.env._('Days cannot be negative.'))

    @api.depends('from_hub_id', 'to_hub_id')
    def _compute_display_name(self):
        for rule in self:
            rule.display_name = '%s → %s' % (rule.from_hub_id.name or '?',
                                             rule.to_hub_id.name or '?')

    def write(self, vals):
        # Somebody checked the row: it is theirs now, not a guess.
        if 'auto' not in vals and {'days', 'arrives', 'cargo'} & set(vals):
            vals = dict(vals, auto=False)
        return super().write(vals)

    @api.model
    def _mart369_fill_routes(self, force=False):
        """Add a row for every pair of pinned hubs that has none, from the
        distance between them (delivery_autosetup.route_for_km). Only while
        the table is on: a shop that does not use hubs is never switched
        over. A row that exists - archived ones too, which are somebody's
        "no" - is never changed. Returns what was added, in words."""
        from .delivery_autosetup import route_for_km
        if not force and not self._mart369_table():
            return []
        hubs = self.env['stock.warehouse'].sudo().search([]).filtered(
            lambda b: has_pin(b.mart369_lat, b.mart369_lng))
        Rule = self.sudo().with_context(active_test=False)
        have = {(r.from_hub_id.id, r.to_hub_id.id) for r in Rule.search([])}
        added = []
        for here in hubs:
            for there in hubs:
                if here == there or (here.id, there.id) in have:
                    continue
                km = haversine_km(here.mart369_lat, here.mart369_lng,
                                  there.mart369_lat, there.mart369_lng)
                days, arrives, cargo = route_for_km(km)
                Rule.create({'from_hub_id': here.id, 'to_hub_id': there.id, 'days': days,
                             'arrives': arrives, 'cargo': cargo, 'auto': True})
                have.add((here.id, there.id))
                added.append(self.env._('Route %(a)s to %(b)s: %(when)s (%(km)s km).',
                                        a=here.name, b=there.name, when=arrives,
                                        km='%d' % round(km)))
        return added

    # -------------------------------------------------------------- reading

    @api.model
    def _mart369_table(self):
        """{(from_id, to_id): rule} for every live row, or {} - which means
        the hub rules are off and the shop works as before."""
        return {(r.from_hub_id.id, r.to_hub_id.id): r
                for r in self.sudo().search([])}
