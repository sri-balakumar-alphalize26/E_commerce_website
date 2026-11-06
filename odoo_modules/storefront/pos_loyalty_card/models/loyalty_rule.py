from odoo import models, fields, api, _
from odoo.exceptions import UserError


class LoyaltyRule(models.Model):
    _name = 'pos.loyalty.rule'
    _description = 'Loyalty Points Rule'
    _order = 'is_active desc, id'

    name = fields.Char(string='Rule Name', required=True, default='Default Rule')
    active = fields.Boolean(string='Archived', default=True)  # standard archive field
    is_active = fields.Boolean(
        string='Active', default=False,
        help='Only one rule can be active at a time. Turning this on turns the '
             'others off. The active rule is used for earning and redeeming points.')

    # Earning rules
    spend_amount = fields.Float(string='Spend Amount', default=100,
                                help='Amount to spend to earn points (e.g., spend 100 to earn X points)')
    points_earned = fields.Float(string='Points Earned', default=10,
                                 help='Points earned per spend amount')

    # Redemption rules
    min_redeem_points = fields.Float(string='Min Points to Redeem', default=100)
    points_per_currency = fields.Float(string='Points per ₹1', default=10,
                                       help='Points needed for ₹1 discount')
    max_redeem_percent = fields.Float(string='Max Redeem %', default=100)

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.model
    def get_active_rule(self):
        """Return the single active rule (fallback to the first rule)."""
        return self.search([('is_active', '=', True)], limit=1) or self.search([], limit=1)

    def _deactivate_others(self, keep):
        if self.env.context.get('_skip_active_sync'):
            return
        others = self.search([('is_active', '=', True), ('id', 'not in', keep.ids)])
        if others:
            others.with_context(_skip_active_sync=True).write({'is_active': False})

    def action_activate(self):
        """Turn this rule ON (write enforces single-active) and reload the view."""
        self.ensure_one()
        self.write({'is_active': True})
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        active_new = recs.filtered('is_active')
        if active_new:
            self._deactivate_others(active_new)
        return recs

    def write(self, vals):
        # Single on/off toggle: turning one ON turns the others OFF; turning the
        # only active one OFF is blocked (same as Loyalty Settings).
        if 'is_active' in vals and not self.env.context.get('_skip_active_sync'):
            if vals.get('is_active'):
                res = super().write(vals)
                self._deactivate_others(self.filtered('is_active'))
                return res
            off = self.filtered('is_active')
            if off and not self.search_count(
                    [('is_active', '=', True), ('id', 'not in', off.ids)]):
                raise UserError(_(
                    "At least one Points Rule must stay ON. To switch, turn ON "
                    "another rule instead — you can't turn off the only active one."))
        return super().write(vals)
