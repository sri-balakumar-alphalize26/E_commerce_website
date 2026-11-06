"""When a delivery can actually arrive.

Replaces `useSlots()` in components/home/Checkout.jsx, which builds its windows
from the browser clock:

    const quick = [{ key: "now", top: "Now", sub: "10-20 min", ... }];
    if (now.getHours() < 17) quick.push({ key: "eve", top: "Today", ... });

So "Now" is offered at three in the morning, no window has a capacity, and two
hundred customers can pick the same one. Here a slot is a record with an
opening hour, a closing hour and a number of orders it can take.

The shape handed back is exactly what the checkout draws - key, top, sub,
label, and a fee on Express - so the step needs no change.
"""

from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

MODE_CHOICES = [
    ('quick', 'Quick'),
    ('all', 'Express'),
]

# "Now" is the only slot that is not a window: it means the next rider out.
KIND_CHOICES = [
    ('now', 'Now'),
    ('window', 'Time window'),
    ('days', 'In a number of days'),
]


class Mart369DeliverySlot(models.Model):
    _name = 'mart369.delivery.slot'
    _description = '369 Mart Delivery Slot'
    _order = 'mode, sequence, id'
    _rec_name = 'top'

    sequence = fields.Integer(default=10)
    mode = fields.Selection(MODE_CHOICES, string='Storefront', required=True, default='quick')
    kind = fields.Selection(KIND_CHOICES, string='Kind', required=True, default='window')
    key = fields.Char(
        string='Key', required=True,
        help="What the app calls this slot in its own state, e.g. now, eve, "
             "tm, std, pri. Keep it stable.")
    top = fields.Char(
        string='Heading', required=True, default='Today',
        help="The bold line on the slot chip, e.g. Today, Tomorrow, Priority.")
    sub = fields.Char(
        string='Detail', help="The small line, e.g. 6 - 8 PM. Left empty for "
                              "a day-based slot, which fills in the date.")

    label = fields.Char(
        string='Confirmation line',
        help="What the order says afterwards, e.g. Arriving in 10-20 mins. "
             "Left empty it is built from the heading and the window.")

    from_hour = fields.Float(
        string='From', default=18.0,
        help="Window slots only. 18.5 is 6:30 PM.")
    to_hour = fields.Float(
        string='To', default=20.0)
    day_offset = fields.Integer(
        string='Days ahead', default=0,
        help="0 is today, 1 tomorrow. For an Express slot this is how many "
             "days the delivery takes.")
    order_before = fields.Float(
        string='Order before', default=24.0,
        help="Hide this slot once the time of day passes this. 17.0 hides a "
             "same-day evening slot after 5 PM. 24 never hides it.")

    fee = fields.Float(
        string='Extra fee', default=0.0,
        help="Added to the bill when this slot is chosen, e.g. 49 for "
             "Priority. Quick slots are normally free.")
    capacity = fields.Integer(
        string='Orders per slot', default=0,
        help="How many orders this window can take. 0 means no limit. The app "
             "stops offering a slot once it is full.")
    active = fields.Boolean(default=True)

    _key_mode_uniq = models.Constraint(
        'unique (mode, key)',
        'That slot key is already used in this storefront.',
    )

    @api.constrains('from_hour', 'to_hour', 'order_before')
    def _check_hours(self):
        for slot in self:
            for value in (slot.from_hour, slot.to_hour, slot.order_before):
                if not 0.0 <= value <= 24.0:
                    raise ValidationError(self.env._(
                        'An hour must be between 0 and 24.'))

    # ------------------------------------------------------------ display

    @api.model
    def _mart369_clock(self, value):
        """18.5 -> '6:30 PM', 20.0 -> '8 PM' - how the app writes a time."""
        hour = int(value) % 24
        minute = int(round((value - int(value)) * 60))
        suffix = 'AM' if hour < 12 else 'PM'
        shown = hour % 12 or 12
        return '%d:%02d %s' % (shown, minute, suffix) if minute else '%d %s' % (shown, suffix)

    def _mart369_day_label(self, when):
        """'Thu, 18 Sep' - the format the checkout already prints.

        Built by hand rather than with strftime('%a, %-d %b'): the no-padding
        flag is %-d on Linux and %#d on Windows, and this runs on both.
        """
        if not hasattr(when, 'strftime'):
            return ''
        return '%s, %d %s' % (when.strftime('%a'), when.day, when.strftime('%b'))

    def _mart369_is_open(self, now):
        """Would the app still offer this slot at this moment?"""
        self.ensure_one()
        if self.kind == 'now':
            return True
        if self.day_offset == 0 and (now.hour + now.minute / 60.0) >= (self.order_before or 24.0):
            return False
        return not self._mart369_is_full(now)

    def _mart369_is_full(self, now):
        """Capacity is per slot per day."""
        self.ensure_one()
        if not self.capacity:
            return False
        if 'sale.order' not in self.env or 'mart369_slot_key' not in self.env['sale.order']._fields:
            # mart369_order is not installed yet, so nothing has booked a slot.
            return False
        day = (fields.Date.context_today(self)
               + timedelta(days=self.day_offset or 0))
        taken = self.env['sale.order'].sudo().search_count([
            ('mart369_slot_key', '=', self.key),
            ('mart369_slot_day', '=', day),
        ])
        return taken >= self.capacity

    def _mart369_serialize(self, now):
        """One slot chip, in the shape useSlots() produced."""
        self.ensure_one()
        vals = {'key': self.key or '', 'top': self.top or ''}
        target = fields.Datetime.context_timestamp(self, now).date() + timedelta(
            days=self.day_offset or 0)

        if self.kind == 'now':
            vals['sub'] = self.sub or ''
            vals['label'] = self.env._('Arriving in %s', self.sub or '')
        elif self.kind == 'days':
            day = self._mart369_day_label(target)
            vals['sub'] = self.env._('By %s', day)
            vals['label'] = self.env._('Arrives by %s', day)
        else:
            # The operator's own wording wins, because the app prints the
            # detail line inside the confirmation: "Today, 6 - 8 PM", not
            # "Today, 6 PM - 8 PM".
            window = self.sub or '%s - %s' % (self._mart369_clock(self.from_hour),
                                              self._mart369_clock(self.to_hour))
            vals['sub'] = window
            if self.day_offset == 0:
                vals['label'] = self.env._('Today, %s', window)
            else:
                vals['label'] = '%s, %s' % (self._mart369_day_label(target), window)

        if self.label:
            # An operator's own wording always wins over the derived line.
            vals['label'] = self.label

        if self.mode == 'all':
            # Express chips carry a fee, even when it is zero: the checkout
            # reads slot.fee to add the priority charge.
            vals['fee'] = round(self.fee or 0.0, 2)
        elif self.fee:
            vals['fee'] = round(self.fee, 2)
        return vals

    @api.model
    def _mart369_slots(self):
        """{'quick': [...], 'all': [...]} - what the checkout asks for."""
        now = fields.Datetime.now()
        out = {'quick': [], 'all': []}
        for slot in self.sudo().search([]):
            if slot.mode in out and slot._mart369_is_open(now):
                out[slot.mode].append(slot._mart369_serialize(now))
        return out

    # -------------------------------------------------------- the console

    def _mart369_admin_row(self):
        """One slot as the admin console draws it.

        The hours go out as the numbers they are stored as, not as '6 PM'.
        The screen prints the time beside the box, but what it edits is the
        number, so that the thing typed and the thing Odoo constrains to 0-24
        are the same thing. A serializer that handed over '6 PM' would make
        the screen parse English back into a float to save it.
        """
        self.ensure_one()
        return {
            'id': self.id,
            'sequence': self.sequence,
            'mode': self.mode,
            'modeLabel': dict(MODE_CHOICES).get(self.mode, self.mode or ''),
            'kind': self.kind,
            'kindLabel': dict(KIND_CHOICES).get(self.kind, self.kind or ''),
            'key': self.key or '',
            'top': self.top or '',
            'sub': self.sub or '',
            'label': self.label or '',
            'fromHour': round(self.from_hour or 0.0, 2),
            'toHour': round(self.to_hour or 0.0, 2),
            'dayOffset': self.day_offset or 0,
            'orderBefore': round(self.order_before or 0.0, 2),
            'fee': round(self.fee or 0.0, 2),
            'capacity': self.capacity or 0,
            'active': self.active,
        }
