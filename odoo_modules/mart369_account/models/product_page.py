"""What a product page says about each review, now that reviews carry more.

`mart369_product` builds the list (product_page.py); this adds what only this
module knows about: the review's id (for Helpful / Report), its headline and
tags, whether the author really bought it, the photos and video staff have
approved, and the shop's public reply. `helpful` stops being a hard-coded 0.
"""

from odoo import api, models

from odoo.addons.mart369_product.models.product_page import REVIEW_DOMAIN


class Mart369ProductPage(models.AbstractModel):
    _inherit = 'mart369.product.page'

    @api.model
    def reviews(self, product, keys, values):
        out = super().reviews(product, keys, values)
        rows = out.get('reviews')
        if not rows:
            return out
        ratings = self.env['rating.rating'].sudo().search(
            REVIEW_DOMAIN + [('res_model', '=', 'product.template'), ('res_id', '=', product.id)],
            order='create_date desc', limit=len(rows))
        for row, rating in zip(rows, ratings):
            row.update({
                'id': rating.id,
                'title': rating.mart369_title or '',
                'tags': [t for t in (rating.mart369_tags or '').split(',') if t],
                'verified': bool(rating.mart369_verified),
                'helpful': rating.mart369_helpful or 0,
                'media': [m._mart369_serialize() for m in rating.mart369_media_ids
                          if m.state == 'approved'],
                'reply': rating.publisher_comment or '',
            })
        return out
