# -*- coding: utf-8 -*-
"""Where the rider was, and when."""

import math

from odoo import api, fields, models

# Below this, a "new" position is the phone's GPS wobbling on the spot. Storing
# it would fill the table and draw a scribble on the customer's map.
_MIN_MOVE_M = 25.0


class SaDeliveryPing(models.Model):
    _name = 'sa.delivery.ping'
    _description = 'Rider Position'
    _order = 'id desc'

    picking_id = fields.Many2one(
        'stock.picking', string='Delivery', required=True,
        ondelete='cascade', index=True)
    latitude = fields.Float('Latitude', digits=(16, 6))
    longitude = fields.Float('Longitude', digits=(16, 6))
    accuracy = fields.Float('Accuracy (m)')

    @api.model
    def _sa_record(self, picking, lat, lng, accuracy=0.0):
        """Store a fix, unless the rider has not really moved.

        The page reports every twenty seconds or so for the length of a
        delivery; without this a half-hour job leaves a hundred rows, most of
        them the same doorstep seen through GPS noise.
        """
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            return self.browse()
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return self.browse()

        last = self.sudo().search(
            [('picking_id', '=', picking.id)], order='id desc', limit=1)
        if last and self._sa_metres(last.latitude, last.longitude,
                                    lat, lng) < _MIN_MOVE_M:
            # Still worth saying the rider is alive, so the customer's page
            # does not show a stale timestamp.
            picking.sudo().write({'sa_rider_fix_on': fields.Datetime.now()})
            return last

        picking.sudo().write({
            'sa_rider_lat': lat,
            'sa_rider_lng': lng,
            'sa_rider_fix_on': fields.Datetime.now(),
        })
        return self.sudo().create({
            'picking_id': picking.id, 'latitude': lat,
            'longitude': lng, 'accuracy': accuracy or 0.0,
        })

    @api.model
    def _sa_metres(self, lat1, lon1, lat2, lon2):
        if not lat1 or not lon1:
            return 1e9
        radius = 6371000.0
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = (math.sin(d_lat / 2) ** 2
             + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
             * math.sin(d_lon / 2) ** 2)
        return radius * 2 * math.asin(math.sqrt(a))
