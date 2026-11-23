# -*- coding: utf-8 -*-
"""A supplier's price in their own currency (owner, 23 Nov 2026).

Since 22 Nov suppliers type the amount in their country's currency, but the
number was kept as if it were the enquiry's: INR 100 went to the customer as
OMR 120 (S00017, S00018). The quote now keeps what they typed and is compared
and sold in the enquiry's currency, by Odoo's own rates. A currency that is
switched off, or whose rate is missing or older than a week, is never guessed:
nothing is quoted from that reply, the counter sees "Needs a price" with what
the supplier said. (Odoo itself converts 1:1 without a rate.)
"""
import json
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

RATE_DAYS = 7
_CODES = ('AED', 'USD', 'EUR', 'GBP', 'INR', 'OMR', 'SAR', 'QAR', 'KWD', 'BHD', 'CNY', 'PKR', 'LKR',
          'BDT', 'NPR', 'SGD', 'HKD', 'MYR', 'THB', 'JPY', 'EGP')
_WORD = (r'(?:us\$|rmb|\u4eba\u6c11\u5e01|\u5143|\u5757|\u20b9|\u20ac|\u00a3|\u00a5|\uffe5|\$|'
         r'rs|rupees?|dhs?|dirhams?|%s)' % '|'.join(c.lower() for c in _CODES))
# the currency touches its number: "INR 100", "100 inr", "Rs.100", "100/- rs"
_BEFORE = re.compile(r'(?<![a-z])(%s)\.?\s*[0-9]' % _WORD, re.IGNORECASE)
_AFTER = re.compile(r'[0-9]\s*(?:/-)?\s*(%s)(?![a-z])' % _WORD, re.IGNORECASE)
# one sign, several currencies: the supplier's own one when it is among them
_SHARED = {
    '$': ('USD', 'SGD', 'AUD', 'CAD', 'HKD', 'NZD', 'TWD'),
    '\u00a5': ('CNY', 'JPY'), '\uffe5': ('CNY', 'JPY'),
    '\u5143': ('CNY', 'HKD', 'TWD'), '\u5757': ('CNY', 'HKD', 'TWD'),
    'rs': ('INR', 'PKR', 'LKR', 'NPR', 'MUR', 'SCR'),
    'rupee': ('INR', 'PKR', 'LKR', 'NPR', 'MUR', 'SCR'), 'rupees': ('INR', 'PKR', 'LKR', 'NPR', 'MUR', 'SCR'),
    'dh': ('AED', 'MAD'), 'dhs': ('AED', 'MAD'), 'dirham': ('AED', 'MAD'), 'dirhams': ('AED', 'MAD'),
}
_ONE = {'us$': 'USD', 'rmb': 'CNY', '\u4eba\u6c11\u5e01': 'CNY', '\u20b9': 'INR', '\u20ac': 'EUR', '\u00a3': 'GBP'}


class SaVendorQuoteMoney(models.Model):
    _inherit = 'sa.vendor.quote'

    sa_typed_amount = fields.Float('Typed amount', readonly=True,
                                   help="What the supplier typed, in their own currency.")
    sa_typed_currency = fields.Char('Typed currency', readonly=True)

    @api.model
    def _sa_currency_in(self, text, assumed=''):
        """The currency code written next to the number, or `assumed`."""
        text = text or ''
        found = _BEFORE.search(text) or _AFTER.search(text)
        if not found:
            return assumed or ''
        word = found.group(1).lower()
        if word in _SHARED:
            return assumed if assumed in _SHARED[word] else _SHARED[word][0]
        return _ONE.get(word) or word.upper()

    @api.model
    def _sa_take_price(self, request, amount, code, vals):
        """The quote for a supplier's `amount` in `code` (created), or an empty
        recordset when it cannot be turned into the enquiry's currency: then
        it is held for the counter. `vals`: the quote's other fields, plus
        'message_ref' to tell a held answer from an older one."""
        vals = dict(vals)
        ref = vals.pop('message_ref', '')
        price = request._sa_price_in_own(amount, code)
        if price is None:
            request._sa_hold_price(vals.get('partner_id'), vals.get('vendor_phone'),
                                   vals.get('vendor_name'), amount, code, ref)
            return self.browse()
        request._sa_release_price(vals.get('partner_id'), vals.get('vendor_phone'))
        target = request.currency_id or self.env.company.currency_id
        return self.sudo().create(dict(
            vals, request_id=request.id, price=price, currency_id=target.id,
            sa_typed_amount=amount, sa_typed_currency=code or target.name or ''))

    def _sa_typed_text(self):
        """"INR 100.00" - as the supplier gave it."""
        self.ensure_one()
        if not self.sa_typed_amount:            # older quotes, typed at the shop
            return '%.2f' % self.price
        return ('%s %.2f' % (self.sa_typed_currency or '', self.sa_typed_amount)).strip()


