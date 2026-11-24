"""Which products the shop lists.

Published is not enough. A service is published so it can be bought - the
wallet top-up, a gift card, a repair charge - but it is not something to
browse: on the Dubai shop "Top-up eWallet", "Gift Card" and "Repair Service"
led the "New this week" row. Archived is not listed either: a hand-picked home
row filters the products already picked, which Odoo's own skipping of archived
records never sees. So every list a shopper sees - rows, categories, search,
offers - asks this one rule, and only those lists do. Looking a
product up by id (the cart, a shared link, the product page) does not, so a
gift card in a basket still works.

Settings > Products adds up to three more conditions: a price, a picture,
stock. A product missing any one that is switched on is not listed. The same
lists and no others - and never WhatsApp, which has its own rules.
"""

from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _mart369_listed_base_domain(self):
        """What may be listed at all, before the Settings > Products switches.
        For checks on what staff arrange, which must not depend on today's
        stock."""
        return [('active', '=', True), ('is_published', '=', True), ('type', '!=', 'service')]

    @api.model
    def _mart369_listed_domain(self):
        return self._mart369_listed_base_domain() + self._mart369_visibility_domain()

    @api.model
    def _mart369_visibility_domain(self):
        """The Settings > Products switches that are on, every one of which a
        product has to pass. Empty when all are off.

        Pictures and free stock are not columns, so those two are lists of ids;
        that also lets `filtered_domain` apply them to hand-picked rows."""
        config = self.env['mart369.config'].sudo()._get()
        domain = []
        if config.require_price:
            domain.append(('list_price', '>', 0))
        if config.require_image:
            domain.append(('id', 'in', self._mart369_pictured_ids()))
        # Without Inventory nothing has stock, and the switch would empty the shop.
        if config.require_stock and 'free_qty' in self.env['product.product']._fields:
            mixin = self.env['mart369.serializable'].sudo()
            found = self.env['product.template'].sudo().search(
                self._mart369_listed_base_domain() + domain)
            mixin._mart369_load_stock(found)
            # None (Inventory does not track it) counts as no stock.
            in_stock = found.filtered(lambda t: (mixin._mart369_free_qty(t) or 0) > 0)
            domain.append(('id', 'in', in_stock.ids))
        return domain

    @api.model
    def _mart369_pictured_ids(self):
        """Products whose card has a picture to draw: their own, or one of
        their Extra Product Media. Asked of the attachments, never of the
        picture itself, which would be downloaded from the image server."""
        Attachment = self.env['ir.attachment'].sudo()

        def having(model):
            groups = Attachment._read_group(
                [('res_model', '=', model), ('res_field', '=', 'image_1920'),
                 ('file_size', '>', 0)], groupby=['res_id'])
            return [res_id for (res_id,) in groups if res_id]

        ids = set(having('product.template'))
        if 'product_template_image_ids' in self._fields:
            extra = self.env['product.image'].sudo().search(
                [('id', 'in', having('product.image'))])
            ids |= set(extra.product_tmpl_id.ids)
        return sorted(ids)
