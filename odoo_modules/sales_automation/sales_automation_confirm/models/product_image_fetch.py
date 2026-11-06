# -*- coding: utf-8 -*-
"""The picture for an enquiry's product.

The product's own picture. The owner (5 Nov 2026): no internet search any more.
A product or enquiry with no picture gets the finder's Gemini reference picture
when that is switched on (cached, never saved on the product: it is a drawing,
not the item).
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
        """(bytes, source) - the picture to show for this enquiry's product.
        source: local / generated / none."""
        self.ensure_one()
        product = self.product_id
        if product and product.image_1920:
            return base64.b64decode(product.image_1920), 'local'
        name = (product.name if product else '') or self._sa_confirm_name()
        Suggest = self.env['sa.ai.suggestion'].sudo()
        if not fetch:
            # The page and the bridge read from the cache made when the link went out.
            cached = Suggest.recall('image', Suggest._key(name)) if name else None
            return (cached[0] if cached else b''), ('generated' if cached else 'none')
        if not name:
            return b'', 'none'
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        if not settings.confirm_fetch_images:
            return b'', 'none'
        key = Suggest._key(name)
        cached = Suggest.recall('image', key)
        picture = cached[0] if cached else b''
        if not picture:
            try:
                prompt = ("Clean studio product photograph of the %s, whole item visible, centred on a plain "
                          "white background, soft lighting, no text, no logo overlays, no watermark, no people." % name)
                picture, mimetype = self.env['sa.ai.classifier'].sudo()._call_gemini_image(prompt)
                if picture:
                    Suggest.store('image', key, image=picture, mimetype=mimetype or 'image/jpeg')
            except Exception as err:  # noqa: BLE001
                _logger.info("Sales Automation: reference picture for %r failed: %s", name, err)
                picture = b''
        return (picture or b''), ('generated' if picture else 'none')
