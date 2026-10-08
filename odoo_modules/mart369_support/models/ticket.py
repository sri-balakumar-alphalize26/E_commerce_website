"""Tickets.

Asking for a human used to be three `setTimeout` calls (`SupportBot.jsx:149`).
The panel said "Finding an available agent…", then "Anjali joined the chat",
then Anjali said she could see your recent orders. No agent existed. Nothing was
recorded. The transcript lived in `sessionStorage` and died with the tab, and
the bot told the customer it had "noted this against your order" when it had
noted nothing anywhere.

A ticket is what makes that sentence true. It carries the conversation on
`mail.thread`, so an operator opening it sees everything the customer already
said and does not make them say it twice - which is the actual complaint behind
most of these.

No helpdesk app: it is not available on this installation, and a ticket with a
status, an owner and a thread is most of what one would have given us anyway.
"""

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

STATE_CHOICES = [
    ('new', 'Waiting'),
    ('open', 'Being handled'),
    ('waiting', 'Waiting on customer'),
    ('done', 'Answered'),
    ('cancelled', 'Dropped'),
]

OPEN_STATES = ('new', 'open', 'waiting')


class Mart369Ticket(models.Model):
    _name = 'mart369.ticket'
    _description = '369 Mart Support Ticket'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: self.env._('New'))
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, ondelete='cascade',
        index=True, tracking=True)
    order_id = fields.Many2one(
        'sale.order', string='About order', ondelete='set null', index=True,
        tracking=True,
        help="The order the conversation was about, when the bot could tell.")
    order_ref = fields.Char(
        related='order_id.mart369_ref', store=True, string='Order number',
        help="Shown instead of Odoo's own order name, because 369M-9001 is what "
             "the customer quoted and what an operator searches for.")

    state = fields.Selection(
        STATE_CHOICES, string='Status', required=True, default='new', index=True,
        tracking=True, group_expand='_mart369_state_groups')
    subject = fields.Char(
        string='What they asked', required=True,
        help="The message that made them ask for a person.")
    user_id = fields.Many2one(
        'res.users', string='Handled by', ondelete='set null', tracking=True)

    opened_at = fields.Datetime(
        string='Asked at', default=fields.Datetime.now, readonly=True)
    answered_at = fields.Datetime(string='First answered', readonly=True, copy=False)
    closed_at = fields.Datetime(string='Closed', readonly=True, copy=False)

    waiting_minutes = fields.Integer(
        string='Waiting', compute='_compute_waiting', store=True,
        help="Minutes between the customer asking and somebody answering. "
             "Still counting while nobody has.")

    @api.model
    def _mart369_state_groups(self, states, domain):
        """Columns in the order a ticket really moves."""
        return [key for key, __ in STATE_CHOICES]

    @api.depends('opened_at', 'answered_at')
    def _compute_waiting(self):
        now = fields.Datetime.now()
        for ticket in self:
            start = ticket.opened_at
            if not start:
                ticket.waiting_minutes = 0
                continue
            end = ticket.answered_at or now
            ticket.waiting_minutes = max(0, int((end - start).total_seconds() // 60))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', self.env._('New')) == self.env._('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'mart369.ticket') or self.env._('New')
        return super().create(vals_list)

    # -------------------------------------------------------------- opening

    @api.model
    def _mart369_open(self, partner, subject, order=None):
        """Open a ticket, or hand back the one already waiting.

        A customer who asks for an agent twice in one afternoon wants the same
        conversation, not two of them in the queue.
        """
        existing = self.sudo().search([
            ('partner_id', '=', partner.id),
            ('state', 'in', list(OPEN_STATES)),
        ], limit=1)
        if existing:
            return existing
        if order is None:
            order = self.env['sale.order'].sudo().search([
                ('partner_id', '=', partner.id),
                ('mart369_ref', '!=', False),
                ('mart369_state', 'in', ('placed', 'packed', 'shipped', 'out')),
            ], order='mart369_placed_at desc', limit=1)
        return self.sudo().create({
            'partner_id': partner.id,
            'subject': (subject or 'Support request')[:200],
            'order_id': order.id if order else False,
        })

    def _mart369_say(self, text, from_customer=True, from_bot=False, reply_to=None):
        """Put one line of the conversation on the ticket, and hand it back.

        The transcript was `sessionStorage` and gone when the tab closed, which
        is why an operator picking a ticket up had no idea what had been said.

        `reply_to` is the customer's line this one answers. For a team reply,
        None means "the oldest one nobody has answered" and False means none.
        The bot quotes only what it is told to: its lines are bookkeeping, so
        a question it already answered is not the next one tagged.
        """
        self.ensure_one()
        if not (text or '').strip():
            return False
        body = (text or '').strip()
        team = not from_customer and not from_bot
        quote = self._mart369_quote_for(reply_to, auto=team)
        # The bot's own lines (the conversation before the hand-over, and its
        # "you're in the queue") are signed by OdooBot, so the panel can tell
        # them from a person's and the ticket shows who really said what.
        if from_bot:
            author = self.env.ref('base.partner_root')
        elif from_customer:
            author = self.partner_id
        else:
            author = self.env.user.partner_id
        message = self.sudo().with_context(mart369_quoted=True).message_post(
            body=body, author_id=author.id, message_type='comment')
        message.sudo().write({'mart369_chat': True,
                              'mart369_reply_to_id': quote.id or False})
        # `message_ids` hangs off res_id, which is not a real relation, so a
        # new message does not reach a list already read in this transaction.
        self.invalidate_recordset(['message_ids'])
        if team and not self.answered_at:
            self.sudo().write({'answered_at': fields.Datetime.now(),
                               'state': 'open',
                               'user_id': self.env.user.id})
        return message

    # ------------------------------------------------------------ quoting

    def _mart369_comments(self):
        """The conversation on this ticket, oldest first: the chat's own
        lines, and messages staff sent from Odoo - never a Log note.

        Searched rather than read off `message_ids`, which can be stale
        within a transaction (it hangs off res_id, not a real relation)."""
        self.ensure_one()
        return self.env['mail.message'].sudo().search([
            ('model', '=', self._name), ('res_id', '=', self.id),
            ('message_type', '=', 'comment'),
        ], order='id').filtered(
            lambda m: m.body and (m.mart369_chat
                                  or not (m.subtype_id and m.subtype_id.internal)))

    def _mart369_customer_lines(self):
        """What the customer said on this ticket, oldest first."""
        self.ensure_one()
        return self._mart369_comments().filtered(lambda m: m.author_id == self.partner_id)

    def _mart369_unanswered(self):
        """The customer's lines no later line has answered, oldest first -
        so three questions and three replies pair up in order."""
        self.ensure_one()
        answered = self._mart369_comments().mapped('mart369_reply_to_id')
        return self._mart369_customer_lines() - answered

    def _mart369_quote_for(self, reply_to, auto=False):
        """The customer line a new line answers: a record or an id, False or
        0 for none, None to pick the oldest unanswered when `auto`."""
        self.ensure_one()
        empty = self.env['mail.message']
        if reply_to is None:
            return self._mart369_unanswered()[:1] if auto else empty
        if not reply_to:
            return empty
        if isinstance(reply_to, models.BaseModel):
            # Handed over by the code that just posted it: it only has to be
            # on this ticket. A customer's chat must never fail on a quote.
            line = reply_to.sudo()[:1]
            return line if line.model == self._name and line.res_id == self.id else empty
        wanted = reply_to
        try:
            wanted = int(wanted)
        except (TypeError, ValueError):
            wanted = 0
        line = self._mart369_customer_lines().filtered(lambda m: m.id == wanted)
        if not line:
            raise UserError(self.env._("That is not something this customer said on this ticket."))
        return line

    def message_post(self, **kwargs):
        """A reply typed in Odoo's own chatter is tagged the way one from the
        console is. `_mart369_say` has already chosen, so it says so."""
        message = super().message_post(**kwargs)
        if self.env.context.get('mart369_quoted') or len(self) != 1 or not message:
            return message
        self.invalidate_recordset(['message_ids'])
        bot = self.env.ref('base.partner_root')
        if (message.message_type == 'comment' and message.author_id
                and message.author_id not in (self.partner_id | bot)
                and not (message.subtype_id and message.subtype_id.internal)
                and not message.mart369_reply_to_id):
            pick = self._mart369_unanswered()[:1]
            if pick:
                message.sudo().mart369_reply_to_id = pick
        return message

    # ------------------------------------------------------------- operator

    def mart369_action_take(self):
        for ticket in self:
            ticket.write({'user_id': self.env.user.id,
                          'state': 'open' if ticket.state == 'new' else ticket.state})
        return True

    def mart369_action_done(self):
        for ticket in self:
            ticket.write({'state': 'done', 'closed_at': fields.Datetime.now()})
        return True

    def mart369_action_drop(self):
        for ticket in self:
            ticket.write({'state': 'cancelled', 'closed_at': fields.Datetime.now()})
        return True

    # --------------------------------------------------------- serializing

    def _mart369_transcript(self, limit=60):
        """The conversation, oldest first, as the panel draws it.

        Plain text, because that is what the panel draws: it puts the text
        into a bubble as a string, so a body handed over as mail HTML came
        back on screen with its paragraph tags showing.
        """
        self.ensure_one()
        # Never a Log note: those are staff writing to each other.
        messages = self._mart369_comments()[-limit:]
        bot = self.env.ref('base.partner_root')
        rows = []
        for message in messages:
            said = html2plaintext(message.body).strip()
            if not said:
                continue
            if message.author_id == self.partner_id:
                row = {'from': 'me'}
            elif message.author_id == bot:
                row = {'from': 'bot'}
            else:
                # The person who really answered, by first name.
                row = {'from': 'agent', 'name': (message.author_id.name or 'Support').split()[0]}
                # The question it answers, shown above it like a WhatsApp reply.
                quoted = message.mart369_reply_to_id
                if quoted:
                    # Its first line only, as WhatsApp previews a reply; the
                    # whole question is a tap away.
                    lines = [ln.strip() for ln in html2plaintext(quoted.body or '').splitlines()]
                    row['replyTo'] = {
                        'id': quoted.id,
                        'text': next((ln for ln in lines if ln), '')[:140],
                        'from': 'me' if quoted.author_id == self.partner_id else 'bot',
                    }
            row.update(id=message.id, text=said,
                       at=int(message.date.timestamp() * 1000) if message.date else None)
            rows.append(row)
        return rows

    def _mart369_serialize(self):
        self.ensure_one()
        return {
            'id': str(self.id),
            'ref': self.name,
            'state': self.state,
            'order': self.order_id.mart369_ref or None,
            'closed': self.state not in OPEN_STATES,
            'messages': self._mart369_transcript(),
        }
