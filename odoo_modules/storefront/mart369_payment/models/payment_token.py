"""Saved cards and UPI IDs.

The app keeps these in ``localStorage`` under `369mart.payments`, and the card the
customer typed passes through React state in full on the way there
(Checkout.jsx:600). The screen that collects it even says the card is "tokenised as
per RBI rules" while the CVV is read and thrown away.

Here a saved method is an ordinary ``payment.token``: the provider tokenises the
card on its own form and hands back a reference, and we keep only what the app
prints - brand, last four, holder, expiry, bank. There is no field anywhere in this
module that a card number could be written into, and :meth:`write` refuses one
anyway, because "there is nowhere to put it" is a weaker guarantee than a check.
"""

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# A saved method never holds anything this long. Twelve to nineteen digits is a
# card number by any scheme, whether or not it is grouped with spaces or dashes.
_PAN = re.compile(r'\d[\d\s-]{10,}\d')

# The four UPI apps the app offers, and the handles that identify them.
# Ported from upiApp() in AccountExtras.jsx:266 so the server fills `app` rather
# than the browser guessing it.
UPI_HANDLES = {
    'okaxis': 'gpay', 'okhdfcbank': 'gpay', 'okicici': 'gpay', 'oksbi': 'gpay',
    'ybl': 'phonepe', 'ibl': 'phonepe', 'axl': 'phonepe',
    'paytm': 'paytm', 'ptyes': 'paytm', 'ptaxis': 'paytm',
    'upi': 'bhim',
}

_VPA = re.compile(r'^[a-z0-9._-]{2,}@[a-z]{2,}$', re.IGNORECASE)


class PaymentToken(models.Model):
    _inherit = 'payment.token'

    mart369_kind = fields.Selection(
        [('card', "Card"), ('upi', "UPI ID")],
        string="369 Mart kind", compute='_compute_mart369_kind', store=True, index='btree_not_null')
    mart369_brand = fields.Selection(
        [('visa', "VISA"), ('mastercard', "Mastercard"),
         ('rupay', "RuPay"), ('amex', "AMEX")],
        string="Brand")
    mart369_last4 = fields.Char(string="Last four", size=4)
    mart369_holder = fields.Char(string="Name on card")
    mart369_exp = fields.Char(string="Expiry", size=5, help="MM/YY, as the app prints it.")
    mart369_bank = fields.Char(string="Bank", default="Saved card")
    mart369_vpa = fields.Char(string="UPI ID")
    mart369_upi_app = fields.Selection(
        [('gpay', "Google Pay"), ('phonepe', "PhonePe"),
         ('paytm', "Paytm"), ('bhim', "BHIM")],
        string="UPI app")
    mart369_default = fields.Boolean(string="Default", copy=False)

    # --------------------------------------------------------------- computes

    @api.depends('payment_method_id', 'payment_method_code', 'mart369_vpa')
    def _compute_mart369_kind(self):
        for token in self:
            code = token.payment_method_code or ''
            if code == 'upi' or token.mart369_vpa:
                token.mart369_kind = 'upi'
            elif code:
                token.mart369_kind = 'card'
            else:
                token.mart369_kind = False

    # ------------------------------------------------------------ the PAN guard

    @api.constrains('mart369_last4', 'mart369_holder', 'mart369_bank',
                    'mart369_vpa', 'mart369_exp')
    def _check_mart369_no_pan(self):
        """No field on a saved method may hold something shaped like a card number.

        This is the check behind the promise the app's own copy makes. It is cheap,
        and the alternative is trusting that nobody ever adds a convenient
        "full number" column later.
        """
        for token in self:
            for name in ('mart369_last4', 'mart369_holder', 'mart369_bank',
                         'mart369_vpa', 'mart369_exp'):
                value = token[name] or ''
                if _PAN.search(value):
                    raise ValidationError(_(
                        "A saved payment method must never hold a card number."))

    # ---------------------------------------------------------------- helpers

    @api.model
    def _mart369_upi_app_from_vpa(self, vpa):
        """Which app a UPI ID belongs to, from its handle."""
        handle = (vpa or '').rsplit('@', 1)[-1].lower()
        return UPI_HANDLES.get(handle, 'bhim')

    @api.model
    def _mart369_check_vpa(self, vpa):
        """(ok, value_or_reason) - the same shape mart369_auth uses for phones."""
        vpa = (vpa or '').strip().lower()
        if not vpa:
            return False, _("Enter your UPI ID.")
        if not _VPA.match(vpa):
            return False, _("Enter a valid UPI ID, like name@okaxis.")
        return True, vpa

    def _mart369_set_default(self):
        """Make this the chosen method, and clear the others of the same kind.

        A customer may have one default card and one default UPI ID at once - the
        app shows an independent Default badge in each list.
        """
        self.ensure_one()
        siblings = self.sudo().search([
            ('partner_id', '=', self.partner_id.id),
            ('mart369_kind', '=', self.mart369_kind),
            ('mart369_default', '=', True),
            ('id', '!=', self.id),
        ])
        siblings.write({'mart369_default': False})
        self.sudo().write({'mart369_default': True})

    def _mart369_serialize(self):
        """Exactly what the app reads from `369mart.payments` (accountStore.js:64).

        `id` is a string because the app compares ids with ===.
        """
        self.ensure_one()
        if self.mart369_kind == 'upi':
            return {
                'id': str(self.id),
                'vpa': self.mart369_vpa or '',
                'name': self.mart369_holder or self.partner_id.name or '',
                'app': self.mart369_upi_app or 'bhim',
                'default': self.mart369_default,
            }
        return {
            'id': str(self.id),
            'brand': self.mart369_brand or 'visa',
            'last4': self.mart369_last4 or '',
            'name': self.mart369_holder or self.partner_id.name or '',
            'exp': self.mart369_exp or '',
            'bank': self.mart369_bank or 'Saved card',
            'default': self.mart369_default,
        }
