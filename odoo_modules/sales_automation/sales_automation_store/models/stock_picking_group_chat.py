# -*- coding: utf-8 -*-
"""A group order is talked to in the group. Every delivery update that used to
go to the customer's private number - packed, rider called, on the way,
delivered, cancelled, refunded - is posted in the group with the customer
mentioned. The one exception is the delivery completion code: posted in a
group it could be handed to the rider by anyone, so it stays private."""
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class SaleOrderGroupConfirmed(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """A paid group order got its signature (or was confirmed any other
        way): once the delivery job exists and carries its promised time -
        which happens inside super(), in the delivery module - post the
        invoice and the delivery date in the group."""
        res = super().action_confirm()
        for so in self:
            req = so._sa_group_enquiry() if hasattr(so, '_sa_group_enquiry') else False
            if req and req.group_id and req.sa_paid_on and not req.sa_paid_told_on:
                try:
                    req.sudo()._sa_group_confirmed(so)
                except Exception as err:  # noqa: BLE001 - the confirmation stands
                    _logger.error("Group confirmed message failed for %s: %s", so.name, err)
        return res


class StockPickingGroupChat(models.Model):
    _inherit = 'stock.picking'

    def _sa_tell_customer(self, body, unique=False):
        self.ensure_one()
        order = self.sale_id
        req = order._sa_group_enquiry() if order else False
        if unique or not req or not req.group_id or not req.group_id.group_jid:
            return super()._sa_tell_customer(body, unique=unique)
        if not self.env['sa.outbox.guard'].sudo().claim(
                'track|%s|%s' % (self.id, body[:40]), 900):
            return False
        try:
            req.sudo()._say(body)
            return True
        except Exception as err:  # noqa: BLE001 - the job matters more
            _logger.warning("Delivery: could not tell the group about job %s: %s",
                            self.sa_ref_code, err)
            return False
