# -*- coding: utf-8 -*-
"""When a delivery can actually arrive."""

from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .qe_delivery_rule import MODE_CHOICES

# "Now" is the only slot that is not a window: it means the next rider out.
KIND_CHOICES = [
    ('now', 'Now'),
    ('window', 'Time window'),
    ('days', 'In a number of days'),
]


class SaQeDeliverySlot(models.Model):
    _name = 'sa.qe.delivery.slot'
    _description = 'Quick / Express Delivery Slot'
    _order = 'mode, sequence, id'

    sequence = fields.Integer(default=10)
    name = fields.Char('Slot', required=True)
    mode = fields.Selection(MODE_CHOICES, required=True, default='quick')
    kind = fields.Selection(KIND_CHOICES, required=True, default='window')
    from_hour = fields.Float('From')
    to_hour = fields.Float('To')
    order_before = fields.Float(
        'Order before', default=24.0,
        help="A same-day slot closes at this hour, shop time. 24 = never.")
    day_offset = fields.Integer(
        'Days from today',
        help="0 = today, 1 = tomorrow. For 'In a number of days' this is the "
             "number of days.")
    fee = fields.Float('Extra fee')
    capacity = fields.Integer(
        'Orders per day', help="0 = no limit.")
    active = fields.Boolean(default=True)
    qe_open = fields.Boolean('Open now', compute='_compute_qe_open')

    @api.constrains('from_hour', 'to_hour', 'order_before', 'day_offset',
                    'fee', 'capacity')
    def _check_values(self):
        for slot in self:
            hours = (slot.from_hour, slot.to_hour, slot.order_before)
            if any(h < 0 or h > 24 for h in hours):
                raise ValidationError(_("Hours run from 0 to 24."))
            if min(slot.day_offset, slot.fee, slot.capacity) < 0:
                raise ValidationError(_("Days, fee and capacity cannot be negative."))

    # ------------------------------------------------------------------
    @api.model
    def _qe_tz(self):
        """The shop's clock. A cut-off of 17:00 means 17:00 where the shop is."""
        name = (self.env.company.partner_id.tz or self.env.user.tz
                or self.env.context.get('tz') or 'UTC')
        try:
            return pytz.timezone(name)
        except pytz.UnknownTimeZoneError:
            return pytz.utc

    @api.model
    def _qe_now_local(self):
        return pytz.utc.localize(fields.Datetime.now()).astimezone(self._qe_tz())

    def _qe_day(self):
        """The calendar day, shop time, an order booked now would arrive."""
        self.ensure_one()
        offset = 0 if self.kind == 'now' else (self.day_offset or 0)
        return self._qe_now_local().date() + timedelta(days=offset)

    def _qe_due(self, day):
        """The UTC moment a booking for `day` is due, or False for 'Now'."""
        self.ensure_one()
        if self.kind == 'window' and self.to_hour and day:
            local = self._qe_tz().localize(
                datetime.combine(day, time.min) + timedelta(hours=self.to_hour))
            return local.astimezone(pytz.utc).replace(tzinfo=None)
        if self.kind == 'days':
            return fields.Datetime.now() + timedelta(days=max(1, self.day_offset))
        return False

    def _qe_is_full(self, exclude=None):
        self.ensure_one()
        if not self.capacity:
            return False
        domain = [('qe_slot_id', '=', self.id),
                  ('qe_slot_day', '=', self._qe_day()),
                  ('state', '!=', 'cancel')]
        if exclude:
            domain.append(('id', 'not in', exclude.ids))
        taken = self.env['sale.order'].sudo().search_count(domain)
        return taken >= self.capacity

    def _qe_is_open(self, exclude=None):
        self.ensure_one()
        if self.kind == 'now':
            return True
        now = self._qe_now_local()
        if (self.kind == 'window' and not self.day_offset
                and (now.hour + now.minute / 60.0) >= (self.order_before or 24.0)):
            return False
        return not self._qe_is_full(exclude=exclude)

    def _compute_qe_open(self):
        for slot in self:
            slot.qe_open = slot._qe_is_open()