class SaGroupRequestMoney(models.Model):
    _inherit = 'sa.group.request'

    sa_held_prices = fields.Text('Prices waiting for the shop', copy=False, readonly=True,
                                 help="Suppliers' prices in a currency with no current rate.")

    # ------------------------------------------------------------ converting
    @api.model
    def _sa_rate_ok(self, currency, company):
        """A rate for today: one at most a week old; the company's own
        currency needs none. The row Odoo would use: the company's, else the
        shared one."""
        today = fields.Date.context_today(self)
        Rate = self.env['res.currency.rate'].sudo()
        row = Rate.browse()
        for owner in (company.root_id.id, False):
            row = Rate.search([('currency_id', '=', currency.id), ('company_id', '=', owner),
                               ('name', '<=', today)], order='name desc', limit=1)
            if row:
                break
        fresh = bool(row and row.name >= today - timedelta(days=RATE_DAYS))
        if currency == company.currency_id:
            return bool(not row or fresh or abs(row.rate - 1.0) < 1e-9)
        return fresh

    def _sa_price_in_own(self, amount, code):
        """`amount` of currency `code` in this enquiry's currency, or None when
        that cannot be told."""
        self.ensure_one()
        company = (self._company_for(self.group_id) if self.group_id else False) or self.env.company
        target = self.currency_id or company.currency_id
        if not code or code == target.name:
            return amount
        source = self.env['res.currency'].sudo().with_context(active_test=False).search(
            [('name', '=', code)], limit=1)
        if not source or not source.active or not (
                self._sa_rate_ok(source, company) and self._sa_rate_ok(target, company)):
            return None
        price = source._convert(amount, target, company, fields.Date.context_today(self))
        return price if price > 0 else None

    # ------------------------------------------------------------ held for the shop
    def _sa_held(self):
        self.ensure_one()
        try:
            return json.loads(self.sa_held_prices or '{}') or {}
        except ValueError:
            return {}

    @api.model
    def _sa_held_key(self, partner_id, phone):
        if partner_id:
            return 'p%s' % int(partner_id)
        return 'n%s' % ''.join(c for c in (phone or '') if c.isdigit())[-9:]

    def _sa_hold_price(self, partner_id, phone, name, amount, code, ref=''):
        """No current rate: kept for the counter, which is told."""
        self.ensure_one()
        held = self._sa_held()
        held[self._sa_held_key(partner_id, phone)] = {
            'name': name or phone or '', 'amount': amount, 'code': code, 'ref': str(ref or ''),
            'partner': int(partner_id or 0)}
        self.sudo().write({'sa_held_prices': json.dumps(held, sort_keys=True)})
        _logger.warning("Sales Automation: %s answered %s %.2f on enquiry %s - no current rate to its "
                        "currency, held for the counter", name or phone, code, amount, self.id)
        self._sa_enquiry_notify()
        return True

    def _sa_release_price(self, partner_id, phone):
        held = self._sa_held()
        if held.pop(self._sa_held_key(partner_id, phone), None) is not None:
            self.sudo().write({'sa_held_prices': json.dumps(held, sort_keys=True) if held else False})

    def _sa_held_of(self, partner_id, phone=''):
        """This supplier's held answer ({} when none)."""
        self.ensure_one()
        return self._sa_held().get(self._sa_held_key(partner_id, phone)) or {}

    def _sa_vendor_lists(self):
        """Not those who gave a price we cannot convert: `_sa_held_lines`."""
        yes, no, silent = super()._sa_vendor_lists()
        held = self._sa_held()
        if not held:
            return yes, no, silent
        names = self.env['res.partner'].sudo().browse(
            [h['partner'] for h in held.values() if h.get('partner')]).exists().mapped('name')
        yes = [n for n in yes if n not in names]
        silent = [n for n in silent if n not in names]
        no = [n for n in no if n not in names]
        return yes, no, silent

    def _sa_held_lines(self):
        """["Kumar: AED 500.00"] - given in a currency without a current rate."""
        self.ensure_one()
        return ['%s: %s %.2f' % (h.get('name') or '', h.get('code') or '', h.get('amount') or 0.0)
                for h in self._sa_held().values()]

    def _sa_held_why(self):
        self.ensure_one()
        return _("no exchange rate to %s - type the price yourself", self.currency_id.name or '')

    # ------------------------------------------------------------ after a price
    def _sa_vendor_price_in(self, quote):
        """A real price came for this enquiry. One already handed to the shop
        closes on it at the next run; a shop price typed first has moved the
        enquiry on and nothing happens."""
        self.ensure_one()
        if quote and self.sa_price_stalled:
            self.sudo().write({'sourcing_deadline': fields.Datetime.now()})
            _logger.info("Sales Automation: late price on stalled enquiry %s - closing on it", self.id)
        return True
