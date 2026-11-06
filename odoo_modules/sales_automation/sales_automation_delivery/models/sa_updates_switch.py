# -*- coding: utf-8 -*-
"""STOP / START UPDATES from the customer's WhatsApp menu (7 Oct 2026).

A customer who tapped STOP UPDATES (`res.partner.sa_wa_updates_off`, kept in
sales_automation) does not get the delivery status messages - accepted,
collected, on the way, near you. What still goes: the delivery code (sent
with `unique=True`, never through here), the "coming back to the shop" news,
invoices and every answer to their own questions."""
from odoo import models


class StockPickingUpdatesSwitch(models.Model):
    _inherit = 'stock.picking'

    def _sa_notify_customer(self, state):
        self.ensure_one()
        customer = (self.sale_id.partner_id or self.partner_id.commercial_partner_id).sudo()
        if state != 'returning' and customer and getattr(customer, 'sa_wa_updates_off', False):
            return False
        return super()._sa_notify_customer(state)
