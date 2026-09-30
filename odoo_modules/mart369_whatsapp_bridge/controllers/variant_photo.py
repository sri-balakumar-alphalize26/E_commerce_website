"""A variant's extra pictures, for the storefront.

They live on `sa.confirm.picture` (sales_automation_confirm's Variant images
tab), which only Sales Automation users may read, so /web/image would answer a
shopper with a placeholder. This serves one picture, and only when it belongs to
a variant of a product that is on the website - the same pictures the WhatsApp
confirmation page already shows to anyone holding its link.

In the bridge because it reads the senior's model; models/variant_media.py
puts these addresses on the storefront's cards.

Named `.../photo/...` so the storefront's /api/mart proxy streams the bytes
instead of reading them as JSON (app/api/mart/[...path]/route.js).
"""

from odoo import http
from odoo.http import request


class Mart369VariantPhoto(http.Controller):

    @http.route('/369mart/variant/photo/<int:picture_id>', type='http', auth='public',
                methods=['GET'], csrf=False, sitemap=False, readonly=True,
                save_session=False)
    def variant_photo(self, picture_id, **kwargs):
        if 'sa.confirm.picture' not in request.env:
            return request.not_found()
        picture = request.env['sa.confirm.picture'].sudo().browse(picture_id).exists()
        variant = picture.product_id if picture and 'product_id' in picture._fields else None
        if (not variant or not picture.image
                or not variant.product_tmpl_id.is_published):
            return request.not_found()
        return request.env['ir.binary']._get_image_stream_from(
            picture, field_name='image', width=512, height=512, crop=False,
        ).get_response(max_age=3600)
