# -*- coding: utf-8 -*-
"""Which shop a delivery leaves from."""

import logging
import math
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaDeliveryShop(models.Model):
    _name = 'sa.delivery.shop'
    _description = 'Delivery Shop'
    _order = 'sequence, id'

    name = fields.Char('Shop', required=True)
    sequence = fields.Integer(
        default=10,
        help="Order the shops are considered in. The first one is also the "
             "fallback when an address matches no service area and nothing "
             "can be measured.")
    active = fields.Boolean(default=True)

    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Warehouse', required=True,
        help="Stock leaves from here. A delivery is matched to a shop by its "
             "picking's warehouse when one is set.")
    partner_id = fields.Many2one(
        'res.partner', string='Address',
        help="Where the rider collects from. Leave empty to use the "
             "warehouse's own address.")

    phone = fields.Char(
        'Shop WhatsApp Number',
        help="Where the pickup code is sent. Staff read it out to the rider "
             "when they hand the parcel over, which is what makes the code "
             "proof of collection rather than proof the rider owns a phone.")

    service_areas = fields.Char(
        'Service Areas',
        help="Comma separated areas this shop covers - muscat, ruwi, qurum, "
             "azaiba. Matched as whole words against the customer's address, "
             "longest area name first, so \"al khuwair\" beats \"khuwair\".\n\n"
             "Leave empty and the shop is only ever chosen by distance or as "
             "the fallback.")

    delivery_partner_ids = fields.Many2many(
        'sa.delivery.partner', 'sa_delivery_partner_shop_rel',
        'shop_id', 'partner_id', string='Riders and Couriers')
    delivery_count = fields.Integer('Deliveries', compute='_compute_counts')
    open_count = fields.Integer('Open', compute='_compute_counts')

    # ---- Map pin (Call a Rider, 3 Oct 2026) ----
    latitude = fields.Float('Latitude', digits=(10, 7),
                            help="The shop's map pin. Riders are ranked by their distance "
                                 "from here. Google Maps: right-click the shop, copy the two "
                                 "numbers. Empty = the address contact's own geo position.")
    longitude = fields.Float('Longitude', digits=(10, 7))
    address_short = fields.Char('Pin (area)', readonly=True)

    def _sa_position(self):
        """(lat, lng) of the shop, or (None, None)."""
        self.ensure_one()
        if self.latitude and self.longitude:
            return self.latitude, self.longitude
        p = self._sa_address()
        if p and p.partner_latitude and p.partner_longitude:
            return p.partner_latitude, p.partner_longitude
        return None, None

    def action_sa_locate(self):
        """Button: find the pin from the address text."""
        Geo = self.env['sa.geocode.cache'].sudo()
        for shop in self:
            p = shop._sa_address()
            text = ', '.join(filter(None, [p.street, p.street2, p.city, p.state_id.name,
                                           p.country_id.name])) if p else ''
            lat, lng = Geo.sa_forward(text or shop.name)
            if not lat:
                raise UserError(_("Could not find \"%s\" on the map. Type the latitude and "
                                  "longitude by hand (Google Maps: right-click the shop and "
                                  "copy the two numbers).", text or shop.name))
            short, _full = Geo.sa_reverse(lat, lng)
            shop.write({'latitude': lat, 'longitude': lng, 'address_short': short})
        return True

    def _compute_counts(self):
        Picking = self.env['stock.picking']
        for shop in self:
            shop.delivery_count = Picking.search_count(
                [('sa_shop_id', '=', shop.id)])
            shop.open_count = Picking.search_count([
                ('sa_shop_id', '=', shop.id),
                ('sa_delivery_state', 'in',
                 ('to_assign', 'offered', 'accepted', 'picked')),
            ])

    # ------------------------------------------------------------------
    # Choosing one
    # ------------------------------------------------------------------
    def _sa_areas(self):
        """This shop's areas, lowercase, longest first."""
        self.ensure_one()
        areas = [a.strip().lower()
                 for a in (self.service_areas or '').split(',')]
        return sorted([a for a in areas if a], key=len, reverse=True)

    def _sa_address(self):
        """The partner carrying this shop's address."""
        self.ensure_one()
        return self.partner_id or self.warehouse_id.partner_id

    @api.model
    def _sa_pick_for(self, partner, warehouse=None):
        """The shop a delivery to `partner` should leave from.

        Three steps, and the order matters. A named service area is the shop
        the business has *told* us covers that address, so it wins outright.
        Distance is a measurement and can only be as good as the geocoding -
        informal Gulf addresses often resolve no further than the city centre.
        The fallback exists so a delivery is never left without a shop.
        """
        shops = self.sudo().search([])
        if not shops:
            return self.browse()
        if len(shops) == 1:
            return shops

        # 1. an area this shop says it covers
        haystack = ' %s ' % ' '.join(
            w for w in re.split(r'[^0-9A-Za-z]+', ' '.join(filter(None, [
                partner.street or '', partner.street2 or '',
                partner.city or '',
            ])).lower()) if w)
        best, best_len = self.browse(), 0
        for shop in shops:
            for area in shop._sa_areas():
                if ' %s ' % area in haystack and len(area) > best_len:
                    best, best_len = shop, len(area)
        if best:
            return best

        # 2. straight-line distance, when both ends have been geocoded
        near = self._sa_nearest(partner, shops)
        if near:
            return near

        # 3. the warehouse the picking already came from, else the first shop
        if warehouse:
            owned = shops.filtered(lambda s: s.warehouse_id == warehouse)
            if owned:
                return owned[0]
        return shops[0]

    @api.model
    def _sa_nearest(self, partner, shops):
        """Closest shop by great-circle distance, or nothing."""
        lat, lon = partner.partner_latitude, partner.partner_longitude
        if not lat or not lon:
            return self.browse()
        best, best_km = self.browse(), None
        for shop in shops:
            here = shop._sa_address()
            if not here or not here.partner_latitude or not here.partner_longitude:
                continue
            km = self._sa_km(lat, lon, here.partner_latitude,
                             here.partner_longitude)
            if best_km is None or km < best_km:
                best, best_km = shop, km
        if best:
            _logger.info("Delivery: %s is the nearest shop to %s (%.1f km)",
                         best.name, partner.display_name, best_km)
        return best

    @api.model
    def _sa_km(self, lat1, lon1, lat2, lon2):
        """Great-circle distance in kilometres."""
        radius = 6371.0
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = (math.sin(d_lat / 2) ** 2
             + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
             * math.sin(d_lon / 2) ** 2)
        return radius * 2 * math.asin(math.sqrt(a))

    def action_open_deliveries(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deliveries - %s', self.name),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('sa_shop_id', '=', self.id)],
            'context': {'search_default_group_delivery_state': 1},
        }
