"""The numbers above 369 Mart -> Support.

Same contract as the customers, payments, orders, reviews, referrals and rewards
strips: one ORM call, tiles that switch the view's own named filters on.
"""

from datetime import timedelta

from odoo import api, fields, models

OPEN_STATES = ('new', 'open', 'waiting')


class Mart369Ticket(models.Model):
    _inherit = 'mart369.ticket'

    @api.model
    def mart369_support_dashboard(self):
        today = fields.Date.context_today(self)
        start = fields.Datetime.to_datetime(today)

        waiting = self.search([('state', '=', 'new')])
        open_tickets = self.search([('state', 'in', list(OPEN_STATES))])
        answered = self.search([('answered_at', '!=', False)])

        # Average wait only over tickets somebody really answered: counting the
        # unanswered ones would flatter the number the longer they are ignored.
        minutes = answered.mapped('waiting_minutes')
        average = round(sum(minutes) / len(minutes)) if minutes else 0
        longest = max(waiting.mapped('waiting_minutes') or [0])

        return {
            'waiting': len(waiting),
            'open': len(open_tickets),
            'today': self.search_count([('opened_at', '>=', start)]),
            'average': average,
            'longest': longest,
            'unanswered': len(open_tickets.filtered(lambda t: not t.answered_at)),
            'mine': self.search_count([
                ('user_id', '=', self.env.user.id),
                ('state', 'in', list(OPEN_STATES)),
            ]),
            'asked': self._mart369_ticket_bars(today),
        }

    @api.model
    def _mart369_ticket_bars(self, today, days=14):
        since = fields.Datetime.to_datetime(today - timedelta(days=days - 1))
        rows = self._read_group(
            [('opened_at', '>=', since)],
            groupby=['opened_at:day'], aggregates=['__count'])
        counted = {}
        for when, count in rows:
            if when:
                counted[fields.Date.to_date(when)] = count
        out = []
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            out.append({'day': day.strftime('%d %b'), 'count': counted.get(day, 0)})
        return out
