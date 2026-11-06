"""How long a customer stays New, and when a quiet one turns Dormant.

Both used to be numbers in the code (7 and 60 days). They are the shop's call,
so they live on the shared settings record and show as the **Customers** group
of the Settings screen - the console's and Odoo's, which read the same groups
(`mart369/models/settings_admin.py`).

Saving either one recomputes every customer's status there and then. The
status is stored, and otherwise only the nightly job and a sign-in refresh it:
a shop that shortens New from 30 days to 14 would go on seeing last month's
sign-ups as New until tomorrow, and read that as the setting not working.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

CUSTOMER_FIELDS = {
    # console key: mart369.config field
    'newDays': 'customer_new_days',
    'dormantDays': 'customer_dormant_days',
}


class Mart369Config(models.Model):
    _inherit = 'mart369.config'

    customer_new_days = fields.Integer(
        string='New for (days)', default=30,
        help='A customer is New for this many days after signing up, then Active.')
    customer_dormant_days = fields.Integer(
        string='Dormant after (days)', default=90,
        help='A customer who has not signed in for this many days is Dormant.')

    @api.constrains('customer_new_days', 'customer_dormant_days')
    def _check_customer_days(self):
        for config in self:
            if config.customer_new_days < 1 or config.customer_dormant_days < 1:
                raise ValidationError(_('The number of days must be 1 or more.'))

    def write(self, vals):
        res = super().write(vals)
        if {'customer_new_days', 'customer_dormant_days'} & set(vals):
            self.env['res.users']._cron_mart369_refresh_status()
        return res

    # ------------------------------------------------------ settings screen

    @api.model
    def _mart369_admin_settings_groups(self):
        groups = super()._mart369_admin_settings_groups()
        config = self._get()
        groups['customers'] = {key: config[field] for key, field in CUSTOMER_FIELDS.items()}
        return groups

    @api.model
    def _mart369_admin_save_group(self, group, values):
        if group != 'customers':
            return super()._mart369_admin_save_group(group, values)
        vals = {}
        for key, field in CUSTOMER_FIELDS.items():
            if key not in values:
                continue
            try:
                days = int(values[key])
            except (TypeError, ValueError):
                raise UserError(_('The number of days must be a whole number.'))
            if days < 1:
                raise UserError(_('The number of days must be 1 or more.'))
            vals[field] = days
        if vals:
            self._get().write(vals)
        return True
