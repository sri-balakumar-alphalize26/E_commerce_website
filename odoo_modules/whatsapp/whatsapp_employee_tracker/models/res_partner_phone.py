# -*- coding: utf-8 -*-
"""One way to find a contact by WhatsApp number (7 Oct 2026).

Every place that turns a WhatsApp number into a contact goes through these two
methods, so a rule about who may own a number lives in one place. Other
modules override `_sa_phone_matches` (369 Mart's bridge keeps unproven website
accounts out of it).

A number matches when its digits are equal, or when both have at least seven
digits and the last ten agree - "+91 98765 43210", "919876543210" and
"9876543210" are one number; "98765 43211" is not.
"""
from odoo import api, models


def _digits(phone):
    return ''.join(c for c in (phone or '') if c.isdigit())


class ResPartnerPhoneLookup(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _sa_phone_e164(self, phone):
        """How a WhatsApp number is saved on a new contact: with "+", so a
        database in another country does not read it as a local number."""
        raw = (phone or '').strip()
        digits = _digits(raw)
        return ('+' + digits) if digits else raw

    @api.model
    def _sa_phone_matches(self, phone):
        """Every contact whose number is this number, oldest first."""
        digits = _digits(phone)
        if len(digits) < 5:
            return self.browse()
        tail = digits[-5:]
        Partner = self.sudo().with_context(active_test=True)
        found = (Partner.search([('phone', 'ilike', tail)], order='id')
                 | Partner.search([('phone_sanitized', 'ilike', tail)], order='id'))

        def same(number):
            d = _digits(number)
            return bool(d) and (d == digits or (len(d) >= 7 and len(digits) >= 7
                                                and d[-10:] == digits[-10:]))
        return found.filtered(lambda p: same(p.phone) or same(p.phone_sanitized)).sorted('id')

    @api.model
    def _sa_phone_owner(self, phone):
        """The customer who owns this number: the first match that buys from
        us (a customer, or not a supplier). Empty when nobody does."""
        return self._sa_phone_matches(phone).filtered(
            lambda p: p.customer_rank > 0 or not p.supplier_rank)[:1]
