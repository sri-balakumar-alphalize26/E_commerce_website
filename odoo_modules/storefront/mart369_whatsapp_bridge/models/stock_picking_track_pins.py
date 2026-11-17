"""Pins the delivery stack cannot see on its own, for the customer's map.

The WhatsApp tracking page and the office's live map draw the shop and the
customer from the delivery job. A storefront shop often has its pin on the
branch (`stock.warehouse.mart369_lat/lng`, Delivery settings) rather than on a
delivery shop or an address contact, and the order's own delivery address may
carry the pin the customer dropped at checkout while the job points at the
customer's main contact. Both are offered here, before the delivery stack falls
back to looking the address up.

Display only, like the hooks they extend: the route, the arrival time, the
rider's pay and who gets called keep using the job's real positions.
"""

from odoo import api, models

from odoo.addons.mart369_cart.models.branch import has_pin


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _mart369_job_branches(self):
        """The branches this job leaves from, most specific first."""
        self.ensure_one()
        job = self.sudo()
        out = self.env['stock.warehouse']
        for warehouse in (job.sa_shop_id.warehouse_id if job.sa_shop_id else None,
                          job.picking_type_id.warehouse_id,
                          job.sale_id.warehouse_id if job.sale_id else None):
            if warehouse and warehouse not in out:
                out |= warehouse
        return out

    def _sa_track_shop_fallback(self):
        self.ensure_one()
        for branch in self._mart369_job_branches():
            if 'mart369_lat' in branch._fields and has_pin(branch.mart369_lat, branch.mart369_lng):
                return branch.mart369_lat, branch.mart369_lng, False
        return super()._sa_track_shop_fallback()

    @api.model
    def _sa_fleet_extra_shops(self, shops, shop_id=None):
        """The office's live map also shows the storefront branches that have
        a pin but no delivery shop of their own. A shop filter keeps only that
        shop's own branch, which a delivery shop already draws."""
        out = super()._sa_fleet_extra_shops(shops, shop_id)
        if shop_id:
            return out
        Shop = self.env['sa.delivery.shop'].sudo()
        covered = set(Shop.search([]).mapped('warehouse_id').ids)
        for branch in self.env['stock.warehouse'].sudo().search([]):
            if branch.id in covered or 'mart369_lat' not in branch._fields:
                continue
            if not has_pin(branch.mart369_lat, branch.mart369_lng):
                continue
            out.append({'id': -branch.id, 'name': branch.name, 'latitude': branch.mart369_lat,
                        'longitude': branch.mart369_lng, 'approximate': False, 'extra': True})
        return out

    def _sa_track_drop_fallback(self):
        self.ensure_one()
        job = self.sudo()
        address = job.sale_id.partner_shipping_id if job.sale_id else None
        if address and address != job.partner_id and has_pin(address.partner_latitude, address.partner_longitude):
            return address.partner_latitude, address.partner_longitude, False
        return super()._sa_track_drop_fallback()
