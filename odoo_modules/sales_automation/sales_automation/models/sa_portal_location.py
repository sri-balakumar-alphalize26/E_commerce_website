# -*- coding: utf-8 -*-
"""The map location on the order page (owner, 23 Nov 2026): instead of asking for
it in the group. "Location not added" with a mark until there is one; the phone
gives it with one tap. For WhatsApp group orders, until a rider has the parcel."""
import logging
import math

from odoo import _, models

_logger = logging.getLogger(__name__)

# the parcel has left with a rider, or the job is over
CLOSED = ('picked', 'dispatched', 'out_for_delivery', 'delivered', 'failed', 'returning', 'returned')


class SaleOrderPortalLocation(models.Model):
    _inherit = 'sale.order'

    def _sa_loc_open(self):
        """Can the customer still add or move the location of this order?"""
        self.ensure_one()
        o = self.sudo()
        if o.state not in ('draft', 'sent', 'sale'):
            return False
        req = o._sa_group_enquiry()
        if not (req and req.group_id and req.order_id == o and req.sa_sign_link_sent_on):
            return False
        if o.state == 'sale' and o._sa_portal_status().get('delivered'):
            return False
        return not o.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel' and (
                getattr(p, 'sa_delivery_state', False) in CLOSED
                or (p.state == 'done' and getattr(p, 'sa_delivery_state', 'none') in ('none', False))))

    def _sa_loc_partner(self):
        self.ensure_one()
        o = self.sudo()
        return o.partner_shipping_id or o.partner_id

    def _sa_portal_location(self):
        """What the card draws: {'open', 'has', 'edit': address id for the map}."""
        self.ensure_one()
        o = self.sudo()
        if not o._sa_loc_open():
            return {'open': False, 'has': False, 'edit': False}
        addr = o._sa_loc_partner()
        return {'open': True, 'has': bool(addr.partner_latitude or addr.partner_longitude),
                'edit': addr.id if o._sa_addr_open() and addr in o._sa_portal_book() else False}

    def _sa_portal_set_location(self, lat, lng):
        """(error text, amount changed) - the same saving as a location sent in
        the group (`_sa_take_location`): this order's address and its jobs."""
        self.ensure_one()
        o = self.sudo()
        if not o._sa_loc_open():
            return _("The location of this order can no longer be changed."), False
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            return _("That location could not be read. Please try again."), False
        if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180) \
                or (abs(lat) < 1e-6 and abs(lng) < 1e-6):
            return _("That location could not be read. Please try again."), False
        before = o.amount_total
        try:
            with self.env.cr.savepoint():
                jobs = o.picking_ids.filtered(
                    lambda p: getattr(p, 'sa_delivery_state', 'none') not in (('none', False, 'cancelled') + CLOSED))
                if not jobs.filtered(lambda p: getattr(p, 'sa_drop_pending', False)):
                    o._sa_loc_partner().write({'partner_latitude': lat, 'partner_longitude': lng})
                if jobs and hasattr(jobs, 'sa_set_customer_pin'):
                    jobs.sa_set_customer_pin(lat, lng, source='whatsapp')
                if o._sa_addr_open():
                    o._sa_addr_redecide()
                o.message_post(body=_("Delivery location set by the customer on the order page "
                                      "(%(lat).5f, %(lng).5f).", lat=lat, lng=lng))
        except Exception:  # noqa: BLE001 - the order keeps what it had
            _logger.exception("Order page: location of %s not saved", o.name)
            return _("Could not save the location. Please try again."), False
        return '', abs(o.amount_total - before) > 0.0001
