# -*- coding: utf-8 -*-
"""The order page says what happens next (owner, 24 Nov 2026): only what is
really sent after signing and paying, by this shop's settings."""
from datetime import timedelta

from markupsafe import Markup

from odoo import _, fields, models

from ..controllers.close_timer import CLOSE_TIMER


class SaleOrderPortalNext(models.Model):
    _inherit = 'sale.order'

    def _sa_portal_next(self, step, status):
        """The sentences for the page, or [] (not a WhatsApp group order)."""
        self.ensure_one()
        order = self.sudo()
        req = order._sa_group_enquiry() if hasattr(order, '_sa_group_enquiry') else False
        if not req or not req.group_id or order.state == 'cancel':
            return []
        end = req._sa_flow_end()
        pdf = _("Your signed order (PDF) is sent to you on WhatsApp.")
        invoice = _("After you pay, your invoice is sent to you on WhatsApp.")
        road = _("We message you on WhatsApp when your order is packed and when the rider is on the way.")
        if step == 'sign':
            return [pdf] + ([_("Your invoice is sent to you on WhatsApp too.")] if end == 'invoice' else [invoice] if end != 'order' else [])
        if step in ('pay', 'pay_link'):
            lines = [pdf] if order.signature else []
            return lines + [invoice] + ([road] if end == 'delivery' else [])
        if step == 'done':
            if status.get('delivered'):
                return []
            return [_("Your invoice is sent to you on WhatsApp.")] + (
                [road] if end == 'delivery' else [_("We will contact you about the handover.")])
        if step == 'wait' and order.signature:
            task = self.env['sa.after.task'].sudo().search(
                [('request_id', '=', req.id), ('step', '=', 'signed')], order='id desc', limit=1)
            if task.mode == 'stop':
                return [pdf] + ([_("Your invoice is sent to you on WhatsApp too.")] if end == 'invoice' else []) + [
                    _("We will contact you about the next step.")]
            if task.mode == 'wait':
                return [pdf, _("Your order is with the shop. We will write to you on WhatsApp about the payment.")]
            if task.mode == 'wait_goods':
                return [pdf, _("We are arranging the goods and will write to you on WhatsApp when they are in.")
                        if req._settings().pay_link_no_stock == 'never'
                        else _("We are arranging the goods. The payment link comes on WhatsApp when they are in.")]
        return []

    def _sa_portal_just_done(self, step):
        """Signed with nothing left to do, or paid: a moment ago."""
        self.ensure_one()
        order = self.sudo()
        if not order._sa_group_enquiry():
            return False
        since = fields.Datetime.now() - timedelta(minutes=2)
        if step == 'wait':
            return bool(order.signed_on and order.signed_on > since)
        if step == 'done':
            done = order.transaction_ids.filtered(lambda t: t.state in ('done', 'authorized')).sorted('id')[-1:]
            return bool(done.last_state_change and done.last_state_change > since)
        return False

    def _sa_portal_page(self, payment_amount=False):
        page = super()._sa_portal_page(payment_amount)
        page['next'] = self._sa_portal_next(page['step'], page['status'])
        page['close'] = Markup(CLOSE_TIMER) if self._sa_portal_just_done(page['step']) else ''
        return page
