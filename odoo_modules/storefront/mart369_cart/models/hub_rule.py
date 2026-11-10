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

    # -------------------------------------------------------------- reading

    @api.model
    def _mart369_table(self):
        """{(from_id, to_id): rule} for every live row, or {} - which means
        the hub rules are off and the shop works as before."""
        return {(r.from_hub_id.id, r.to_hub_id.id): r
                for r in self.sudo().search([])}
