"""The numbers above 369 Mart -> Orders.

One call, because the strip is drawn on every board refresh and five separate
round trips to count five things is the quickest way to make a screen feel slow.
Counted with `search_count` and one `_read_group` rather than by reading orders
into memory: the board is the busiest screen in the backend and it is looked at
all day.

The same shape as `mart369_auth`'s customer dashboard and `mart369_payment`'s
payments one, so the three strips stay interchangeable.
"""

from datetime import timedelta

from odoo import api, fields, models

LIVE_STATES = ('placed', 'packed', 'shipped', 'out')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def mart369_order_dashboard(self):
        """Everything the strip prints, in one call."""
        today = fields.Date.context_today(self)
        start = fields.Datetime.to_datetime(today)
        currency = self.env.company.currency_id
        mine = [('mart369_ref', '!=', False), ('mart369_state', 'not in', (False, 'draft'))]

        today_orders = self.search(mine + [('mart369_placed_at', '>=', start)])
        today_value = self._mart369_in_company_currency(today_orders)

        packing = self.search_count(mine + [('mart369_state', '=', 'placed')])
        out = self.search_count(mine + [('mart369_state', '=', 'out')])
        late = self.search_count(mine + [('mart369_late', '=', True)])

        cash_orders = self.search(mine + [
            ('mart369_state', 'in', list(LIVE_STATES)),
            ('mart369_method', '=', 'cod'),
        ])
        returns = self.env['mart369.order.return'].search_count(
            [('state', 'in', ('requested', 'pickup', 'picked'))])

        return {
            'today': len(today_orders),
            'today_value': currency.format(today_value),
            'packing': packing,
            'out': out,
            'late': late,
            'live': self.search_count(mine + [('mart369_state', 'in', list(LIVE_STATES))]),
            'cash': currency.format(self._mart369_in_company_currency(cash_orders)),
            'cash_count': len(cash_orders),
            'returns': returns,
            'placed': self._mart369_placed_bars(today),
        }

    @api.model
    def _mart369_in_company_currency(self, orders):
        """Add orders up in one currency.

        An order carries the currency its pricelist gave it, which is not
        necessarily the company's. Summing `amount_total` across them and
        printing the result with the company symbol is how a board ends up
        showing "830.000 OMR" over cards that say "$280.00" - a number that is
        not true in either currency.
        """
        company = self.env.company
        target = company.currency_id
        total = 0.0
        today = fields.Date.context_today(self)
        for order in orders:
            source = order.currency_id or target
            if source == target:
                total += order.amount_total
            else:
                total += source._convert(
                    order.amount_total, target, company,
                    order.date_order and order.date_order.date() or today)
        return total

    @api.model
    def _mart369_placed_bars(self, today, days=14):
        """Orders a day for the last fortnight, for the sparkline."""
        since = fields.Datetime.to_datetime(today - timedelta(days=days - 1))
        rows = self._read_group(
            [('mart369_ref', '!=', False),
             ('mart369_state', 'not in', (False, 'draft')),
             ('mart369_placed_at', '>=', since)],
            groupby=['mart369_placed_at:day'],
            aggregates=['__count'],
        )
        counted = {}
        for when, count in rows:
            if when:
                counted[fields.Date.to_date(when)] = count
        out = []
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            out.append({'day': day.strftime('%d %b'), 'count': counted.get(day, 0)})
        return out
