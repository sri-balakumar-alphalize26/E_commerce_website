# -*- coding: utf-8 -*-
"""What Store > Vendor Orders shows. Reading only."""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

OPEN = ('waiting', 'review', 'no_vendor')
DONE = ('received', 'cancelled')
DONE_DAYS = 7
PAGE = 300


def iso(value):
    return value.isoformat() + 'Z' if value else ''


class SaBuyLineScreen(models.Model):
    _inherit = 'sa.buy.line'

    def _sa_own_money(self, amount, currency):
        """`amount` in the company's currency, or None without a current rate."""
        self.ensure_one()
        own = self.company_id.currency_id
        if not currency or currency == own:
            return amount
        Request = self.env['sa.group.request']
        if not (Request._sa_rate_ok(currency, self.company_id) and Request._sa_rate_ok(own, self.company_id)):
            return None
        return currency._convert(amount, own, self.company_id, fields.Date.context_today(self), round=False)

    def _sa_prices(self):
        """Each vendor's newest price, the best first. A vendor who said no is
        left out; a price that cannot be converted comes last, without margin."""
        self.ensure_one()
        rec = self.sudo()
        newest = {}
        for quote in rec.request_id.quote_ids.sorted('id'):
            newest[quote._sa_who()] = quote
        no = rec.request_id.sa_vendor_no_ids
        sell = rec._sa_own_money(rec.sell_unit, rec.sell_currency_id)
        rows = []
        for quote in newest.values():
            if quote.partner_id and quote.partner_id in no:
                continue
            cost = rec._sa_own_money(quote.price, quote.currency_id)
            rows.append({
                'quote': quote, 'cost': cost,
                'margin': rec.qty * (sell - cost) if cost is not None and sell is not None else None,
                'key': (cost is None, cost or 0.0, quote.delay_days or 0, quote._sa_arrived(), quote.id)})
        rows.sort(key=lambda row: row['key'])
        return rows

    def _sa_better(self, rows):
        """(row, saving) when somebody is now cheaper than the price the
        customer was quoted from by at least the setting, else (None, 0)."""
        self.ensure_one()
        base = self.sudo().request_id.best_quote_id
        now = self._sa_own_money(base.price, base.currency_id) if base else None
        if now is None or not rows or rows[0]['cost'] is None or rows[0]['quote'] == base:
            return None, 0.0
        saving = self.qty * (now - rows[0]['cost'])
        least = max(self.env['sa.ai.settings'].sudo().get_settings().late_min_saving_amount, 0.0)
        if saving <= 0.004 or saving + 0.004 < least:
            return None, 0.0
        return rows[0], saving

    @api.model
    def _sa_vendor_name(self, quote):
        return quote.partner_id.name or quote.vendor_name or _("Vendor")

    def _sa_screen_row(self):
        self.ensure_one()
        rec = self.sudo()
        request = rec.request_id
        rows = rec._sa_prices()
        better, saving = rec._sa_better(rows)
        priced = {row['quote'].partner_id.id for row in rows}
        asked = request.sourcing_vendor_ids
        no = request.sa_vendor_no_ids
        yes = request.sa_vendor_yes_ids.filtered(lambda p: p.id not in priced and p not in no)
        silent = asked.filtered(lambda p: p.id not in priced and p not in no and p not in yes)
        name = self._sa_vendor_name
        return {
            'id': rec.id, 'state': rec.state, 'at': iso(rec.paid_on), 'ref': request.ref_code or str(request.id),
            'product': rec.product_id.display_name, 'qty': rec.qty, 'unit': rec.uom_id.name,
            'customer': request.requester_name or '', 'group': request.group_id.name or '',
            'order_id': rec.order_id.id, 'order_name': rec.order_id.name,
            'paid': rec.qty * rec.sell_unit, 'sell_currency': rec.sell_currency_id.name,
            'currency': rec.company_id.currency_id.name, 'company': rec.company_id.name,
            'asked': len(asked), 'replied': len(rows), 'said_no': len(no), 'no_reply': len(silent),
            'best': {'vendor': name(rows[0]['quote']), 'cost': rows[0]['cost'], 'margin': rows[0]['margin']} if rows else False,
            'better': {'vendor': name(better['quote']), 'saving': saving, 'than': name(request.best_quote_id)} if better else False,
            'loss': bool(rows and rows[0]['margin'] is not None and rows[0]['margin'] < -0.004),
            'prices': [{
                'id': row['quote'].id, 'place': n, 'vendor': name(row['quote']), 'cost': row['cost'], 'margin': row['margin'],
                'typed': row['quote']._sa_typed_text(), 'days': row['quote'].delay_days or 0,
                'at': iso(row['quote']._sa_arrived()), 'late': row['quote'].sa_late,
                'quoted': row['quote'] == request.best_quote_id} for n, row in enumerate(rows, 1)],
            'yes': yes.mapped('name'), 'no': no.mapped('name'), 'silent': silent.mapped('name'),
            'held': request._sa_held_lines(),
        }

    @api.model
    def _sa_screen_warnings(self):
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        out = []
        if settings.pay_link_no_stock != 'sign':
            out.append(_("Customers do not pay before the goods are bought, so few items come here. "
                         "Set \"Without Stock\" to \"At the signature\" in Configuration > Payments."))
        if self.env['sa.group.request']._sa_flow_end() in ('order', 'invoice'):
            out.append(_("The order flow ends before the payment (Delivery Settings), so no items come here."))
        return out

    @api.model
    def sa_vendor_orders(self):
        if not self.env.user.has_group('sales_automation.group_sa_user'):
            raise AccessError(_("Only Sales Automation users can see the vendor orders."))
        since = fields.Datetime.now() - timedelta(days=DONE_DAYS)
        # the user's own rights and companies decide which lines
        lines = self.search(['|', ('state', 'not in', DONE), ('write_date', '>=', since)], limit=PAGE + 1)
        rows = [line._sa_screen_row() for line in lines[:PAGE]]
        todo = [row for row in rows if row['state'] in OPEN]
        totals = {key: sum(row[key] for row in todo) for key in ('asked', 'replied', 'said_no', 'no_reply')}
        totals['better'] = sum(1 for row in todo if row['better'])
        return {'rows': rows, 'more': len(lines) > PAGE, 'warnings': self._sa_screen_warnings(), 'totals': totals}
