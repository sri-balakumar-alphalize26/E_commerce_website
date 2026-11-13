# -*- coding: utf-8 -*-
"""The logo every page sent by link shows - the WhatsApp product page, the
sign and pay page, Odoo's payment pages, the delivery and tracking pages.

13 Nov 2026, owner: change the logo once on the storefront and it changes
here too. In order:
  1. the logo uploaded in the 369 Mart console (Settings > Store), when the
     storefront modules are installed (mart369.config.shop_logo);
  2. the system parameter `sa.brand_logo_url`;
  3. the logo that ships with this module.
"""
from odoo import api, models

DEFAULT_LOGO = '/sales_automation/static/src/img/369mart-logo.png'


class SaBrand(models.AbstractModel):
    _name = 'sa.brand'
    _description = 'Logo of the pages sent by link'

    @api.model
    def logo_url(self, fallback=DEFAULT_LOGO):
        """fallback: what to give when neither an uploaded logo nor the
        parameter is set - '' lets a page use a logo of its own."""
        config = self.env.get('mart369.config')
        if config is not None and 'shop_logo' in config._fields:
            try:
                url = config.sudo()._get()._mart369_logo_url()
            except Exception:  # noqa: BLE001 - their change must never break a page
                url = ''
            if url:
                return url
        return (self.env['ir.config_parameter'].sudo().get_param('sa.brand_logo_url', '')
                or fallback)
