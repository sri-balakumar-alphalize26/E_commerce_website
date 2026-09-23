"""Where 369 Mart delivers, and how fast.

Replaces `demoCheck` in components/home/LocationPicker.jsx, which is a regex:

    if (!/^6[789]\\d{4}$/.test(pin)) return { ok: false, error: "..." };
    return { ok: true, quick: pin.startsWith("68") || pin.startsWith("69"), eta: "13 mins" };

That is "Kerala is servicable, everywhere else is not", with one ETA for every
address in the state. Here a pincode - or a run of them - is a record an
operator can add without a developer, and the ETA belongs to the area.

Matching is longest-prefix: an entry for 6820 beats an entry for 68, so a city
can have its own promise inside a region that already has one.
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Mart369ServiceArea(models.Model):
    _name = 'mart369.service.area'
    _description = '369 Mart Service Area'
    _order = 'pincode'
    _rec_name = 'pincode'

    pincode = fields.Char(
        string='Pincode', required=True, index=True,
        help="A full pincode (682016) or the start of one (68), which covers "
             "every pincode beginning with it.")
    name = fields.Char(
        string='Area', help="What to call this area in Odoo. The app never "
                            "shows it.")
    quick = fields.Boolean(
        string='Quick delivery', default=True,
        help="On: 10-minute groceries reach this area. Off: Express only.")
    express = fields.Boolean(
        string='Express delivery', default=True,
        help="On: items that ship over days reach this area.")
    eta = fields.Char(
        string='Delivery promise', default='13 mins',
        help="What the app tells a customer here, e.g. 13 mins.")
    active = fields.Boolean(default=True)

    _pincode_uniq = models.Constraint(
        'unique (pincode)',
        'That pincode is already covered by another area.',
    )

    @api.constrains('pincode')
    def _check_pincode(self):
        for area in self:
            value = (area.pincode or '').strip()
            if not value.isdigit():
                raise ValidationError(self.env._(
                    "A pincode is digits only. '%s' is not.", area.pincode))

    # -------------------------------------------------------------- lookup

    @api.model
    def _mart369_match(self, pin):
        """The most specific area covering this pincode, or nothing.

        Longest prefix wins, so 6820 beats 68 and an exact pincode beats both.
        """
        pin = ''.join((pin or '').split())
        if not pin.isdigit():
            return self.browse()
        prefixes = [pin[:n] for n in range(len(pin), 0, -1)]
        areas = self.sudo().search([('pincode', 'in', prefixes)])
        if not areas:
            return self.browse()
        return max(areas, key=lambda a: len(a.pincode or ''))

    @api.model
    def _mart369_check(self, pin):
        """Exactly the answer `demoCheck` gives, so the picker is unchanged:
        {ok: True, quick: bool, eta: str} or {ok: False, error: str}."""
        pin = ''.join((pin or '').split())
        if not (pin.isdigit() and len(pin) >= 3):
            return {'ok': False, 'error': self.env._('Enter a valid pincode.')}
        area = self._mart369_match(pin)
        if not area or not (area.quick or area.express):
            return {'ok': False,
                    'error': self.env._("We don't deliver to this pincode yet.")}
        return {'ok': True, 'quick': area.quick, 'eta': area.eta or ''}

    # -------------------------------------------------------- the console

    def _mart369_admin_row(self):
        """One area as the admin console draws it.

        `_mart369_check` above answers a customer's question - can you reach
        me, and how fast - and deliberately says nothing about which record
        answered it. This says which record, and everything on it.
        """
        self.ensure_one()
        return {
            'id': self.id,
            'pincode': self.pincode or '',
            'name': self.name or '',
            'quick': self.quick,
            'express': self.express,
            'eta': self.eta or '',
            'active': self.active,
        }
