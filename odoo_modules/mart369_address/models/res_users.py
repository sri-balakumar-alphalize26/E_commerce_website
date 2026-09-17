"""The customer's delivery addresses, reachable from their user form."""

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    mart369_address_ids = fields.One2many(
        'res.partner', 'parent_id', string='Delivery addresses',
        compute='_compute_mart369_address_ids', inverse='_inverse_mart369_address_ids',
        domain=[('type', 'in', ['delivery', 'other'])],
        help="Addresses this customer has saved in the 369 Mart app.")

    def _compute_mart369_address_ids(self):
        for user in self:
            user.mart369_address_ids = self.env['res.partner'].search([
                ('parent_id', '=', user.partner_id.id),
                ('type', 'in', ['delivery', 'other']),
            ], order='mart369_default desc, id asc')

    def _inverse_mart369_address_ids(self):
        """Rows added on the form belong to this customer and are deliveries."""
        for user in self:
            user.mart369_address_ids.filtered(lambda p: not p.parent_id).write({
                'parent_id': user.partner_id.id, 'type': 'other',
            })
