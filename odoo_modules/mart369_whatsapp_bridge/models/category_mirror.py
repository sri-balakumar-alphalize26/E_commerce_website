"""The website and NEW ORDER list the same categories in the same order.

mart369_catalog gives each Product Category a website twin and keeps its name
and place in step (product_category.py there). The WhatsApp package adds two
fields of its own to a Product Category: *WhatsApp menu order*
(`sa_menu_sequence`) and *Hide from the WhatsApp menu* (`sa_menu_hide`). Here
they are kept in step with the twin's order (`sequence`) and *Show in the
app* (`mart_in_app`), both ways - so hiding a category, or moving it up, on
either screen does it on both.
"""

from odoo import api, models


class ProductCategoryMenuMirror(models.Model):
    _inherit = 'product.category'

    @api.model
    def _mart369_mirror_fields(self):
        return super()._mart369_mirror_fields() | {'sa_menu_sequence', 'sa_menu_hide'}

    def _mart369_mirror_vals(self):
        vals = super()._mart369_mirror_vals()
        vals.update({
            'sequence': self.sa_menu_sequence,
            'mart_in_app': not self.sa_menu_hide,
        })
        return vals


class ProductPublicCategoryMenuMirror(models.Model):
    _inherit = 'product.public.category'

    def _mart369_source_vals(self, vals):
        out = super()._mart369_source_vals(vals)
        if 'sequence' in vals:
            out['sa_menu_sequence'] = self.sequence
        if 'mart_in_app' in vals:
            out['sa_menu_hide'] = not self.mart_in_app
        return out
