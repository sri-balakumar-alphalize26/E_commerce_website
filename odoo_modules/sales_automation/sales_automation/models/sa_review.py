# -*- coding: utf-8 -*-
"""Rate your products - for orders bought through WhatsApp (13 Nov 2026).

Customers who ordered in WhatsApp had no way to write a review: the website's
review form needs a website account and a website order. Once the order is
delivered, the private "Delivered" message carries a link to
/wa/review/<order>?access_token=<the order's portal token>, a page in the
369 Mart look with one card per product: stars and an optional line.

Reviews are saved the way the website saves them (rating.rating via
mart369_account's `_mart369_write_review`, so staff moderate them in the same
place and they show on the product page), else as a plain Odoo rating.
"""
import hmac

from odoo import _, api, models


class SaleOrderReview(models.Model):
    _inherit = 'sale.order'

    def _sa_review_check(self, token):
        """The order, sudo, when `token` is its portal token; else empty."""
        order = self.sudo().exists()
        if not order or not token or not order.access_token:
            return self.browse()
        if not hmac.compare_digest(str(order.access_token), str(token)):
            return self.browse()
        return order

    def _sa_review_open(self):
        """Ratings only once the order is delivered."""
        self.ensure_one()
        return bool(self._sa_portal_status().get('delivered'))

    def _sa_review_path(self):
        self.ensure_one()
        self._portal_ensure_token()
        return '/wa/review/%s?access_token=%s' % (self.id, self.access_token)

    def _sa_review_products(self):
        """The products bought, once each - no delivery or discount lines."""
        self.ensure_one()
        seen, out = set(), self.env['product.template']
        for line in self.sudo().order_line:
            if self._sa_line_kind(line) != 'item' or not line.product_id:
                continue
            tmpl = line.product_id.product_tmpl_id
            if tmpl.id not in seen:
                seen.add(tmpl.id)
                out |= tmpl
        return out

    def _sa_review_existing(self, product):
        self.ensure_one()
        return self.env['rating.rating'].sudo().search([
            ('res_model', '=', 'product.template'), ('res_id', '=', product.id),
            ('partner_id', '=', self.partner_id.id),
        ], order='id desc', limit=1)

    def _sa_review_items(self):
        self.ensure_one()
        items = []
        for tmpl in self._sa_review_products():
            existing = self._sa_review_existing(tmpl)
            items.append({
                'product': tmpl,
                'name': tmpl.name or '',
                # Asked without downloading: on the image server a picture is
                # linked straight there, anything else is shown as before.
                'image': self.env['sa.picture'].url(
                    tmpl, 'image_256', '/web/image/product.template/%s/image_256' % tmpl.id),
                'picture': self.env['sa.picture'].src(tmpl, 'image_128'),
                'stars': int(round(existing.rating)) if existing else 0,
                'text': (existing.feedback or '') if existing else '',
            })
        return items

    def _sa_review_save(self, product, stars, text):
        """Save (or change) this customer's review of one product they bought."""
        self.ensure_one()
        if product not in self._sa_review_products():
            return False
        stars = max(1, min(5, int(stars or 0)))
        text = (text or '').strip()[:500]
        Rating = self.env['rating.rating'].sudo()
        partner = self.partner_id
        if hasattr(Rating, '_mart369_write_review'):
            row = Rating._mart369_write_review(partner, product, {'stars': stars, 'text': text})
            # This order is delivered and contains the product: a real purchase,
            # whatever the website's own order states say.
            if 'mart369_verified' in row._fields and not row.mart369_verified:
                row.mart369_verified = True
            return row
        existing = self._sa_review_existing(product)
        vals = {'rating': stars, 'feedback': text, 'consumed': True, 'is_internal': False}
        if existing:
            existing.write(vals)
            return existing
        vals.update({'res_model_id': self.env['ir.model']._get_id('product.template'),
                     'res_id': product.id, 'partner_id': partner.id})
        return Rating.create(vals)

    @api.model
    def _sa_review_message_line(self, order):
        """The line added to the private Delivered message, or ''."""
        if not order or not order._sa_review_products():
            return ''
        link = self.env['wa.auto.reply'].sudo()._sa_public_link(order._sa_review_path())
        return _("\n\n⭐ How was it? Rate your products: %s", link)
