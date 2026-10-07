"""Country-aware mobile numbers.

The rule is never written down here. Google's libphonenumber already knows,
per country, how many digits a mobile has and which digits it may start with,
so we ask it. India happens to mean "+91, ten digits, starts 6-9"; Oman means
"+968, eight digits"; the same code covers both.

Asking only "is this a valid number?" is not enough - libphonenumber calls
1234567890 a valid *landline* in India. Requiring the MOBILE type is what
rejects it.

This lives in mart369_auth rather than the address module because signup
collects a mobile too, and a dependency only points one way.
"""

import phonenumbers
from phonenumbers import PhoneNumberType

from odoo import _, api, fields, models

_MOBILE_TYPES = (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE)


def _digits(number):
    return ''.join(c for c in (number or '') if c.isdigit())


class ResPartner(models.Model):
    _inherit = 'res.partner'

    mart369_phone_verified = fields.Boolean(
        string='Mobile proven', copy=False,
        help="The customer proved this mobile number with a code sent to it. "
             "Only a proven number signs in, and only a proven number joins "
             "this account to the same person's WhatsApp orders.")
    mart369_phone_verified_at = fields.Datetime(string='Mobile proven on', copy=False)

    # -------------------------------------------------------------- country

    @api.model
    def _mart369_country(self, partner=None):
        """Whose phone rules apply: the address's own country, else the
        customer's, else the company's."""
        if partner:
            country = partner.country_id or partner.parent_id.country_id
            if country:
                return country
        return self.env.company.country_id

    @api.model
    def _mart369_region(self, partner=None):
        return (self._mart369_country(partner).code or 'IN').upper()

    # --------------------------------------------------------------- mobile

    @api.model
    def _mart369_check_mobile(self, number, partner=None, required=True, region=None):
        """Validate a mobile for the applicable country.

        Returns ``(True, '+917092090133')`` or ``(False, 'why not')``. An empty
        value is allowed when ``required`` is False, giving ``(True, '')``.
        ``region`` - the ISO code a form's country picker chose - wins over the
        partner's; a number typed with its own +code is read as that country
        either way.
        """
        number = (number or '').strip()
        if not number:
            return (False, _('Enter a mobile number.')) if required else (True, '')
        region = (region or '').upper() or self._mart369_region(partner)
        try:
            parsed = phonenumbers.parse(number, region)
        except phonenumbers.NumberParseException:
            return False, _('Enter a valid mobile number.')
        if not phonenumbers.is_valid_number(parsed):
            hint = self._mart369_phone_hint(region)
            return False, _(
                'Enter a %(length)s-digit mobile number for %(country)s.',
                length=hint['length'], country=hint['country'])
        if phonenumbers.number_type(parsed) not in _MOBILE_TYPES:
            return False, _('That looks like a landline. Enter a mobile number.')
        return True, phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    @api.model
    def _mart369_phone_hint(self, region=None, partner=None):
        """What a form should show: dial code, digit count and a real example,
        so the UI can render '+91' and cap the length without knowing any
        country rules itself."""
        region = (region or self._mart369_region(partner)).upper()
        country = self.env['res.country'].search([('code', '=', region)], limit=1)
        label = country.display_name or region
        try:
            example = phonenumbers.example_number_for_type(region, PhoneNumberType.MOBILE)
            national = phonenumbers.national_significant_number(example)
            dial = phonenumbers.country_code_for_region(region)
        except Exception:  # noqa: BLE001 - unknown region: give the UI something usable
            return {'region': region, 'dial': '', 'length': 0, 'example': '', 'country': label}
        return {
            'region': region,
            'dial': '+%s' % dial,
            'length': len(national),
            'example': national,
            'country': label,
        }

    # ------------------------------------------------------- the phone form

    @api.model
    def _mart369_phone_form(self, country=None):
        """What a sign-in or sign-up form needs before anyone is signed in:
        the default country - the company's, from the database, never a
        hard-coded +91 - every country with its dial code, and the default's
        digit count and example."""
        Country = self.env['res.country'].sudo()
        chosen = Country.browse()
        if country:
            chosen = (Country.browse(int(country)).exists()
                      if str(country).isdigit()
                      else Country.search([('code', '=ilike', str(country))], limit=1))
        if not chosen and not self.env.user._is_public():
            chosen = self.env.user.partner_id.country_id
        if not chosen:
            chosen = self.env.company.country_id or Country.search(
                [('code', '=', 'IN')], limit=1)
        rows = [{'id': c.id, 'code': c.code, 'name': c.name,
                 'dial': '+%s' % c.phone_code}
                for c in Country.search([], order='name') if c.phone_code]
        return {
            'ok': True,
            'country': {'id': chosen.id, 'code': chosen.code, 'name': chosen.name,
                        'dial': '+%s' % chosen.phone_code if chosen.phone_code else ''},
            'countries': rows,
            'phone': self._mart369_phone_hint(chosen.code or 'IN'),
        }

    # ------------------------------------------------- who owns this number

    @api.model
    def _mart369_phone_owner(self, phone):
        """(partner, user) behind a mobile number; either may be empty.

        Here: a storefront account carrying the number, a proven one first.
        mart369_whatsapp_bridge adds the customer who only ever ordered on
        WhatsApp - a partner with no user.
        """
        Users = self.env['res.users'].sudo()
        users = Users.search([
            ('share', '=', True),
            '|', ('partner_id.phone', '=', phone),
            ('partner_id.phone_sanitized', '=', phone),
        ])
        public = self.env.ref('base.public_user', raise_if_not_found=False)
        if public:
            users -= public
        if not users:
            return self.browse(), Users.browse()
        user = (users.filtered('partner_id.mart369_phone_verified')
                or users.sorted(lambda u: u.login_date or u.create_date,
                                reverse=True))[:1]
        return user.partner_id, user

    # ------------------------------------------------------------- the hooks

    @api.model
    def _mart369_send_login_code(self, phone, code):
        """Deliver a code: 'sent', 'queued', 'offline' or 'none'.

        Nothing can carry it from here; mart369_whatsapp_bridge sends it on
        WhatsApp.
        """
        return 'none'

    def _mart369_after_phone_verified(self):
        """Called once a number is proven on this customer. Answers what
        joined: {'orders': n, 'addresses': n}. The bridge joins the same
        person's WhatsApp contact here."""
        return {'orders': 0, 'addresses': 0}

    def _mart369_prove_phone(self, phone):
        """Mark `phone` proven on this customer, and let the rest follow."""
        self.ensure_one()
        self.sudo().with_context(mart369_phone_proven=True).write({
            'phone': phone,
            'mart369_phone_verified': True,
            'mart369_phone_verified_at': fields.Datetime.now(),
        })
        return self.sudo()._mart369_after_phone_verified() or {}

    def write(self, vals):
        """A changed number is an unproven number - unless it is the same
        digits written another way, or the proof itself is writing it."""
        if 'phone' not in vals or self.env.context.get('mart369_phone_proven'):
            return super().write(vals)
        new = _digits(vals.get('phone'))
        changed = self.filtered(
            lambda p: p.mart369_phone_verified and _digits(p.phone) != new)
        res = super().write(vals)
        if changed:
            super(ResPartner, changed).write({
                'mart369_phone_verified': False,
                'mart369_phone_verified_at': False,
            })
        return res
