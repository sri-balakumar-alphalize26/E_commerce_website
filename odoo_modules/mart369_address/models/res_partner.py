"""A 369 Mart delivery address.

No new model: an address is an ordinary ``res.partner`` sitting under the
customer with ``type='delivery'``, which is the shape sale orders, delivery
and invoicing already understand. Three small fields are added for what the
app shows and Odoo has no equivalent of.

The app sends and receives ``city`` as one string ("Dindigul 624003") because
that is how it displays it; Odoo keeps ``city`` and ``zip`` apart so the data
stays useful to delivery and invoicing. The joining and splitting happens here.

One Odoo rule shapes all of this: **a partner may have only one child of type
'delivery'**. Creating a second silently demotes the first to 'other'. So every
369 Mart address is stored as 'other', and the customer's chosen one is marked
'delivery' - which lets Odoo's own address_get('delivery') keep working, and
means Odoo demotes the previous choice for us.
"""

import re

from odoo import _, api, fields, models

# Postcodes run from three digits (Oman: 'Muscat 112') to ten.
_PIN = re.compile(r'\b(\d{3,10})\s*$')

ICONS = {'home': 'home', 'work': 'brief'}

# Both count as a 369 Mart address; only the chosen one is 'delivery'.
ADDRESS_TYPES = ('delivery', 'other')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    mart369_label = fields.Char(
        string='Address type', default='Home',
        help="What the customer calls this address - Home, Work, Parents, "
             "anything. Shown as a chip in the app.")
    mart369_alt_phone = fields.Char(
        string='Alternate phone',
        help="A second number to try if the first does not answer. Optional.")
    mart369_default = fields.Boolean(
        string='Default address',
        help="The address the app selects for this customer. Exactly one "
             "address can be the default.")
    mart369_gap_label = fields.Char(
        string='Missing', compute='_compute_mart369_gap_label',
        help="What this address still needs before a rider can be sent to it. "
             "Empty when nothing is missing.")

    # -------------------------------------------------------------- helpers

    def _mart369_icon(self):
        self.ensure_one()
        return ICONS.get((self.mart369_label or '').strip().lower(), 'pin')

    def _mart369_city_line(self):
        """'Dindigul 624003' - city and pincode as the app shows them."""
        self.ensure_one()
        return ' '.join(p for p in (self.city, self.zip) if p)

    @api.model
    def _mart369_split_city(self, value):
        """The reverse: take what the app sent and separate the pincode."""
        value = (value or '').strip()
        if not value:
            return '', ''
        found = _PIN.search(value)
        if not found:
            return value, ''
        return value[:found.start()].strip().rstrip(',').strip(), found.group(1)

    def _mart369_serialize(self):
        self.ensure_one()
        return {
            'id': self.id,
            'label': self.mart369_label or 'Home',
            'name': self.name or '',
            'phone': self.phone or '',
            'alt': self.mart369_alt_phone or '',
            'line': self.street or '',
            'area': self.street2 or '',
            'city': self._mart369_city_line(),
            'state': self.state_id.name or '',
            'icon': self._mart369_icon(),
            'default': self.mart369_default,
            'lat': self.partner_latitude or 0.0,
            'lng': self.partner_longitude or 0.0,
        }

    def _mart369_set_default(self):
        """Make this the customer's default, and only this one.

        Setting type='delivery' is what makes Odoo treat it as *the* shipping
        address; Odoo demotes whichever sibling held that before.
        """
        self.ensure_one()
        siblings = self.search([
            ('parent_id', '=', self.parent_id.id),
            ('type', 'in', ADDRESS_TYPES),
            ('id', '!=', self.id),
        ])
        siblings.filtered('mart369_default').mart369_default = False
        self.write({'mart369_default': True, 'type': 'delivery'})

    def write(self, values):
        """Setting the flag means becoming the default, not just wearing it.

        `_mart369_set_default` above is what clears the sibling and moves
        `type='delivery'` across, but nothing forced anybody through it - and
        the backend list offers the flag as a toggle. Ticking it there set a
        second `mart369_default` while the real shipping address stayed put, so
        the shop had two defaults and delivered to the older one.

        Writing the flag by hand now goes through the same door. Turning it
        *off* is left alone: a customer who has no default is a state the
        delete route already has to handle.
        """
        becoming = values.get('mart369_default') and len(self) == 1
        if becoming and not self.env.context.get('mart369_setting_default'):
            rest = {k: v for k, v in values.items() if k != 'mart369_default'}
            if rest:
                super().write(rest)
            self.with_context(mart369_setting_default=True)._mart369_set_default()
            return True
        return super().write(values)

    # ------------------------------------------------------- what it misses

    def _mart369_gaps(self):
        """What this address is missing, as nouns a view can prefix with
        "Missing": ``['pincode', 'map location']``.
        """
        self.ensure_one()
        gaps = []
        if not self.phone:
            gaps.append(_('mobile'))
        if not self.zip:
            gaps.append(_('pincode'))
        if not self.street:
            gaps.append(_('street'))
        if not (self.partner_latitude or self.partner_longitude):
            gaps.append(_('map location'))
        return gaps

    @api.depends('phone', 'zip', 'street', 'partner_latitude', 'partner_longitude')
    def _compute_mart369_gap_label(self):
        """The same list, as one string a view can show in red."""
        for address in self:
            address.mart369_gap_label = ', '.join(address._mart369_gaps())

    # ------------------------------------------------- button on the kanban

    def action_mart369_make_default(self):
        for address in self:
            address._mart369_set_default()
        return True
