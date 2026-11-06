# -*- coding: utf-8 -*-
"""How soon we promise to deliver, and on what evidence."""

import json
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SaDeliverySettings(models.Model):
    _name = 'sa.delivery.settings'
    _description = 'Delivery Settings'

    name = fields.Char(default='Delivery Settings', readonly=True)
    ops_api_key = fields.Char(
        'Order flow API key', copy=False,
        help="Key for the full-flow API (/api/sa/*) used by the shop / admin "
             "app: send it in the X-SA-Key header, with X-Odoo-Database naming "
             "this database. Empty = the API accepts only logged-in 369ai users.")

    # ---- Calling a rider (3 Oct 2026) ----
    call_rider_mode = fields.Selection([
        ('ask', 'Ask each time - the counter presses Auto or ticks riders'),
        ('auto', 'Automatic - the nearest free rider (anyone on duty if nobody is near)'),
        ('auto_radius', 'Automatic - only riders within the search radius (km)'),
        ('manual', 'Manual - the counter ticks the riders in a list'),
    ], 'Call a Rider mode', default='ask', required=True,
        help="What the Call a Rider button does.\n"
             "Ask each time: a list opens with an Auto button and tick boxes.\n"
             "Automatic: no list - the nearest free rider is called at once; riders outside "
             "the radius or without a position are tried only when nobody inside is free.\n"
             "Automatic within the radius: as above, but never outside the radius (km) - if "
             "nobody inside is free the job waits for the counter.\n"
             "Manual: the list opens, the counter ticks one or several riders; they are called "
             "one at a time, nearest free first, and nobody else is called.")
    auto_call_rider_on_packed = fields.Boolean(
        'Call a rider automatically at Packed', default=False,
        help="On: the moment the counter presses Packed, the nearest free rider is "
             "called. Off (default): the job waits at Ready until somebody presses "
             "Call a Rider and either picks a rider or lets Auto choose.")
    dispatch_radius_km = fields.Float(
        'Search radius (km)', default=5.0,
        help="Free riders inside this distance from the shop are called first, "
             "nearest first. 0 = no limit. Riders outside the radius are only called "
             "when nobody inside is free.")
    position_max_age_minutes = fields.Integer(
        'A position counts for (minutes)', default=30,
        help="A rider whose last GPS fix is older than this is treated as 'position "
             "unknown' and ranks after everyone with a fresh fix.")
    offer_timeout_seconds = fields.Integer(
        'Rider must answer within (seconds)', default=90,
        help="No Accept within this time: the next candidate is called and this rider "
             "is not asked again for the same job.")
    max_offer_rounds = fields.Integer(
        'Riders tried before stopping', default=5,
        help="After this many unanswered offers the job waits for the counter.")
    geocode_provider = fields.Selection([
        ('nominatim', 'OpenStreetMap (Nominatim, free)'),
        ('google', 'Google Maps (key below)'),
    ], 'Address lookup', default='nominatim', required=True,
        help="Turns a rider's GPS position into 'Area, City' for the fleet view.")
    geocode_google_key = fields.Char('Google Maps API key')
    fcm_service_account_json = fields.Text(
        'Firebase service account (JSON)', groups='base.group_system',
        help="Firebase console > Project settings > Service accounts > Generate new "
             "private key. Paste the whole JSON. Empty = no push; the rider app still "
             "sees the offer on its next refresh and on WhatsApp.")
    fcm_project = fields.Char('Firebase project', compute='_compute_fcm_project')
    fcm_last_error = fields.Char('Last push error', readonly=True)

    @api.depends('fcm_service_account_json')
    def _compute_fcm_project(self):
        for s in self:
            try:
                acc = json.loads(s.fcm_service_account_json or '{}')
                s.fcm_project = acc.get('project_id') or ''
            except ValueError:
                s.fcm_project = _("(not valid JSON)")

    def action_ops_new_key(self):
        import secrets
        self.ensure_one()
        self.write({'ops_api_key': secrets.token_urlsafe(32)})
        return True
    flow_end = fields.Selection([
        ('order', 'Order confirmed - stop at the signed order (no payment link, no delivery)'),
        ('invoice', 'Invoice sent - the invoice is posted in the group, no payment link, no delivery'),
        ('paid', 'Payment received - pay link and paid invoice, no delivery job'),
        ('delivery', 'Delivered - the full flow: rider, pickup code, delivery code'),
    ], 'WhatsApp order flow ends at', default='delivery', required=True,
        help="Every WhatsApp order runs: order signed -> invoice -> payment -> "
             "delivery. Pick the last step this shop does by itself. Before "
             "'Delivered' no delivery job is raised: the delivery order stays "
             "a plain 369ai transfer that the shop validates by hand.")

    # ---- Quick: it is on the shelf ----
    quick_enabled = fields.Boolean(
        'Offer Quick Delivery', default=True,
        help="When every line of the order is in stock at the chosen shop, "
             "the delivery is promised within the hours below instead of the "
             "express lead time.")
    quick_hours = fields.Integer(
        'Quick Delivery Within (hours)', default=4,
        help="Promised time when the goods are already on the shelf. Four "
             "hours is a working half-day; set it to the time a rider "
             "realistically needs across your service area, not the best case.")

    # ---- Express: it has to be brought in ----
    express_days = fields.Integer(
        'Express Delivery Within (days)', default=3,
        help="Promised time when something has to be ordered in from a "
             "supplier first. This is what the customer is told, so it should "
             "include the supplier's own lead time, not just your dispatch.")

    otp_test_mode = fields.Boolean(
        'Return OTPs in the API (testing only)', default=False,
        help="Hands the pickup and delivery codes back in the API response so "
             "the flow can be driven from Postman while no WhatsApp session is "
             "connected.\n\n"
             "Leave this OFF anywhere real: with it on, anyone holding a "
             "rider's token can read the code that proves a customer received "
             "their parcel. Every use is written to the log.")

    promise_customer = fields.Boolean(
        'Tell the Customer the Date', default=True,
        help="Include the promised date in the WhatsApp message and on the "
             "tracking page. Turn it off if you would rather not commit to a "
             "date in writing.")

    cutoff_hour = fields.Integer(
        'Same-Day Cut-off (hour, 0-23)', default=16,
        help="An in-stock order confirmed after this hour is promised for the "
             "next day rather than today. 16 means anything after 4pm rolls "
             "over. Set 0 to promise the quick window whatever the time.")

    @api.model
    def get_settings(self):
        settings = self.search([], limit=1)
        if not settings:
            settings = self.create({})
        return settings

    # ------------------------------------------------------------------
    def _promise_for(self, picking):
        """(kind, promised datetime) for a delivery.

        `quick` when the shop can supply every line from what it holds now,
        `express` when anything has to come in first. Judged on the free
        quantity at the picking's own source location - the number the shop
        can actually give away today, not what the company owns somewhere.
        """
        self.ensure_one()
        now = fields.Datetime.now()
        kind = 'quick' if self.quick_enabled else 'express'

        if kind == 'quick':
            location = picking.location_id
            for move in picking.move_ids:
                product = move.product_id
                if not product.is_storable:
                    continue
                available = product.with_context(
                    location=location.id).free_qty
                if available < move.product_uom_qty:
                    kind = 'express'
                    break

        if kind == 'quick':
            promised = fields.Datetime.add(now, hours=max(1, self.quick_hours))
            # After the cut-off, "today" is not a promise anyone should make.
            if self.cutoff_hour and now.hour >= self.cutoff_hour:
                promised = fields.Datetime.add(promised, days=1)
        else:
            promised = fields.Datetime.add(now, days=max(1, self.express_days))
        return kind, promised

    def action_open(self):
        settings = self.get_settings()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delivery Settings'),
            'res_model': 'sa.delivery.settings',
            'res_id': settings.id,
            'view_mode': 'form',
            'target': 'current',
        }
