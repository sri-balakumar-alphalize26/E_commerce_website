import logging
from odoo import models, fields, api

from .phone_digits import same_number

_logger = logging.getLogger(__name__)


class CommunicationLog(models.Model):
    """
    Materialized communication log that enriches whatsapp.message
    with employee tracking context. Populated by cron from whatsapp.message.
    """
    _name = 'wa.communication.log'
    _description = 'Employee Communication Log'
    _order = 'message_date desc, id desc'
    _rec_name = 'display_name_custom'

    employee_session_id = fields.Many2one(
        'wa.employee.session', string='Employee Session',
        required=True, ondelete='cascade', index=True,
    )
    employee_id = fields.Many2one(
        related='employee_session_id.employee_id',
        store=True, string='Employee', index=True,
    )
    department_id = fields.Many2one(
        related='employee_session_id.department_id',
        store=True, string='Department', index=True,
    )
    message_id = fields.Many2one(
        'whatsapp.message', string='Original Message',
        required=True, ondelete='cascade', index=True,
    )
    own_phone = fields.Char(related='employee_session_id.phone_number', string='Number')
    phone = fields.Char('Contact Phone', index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Contact',
    )
    message_text = fields.Text('Message Content')
    direction = fields.Selection([
        ('incoming', 'Incoming'),
        ('outgoing', 'Outgoing'),
    ], string='Direction', index=True)
    message_date = fields.Datetime('Date/Time', index=True)
    status = fields.Selection([
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('received', 'Received'),
        ('failed', 'Failed'),
    ], string='Status')

    # ---- Enrichment ----
    word_count = fields.Integer('Word Count')
    has_attachment = fields.Boolean('Has Attachment')
    is_group_message = fields.Boolean('Group Message')
    conversation_id = fields.Many2one(
        'wa.conversation', string='Conversation',
        index=True,
    )
    is_flagged = fields.Boolean('Flagged', index=True)
    flag_reason = fields.Char('Flag Reason')

    # ---- Voice Message ----
    is_voice_message = fields.Boolean('Voice Message', index=True)
    voice_transcription = fields.Text('Voice Transcription')
    voice_language = fields.Char('Detected Language')
    voice_translation = fields.Text('English Translation')

    # ---- Computed display ----
    display_name_custom = fields.Char(
        compute='_compute_display_name_custom', string='Description',
    )
    hour_of_day = fields.Integer(
        'Hour of Day', compute='_compute_time_parts', store=True,
    )
    day_of_week = fields.Char(
        'Day of Week', compute='_compute_time_parts', store=True,
    )

    def _compute_display_name_custom(self):
        for rec in self:
            direction = '→' if rec.direction == 'outgoing' else '←'
            preview = (rec.message_text or '')[:40]
            rec.display_name_custom = (
                f"{rec.employee_id.name or '?'} {direction} {rec.phone or '?'}: "
                f"{preview}"
            )

    @api.depends('message_date')
    def _compute_time_parts(self):
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                'Friday', 'Saturday', 'Sunday']
        for rec in self:
            if rec.message_date:
                rec.hour_of_day = rec.message_date.hour
                rec.day_of_week = days[rec.message_date.weekday()]
            else:
                rec.hour_of_day = 0
                rec.day_of_week = ''

    # ----------------------------------------------------------
    # Cron: Sync messages into communication log
    # ----------------------------------------------------------
    @api.model
    def _cron_sync_messages(self):
        """
        Pull new whatsapp.message records into communication log.
        Only processes messages from monitored employee sessions.
        """
        _logger.info("📊 WA Tracker: Syncing messages to communication log...")

        emp_sessions = self.env['wa.employee.session'].search([
            ('monitoring_enabled', '=', True),
            ('session_id', '!=', False),
        ])

        if not emp_sessions:
            _logger.info("📊 WA Tracker: No monitored sessions found.")
            return

        total_new = 0
        for emp_session in emp_sessions:
            total_new += self._sync_for(emp_session)

        if total_new:
            _logger.info(
                "📊 WA Tracker: Synced %d new messages to communication log.",
                total_new,
            )
            # Immediately run auto-reply check after syncing new messages.
            # This ensures the configured timeout is respected without waiting
            # for a separate cron cycle (which could add up to 1 extra minute).
            self.env['wa.auto.reply']._cron_check_auto_reply()

        emp_sessions._compute_stats()
        # Also refresh quality scores
        self.env['wa.quality.score']._cron_compute_scores()

    @api.model
    def _sync_for(self, emp_session):
        """What is not in the log yet of this employee on this number: theirs,
        or of nobody yet. Never another number's, never another person's."""
        total_new = 0
        if emp_session.monitoring_enabled:
            existing_msg_ids = self.search([
                ('employee_session_id', '=', emp_session.id),
            ]).mapped('message_id.id')
            new_messages = self.env['whatsapp.message'].search([
                ('session_id', '=', emp_session.session_id.id),
                ('id', 'not in', existing_msg_ids),
                ('employee_session_id', 'in', [emp_session.id, False]),
            ], order='create_date asc')
            new_messages = new_messages.filtered(
                lambda m: m.employee_session_id or not m.own_number
                or same_number(m.own_number, emp_session._number_now()))

            for msg in new_messages:
                if not msg.employee_session_id:
                    msg.employee_session_id = emp_session.id
                # Get or create conversation
                conversation = self.env['wa.conversation']._get_or_create(
                    emp_session, msg.phone, msg.partner_id,
                )

                # Create log entry
                word_count = len((msg.message or '').split())
                vals = {
                    'employee_session_id': emp_session.id,
                    'message_id': msg.id,
                    'phone': msg.phone,
                    'partner_id': msg.partner_id.id if msg.partner_id else False,
                    'message_text': msg.message,
                    'direction': msg.direction,
                    'message_date': msg.create_date,
                    'status': msg.status,
                    'word_count': word_count,
                    'has_attachment': bool(msg.attachment_ids),
                    'is_group_message': msg.is_group,
                    'conversation_id': conversation.id if conversation else False,
                }
                log_entry = self.create(vals)
                total_new += 1

                # Update conversation stats
                if conversation:
                    conversation._update_stats()

                # Check keyword alerts
                self.env['wa.keyword.alert.log']._check_message(
                    log_entry, emp_session,
                )

                # Analyze message tone (sentiment + keywords)
                self.env['wa.message.tone'].create_or_update_for_message(
                    log_entry.id,
                )
        return total_new
