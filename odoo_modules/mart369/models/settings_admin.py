"""The console's Settings screen, and where each of its fields really lives.

The screen used to keep its own copy of everything in React state and "save"
nowhere. Each group now reads and writes the record that already decides the
thing - a copy kept here would be a second place deciding whether the shop's
phone number is this or that, and the two would drift:

* **store** is the company: name, phone, email, address and GSTIN (Odoo's
  `vat`). Opening hours are not here - nothing in the shop reads them; the
  delivery slots are what decide when an order can be placed.
* **alerts** are the only fields that had no home anywhere, so they live on
  this model - and only the two the console actually acts on.
* **pay** is added by `mart369_payment`, which owns the payment providers.

A module adds a group by overriding `_mart369_admin_settings_groups` and
`_mart369_admin_save_group`, the way `mart369_payment` does.

Nothing is sudo'd. Writing the company needs Odoo's own settings right, and a
designer without it is told so rather than quietly lifted over it.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

STORE_FIELDS = {
    # console key: res.company field
    'name': 'name',
    'phone': 'phone',
    'email': 'email',
    'street': 'street',
    'street2': 'street2',
    'city': 'city',
    'zip': 'zip',
    'gstin': 'vat',
}

ALERT_FIELDS = {
    'newOrder': 'alert_new_order',
    'lowStock': 'alert_low_stock',
}


class Mart369Config(models.Model):
    _inherit = 'mart369.config'

    alert_new_order = fields.Boolean(
        string='Alert on new orders', default=True,
        help="The console's bell and sidebar badge count orders waiting to be "
             "moved on. Off: they stay quiet.")
    alert_low_stock = fields.Boolean(
        string='Alert on low stock', default=True,
        help="The console's bell says how many products are at or below the "
             "level where the app starts saying \"Only N left\".")

    # -------------------------------------------------------------- reading

    @api.model
    def mart369_admin_settings(self):
        """Every group the screen draws, keyed by group."""
        return self._mart369_admin_settings_groups()

    @api.model
    def _mart369_admin_settings_groups(self):
        company = self.env.company
        config = self._get()
        return {
            'store': {key: company[field] or '' for key, field in STORE_FIELDS.items()},
            'alerts': {key: bool(config[field]) for key, field in ALERT_FIELDS.items()},
        }

    # -------------------------------------------------------------- writing

    @api.model
    def mart369_admin_save(self, group, values):
        """Save one group and hand back every group as it now stands."""
        if not isinstance(values, dict):
            raise UserError(_('Nothing to save.'))
        self._mart369_admin_save_group(group, values)
        return self.mart369_admin_settings()

    @api.model
    def _mart369_admin_save_group(self, group, values):
        if group == 'store':
            vals = {}
            for key, field in STORE_FIELDS.items():
                if key in values:
                    vals[field] = (values[key] or '').strip() or False
            if 'name' in vals and not vals['name']:
                raise UserError(_('The store needs a name.'))
            if vals:
                self.env.company.write(vals)
            return True
        if group == 'alerts':
            vals = {field: bool(values[key])
                    for key, field in ALERT_FIELDS.items() if key in values}
            if vals:
                self._get().write(vals)
            return True
        raise UserError(_('There is no such group of settings.'))
