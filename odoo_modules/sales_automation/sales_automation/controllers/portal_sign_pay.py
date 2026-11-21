# -*- coding: utf-8 -*-
"""Sign, then pay at once (owner, 21 Nov 2026).

A WhatsApp group order is signed on its order page; the signature confirms it
and `_sa_group_signed` (models/sa_group_details.py) sends the pay link. The
customer then had to go back to WhatsApp for that second link. Now, when the
pay link has just gone out, the page they signed on opens straight on the
payment instead - one link, no extra step. The pay link in the chat stays as
the backup.

Not when no payment is asked yet (goods being arranged, the flow ending at the
signed order or the invoice), when nothing is left to pay, or while a
"💎 USE POINTS" choice is open in the group: the amount could still change,
so the page keeps its Pay button, which reads the amount when pressed.
"""
import logging

from odoo import http
from odoo.addons.sale.controllers.portal import CustomerPortal
from odoo.http import request

_logger = logging.getLogger(__name__)


class SaSignThenPay(CustomerPortal):

    @http.route()
    def portal_quote_accept(self, order_id, access_token=None, name=None, signature=None):
        res = super().portal_quote_accept(order_id, access_token=access_token, name=name,
                                          signature=signature)
        if not isinstance(res, dict) or res.get('error') or not res.get('redirect_url'):
            return res
        try:
            url = self._sa_pay_now_url(order_id)
        except Exception:  # noqa: BLE001 - the signed page shows either way
            _logger.exception("Sales Automation: pay-after-sign for order %s failed", order_id)
            url = ''
        if url:
            res['redirect_url'] = url
        return res

    def _sa_pay_now_url(self, order_id):
        """The order page opened on the payment, or '' to keep Odoo's page."""
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        if not order or order.state != 'sale' or not hasattr(order, '_sa_group_enquiry'):
            return ''
        req = order._sa_group_enquiry()
        if not req or not req.group_id or not req.sa_pay_link_sent_on:
            return ''
        if 'ss_points' in (getattr(req, 'sa_menu_json', '') or ''):
            return ''
        due = order._sa_portal_status().get('due') or 0.0
        if due <= 0.005:
            return ''
        amount = order.currency_id.round(due) if order.currency_id else round(due, 2)
        return order.get_portal_url(query_string='&message=sign_ok&payment_amount=%s' % amount)
