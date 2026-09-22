"""The numbers above 369 Mart -> Support.

Same contract as the customers, payments, orders, reviews, referrals and rewards
strips: one ORM call, tiles that switch the view's own named filters on.

**The waits here are worked out, not read.** `waiting_minutes` is a stored
compute on `opened_at` and `answered_at` (ticket.py), and neither of those
changes while a ticket sits unanswered - so it stays at whatever it was when
the ticket was created, which is nought. Reading it here reported the shortest
possible wait for exactly the tickets this strip exists to surface, and
disagreed with the desk next door, which has always computed it live.

The stored field stays on the model: it is right once a ticket has been
answered, and it is what grouping and sorting in the list view use. It is only
wrong to *read* for a ticket still waiting, which is what `_mart369_waited()`
in ticket_admin.py is for. Both screens now ask the same question the same way.
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

        waiting_domain = [('state', '=', 'new')]
        open_domain = [('state', 'in', list(OPEN_STATES))]

        # Average wait only over tickets somebody really answered: counting the
        # unanswered ones would flatter the number the longer they are ignored.
        answered = self.search([('answered_at', '!=', False)])
        minutes = [t._mart369_waited() for t in answered]
        average = round(sum(minutes) / len(minutes)) if minutes else 0

        # The longest anybody is still waiting. Read off `opened_at` rather
        # than the stored field, which never moves for an unanswered ticket.
        waits = [t._mart369_waited() for t in self.search(waiting_domain)]
        longest = max(waits) if waits else 0

        return {
            'waiting': self.search_count(waiting_domain),
            'open': self.search_count(open_domain),
            'today': self.search_count([('opened_at', '>=', start)]),
            'average': average,
            'longest': longest,
            'unanswered': self.search_count(
                open_domain + [('answered_at', '=', False)]),
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
