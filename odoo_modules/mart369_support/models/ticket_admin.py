"""What the app's own admin console reads, and what the support desk draws.

Until now nobody could answer a ticket. Every route in controllers/support_api.py
is fenced to `request.env.user.partner_id` - correctly, they are the shopper's
own conversation - so a customer could ask for a person and there was no screen
anywhere that told a person they had.

Three things are kept apart here on purpose.

**The shopper's serializer is not widened.** `_mart369_serialize()` is what the
chat panel receives. Growing it to carry the customer's name, who is handling
the ticket and how long it has waited is how one staff screen ends up leaking
the next customer's details. Staff get their own shape, built here.

**The next step is the server's.** A ticket that nobody has taken wants "Take
it"; one being handled wants "Answered". The payload says what the button is
called and which method it calls, so the words on the button cannot drift from
what pressing it does.

**The wait is computed, not read.** `waiting_minutes` is a stored compute on
`opened_at` and `answered_at` (ticket.py:79). Neither of those changes while a
ticket sits unanswered, so the stored value is frozen at the moment the ticket
was created - the longest-waiting ticket in the shop reports a wait of nought.
The stored field is still right for a ticket that has been answered, and it is
what grouping and sorting use, so it stays; but every number a human reads
comes from `_mart369_waited()` below.
"""

from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .ticket import OPEN_STATES, STATE_CHOICES

STATE_LABELS = dict(STATE_CHOICES)

# What the one button on a row is called, by the state the ticket is in now,
# and the method it calls. `None` means there is nothing left to do.
NEXT_STEP = {
    'new': {'label': 'Take it', 'action': 'take'},
    'open': {'label': 'Answered', 'action': 'done'},
    'waiting': {'label': 'Answered', 'action': 'done'},
    'done': None,
    'cancelled': None,
}

# Which tickets each tab is asking for. 'needs' is the one the screen opens on:
# somebody is waiting and nobody has replied yet.
TABS = {
    'needs': [('state', 'in', list(OPEN_STATES)), ('answered_at', '=', False)],
    'new': [('state', '=', 'new')],
    'open': [('state', '=', 'open')],
    'waiting': [('state', '=', 'waiting')],
    'done': [('state', '=', 'done')],
    'cancelled': [('state', '=', 'cancelled')],
    'all': [],
}

SORTS = {
    'old': 'opened_at asc, id asc',
    'new': 'opened_at desc, id desc',
}

MAX_ROWS = 100

# The shopper side caps what it accepts at 500 (support_api.py). A reply is
# held to the same, so neither direction can post something the other cannot.
MAX_REPLY = 500

# Past this, a ticket is late. The same half hour the backend kanban already
# flags on (views/ticket_views.xml), so the two screens agree about which
# tickets are the embarrassing ones.
LATE_MINUTES = 30


