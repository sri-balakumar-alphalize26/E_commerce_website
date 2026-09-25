"""Staff add or fix a customer's address - the Amazon / Flipkart support desk.

Opened from a customer's "Delivery addresses" tab: **+ Add address**, or
**Edit** on one card. It asks for what the customer's own form asks for, in the
same order, and saves through the same rules (models/address_rules.py): the
same required lines, the same mobile check for the address's country, and the
same promise that an order's address is never rewritten.

Staff never delete here. Removing an address is the customer's call.
"""

import phonenumbers

from odoo import _, api, fields, models
from odoo.exceptions import UserError

LABELS = [('Home', 'Home'), ('Work', 'Work'), ('Other', 'Other')]


def _foreign_number(number, country):
    """True when ``number`` plainly belongs to another country than
    ``country`` - an Omani +968 mobile on an Indian address, say. A number
    without a country code is the form's own, so never foreign."""
    number = (number or '').strip()
    if not number or not country.code:
        return False
    try:
        parsed = phonenumbers.parse(number, country.code.upper())
    except phonenumbers.NumberParseException:
        return False
    return phonenumbers.region_code_for_number(parsed) not in (None, country.code.upper())


class Mart369AddressWizard(models.TransientModel):
    _name = 'mart369.address.wizard'
    _description = "Add or edit a customer's delivery address"

    customer_id = fields.Many2one('res.partner', string='Customer', required=True, readonly=True)
    address_id = fields.Many2one('res.partner', string='Address', readonly=True)
    label = fields.Selection(LABELS, string='Address type', required=True, default='Home')
    name = fields.Char('Full name', required=True)
    phone = fields.Char('Mobile number', required=True)
    alt = fields.Char('Alternate mobile')
    country_id = fields.Many2one('res.country', string='Country', required=True)
    phone_hint = fields.Char(compute='_compute_hints')
    zip = fields.Char('Pincode', required=True)
    pin_found = fields.Char(readonly=True)
    street = fields.Char('House no., building, apartment', required=True)
    street2 = fields.Char('Road name, area, colony', required=True)
    landmark = fields.Char('Landmark')
    city = fields.Char('City / District / Town', required=True)
    state_id = fields.Many2one('res.country.state', string='State',
                               domain="[('country_id', '=', country_id)]")
    has_states = fields.Boolean(compute='_compute_hints')

    # ------------------------------------------------------------- opening

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        Partner = self.env['res.partner'].sudo()
        address = Partner.browse(self.env.context.get('default_address_id')).exists()
        customer = address.parent_id or Partner.browse(values.get('customer_id')).exists()
        if address:
            label = address.mart369_label or 'Home'
            values.update({
                'customer_id': customer.id,
                'label': label if label in dict(LABELS) else 'Other',
                'name': address.name,
                'phone': address.phone,
                'alt': address.mart369_alt_phone,
                'country_id': (address.country_id or Partner._mart369_default_country(customer)).id,
                'zip': address.zip,
                'street': address.street,
                'street2': address.street2,
                'landmark': address.mart369_landmark,
                'city': address.city,
                'state_id': address.state_id.id,
            })
        elif customer:
            # A new address is for the customer unless staff say otherwise -
            # but their account mobile only when it fits the address's
            # country, or an Omani number sits in an Indian form.
            country = Partner._mart369_default_country(customer)
            values.update({
                'name': customer.name,
                'phone': '' if _foreign_number(customer.phone, country) else customer.phone,
                'country_id': country.id,
            })
        return values

    @api.depends('country_id')
    def _compute_hints(self):
        Partner = self.env['res.partner']
        for wizard in self:
            hint = Partner._mart369_phone_hint(region=wizard.country_id.code) if wizard.country_id else {}
            wizard.phone_hint = (_('%(dial)s · %(length)s digits', dial=hint['dial'], length=hint['length'])
                                 if hint.get('dial') else '')
            wizard.has_states = bool(wizard.country_id.state_ids)

    # ------------------------------------------------------------ filling in

    @api.onchange('country_id')
    def _onchange_country(self):
        if self.state_id and self.state_id.country_id != self.country_id:
            self.state_id = False
        if _foreign_number(self.phone, self.country_id):
            self.phone = False
        if _foreign_number(self.alt, self.country_id):
            self.alt = False
        self.pin_found = False

    @api.onchange('zip')
    def _onchange_zip(self):
        """Indian pincodes fill the city and state, as the customer's form
        does - but never over something already typed."""
        self.pin_found = False
        if (self.country_id.code or '').upper() != 'IN' or not self.zip:
            return
        found = self.env['res.partner']._mart369_pincode_lookup(self.zip.strip())
        if not found.get('ok'):
            return
        if not self.city:
            self.city = found.get('town')
        if not self.state_id and found.get('state_id'):
            self.state_id = found['state_id']
        areas = found.get('areas') or []
        self.pin_found = ', '.join(p for p in (found.get('town'), found.get('state')) if p)
        if areas:
            self.pin_found += _(' · areas: %s', ', '.join(areas[:8]))

    # ------------------------------------------------------------------ saving

    def action_save(self):
        """Save through the same staff methods the console uses
        (models/address_staff.py), so the checks and the history note match."""
        self.ensure_one()
        Partner = self.env['res.partner']
        body = {
            'label': self.label, 'name': self.name or '', 'phone': self.phone or '',
            'alt': self.alt or '', 'pin': (self.zip or '').strip(), 'town': self.city or '',
            'line': self.street or '', 'area': self.street2 or '', 'landmark': self.landmark or '',
            'state_id': self.state_id.id or False, 'country_id': self.country_id.id,
        }
        if self.address_id:
            result = Partner.mart369_admin_edit(self.address_id.id, body)
        else:
            login = self.customer_id.sudo().user_ids.filtered('share')[:1]
            result = Partner.mart369_admin_add(login.id, body)
        if not result.get('ok'):
            raise UserError(result.get('error') or _('That address could not be saved.'))
        return {'type': 'ir.actions.act_window_close'}
