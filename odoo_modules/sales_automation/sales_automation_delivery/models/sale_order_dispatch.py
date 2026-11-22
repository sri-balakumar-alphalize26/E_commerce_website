# -*- coding: utf-8 -*-
"""Confirming an order sends the delivery out."""

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """Dispatch every outgoing picking this confirmation produced.

        One override covers every route an order can be confirmed by: the
        WhatsApp group flow, the tracker's `_wa_finalize`, the payment
        transaction's `_post_process`, and a person pressing Confirm in Odoo.
        Hooking the order rather than each of those is what stops a new path
        being added later that quietly delivers nothing.
        """
        result = super().action_confirm()
        try:
            self._sa_dispatch_deliveries()
        except Exception as err:  # noqa: BLE001 - never block a confirmation
            _logger.exception("Delivery: dispatch after confirming %s "
                              "failed: %s", self.mapped('name'), err)
        return result

    def action_cancel(self):
        """Cancelling the order stops the delivery too.

        One override covers every route a cancel arrives by: a manager in
        Odoo, and the customer typing *cancel* in the WhatsApp group - which
        already ends at `order.action_cancel()` in
        `sa_group_request._sa_cancel_deal`. Without this the order would be
        cancelled while a rider still had the parcel and a job on their phone.
        """
        for order in self:
            jobs = order.picking_ids.filtered(
                lambda p: p.sa_delivery_state in p._SA_CANCELLABLE)
            if jobs:
                jobs.sa_action_cancel(
                    reason=self.env.context.get('sa_cancel_reason') or '')
        return super().action_cancel()

    def _sa_dispatch_deliveries(self):
        Shop = self.env['sa.delivery.shop'].sudo()
        Rider = self.env['sa.delivery.partner'].sudo()
        flow_end = self.env['sa.delivery.settings'].sudo().get_settings().flow_end
        if flow_end and flow_end != 'delivery':
            _logger.info("Delivery: the flow ends at %s - no job for %s",
                         flow_end, self.mapped('name'))
            return True

        for order in self:
            pickings = order.picking_ids.filtered(
                lambda p: p.picking_type_id.code == 'outgoing'
                and p.state not in ('done', 'cancel')
                and p.sa_delivery_state in ('none', False))
            if not pickings:
                continue

            settings = self.env['sa.delivery.settings'].sudo().get_settings()

            for picking in pickings:
                shop = Shop._sa_pick_for(
                    picking.partner_id or order.partner_shipping_id,
                    warehouse=picking.picking_type_id.warehouse_id)
                # Call a Rider (3 Oct): the counter calls one after Packed, unless
                # the setting calls one automatically.
                rider = Rider._sa_pick_for(shop) if settings.auto_call_rider_on_packed else Rider
                # Quick when the shelf can cover it, express when a supplier
                # has to. Decided here, once, so the customer is told one date
                # and the rider sees the same one.
                kind, promised = settings._promise_for(picking)
                picking.write({
                    'sa_shop_id': shop.id if shop else False,
                    'sa_delivery_partner_id': rider.id if rider else False,
                    'sa_delivery_state': 'to_assign',
                    'sa_currency_id': order.currency_id.id,
                    'sa_cod_amount': order._sa_amount_to_collect(),
                    'sa_delivery_kind': kind,
                    'sa_promised_on': promised,
                })
                picking._sa_ensure_identity()
                if rider:
                    picking.sa_action_offer()
                else:
                    _logger.info("Delivery: %s has no rider for shop %s - "
                                 "left to dispatch by hand", picking.name,
                                 shop.name if shop else '(none)')
        return True

    def _sa_refresh_cod(self):
        """The rider's amount to collect follows a payment made later."""
        jobs = self.mapped('picking_ids').filtered(
            lambda p: p.sa_delivery_state not in ('none', False))
        if jobs:
            jobs.sudo().sa_refresh_cod()
            # A tracking link held until payment goes out now (22 Nov 2026).
            jobs.sudo()._sa_track_send_held()
        return True

    def _sa_amount_to_collect(self):
        """What the rider has to bring back, if anything.

        Anything already settled - an online payment, a credit note, a
        deposit - reduces it. An order with no invoice yet is treated as
        unpaid, which is the safe direction: a rider told to collect nothing
        on an unpaid order loses the money.
        """
        self.ensure_one()
        invoices = self.invoice_ids.filtered(lambda m: m.state == 'posted')
        if invoices:
            # "in payment" = the money is in, only the bank line is pending
            return sum(0.0 if m.payment_state in ('paid', 'in_payment')
                       else m.amount_residual for m in invoices)
        if self.amount_total and self.transaction_ids.filtered(
                lambda t: t.state == 'done'):
            return 0.0
        return self.amount_total


class PaymentTransactionCod(models.Model):
    _inherit = 'payment.transaction'

    def _post_process(self):
        res = super()._post_process()
        try:
            self.filtered(lambda t: t.state == 'done').mapped(
                'sale_order_ids')._sa_refresh_cod()
        except Exception as err:  # noqa: BLE001 - bookkeeping, never block
            _logger.warning("Delivery: COD refresh after payment failed: %s", err)
        return res


class AccountMoveCod(models.Model):
    _inherit = 'account.move'

    def _compute_payment_state(self):
        res = super()._compute_payment_state()
        try:
            settled = self.filtered(lambda m: m.move_type == 'out_invoice'
                                    and m.payment_state in ('paid', 'in_payment', 'partial'))
            if settled:
                settled.mapped('line_ids.sale_line_ids.order_id')._sa_refresh_cod()
        except Exception as err:  # noqa: BLE001 - bookkeeping, never block
            _logger.warning("Delivery: COD refresh after a payment failed: %s", err)
        return res
