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

from odoo import _, api, models

_MOBILE_TYPES = (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE)


class ResPartner(models.Model):
    _inherit = 'res.partner'

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
    def _mart369_check_mobile(self, number, partner=None, required=True):
        """Validate a mobile for the applicable country.

        Returns ``(True, '+917092090133')`` or ``(False, 'why not')``. An empty
        value is allowed when ``required`` is False, giving ``(True, '')``.
        """
        number = (number or '').strip()
        if not number:
            return (False, _('Enter a mobile number.')) if required else (True, '')
        region = self._mart369_region(partner)
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