class Mart369TicketAdmin(models.Model):
    _inherit = 'mart369.ticket'

    # ------------------------------------------------------------ the wait

    def _mart369_waited(self):
        """Minutes this customer has been waiting, worked out now.

        Not `waiting_minutes`. See the module docstring - the stored one is
        frozen for exactly the tickets somebody needs to see.
        """
        self.ensure_one()
        if not self.opened_at:
            return 0
        end = self.answered_at or fields.Datetime.now()
        return max(0, int((end - self.opened_at).total_seconds() // 60))

    # ------------------------------------------------------- serializing

    def _mart369_admin_row(self):
        """One ticket as the queue draws it, without its conversation."""
        self.ensure_one()
        waited = self._mart369_waited()
        return {
            'id': self.id,
            'ref': self.name or '',
            'customer': self.partner_id.display_name or 'Someone',
            'subject': self.subject or '',
            'order': self.order_ref or None,
            'state': self.state,
            'stateLabel': STATE_LABELS.get(self.state, self.state),
            'assignee': self.user_id.name or None,
            'assigneeId': self.user_id.id or None,
            'openedAt': int(self.opened_at.timestamp() * 1000) if self.opened_at else None,
            'answeredAt': int(self.answered_at.timestamp() * 1000) if self.answered_at else None,
            'waited': waited,
            # Answered is not the same as replied-to-recently, and only one of
            # them is embarrassing. This is the one the tiles count.
            'late': bool(not self.answered_at
                         and self.state in OPEN_STATES
                         and waited >= LATE_MINUTES),
            'replies': len(self._mart369_transcript()),
            'next': NEXT_STEP.get(self.state),
        }

    def _mart369_admin_detail(self):
        """The row, plus the conversation the panel is opened to read."""
        self.ensure_one()
        detail = self._mart369_admin_row()
        detail['messages'] = self._mart369_transcript()
        # Hidden rather than disabled, the way the returns desk does it: there
        # is nothing to reply to once a ticket is closed.
        detail['canReply'] = self.state in OPEN_STATES
        return detail

    # ------------------------------------------------------------ reading

    @api.model
    def _mart369_admin_domain(self, tab=None, q=None, mine=None, assignee=None):
        domain = list(TABS.get(tab or 'needs', TABS['needs']))
        if mine:
            domain += [('user_id', '=', self.env.uid)]
        elif assignee:
            domain += [('user_id', '=', int(assignee))]
        term = (q or '').strip()
        if term:
            domain += ['|', '|',
                       ('name', 'ilike', term),
                       ('partner_id.name', 'ilike', term),
                       ('subject', 'ilike', term)]
        return domain

    @api.model
    def mart369_admin_list(self, tab=None, q=None, mine=None, assignee=None,
                           sort=None, limit=30, offset=0):
        """One page of the queue, the tile counts, and who can be assigned."""
        domain = self._mart369_admin_domain(tab=tab, q=q, mine=mine, assignee=assignee)
        limit = max(1, min(int(limit or 30), MAX_ROWS))
        offset = max(0, int(offset or 0))
        order = SORTS.get(sort or 'old', SORTS['old'])
        tickets = self.search(domain, limit=limit, offset=offset, order=order)
        payload = self.mart369_admin_counts()
        payload.update({
            'tickets': [t._mart369_admin_row() for t in tickets],
            'total': self.search_count(domain),
            'limit': limit,
            'offset': offset,
            'states': [{'key': key, 'label': label} for key, label in STATE_CHOICES],
            'staff': self._mart369_admin_staff(),
        })
        return payload

    @api.model
    def _mart369_admin_staff(self):
        """Who a ticket can be handed to: whoever has already handled one, plus
        whoever is looking now. Cheaper and more useful than every internal
        user in the database, most of whom never touch support."""
        handled = self.search([('user_id', '!=', False)]).mapped('user_id')
        return [{'id': user.id, 'name': user.name}
                for user in (handled | self.env.user)]

    @api.model
    def mart369_admin_counts(self):
        """The tiles, and the number on each tab.

        `search_count` rather than reading rows: the sidebar badge asks for
        this every minute and wants numbers, not tickets.
        """
        counts = {key: self.search_count(where) for key, where in TABS.items()}

        # The longest anybody is currently waiting. Read off `opened_at` rather
        # than the stored `waiting_minutes`, which never moves for an
        # unanswered ticket - the exact tickets this tile is about.
        oldest = self.search(TABS['needs'], order='opened_at asc', limit=1)
        longest = oldest._mart369_waited() if oldest else 0

        today = fields.Datetime.to_datetime(fields.Date.context_today(self))
        return {
            'counts': counts,
            'longest': longest,
            'late': self.search_count(
                TABS['needs'] + [('opened_at', '<=', fields.Datetime.now()
                                  - timedelta(minutes=LATE_MINUTES))]),
            'answeredToday': self.search_count([('answered_at', '>=', today)]),
        }

    # --------------------------------------------------------- one ticket

    @api.model
    def _mart369_admin_find(self, ref):
        """One ticket by the reference both screens show.

        By reference rather than id for the same reason the orders console does
        it: that is what is on the screen. Not sudo'd, so Odoo's access rules
        apply - see the controller's docstring.
        """
        if not ref or not isinstance(ref, str):
            return self.browse()
        return self.search([('name', '=', ref)], limit=1)

    @api.model
    def mart369_admin_detail(self, ref):
        """Everything the panel draws, or {} if there is no such ticket.

        Public because the desk reaches these over `orm.call`, which refuses a
        name starting with an underscore.
        """
        ticket = self._mart369_admin_find(ref)
        return ticket._mart369_admin_detail() if ticket else {}

    # ------------------------------------------------------------ writing

    def mart369_action_wait(self):
        """Waiting on the customer.

        The fifth state has existed since the model was written and no button
        anywhere could reach it, so a ticket parked on a customer looked
        exactly like one nobody had touched - and was counted as one.
        """
        for ticket in self:
            ticket.write({'state': 'waiting'})
        return True

    @api.model
    def mart369_admin_reply(self, ref, text):
        """Answer the customer.

        Straight through `_mart369_say(from_customer=False)`, which already
        stamps `answered_at`, moves a new ticket to being handled and puts the
        replier's name on it. Doing any of that here as well would be a second
        opinion about what a reply means.
        """
        ticket = self._mart369_admin_find(ref)
        if not ticket:
            raise UserError(self.env._("That ticket no longer exists."))
        said = (text or '').strip()
        if not said:
            raise UserError(self.env._("Write something before sending it."))
        if ticket.state not in OPEN_STATES:
            raise UserError(self.env._(
                "This ticket is closed. Reopen it before replying."))
        ticket._mart369_say(said[:MAX_REPLY], from_customer=False)
        return ticket._mart369_admin_detail()

    @api.model
    def mart369_admin_advance(self, ref, action):
        """Take it, answer it, drop it, or park it on the customer.

        The screen sends the action the server gave it in `next`, rather than a
        state it worked out for itself.
        """
        ticket = self._mart369_admin_find(ref)
        if not ticket:
            raise UserError(self.env._("That ticket no longer exists."))
        method = {
            'take': ticket.mart369_action_take,
            'done': ticket.mart369_action_done,
            'drop': ticket.mart369_action_drop,
            'wait': ticket.mart369_action_wait,
        }.get(action)
        if not method:
            raise UserError(self.env._("That is not something a ticket can do."))
        method()
        return ticket._mart369_admin_row()

    @api.model
    def mart369_admin_assign(self, ref, user_id=None):
        """Hand a ticket to somebody, or let it go.

        A falsy `user_id` clears it rather than being refused: taking a name
        off a ticket is how it goes back to the pile.
        """
        ticket = self._mart369_admin_find(ref)
        if not ticket:
            raise UserError(self.env._("That ticket no longer exists."))
        ticket.write({'user_id': int(user_id) if user_id else False})
        return ticket._mart369_admin_row()
