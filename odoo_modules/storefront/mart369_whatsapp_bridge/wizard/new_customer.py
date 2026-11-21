# -*- coding: utf-8 -*-
"""➕ New customer: staff add a customer by mobile number.

Two doors, one rule: this backend wizard and the app's admin console
(controllers/new_customer_api.py) both call `_mart369_create_customer`.

The customer gets a storefront login straight away (login = the mobile
number, the way a phone sign-up is made) with the number marked proven -
staff vouch for it. So:

- on the website, that number signs in with a code: no sign-up form and no
  password question (mart369_auth/controllers/phone_api.py asks a password
  only of a login whose number was never proven);
- on WhatsApp the bot already knows them (partner_link.py keeps a login whose
  number is proven): their name is not asked again and a saved address with
  a postcode skips the address questions. The bot's flow itself is unchanged.

A WhatsApp customer the bot already made a contact for is reused - their
orders and addresses stay theirs - and a number that already has a login is
refused. No email or WhatsApp message goes to the customer.
"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class Mart369NewCustomer(models.TransientModel):
    _name = 'mart369.new.customer'
    _description = 'New 369 Mart customer'

    name = fields.Char('Name', required=True)
    country_id = fields.Many2one('res.country', 'Country', required=True,
                                 default=lambda self: self.env.company.country_id)
    mobile = fields.Char('Mobile', required=True,
                         help="The number they will sign in with and order from on WhatsApp.")
    email = fields.Char('Email')

    label = fields.Selection([('Home', 'Home'), ('Work', 'Work'), ('Other', 'Other')],
                             'Address type', default='Home')
    line = fields.Char('House / flat / building')
    area = fields.Char('Street or area')
    landmark = fields.Char('Landmark')
    town = fields.Char('City / town')
    zip = fields.Char('Postcode')
    state_id = fields.Many2one('res.country.state', 'State',
                               domain="[('country_id', '=', country_id)]")
    alt = fields.Char('Other number', help="Another number to call, if they don't answer.")

    @api.onchange('country_id')
    def _onchange_country_id(self):
        if self.state_id and self.state_id.country_id != self.country_id:
            self.state_id = False

    # ------------------------------------------------------------------
    # The backend wizard
    # ------------------------------------------------------------------
    def action_create(self):
        self.ensure_one()
        body = {'name': self.name, 'country_id': self.country_id.id, 'mobile': self.mobile,
                'email': self.email or ''}
        if any((self.line, self.area, self.town, self.zip)):
            body['address'] = {
                'label': self.label or 'Home', 'name': (self.name or '').strip(),
                'line': self.line or '', 'area': self.area or '', 'landmark': self.landmark or '',
                'town': self.town or '', 'pin': (self.zip or '').strip(),
                'state_id': self.state_id.id or False, 'alt': self.alt or '',
            }
        result = self._mart369_create_customer(body)
        if not result.get('ok'):
            raise UserError(result.get('error'))
        view = self.env.ref('mart369_auth.view_mart369_customer_form', raise_if_not_found=False)
        return {
            'type': 'ir.actions.act_window', 'res_model': 'res.users', 'res_id': result['id'],
            'view_mode': 'form', 'views': [(view.id if view else False, 'form')], 'target': 'current',
        }

    # ------------------------------------------------------------------
    # The backend's own popup (static/src/new_customer): what it may call
    # ------------------------------------------------------------------
    def _mart369_staff_only(self):
        user = self.env.user
        if not (user.has_group('base.group_system') or user.has_group('website.group_website_designer')):
            raise AccessError(_("You do not have access to this."))

    @api.model
    def mart369_popup_form(self, country=None):
        """The countries, the phone rule (dial code, length, first digits),
        the postcode length and the states - the shop's own address form."""
        self._mart369_staff_only()
        return self.env['res.partner'].sudo()._mart369_form_meta(country)

    @api.model
    def mart369_popup_pincode(self, pin):
        """City and state for an Indian postcode (India Post), as the shop's form."""
        self._mart369_staff_only()
        return self.env['res.partner'].sudo()._mart369_pincode_lookup(str(pin or ''))

    @api.model
    def mart369_popup_create(self, body):
        self._mart369_staff_only()
        result = self._mart369_create_customer(body)
        if result.get('ok'):
            view = self.env.ref('mart369_auth.view_mart369_customer_form', raise_if_not_found=False)
            result['view_id'] = view.id if view else False
        return result

    # ------------------------------------------------------------------
    # The rule, for both doors
    # ------------------------------------------------------------------
    @api.model
    def _mart369_create_customer(self, body):
        """Add a customer from `body`:
        {name, mobile, country_id (id or code), email?, address?: the shop's
        address form - label, name, line, area, landmark, town, pin, state_id,
        alt}. Answers {ok, id (the login), name, phone} or {ok: False,
        error, field}."""
        Partner = self.env['res.partner'].sudo()
        Users = self.env['res.users'].sudo()
        body = dict(body or {})
        fail = lambda error, field=None: {'ok': False, 'error': error, 'field': field}

        name = (body.get('name') or '').strip()
        if len(name) < 2:
            return fail(_("Enter the customer's name."), 'name')
        country = (Partner._mart369_find_country(body.get('country_id') or body.get('country'))
                   if hasattr(Partner, '_mart369_find_country') else self.env['res.country'])
        country = country or self.env.company.country_id
        holder = Partner.new({'country_id': country.id})
        ok, phone = Partner._mart369_check_mobile(body.get('mobile') or body.get('phone'),
                                                  partner=holder, region=country.code)
        if not ok:
            return fail(phone, 'mobile')

        # One person, one account: a number that already signs in is theirs.
        partner, user = Partner._mart369_phone_owner(phone)
        if user or Users.with_context(active_test=False).search_count([('login', '=', phone)]):
            who = (user.partner_id.name if user else '') or phone
            return fail(_("%(phone)s already has an account: %(who)s.", phone=phone, who=who), 'mobile')
        email = (body.get('email') or '').strip().lower()
        if email and Users.with_context(active_test=False).search_count(
                ['|', ('login', '=ilike', email), ('email', '=ilike', email)]):
            return fail(_("An account already uses the email %s.") % email, 'email')

        # The address is checked before anything is made, so a bad postcode
        # leaves nothing half-created behind.
        address = body.get('address') if isinstance(body.get('address'), dict) else None
        if address:
            address = dict(address, name=(address.get('name') or name), phone=phone,
                           country_id=address.get('country_id') or country.id)
            __, error = Partner._mart369_address_values(address, parent=partner or Partner)
            if error:
                return fail(error[0], error[1])
            # Staff save every line, the landmark too: the rider reads it, and
            # with it saved the WhatsApp bot has nothing left to ask.
            if not (address.get('landmark') or '').strip():
                return fail(_("Enter a landmark the rider can see."), 'landmark')

        if partner:
            # The contact the bot made for this number: theirs, with its orders.
            vals = {'customer_rank': max(partner.customer_rank or 0, 1)}
            if not partner.name or partner.name.startswith('WhatsApp Customer'):
                vals['name'] = name
            if not partner.country_id:
                vals['country_id'] = country.id
            partner.write(vals)
        else:
            partner = Partner.create({'name': name, 'phone': phone, 'country_id': country.id,
                                      'customer_rank': 1})
        user = Users._create_user_from_template({'login': phone, 'name': partner.name,
                                                 'partner_id': partner.id})
        if email:
            partner.email = email
        # Staff vouch for the number: no password question on the website,
        # and the WhatsApp bot recognises this customer.
        partner._mart369_prove_phone(phone)
        if 'sa_name_confirmed_on' in partner._fields:
            partner.sa_name_confirmed_on = fields.Datetime.now()
        if address:
            values, error = Partner._mart369_address_values(address, parent=partner)
            if error:
                raise UserError(error[0])   # checked above; never half-made
            partner._mart369_add_address(values)
        if hasattr(partner, '_mart369_staff_note'):
            partner._mart369_staff_note(_("Customer added by %s.") % self.env.user.name)
        return {'ok': True, 'id': user.id, 'name': partner.name, 'phone': phone}
