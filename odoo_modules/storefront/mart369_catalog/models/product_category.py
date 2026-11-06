"""One category tree: the Product Category, with the website's look on top.

The WhatsApp package files every product under a **Product Category**
(Sales > Configuration > Categories) and walks those for NEW ORDER. The
storefront draws `product.public.category`, which is where the app's look
lives - slug, colours, blurb, logo. So each Product Category gets a website
twin, its *mirror*: the name and place come from the Product Category, the
look is the website's own, and a product's website category is always the
mirror of its Product Category.

Names are typed once. Renaming or moving either one renames or moves the
other (the console's category screens edit the website twin), with
`mart369_mirror_sync` in the context so the two writes do not chase each
other. mart369_whatsapp_bridge adds the WhatsApp menu order and Hide to what
is kept in step.

A Product Category with no mirror (Goods, Services, Deliveries...) is
internal: it is never on the website.
"""

from odoo import api, fields, models

SYNC = 'mart369_mirror_sync'


class ProductCategory(models.Model):
    _inherit = 'product.category'

    mart_mirror_id = fields.Many2one(
        'product.public.category', string='On the website', copy=False,
        index=True, ondelete='set null',
        help="The category's twin on the 369 Mart website: its look (logo, "
             "colours, one-line description) is set there, its name and "
             "place here. Empty: an internal category, never on the website.")

    # ---------------------------------------------------- what is kept in step

    @api.model
    def _mart369_mirror_fields(self):
        """The Product Category's own fields the mirror follows."""
        return {'name', 'parent_id'}

    def _mart369_mirror_vals(self):
        """The mirror's values, from this Product Category."""
        self.ensure_one()
        return {
            'name': self.name,
            # The parent's twin, so the website keeps the same tree.
            'parent_id': self.parent_id.mart_mirror_id.id or False,
        }

    # ------------------------------------------------------------ the twins

    @api.model_create_multi
    def create(self, vals_list):
        categories = super().create(vals_list)
        if not self.env.context.get(SYNC):
            Public = self.env['product.public.category'].sudo().with_context(**{SYNC: True})
            for category in categories.filtered(lambda c: not c.mart_mirror_id):
                category.with_context(**{SYNC: True}).mart_mirror_id = Public.create(
                    category._mart369_mirror_vals())
        return categories

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get(SYNC):
            return res
        if set(vals) & (self._mart369_mirror_fields() | {'mart_mirror_id'}):
            for category in self.filtered('mart_mirror_id'):
                category.mart_mirror_id.sudo().with_context(**{SYNC: True}).write(
                    category._mart369_mirror_vals())
        if 'mart_mirror_id' in vals:
            # A twin linked (or changed) later: its products move with it.
            for category in self:
                self.env['product.template'].sudo().search(
                    [('categ_id', '=', category.id)])._mart369_follow_category()
        return res

    def unlink(self):
        # The twin stays - a customer may have its link - but leaves the app.
        self.mart_mirror_id.sudo().with_context(**{SYNC: True}).write({'mart_in_app': False})
        return super().unlink()
