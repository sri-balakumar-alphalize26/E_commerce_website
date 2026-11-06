# -*- coding: utf-8 -*-
"""Route a paid order to the shop instead of straight to a rider."""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Read straight off the delivery, so the ordinary Sales list can show
    # where an order actually is without anyone opening it.
    sa_delivery_state = fields.Selection(
        related='picking_ids.sa_delivery_state', string='Delivery Stage',
        readonly=True)
    sa_shop_id = fields.Many2one(
        related='picking_ids.sa_shop_id', string='Shop', readonly=True)
    sa_delivery_partner_id = fields.Many2one(
        related='picking_ids.sa_delivery_partner_id', string='Rider',
        readonly=True)
    sa_ref_code = fields.Char(
        related='picking_ids.sa_ref_code', string='Job', readonly=True)

    def _sa_dispatch_deliveries(self):
        """Hold the job at the shop rather than paging a rider immediately.

        The parent offers the job the moment the order is confirmed, which is
        how a rider could arrive while the goods were still on the shelf. The
        shop now takes it first; the rider is called from `sa_shop_ready`.

        Switched off per shop by unticking `Shop Confirms Orders`, and then
        the parent's behaviour is unchanged - a business with one person doing
        both jobs should not have to press two extra buttons.
        """
        result = super()._sa_dispatch_deliveries()

        Settings = self.env['sa.delivery.settings'].sudo()
        if not Settings.get_settings().shop_confirms:
            return result

        held = self.env['stock.picking']
        for order in self:
            for picking in order.picking_ids:
                # Only a job that was just handed to a rider, and only before
                # the rider has done anything with it.
                if picking.sa_delivery_state not in ('offered', 'to_assign'):
                    continue
                if picking.sa_accepted_on:
                    continue
                picking.write({'sa_delivery_state': 'awaiting_shop'})
                held |= picking

        if held:
            held._sa_store_notify()
            _logger.info("Store: %s order(s) waiting for the shop",
                         len(held))
        return result
