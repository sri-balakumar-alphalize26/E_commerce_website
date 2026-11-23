# -*- coding: utf-8 -*-
"""Every vendor's price on the Enquiries screen, the moment it comes (owner, 23
Nov 2026). The list and the cards showed the lowest only, and a reply by chat
was seen at the next poll."""
from odoo import api, models


class SaVendorQuoteShown(models.Model):
    _inherit = 'sa.vendor.quote'

    @api.model_create_multi
    def create(self, vals_list):
        quotes = super().create(vals_list)
        quotes.request_id._sa_enquiry_notify()
        return quotes

    def write(self, vals):
        res = super().write(vals)
        if 'price' in vals:
            self.request_id._sa_enquiry_notify()
        return res


class SaGroupRequestPrices(models.Model):
    _inherit = 'sa.group.request'

    def _sa_vendor_prices(self):
        """One line per vendor, their newest price, the lowest first."""
        self.ensure_one()
        newest = {}
        for quote in self.quote_ids.sorted('id'):
            if (quote.price or 0.0) > 0:
                newest[quote._sa_who()] = quote
        quotes = sorted(newest.values(), key=lambda q: (round(q.price, 4), q._sa_arrived(), q.id))
        # two vendors with the same price are both the lowest
        low = round(quotes[0].price, 4) if quotes else 0.0
        return [{
            'id': q.id, 'vendor': q.partner_id.name or q.vendor_name or q.vendor_phone or '', 'price': q.price,
            'sell': q.sa_sell_price, 'lowest': round(q.price, 4) == low, 'late': q.sa_late,
            'days': q.delay_days or 0} for q in quotes]

    @api.model
    def sa_enquiry_queue(self):
        data = super().sa_enquiry_queue()
        # one that waits for the counter to choose a price is in Needs you only
        choose = {row['id'] for row in data.get('stalled') or [] if row.get('choice')}
        data['tracking'] = [row for row in data.get('tracking') or [] if row['id'] not in choose]
        rows = [row for key in ('tracking', 'stalled') for row in data.get(key) or []]
        at = {r.id: r for r in self.sudo().browse([row['id'] for row in rows])}
        for row in rows:
            row['prices'] = at[row['id']]._sa_vendor_prices()
        return data

    @api.model
    def sa_enquiry_detail(self, request_id):
        detail = super().sa_enquiry_detail(request_id)
        prices = self.sudo().browse(int(request_id))._sa_vendor_prices()
        low = {p['vendor'] for p in prices if p['lowest']} if len(prices) > 1 else set()
        for vendor in detail['vendors']:
            vendor['lowest'] = bool(vendor['replied'] and vendor['name'] in low)
        return detail
