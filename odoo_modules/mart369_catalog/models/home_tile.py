"""A home-page tile linked to a category wears that category's colours - and,
when its picture is "the category's logo", that logo.

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

    # ---------------------------------------------------------------- the logo
    # A tile whose picture is "the category's logo" draws what the catalogue
    # says: the category's uploaded picture, filling the whole tile, else its
    # built-in drawing, else the tile's own drawing. Changing a sub-category's
    # logo in Catalogue > Categories therefore changes its tile too.

    def _mart369_logo(self):
        """The linked category's logo when this tile wears it, else {}."""
        self.ensure_one()
        if self.image_source != 'category' or not self.public_categ_id:
            return {}
        return self.public_categ_id._mart369_logo()

    @api.depends('image_source', 'image_1920', 'image_url',
                 'public_categ_id.mart_logo', 'public_categ_id.write_date')
    def _compute_image_path(self):
        super()._compute_image_path()
        for rec in self:
            logo = rec._mart369_logo()
            if logo:
                rec.image_path = logo['image']

    @api.onchange('public_categ_id')
    def _onchange_public_categ_id(self):
        super()._onchange_public_categ_id()
        # A tile linked to a category wears its logo unless told otherwise.
        if self.public_categ_id and self.image_source in ('upload', 'art') \
                and not self.image_1920:
            self.image_source = 'category'

    def _serialize(self):
        vals = super()._serialize()
        logo = self._mart369_logo()
        if logo:
            if logo['image']:
                vals['image'] = logo['image']
                # An uploaded logo is cropped square to fill the tile, not
                # sit inside it like a drawing.
                vals['fill'] = True
            elif logo['art']:
                vals['art'] = logo['art']
        return vals

    def _builder_vals(self):
        vals = super()._builder_vals()
        logo = self._mart369_logo()
        # What the tile actually draws, for the builders' previews.
        vals['paint_art'] = (logo.get('art') if logo and not logo['image'] else '') \
            or self.art or 'Pack'
        vals['logo_from'] = self.public_categ_id.name if logo else ''
        return vals
