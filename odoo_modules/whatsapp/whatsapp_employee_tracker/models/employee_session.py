import logging
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class EmployeeWhatsAppSession(models.Model):
    """Links an employee to their company WhatsApp session with tracking."""
    _name = 'wa.employee.session'
    _description = 'Employee WhatsApp Session Assignment'
    _rec_name = 'employee_id'
    _order = 'employee_id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        required=True, ondelete='restrict', index=True,
    )
    session_id = fields.Many2one(
        'whatsapp.session', string='WhatsApp Session',
        required=True, ondelete='restrict', index=True,
        help='The WhatsApp session assigned to this employee.',
    )
    # 26 Nov 2026: the branch, so switching branch shows only its people.
    company_id = fields.Many2one(
        'res.company', string='Branch', compute='_compute_company_id', store=True, index=True,
    )
    department_id = fields.Many2one(
        related='employee_id.department_id', store=True,
        string='Department',
    )
    manager_id = fields.Many2one(
        related='employee_id.parent_id', store=True,
        string='Manager',
    )
    job_title = fields.Char(
        related='employee_id.job_title', store=True,
    )
    session_status = fields.Selection(
        related='session_id.status', string='WA Status',
    )
    phone_number = fields.Char(
        'Assigned Phone', required=True,
        help='Company WhatsApp number assigned to this employee.',
    )
    active = fields.Boolean(default=True)
    monitoring_enabled = fields.Boolean(
        'Enable Monitoring', default=True,
        help='Track all messages on this session.',
    )
    # ---- Auto-Reply Settings ----
    auto_reply_enabled = fields.Boolean(
        'Enable Auto-Reply', default=False,
        help='Automatically reply with product suggestions when employee does not respond in time.',
    )
    auto_reply_timeout = fields.Integer(
        'Reply Timeout (seconds)', default=120,
        help='Seconds to wait for employee response before auto-replying. Default: 120 (2 minutes). Set low for testing.',
    )
    auto_reply_greeting = fields.Char(
        'Greeting Message', default='Hi! Thank you for reaching out.',
        help='Greeting text before product suggestions.',
    )
    auto_reply_no_match = fields.Char(
        'No Match Message',
        default='Sorry, I could not find matching products. An agent will assist you shortly.',
        help='Message when no products match the query.',
    )
    auto_reply_max_products = fields.Integer(
        'Max Products to Suggest', default=5,
    )
    auto_reply_bargain_enabled = fields.Boolean(
        'Enable Price Bargain', default=True,
        help='Allow the assistant to negotiate price down to the sale price for new customers.',
    )
    auto_reply_hide_quantity = fields.Boolean(
        'Hide Stock Quantity', default=True,
        help='Do not show stock quantity to the customer in product detail.',
    )
    auto_reply_stock_restrict = fields.Boolean(
        'Restrict to Available Stock', default=False,
        help='Block orders above on-hand stock. Off = allow any quantity.',
    )
    auto_reply_ask_delivery = fields.Boolean(
        'Ask Delivery Address', default=True,
        help='Ask the customer for a delivery address after ordering.',
    )
    auto_reply_payment_enabled = fields.Boolean(
        'Enable Payment Step', default=True,
        help='Send a payment link + Cash on Delivery option after ordering.',
    )
    auto_reply_cod_enabled = fields.Boolean(
        'Enable Cash on Delivery', default=True,
    )
    auto_reply_auto_invoice = fields.Boolean(
        'Automatic Invoice (off = Agent verify)', default=True,
        help='ON: after payment auto-create/post invoice + send PDF. OFF: send a receipt + "agent will verify"; agent posts the invoice in 369ai to send it.',
    )
    auto_reply_company_id = fields.Many2one('res.company', string='Order Company', required=True, default=lambda self: self.env.company)
    auto_reply_payment_provider_id = fields.Many2one(
        'payment.provider', string='Payment Provider (optional)',
    )
    notes = fields.Text('Notes')

    # ---- Computed Stats ----
    total_messages = fields.Integer(
        compute='_compute_stats', string='Total Messages', store=True,
    )
    total_sent = fields.Integer(
        compute='_compute_stats', string='Messages Sent', store=True,
    )
    total_received = fields.Integer(
        compute='_compute_stats', string='Messages Received', store=True,
    )
    unique_contacts = fields.Integer(
        compute='_compute_stats', string='Unique Contacts', store=True,
    )
    alert_count = fields.Integer(
        compute='_compute_alert_count', string='Active Alerts',
    )
    avg_response_minutes = fields.Float(
        compute='_compute_response_time', string='Avg Response (min)',
    )
    last_activity = fields.Datetime(
        compute='_compute_last_activity', string='Last Activity',
    )
    quality_score = fields.Float(
        compute='_compute_quality_score', string='Quality Score',
    )
    today_sent = fields.Integer(
        compute='_compute_today_stats', string='Sent Today',
    )
    today_received = fields.Integer(
        compute='_compute_today_stats', string='Received Today',
    )

    # One employee on one number. Several per employee over time, one now:
    # the old ones are archived and keep their chats (23 Nov 2026).
    own_number = fields.Char('Number (digits)', compute='_compute_own_number', store=True, index=True)
    since = fields.Datetime('From', default=fields.Datetime.now, readonly=True, copy=False)
    until = fields.Datetime('Until', readonly=True, copy=False)
    has_chats = fields.Boolean(compute='_compute_has_chats')

    _employee_now_unique = models.UniqueIndex(
        '(employee_id) WHERE active IS TRUE', 'Each employee can only have one WhatsApp number at a time.')
    _session_now_unique = models.UniqueIndex(
        '(session_id) WHERE active IS TRUE', 'Each WhatsApp session can only be assigned to one employee.')

    session_number = fields.Char(compute='_compute_session_number')
    free_session_ids = fields.Many2many('whatsapp.session', compute='_compute_free_sessions')

    @api.depends('auto_reply_company_id', 'session_id.company_id')
    def _compute_company_id(self):
        """The branch chosen when the number was connected, else the number's own."""
        for rec in self:
            rec.company_id = rec.auto_reply_company_id or rec.session_id.company_id

    @api.depends('session_id')
    def _compute_session_number(self):
        for rec in self:
            rec.session_number = rec.sudo().session_id.authorized_number or ''

    @api.depends('session_id')
    def _compute_free_sessions(self):
        taken = self.env['wa.employee.session'].sudo().search([]).session_id
        free = self.env['whatsapp.session'].search([('active', '=', True)]) - taken
        for rec in self:
            rec.free_session_ids = free | rec.session_id

    @api.onchange('session_id')
    def _onchange_session_number(self):
        if self.session_number:
            self.phone_number = '+' + self.session_number

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('phone_number') and vals.get('session_id'):
                number = self.env['whatsapp.session'].sudo().browse(vals['session_id']).authorized_number
                if number:
                    vals['phone_number'] = '+' + number
        return super().create(vals_list)

    def action_connect_new(self):
        return self.env['whatsapp.session'].action_connect_new()

    @api.constrains('phone_number', 'session_id')
    def _check_phone_is_the_sessions(self):
        """The Assigned Phone is the session's own number, once the panel has
        told it (23 Nov 2026)."""
        digits = lambda text: ''.join(c for c in (text or '') if c.isdigit())  # noqa: E731
        for rec in self:
            number = digits(rec.session_id.authorized_number)
            if rec.active and number and digits(rec.phone_number)[-9:] != number[-9:]:
                raise ValidationError(_(
                    "The session '%(session)s' is the number +%(number)s; the Assigned Phone is %(phone)s.",
                    session=rec.session_id.name, number=number, phone=rec.phone_number or '-'))

    # ----------------------------------------------------------
    # Computed Fields
    # ----------------------------------------------------------
    @api.depends('session_id')
    def _compute_stats(self):
        Message = self.env['whatsapp.message']
        for rec in self:
            mine = [('employee_session_id', '=', rec.id)] if isinstance(rec.id, int) else [('id', '=', 0)]
            counts = {direction: n for direction, n in Message._read_group(mine, ['direction'], ['__count'])}
            rec.total_messages = sum(counts.values())
            rec.total_sent = counts.get('outgoing', 0)
            rec.total_received = counts.get('incoming', 0)
            rec.unique_contacts = Message._read_group(mine, [], ['phone:count_distinct'])[0][0] or 0

    def _compute_alert_count(self):
        for rec in self:
            rec.alert_count = self.env['wa.keyword.alert.log'].search_count([
                ('employee_session_id', '=', rec.id),
                ('status', '=', 'new'),
            ])

    def _compute_response_time(self):
        """Calculate average response time for outgoing replies."""
        for rec in self:
            if not rec.session_id:
                rec.avg_response_minutes = 0.0
                continue

            # Get conversations with response times
            scores = self.env['wa.quality.score'].search([
                ('employee_session_id', '=', rec.id),
            ])
            if scores:
                avg = sum(scores.mapped('avg_response_minutes')) / len(scores)
                rec.avg_response_minutes = round(avg, 1)
            else:
                rec.avg_response_minutes = 0.0

    def _compute_last_activity(self):
        for rec in self:
            if rec.session_id:
                last_msg = self.env['whatsapp.message'].search([
                    ('employee_session_id', '=', rec.id),
                ], order='create_date desc', limit=1)
                rec.last_activity = last_msg.create_date if last_msg else False
            else:
                rec.last_activity = False

    def _compute_quality_score(self):
        for rec in self:
            scores = self.env['wa.quality.score'].search([
                ('employee_session_id', '=', rec.id),
            ])
            if scores:
                rec.quality_score = round(
                    sum(scores.mapped('score')) / len(scores), 1
                )
            else:
                rec.quality_score = 0.0

    def _compute_today_stats(self):
        today_start = fields.Datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for rec in self:
            if rec.session_id:
                domain = [
                    ('employee_session_id', '=', rec.id),
                    ('create_date', '>=', today_start),
                ]
                rec.today_sent = self.env['whatsapp.message'].search_count(
                    domain + [('direction', '=', 'outgoing')]
                )
                rec.today_received = self.env['whatsapp.message'].search_count(
                    domain + [('direction', '=', 'incoming')]
                )
            else:
                rec.today_sent = 0
                rec.today_received = 0

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------
    def action_view_messages(self):
        """View all messages for this employee's session."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Messages - %s', self.employee_id.name),
            'res_model': 'whatsapp.message',
            'view_mode': 'list,form',
            'domain': [('employee_session_id', '=', self.id)],
            'context': {'search_default_group_direction': 1},
        }

    def action_view_alerts(self):
        """View keyword alerts for this employee."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Alerts - %s', self.employee_id.name),
            'res_model': 'wa.keyword.alert.log',
            'view_mode': 'kanban,list,form',
            'domain': [('employee_session_id', '=', self.id)],
        }

    def action_open_chats(self):
        """Open employee chats from dashboard kanban card click."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'wa_chat_split_view',
            'name': _('Chats - %s', self.employee_id.name),
            'context': {'active_employee_session_id': self.id},
        }

    def action_full_history(self):
        """Every number this employee ever had."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'wa_chat_split_view',
            'name': _('All chats - %s', self.employee_id.name),
            'context': {'active_employee_session_id': self.id, 'wa_all_numbers': True},
        }

    def action_view_conversations(self):
        """View conversation threads for this employee."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Chats - %s', self.employee_id.name),
            'res_model': 'wa.conversation',
            'view_mode': 'kanban,list,form',
            'domain': [('employee_session_id', '=', self.id)],
        }

    def action_view_quality_scores(self):
        """View quality scores for this employee."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Quality Scores - %s', self.employee_id.name),
            'res_model': 'wa.quality.score',
            'view_mode': 'list,form',
            'domain': [('employee_session_id', '=', self.id)],
        }

    def action_refresh_stats(self):
        """Manually recompute stats."""
        self._compute_stats()
        self._compute_alert_count()
        self._compute_response_time()
        self._compute_last_activity()
        self._compute_quality_score()
        self._compute_today_stats()
