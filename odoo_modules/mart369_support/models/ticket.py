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

    def _mart369_say(self, text, from_customer=True):
        """Put one line of the conversation on the ticket.

        The transcript was `sessionStorage` and gone when the tab closed, which
        is why an operator picking a ticket up had no idea what had been said.
        """
        self.ensure_one()
        if not (text or '').strip():
            return False
        body = (text or '').strip()
        self.sudo().message_post(
            body=body,
            author_id=self.partner_id.id if from_customer else self.env.user.partner_id.id,
            message_type='comment',
        )
        if not from_customer and not self.answered_at:
            self.sudo().write({'answered_at': fields.Datetime.now(),
                               'state': 'open',
                               'user_id': self.env.user.id})
        return True

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
        """The conversation, oldest first, as the panel draws it."""
        self.ensure_one()
        messages = self.sudo().message_ids.filtered(
            lambda m: m.message_type == 'comment' and m.body)
        rows = []
        for message in reversed(messages[:limit]):
            mine = message.author_id == self.partner_id
            rows.append({
                'from': 'me' if mine else 'agent',
                'text': message.body,
                'at': int(message.date.timestamp() * 1000) if message.date else None,
            })
        return rows

    def _mart369_serialize(self):
        self.ensure_one()
        return {
            'id': str(self.id),
            'ref': self.name,
            'state': self.state,
            'order': self.order_id.mart369_ref or None,
            'messages': self._mart369_transcript(),
        }
