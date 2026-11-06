"""A top-bar pill that opens a category wears that category's logo.

The pill's icon used to be chosen on the pill, so the logo a category was
given in the catalogue never reached the one place a main category shows a
logo. Now a pill that opens a category draws the category's: its uploaded
picture, else its built-in mark, and only then the pill's own icon. Pills
that open anything else - My Home, Offers - keep their own.

It lives here for the same reason the tile colours do (home_tile.py): the
logo is the catalogue's, and this module already depends on the home page.
"""

from odoo import models


class Mart369HomeTab(models.Model):
    _inherit = 'mart369.home.tab'

    def _mart369_category(self):
        """The category this pill opens, or an empty recordset.

        `route_param` is `peripherals` or `peripherals/keyboards`; the last
        part is the category the customer lands on.
        """
        self.ensure_one()
        Category = self.env['product.public.category'].sudo()
        if self.route_view != 'category' or not self.route_param:
            return Category
        slug = self.route_param.strip('/').rsplit('/', 1)[-1]
        return Category.search([('mart_slug', '=', slug)], limit=1) if slug else Category

    def _serialize(self):
        vals = super()._serialize()
        category = self._mart369_category()
        if category:
            logo = category._mart369_logo()
            if logo['icon']:
                vals['icon'] = logo['icon']
            # Optional keys are left out entirely, never sent as null.
            if logo['image']:
                vals['image'] = logo['image']
        return vals

    def _builder_vals(self):
        vals = super()._builder_vals()
        category = self._mart369_category()
        logo = category._mart369_logo() if category else {}
        # Whose logo the pill wears, so both page editors can say where to
        # change it instead of offering an icon picker that does nothing.
        vals['logo_from'] = category.name if logo.get('icon') or logo.get('image') else ''
        vals['logo_icon'] = logo.get('icon') or ''
        vals['logo_image'] = logo.get('image') or ''
        return vals
