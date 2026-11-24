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
* **visibility** decides which products the web shop lists - see
  product_listing.py, the one rule that reads it.
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

VISIBILITY_FIELDS = {
    'requirePrice': 'require_price',
    'requireImage': 'require_image',
    'requireStock': 'require_stock',
}


class Mart369Config(models.Model):
    _inherit = 'mart369.config'

    alert_new_order = fields.Boolean(
        string='Alert on new orders', default=True,
        help="The console's bell and sidebar badge count orders waiting to be "
             "moved on. Off: they stay quiet.")
    shop_logo = fields.Image(
        string='Shop logo', max_width=1024, max_height=1024,
        help="The logo the storefront and every page sent by link (WhatsApp "
             "product page, sign and pay page, payment pages) show. Empty: "
             "the logo that ships with the shop.")
    alert_low_stock = fields.Boolean(
        string='Alert on low stock', default=True,
        help="The console's bell says how many products are at or below the "
             "level where the app starts saying \"Only N left\".")

    require_price = fields.Boolean(
        string='Show only products with a price',
        help="On: the web shop does not list a product with no price, or a price of 0.")
    require_image = fields.Boolean(
        string='Show only products with a picture',
        help="On: the web shop does not list a product with no picture.")
    require_stock = fields.Boolean(
        string='Show only products in stock',
        help="On: the web shop does not list a product with no stock left, or "
             "whose stock is not counted.")

    # -------------------------------------------------------------- reading

    @api.model
    def mart369_admin_settings(self):
        """Every group the screen draws, keyed by group."""
        return self._mart369_admin_settings_groups()

    @api.model
    def _mart369_admin_settings_groups(self):
        company = self.env.company
        config = self._get()
        store = {key: company[field] or '' for key, field in STORE_FIELDS.items()}
        store['logo'] = config._mart369_logo_url()
        return {
            'store': store,
            'alerts': {key: bool(config[field]) for key, field in ALERT_FIELDS.items()},
            'visibility': {key: bool(config[field])
                           for key, field in VISIBILITY_FIELDS.items()},
        }

    # ------------------------------------------------------------ the logo

    def _mart369_logo_url(self):
        """'/369mart/logo?v=<when>' when a logo was uploaded, else ''. The
        version changes with every upload, so browsers never keep the old one."""
        config = self.sudo()._get()
        if not config.shop_logo:
            return ''
        stamp = int(config.write_date.timestamp()) if config.write_date else 0
        return '/369mart/logo?v=%s' % stamp

    @api.model
    def _mart369_save_logo(self, value):
        """value: a data URL from the console ("data:image/png;base64,..."),
        '' or None to go back to the shop's own logo, or the current
        '/369mart/logo?...' address, which means unchanged."""
        if isinstance(value, str) and value.startswith('/369mart/logo'):
            return
        config = self._get()
        if not value:
            config.write({'shop_logo': False})
            return
        if not isinstance(value, str) or not value.startswith('data:image/') or ';base64,' not in value:
            raise UserError(_('The logo must be a PNG, JPG or WebP picture.'))
        mimetype, data = value[5:].split(';base64,', 1)
        if mimetype not in ('image/png', 'image/jpeg', 'image/webp'):
            raise UserError(_('The logo must be a PNG, JPG or WebP picture.'))
        if len(data) > 4 * 1024 * 1024:
            raise UserError(_('The logo is too big - please use one under 3 MB.'))
        config.write({'shop_logo': data})

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
            if 'logo' in values:
                self._mart369_save_logo(values['logo'])
            return True
        if group == 'alerts':
            vals = {field: bool(values[key])
                    for key, field in ALERT_FIELDS.items() if key in values}
            if vals:
                self._get().write(vals)
            return True
        if group == 'visibility':
            vals = {field: bool(values[key])
                    for key, field in VISIBILITY_FIELDS.items() if key in values}
            if vals:
                self._get().write(vals)
            return True
        raise UserError(_('There is no such group of settings.'))
