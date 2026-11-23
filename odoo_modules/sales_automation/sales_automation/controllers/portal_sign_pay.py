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
import binascii
import logging

from odoo import _, fields, http
from odoo.addons.sale.controllers.portal import CustomerPortal
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from .link_expired import expired_page, visit_expired

_logger = logging.getLogger(__name__)


class SaSignThenPay(CustomerPortal):

    @http.route()
    def portal_order_page(self, order_id, access_token=None, **kw):
        """A WhatsApp group order's link works a week after it is over."""
        order = request.env['sale.order'].browse(order_id)._sa_review_check(access_token) if access_token else None
        if order and visit_expired(order):
            return expired_page()
        return super().portal_order_page(order_id, access_token=access_token, **kw)

    @http.route()
    def portal_quote_accept(self, order_id, access_token=None, name=None, signature=None):
        quick = self._sa_quick_sign(order_id, access_token, name, signature)
        res = quick if quick is not None else super().portal_quote_accept(
            order_id, access_token=access_token, name=name, signature=signature)
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

    def _sa_quick_sign(self, order_id, access_token, name, signature):
        """Odoo's own accept for a WhatsApp group order, without making the
        signed PDF while the customer waits: the task makes it once, for the
        order and for WhatsApp (models/sa_after_order.py). None for any other
        order - and for every refusal, which Odoo words itself."""
        access_token = access_token or request.httprequest.args.get('access_token')
        try:
            order = self._document_check_access('sale.order', order_id, access_token=access_token)
        except (AccessError, MissingError):
            return None
        if not signature or not order._has_to_be_signed() or not order._sa_after_signed_here():
            return None
        try:
            order.write({'signed_by': name, 'signed_on': fields.Datetime.now(), 'signature': signature})
            request.env.cr.flush()
        except (TypeError, binascii.Error):
            return {'error': _('Invalid signature data.')}
        if not order._has_to_be_paid():
            order.with_context(sale_include_signature=True)._validate_order()
        query = '&message=sign_ok'
        if order._has_to_be_paid():
            query += '&allow_payment=yes'
        if order.state != 'sale':
            # not confirmed here (a payment is asked first): no task follows,
            # so the signed PDF is kept on the order as Odoo does
            pdf = request.env['ir.actions.report'].sudo().with_context(
                sale_include_signature=True)._render_qweb_pdf('sale.action_report_saleorder', [order.id])[0]
            order.message_post(attachments=[('%s.pdf' % order.name, pdf)], author_id=order.partner_id.id,
                               body=_('Order signed by %s', name), message_type='comment',
                               subtype_xmlid='mail.mt_comment')
        return {'force_refresh': True, 'redirect_url': order.get_portal_url(query_string=query)}

    @http.route('/my/orders/<int:order_id>/step', type='http', auth='public', methods=['GET'],
                website=True, sitemap=False)
    def sa_order_step(self, order_id, access_token=None, **kw):
        """The waiting page asks whether there is something to do now."""
        order = request.env['sale.order'].browse(order_id)._sa_review_check(access_token)
        if not order or visit_expired(order):
            return request.make_json_response({'step': ''}, status=404)
        req = order._sa_group_enquiry()
        waiting = bool(req and order.state == 'sale' and not req.sa_pay_link_sent_on
                       and not req._sa_order_is_paid(order))
        return request.make_json_response({'step': 'wait' if waiting else 'go'},
                                          headers=[('Cache-Control', 'no-store')])

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
