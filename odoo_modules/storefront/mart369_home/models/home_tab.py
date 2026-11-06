from odoo import api, fields, models

from odoo.addons.mart369.models.serializers import ICON_CHOICES, slugify


class Mart369HomeTab(models.Model):
    """One pill in the row of shortcuts across the top of the app."""

    _name = 'mart369.home.tab'
    _description = '369 Mart Home Tab'
    _inherit = ['mart369.serializable', 'mart369.home.trashable']
    _order = 'sequence, id'
    _trash_what = 'Tab'

    mode_id = fields.Many2one(
        'mart369.home.mode', string='App Mode',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(
        default=10,
        help='Drag the rows to change the order the pills appear in.')
    active = fields.Boolean(
        default=True,
        help='Off: this pill disappears from the app.')

    name = fields.Char(
        string='Label', required=True,
        help='The words on the pill, e.g. Groceries.')
    key = fields.Char(
        string='Key', required=True,
        help='A short internal name, e.g. grocery. Filled in for you from the '
             'label. Leave it alone once the app is live.')
    icon = fields.Selection(
        ICON_CHOICES, string='Icon', required=True, default='grid',
        help='The small drawing on the pill. Only these are available - the '
             'app draws them itself, so there is nothing to upload.')

    route_view = fields.Selection([
        ('home', 'The home page'),
        ('category', 'A category page'),
        ('offers', 'The offers page'),
        ('buyagain', 'The buy-again page'),
    ], string='Opens', required=True, default='category',
        help='Where the customer lands after tapping this pill.')
    route_param = fields.Char(
        string='Category address',
        help='Only for a category page: the address of the category to open, '
             'e.g. fruits-vegetables or fruits-vegetables/fresh-fruits.')

    _key_uniq = models.Constraint(
        'unique (mode_id, key)',
        'Two tabs in the same app mode cannot share a key.')

    @api.onchange('name')
    def _onchange_name(self):
        if self.name and not self.key:
            self.key = slugify(self.name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('key'):
                vals['key'] = slugify(vals.get('name'))
        return super().create(vals_list)

    def action_toggle_active(self):
        for rec in self:
            rec.active = not rec.active
        return True

    # ------------------------------------------------------------- serialise

    def _serialize(self):
        self.ensure_one()
        return {'key': self.key, 'label': self.name, 'icon': self.icon}

    def _builder_vals(self):
        """What the visual builder needs to list and edit this tab."""
        self.ensure_one()
        return {
            'id': self.id,
            'key': self.key,
            'name': self.name,
            'icon': self.icon,
            'route_view': self.route_view,
            'route_param': self.route_param or '',
            'active': self.active,
            'sequence': self.sequence,
        }
