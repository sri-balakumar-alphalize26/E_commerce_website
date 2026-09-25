"""Settings > Orders: how long a customer has to answer a replacement offer.

The shop's call, so it lives on the shared settings record and shows as the
**Orders** group of both Settings screens (mart369/models/settings_admin.py),
the way mart369_auth adds Customers. A change applies to offers made from now
on; one already sent keeps the deadline it was sent with.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

ORDER_FIELDS = {
    # console key: mart369.config field
    'substituteQuick': 'substitute_quick_minutes',
    'substituteExpress': 'substitute_express_minutes',
}


class Mart369Config(models.Model):
    _inherit = 'mart369.config'

    substitute_quick_minutes = fields.Integer(
        string='Quick: answer a replacement within (minutes)', default=10,
        help='How long a customer has to accept or refuse a replacement on a '
             'Quick order. No answer: the item is refunded.')
    substitute_express_minutes = fields.Integer(
        string='Express: answer a replacement within (minutes)', default=120,
        help='The same for an Express order.')

    @api.constrains('substitute_quick_minutes', 'substitute_express_minutes')
    def _check_substitute_minutes(self):
        for config in self:
            if config.substitute_quick_minutes < 1 or config.substitute_express_minutes < 1:
                raise ValidationError(_('The wait must be at least a minute.'))

    @api.model
    def _mart369_admin_settings_groups(self):
        groups = super()._mart369_admin_settings_groups()
        config = self._get()
        groups['orders'] = {key: config[field] for key, field in ORDER_FIELDS.items()}
        return groups

    @api.model
    def _mart369_admin_save_group(self, group, values):
        if group != 'orders':
            return super()._mart369_admin_save_group(group, values)
        vals = {}
        for key, field in ORDER_FIELDS.items():
            if key not in values:
                continue
            try:
                minutes = int(values[key])
            except (TypeError, ValueError):
                raise UserError(_('The wait must be a whole number of minutes.'))
            if minutes < 1:
                raise UserError(_('The wait must be at least a minute.'))
            vals[field] = minutes
        if vals:
            self._get().write(vals)
        return True
