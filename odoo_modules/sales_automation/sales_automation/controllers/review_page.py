# -*- coding: utf-8 -*-
"""/wa/review/<order> - "Rate your products" for an order bought through
WhatsApp, opened from the private Delivered message (13 Nov 2026). The order's
own portal token is the whole credential. See models/sa_review.py."""
from markupsafe import Markup

from odoo import http
from odoo.http import request

from .close_timer import CLOSE_TIMER
from .link_expired import expired_page, visit_expired


class SaReviewPage(http.Controller):

    def _order(self, order_id, token):
        return request.env['sale.order'].browse(order_id)._sa_review_check(token)

    @http.route('/wa/review/<int:order_id>', type='http', auth='public', methods=['GET'],
                website=True, sitemap=False)
    def review(self, order_id, access_token=None, saved=None, **kw):
        order = self._order(order_id, access_token)
        if not order:
            return request.not_found()
        if visit_expired(order):
            return expired_page()
        items = order._sa_review_items()
        return request.render('sales_automation.sa_review_page', {
            # the last product was just rated
            'close': Markup(CLOSE_TIMER) if saved and items and all(i['stars'] for i in items) else '',
            'order': order,
            'token': access_token,
            'open': order._sa_review_open(),
            'items': items,
            'saved': str(saved or ''),
        })

    @http.route('/wa/review/<int:order_id>/<int:product_id>', type='http', auth='public',
                methods=['POST'], website=True, sitemap=False)
    def save(self, order_id, product_id, access_token=None, stars=None, text=None, **kw):
        order = self._order(order_id, access_token)
        if order and visit_expired(order):
            return expired_page()
        if not order or not order._sa_review_open():
            return request.not_found()
        product = request.env['product.template'].sudo().browse(product_id).exists()
        try:
            ok = product and stars and order._sa_review_save(product, int(stars), text)
        except (TypeError, ValueError):
            ok = False
        return request.redirect('/wa/review/%s?access_token=%s&saved=%s#p%s' % (
            order.id, order.access_token, product_id if ok else '', product_id))
