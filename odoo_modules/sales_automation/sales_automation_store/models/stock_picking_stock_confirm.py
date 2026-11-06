# -*- coding: utf-8 -*-
"""When a group order's job finally reserves its goods, ask the customer in
the group to confirm and pay. Fires from "Goods arrived" (which reserves) and
from Check Availability alike, once per job, only for orders never paid."""
import logging
from datetime import timedelta

from odoo import fields, models

_logger = logging.getLogger(__name__)


class StockPickingStockConfirm(models.Model):
    _inherit = 'stock.picking'

    sa_stock_confirm_asked_on = fields.Datetime('Customer Asked to Confirm On', copy=False)

    def action_assign(self):
        res = super().action_assign()
        try:
            self._sa_maybe_ask_stock_confirm()
        except Exception as err:  # noqa: BLE001 - reservation must never fail for a message
            _logger.warning("Stock confirm: could not ask the customer: %s", err)
        return res

    def _sa_maybe_ask_stock_confirm(self):
        now = fields.Datetime.now()
        for job in self:
            if job.state != 'assigned' or job.sa_stock_confirm_asked_on:
                continue
            if job.sa_delivery_state not in ('awaiting_shop', 'preparing'):
                continue
            order = job.sale_id
            req = order._sa_group_enquiry() if order else False
            if not req or not req.group_id:
                continue
            # Only goods that were waited for: bought in, or a job that sat
            # unreserved for a while. A fresh in-stock order keeps its flow.
            waited = bool(job.sa_supply_arrived_on) or (
                job.create_date and (now - job.create_date) > timedelta(minutes=5))
            if not waited:
                continue
            # A signed order was committed to already: the shop's Accept sends
            # the pay link (stock_picking_oos_gate.py); no second confirm.
            if getattr(order, 'signature', False):
                continue
            paid = order.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
                and m.payment_state in ('paid', 'in_payment'))
            if paid:
                continue
            if req.sudo()._sa_ask_stock_confirm(job):
                job.write({'sa_stock_confirm_asked_on': now})
        return True
