"""The storefront shows a variant the way the WhatsApp page does.

sales_automation_confirm gives every variant a *Variant images* tab
(`sa_variant_picture_ids`) and a *Variant specs* table (`_sa_spec_rows()`).
The storefront's cards (mart369.serializable) only know plain Odoo - the
variant's image and its attribute values - and this is where they learn the
senior's two tabs, so the website and the chat list the same photos and the
same rows. This module is the only place the two stacks meet.
"""

from odoo import api, models

from odoo.addons.mart369.models.serializers import MAX_EXTRA_IMAGES


class Mart369SerializableVariantMedia(models.AbstractModel):
    _inherit = 'mart369.serializable'

    @api.model
    def _mart369_variant_extra_images(self, variant):
        """The Variant images tab, in its order, after the variant's own image.

        Served by /369mart/variant/photo/<id> (controllers/variant_photo.py):
        the pictures' model is readable by Sales Automation users only."""
        images = super()._mart369_variant_extra_images(variant)
        # bin_size: only whether a picture is there, not its bytes.
        pictures = variant.with_context(bin_size=True).sa_variant_picture_ids.sorted(
            lambda p: (p.sequence, p.id)).filtered('image')
        return images + ['%s/369mart/variant/photo/%d' % (self._api_base(), pic.id)
                         for pic in pictures[:MAX_EXTRA_IMAGES]]

    @api.model
    def _mart369_variant_spec_rows(self, variant):
        """The Variant specs table - the exact rows the WhatsApp page lists:
        attribute lines by default, edited lines win, extra lines appended."""
        return variant._sa_spec_rows()
