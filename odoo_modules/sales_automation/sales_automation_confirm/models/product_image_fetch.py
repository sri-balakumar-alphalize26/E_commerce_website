# -*- coding: utf-8 -*-
"""The picture for an enquiry's product.

The product's own picture or none. The owner (23 Nov 2026): nothing from the
internet and nothing drawn by an AI.
"""
import base64
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


def _media_bytes(images):
    """Decoded pictures of product.image records, in the shop's order, no repeats."""
    out = []
    for img in images.sorted(lambda i: (i.sequence, i.id)):
        data = img.image_1920
        if data:
            raw = base64.b64decode(data)
            if raw not in out:
                out.append(raw)
    return out


class ProductTemplateConfirmPicture(models.Model):
    _inherit = 'product.template'

    sa_extra_picture_ids = fields.One2many('sa.confirm.picture', 'product_tmpl_id', 'Other shots (confirmation page)')


class SaGroupRequestPicture(models.Model):
    _inherit = 'sa.group.request'

    def _sa_confirm_name(self):
        """What the customer is confirming when there is no product record."""
        self.ensure_one()
        if self.state == 'finding' and getattr(self, 'finder_model', False):
            return self.finder_model
        return self.ai_search_term or self.raw_text or ''

    def _sa_confirm_picture(self, fetch=True):
        """(bytes, source) - the product's own picture. source: local / none."""
        self.ensure_one()
        product = self.product_id
        if product and product.image_1920:
            return base64.b64decode(product.image_1920), 'local'
        return b'', 'none'
