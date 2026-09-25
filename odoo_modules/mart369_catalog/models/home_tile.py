"""A home-page tile linked to a category wears that category's colours.

The home page's category strip used to carry a background and a drawing
colour of its own on every tile, so recolouring a category in the catalogue
left its tile the pale grey it was made with. Now a tile linked to a category
- main or sub - is painted with the category's tone and accent, and only a
tile pointing somewhere else keeps colours of its own. Nothing is copied, so
there is nothing to fall out of step.

It lives here rather than in mart369_home because the colours are the
catalogue's, and this module already depends on the home page (through
mart369_product); the other way round would be a loop.
"""

from odoo import api, models


class Mart369HomeTile(models.Model):
    _inherit = 'mart369.home.tile'

    def _mart369_colours(self):
        self.ensure_one()
        categ = self.public_categ_id
        if categ and categ.mart_tone:
            return categ.mart_tone, categ.mart_accent or self.color or ''
        return super()._mart369_colours()

    @api.depends('public_categ_id.mart_tone')
    def _compute_colour_from(self):
        for rec in self:
            categ = rec.public_categ_id
            rec.colour_from = categ.display_name if categ and categ.mart_tone else False

    @api.depends('name', 'bg', 'color', 'badge', 'image_path',
                 'public_categ_id.mart_tone', 'public_categ_id.mart_accent')
    def _compute_preview_html(self):
        return super()._compute_preview_html()
