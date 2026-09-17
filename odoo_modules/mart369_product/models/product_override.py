from odoo import fields, models

STATE = [
    ('follow', 'Follow the default'),
    ('show', 'Always show'),
    ('hide', 'Always hide'),
]


class Mart369ProductOverride(models.Model):
    """One product deliberately differing from the default.

    Rows only exist where an employee chose to deviate: a product that
    follows the defaults everywhere has none at all. That is what makes
    "switch this off for the whole shop" keep working after the fact - every
    product still following picks the change up.
    """

    _name = 'mart369.product.override'
    _description = '369 Mart Product Page Override'
    _order = 'product_tmpl_id, field_id'
    _rec_name = 'field_id'

    product_tmpl_id = fields.Many2one(
        'product.template', string='Product',
        required=True, ondelete='cascade', index=True)
    field_id = fields.Many2one(
        'mart369.product.field', string='Field',
        required=True, ondelete='cascade', index=True)
    state = fields.Selection(
        STATE, string='Shown?', required=True, default='follow',
        help='Follow the default: this product does whatever the shop-wide '
             'setting says, now and later. Always show / Always hide: this '
             'product ignores the shop-wide setting.')
    value = fields.Text(
        string='Value for this product',
        help='Leave empty to use the category value, or the shop default.')
    section_id = fields.Many2one(
        related='field_id.section_id', string='Section', store=True)

    _product_field_uniq = models.Constraint(
        'unique (product_tmpl_id, field_id)',
        'That field already has a setting on this product.')

    def action_reset(self):
        """Back to following the default, value and all."""
        self.write({'state': 'follow', 'value': False})
        return True
