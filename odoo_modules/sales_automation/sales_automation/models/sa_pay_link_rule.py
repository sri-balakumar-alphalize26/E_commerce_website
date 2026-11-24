# -*- coding: utf-8 -*-
"""When the payment link goes out: the admin says it, with stock and without
(owner, 23 Nov 2026). Sales Automation > Configuration > Payments."""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

WHEN = [('sign', 'At the signature'), ('accept', 'When the shop accepts'), ('never', 'Not sent automatically')]


class SaAiSettingsPayLink(models.Model):
    _inherit = 'sa.ai.settings'

    pay_link_in_stock = fields.Selection(WHEN, 'With Stock', default='sign', required=True)
    pay_link_no_stock = fields.Selection(WHEN, 'Without Stock', default='sign', required=True)
    pay_link_words = fields.Text(compute='_compute_pay_link_words')

    @api.depends('pay_link_in_stock', 'pay_link_no_stock')
    def _compute_pay_link_words(self):
        goods = {'sign': _("as soon as the customer signs"), 'accept': _("when the shop presses Accept"),
                 'never': _("only when somebody presses Send payment link")}
        bare = {'sign': _("as soon as the customer signs - they pay before the goods are here"),
                'accept': _("when the goods are here and the shop accepts"), 'never': goods['never']}
        for rec in self:
            rec.pay_link_words = _("All goods in stock: the payment link goes %(a)s.\nSomething not in stock: it goes %(b)s.",
                                   a=goods.get(rec.pay_link_in_stock, ''), b=bare.get(rec.pay_link_no_stock, ''))


class SaGroupRequestPayLink(models.Model):
    _inherit = 'sa.group.request'

    def _sa_pay_link_when(self, order):
        """'sign', 'accept' or 'never' for this order, now. Partly in stock is
        not in stock."""
        self.ensure_one()
        settings = self._settings()
        in_stock = self._sa_lines_in_stock(order)
        when = (settings.pay_link_in_stock if in_stock else settings.pay_link_no_stock) or 'sign'
        if when == 'accept' and self._sa_flow_end() != 'delivery':
            return 'sign'           # no counter step in this flow
        return when

    def _sa_accept_pay_link(self, job):
        """The shop accepted. Nothing by itself when the admin said so."""
        self.ensure_one()
        order = job.sale_id.sudo()
        settings = self._settings()
        rules = {settings.pay_link_in_stock, settings.pay_link_no_stock}
        if order and not self.sa_pay_link_sent_on and rules == {'never'}:
            return False
        if order and not self.sa_pay_link_sent_on and 'never' in rules:
            # which of the two it was at the signature
            waited = bool(getattr(job, 'sa_supply_arrived_on', False)) or self._sa_waited_for_goods(order)
            if (settings.pay_link_no_stock if waited else settings.pay_link_in_stock) == 'never':
                return False
        return super()._sa_accept_pay_link(job)

    def _sa_waited_for_goods(self, order):
        task = self.env['sa.after.task'].sudo().search([('request_id', '=', self.id), ('step', '=', 'signed')], order='id desc', limit=1)
        return bool(task and task.mode == 'wait_goods') or not self._sa_lines_in_stock(order)

    def _sa_send_pay_link_now(self):
        """Send payment link, by hand: on the counter and on the order."""
        self.ensure_one()
        order = self.order_id.sudo()
        if not order or order.state == 'cancel':
            raise UserError(_("There is no order to pay."))
        if self._sa_order_is_paid(order):
            raise UserError(_("This order is paid already."))
        if order._has_to_be_signed():
            raise UserError(_("The customer has not signed the order yet."))
        if not self.group_id.group_jid:
            raise UserError(_("The order has no WhatsApp group."))
        if not self.env['sa.outbox.guard'].sudo().claim('paylinkhand|%s' % self.id, 600):
            raise UserError(_("The payment link went out a moment ago. Wait ten minutes."))
        sent = self._say(_("\U0001F4B3 Payment for your order *#%(ref)s*\n\n%(order)s\n%(lines)s\n*Total: %(cur)s %(total).2f*\n\n%(pay)s",
                           ref=self.ref_code or order.name, order=order.name, lines=self._sa_order_lines_text(order),
                           cur=order.currency_id.symbol or '', total=order.amount_total, pay=self._sa_pay_link_any_state(order)))
        if sent is False:
            self.env['sa.outbox.guard'].sudo().release('paylinkhand|%s' % self.id)
            raise UserError(_("The payment link could not be sent. Is WhatsApp connected?"))
        self.write({'sa_pay_link_sent_on': fields.Datetime.now(), 'sa_stock_confirmed': True,
                    'sa_pay_remind_count': 0, 'sa_pay_reminded_on': False})
        _logger.info("Sales Automation: payment link of %s sent by hand by %s", order.name, self.env.user.name)
        return True


class SaleOrderPayLink(models.Model):
    _inherit = 'sale.order'

    sa_can_send_pay_link = fields.Boolean(compute='_compute_sa_can_send_pay_link')

    @api.depends('state')
    def _compute_sa_can_send_pay_link(self):
        for order in self:
            request = order._sa_group_enquiry() if order.id else False
            order.sa_can_send_pay_link = bool(request and request.group_id.group_jid and order.state == 'sale'
                                              and not request._sa_order_is_paid(order))

    def action_sa_send_pay_link(self):
        self.ensure_one()
        request = self._sa_group_enquiry()
        if not request:
            raise UserError(_("This order did not come from a WhatsApp group."))
        request.sudo()._sa_send_pay_link_now()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': _("Payment link sent to %s.", request.group_id.name)}}
