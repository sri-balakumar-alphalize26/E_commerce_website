# -*- coding: utf-8 -*-
"""How far a shop's Quick delivery reaches."""

from odoo import api, fields, models


class SaDeliveryShop(models.Model):
    _inherit = 'sa.delivery.shop'

    qe_quick = fields.Boolean(
        'Quick delivery',
        help="This shop delivers Quick to customers within its reach.")
    qe_quick_km = fields.Float(
        'Quick reach (km)',
        help="How far Quick reaches, in a straight line from the shop's map "
             "pin to the customer's. 0 = nowhere.")
    qe_ready = fields.Boolean('Quick ready', compute='_compute_qe_ready')

    @api.depends('qe_quick', 'qe_quick_km', 'latitude', 'longitude', 'partner_id',
                 'warehouse_id')
    def _compute_qe_ready(self):
        for shop in self:
            shop.qe_ready = shop._qe_ready()

    def _qe_ready(self):
        """Quick on, a reach above 0, and a pin to measure from."""
        self.ensure_one()
        lat, lng = self._sa_position()
        return bool(self.qe_quick and self.qe_quick_km > 0 and lat and lng)

    def _qe_in_reach(self, lat, lng):
        """[(shop, km)] of these shops whose reach covers the pin, nearest first."""
        found = []
        for shop in self:
            here = shop._sa_position()
            km = self._sa_km(lat, lng, here[0], here[1])
            if km <= shop.qe_quick_km:
                found.append((shop, km))
        return sorted(found, key=lambda pair: pair[1])

    def _qe_has_stock(self, product, qty):
        """Can this shop give `qty` of `product` away today."""
        self.ensure_one()
        if not product.is_storable:
            return True
        warehouse = self.warehouse_id
        free = product.sudo().with_company(warehouse.company_id).with_context(
            warehouse_id=warehouse.id).free_qty
        return free >= qty

    @api.model
    def _sa_pick_for(self, partner, warehouse=None):
        """A Quick order leaves from the shop that made it Quick."""
        forced = self.env.context.get('qe_force_shop')
        if forced:
            shop = self.sudo().browse(forced).exists()
            if shop:
                return shop
        return super()._sa_pick_for(partner, warehouse=warehouse)
