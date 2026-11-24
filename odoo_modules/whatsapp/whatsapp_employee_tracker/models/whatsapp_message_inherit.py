import logging
import threading
from odoo import models, fields, api, SUPERUSER_ID
from odoo.modules.registry import Registry
import random
import time
from psycopg2 import errorcodes as _pg_errorcodes

# The codes Odoo itself retries a request for. A serialization
# failure here is two customers finishing at the same moment, not a
# fault, and the work is safe to repeat.
_PG_RETRY_CODES = (_pg_errorcodes.SERIALIZATION_FAILURE,
                   _pg_errorcodes.DEADLOCK_DETECTED,
                   _pg_errorcodes.LOCK_NOT_AVAILABLE)
_AUTO_REPLY_ATTEMPTS = 3

_logger = logging.getLogger(__name__)


class WhatsAppMessageInherit(models.Model):
    _inherit = 'whatsapp.message'

    employee_session_id = fields.Many2one(
        'wa.employee.session', string='Employee Session',
        index=True, readonly=True, copy=False, ondelete='set null',
        help='Set when the message is stored; a later change of employee or number does not touch it.',
    )
    employee_id = fields.Many2one(
        related='employee_session_id.employee_id',
        store=True, string='Employee',
    )
    push_name = fields.Char('WhatsApp Name', help='Contact push name from WhatsApp')
    is_voice_message = fields.Boolean('Voice Message', default=False)
    voice_transcription = fields.Text('Voice Transcription')
    voice_language = fields.Char('Detected Language', help='ISO language code detected by Whisper e.g. en, ar, ml, hi')
    voice_translation = fields.Text('English Translation')

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to instantly sync messages to WA Tracker."""
        records = super().create(vals_list)
        Owner = self.env['wa.employee.session']
        for rec in records.filtered(lambda r: r.session_id and not r.employee_session_id):
            owner = Owner._of_message(rec.session_id, rec.own_number)
            if owner:
                rec.sudo().employee_session_id = owner.id
        try:
            self.sudo()._instant_sync_to_tracker(records.sudo())
        except Exception as e:
            _logger.warning(
                "WA Tracker: Real-time sync failed (cron will catch up): %s", e
            )
        return records

    def write(self, vals):
        """Override write to update tracker when message status changes."""
        res = super().write(vals)
        if 'status' in vals or 'message' in vals:
            try:
                self.sudo()._instant_update_tracker(vals)
            except Exception as e:
                _logger.warning(
                    "WA Tracker: Real-time update failed: %s", e
                )
        return res

    def _instant_sync_to_tracker(self, messages):
        """Instantly process new messages into the tracker system."""
        CommLog = self.env['wa.communication.log']
        Conversation = self.env['wa.conversation']
        AlertLog = self.env['wa.keyword.alert.log']

        for msg in messages:
            if not msg.session_id:
                continue

            # Find the employee session for this WhatsApp session
            emp_session = msg.employee_session_id
            if not emp_session or not emp_session.monitoring_enabled:
                continue

            # Check if already in log (avoid duplicates)
            existing = CommLog.search([
                ('message_id', '=', msg.id),
            ], limit=1)
            if existing:
                continue

            # Get or create conversation thread
            conversation = Conversation._get_or_create(
                emp_session, msg.phone, msg.partner_id,
            )

            # Create communication log entry
            word_count = len((msg.message or '').split())

            # Clean phone from JID format
            import re
            clean_phone = msg.phone or ''
            user_match = re.search(r'User:\s*"(\d+)"', clean_phone)
            if user_match:
                clean_phone = user_match.group(1)
            else:
                digits = re.sub(r'[^\d]', '', clean_phone)
                if digits and len(digits) >= 6:
                    clean_phone = digits

            log_entry = CommLog.create({
                'employee_session_id': emp_session.id,
                'message_id': msg.id,
                'phone': clean_phone,
                'partner_id': msg.partner_id.id if msg.partner_id else False,
                'message_text': msg.message,
                'direction': msg.direction,
                'message_date': msg.create_date,
                'status': msg.status,
                'word_count': word_count,
                'has_attachment': bool(msg.attachment_ids) if hasattr(msg, 'attachment_ids') else False,
                'is_group_message': msg.is_group if hasattr(msg, 'is_group') else False,
                'conversation_id': conversation.id if conversation else False,
                'is_voice_message': getattr(msg, 'is_voice_message', False),
                'voice_transcription': getattr(msg, 'voice_transcription', '') or '',
                'voice_language': getattr(msg, 'voice_language', '') or '',
                'voice_translation': getattr(msg, 'voice_translation', '') or '',
            })

            # Update conversation stats
            if conversation:
                conversation._update_stats()

            # Check keyword alerts instantly
            AlertLog._check_message(log_entry, emp_session)

            # Analyze tone for outgoing employee messages
            self.env['wa.message.tone'].create_or_update_for_message(log_entry.id)

            # Schedule auto-reply (incoming only). Fast-path: if the customer
            # message already matches products in catalog, fire near-instantly
            # instead of waiting the full configured timeout.
            if msg.direction == 'incoming' and emp_session.auto_reply_enabled and emp_session.active:
                timeout = emp_session.auto_reply_timeout or 120
                try:
                    AutoReply = self.env['wa.auto.reply']
                    if hasattr(AutoReply, '_search_products'):
                        # Voice messages: msg.message already holds the transcription
                        # (set by whatsapp_gateway._on_message). Plain text just uses
                        # msg.message directly.
                        matches = AutoReply._search_products(
                            msg.message or '',
                            emp_session.auto_reply_max_products or 5,
                        )
                        if matches:
                            timeout = 1  # fire immediately, skip the wait
                            _logger.info(
                                "Auto-reply fast-path: %d product match(es) "
                                "for msg %s — firing in 1s",
                                len(matches), log_entry.id,
                            )
                except Exception as e:
                    _logger.warning(
                        "Auto-reply product pre-check failed (msg %s): %s",
                        log_entry.id, e,
                    )
                self._schedule_auto_reply(
                    log_entry.id, conversation.id if conversation else False,
                    emp_session.id, timeout, self.env.cr.dbname,
                )

            _logger.info(
                "WA Tracker: Instant sync - %s %s message for %s",
                msg.direction, msg.phone, emp_session.employee_id.name or 'Unknown',
            )

        # The counters on the employee session are written by the minute job
        # (communication_log.py): written here, two messages at the same moment
        # collided on them and one was handled - and sent - again (23 Nov 2026).

    def _instant_update_tracker(self, vals):
        """Update tracker log when message status changes."""
        CommLog = self.env['wa.communication.log']
        for msg in self:
            log = CommLog.search([('message_id', '=', msg.id)], limit=1)
            if log:
                update_vals = {}
                if 'status' in vals:
                    update_vals['status'] = vals['status']
                if 'message' in vals:
                    update_vals['message_text'] = vals['message']
                    update_vals['word_count'] = len((vals['message'] or '').split())
                if update_vals:
                    log.write(update_vals)

    def _schedule_auto_reply(self, log_id, conv_id, emp_session_id, timeout_seconds, db_name):
        """Spawn a daemon timer thread: after timeout_seconds, send auto-reply
        if the employee still hasn't replied."""

        def _fire():
            for attempt in range(1, _AUTO_REPLY_ATTEMPTS + 1):
                # Only an explicit False asks for another go. The guards inside
                # return None when there is nothing to do, and that is settled.
                if _fire_once(attempt) is not False:
                    return

        def _fire_once(attempt):
            """False to retry; anything else means the matter is settled."""
            try:
                with Registry(db_name).cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})

                    # Fetch the specific triggering message
                    trigger_log = env['wa.communication.log'].browse(log_id)
                    if not trigger_log.exists():
                        return

                    # Skip if employee has already replied *after* this message
                    later_outgoing = env['wa.communication.log'].search([
                        ('conversation_id', '=', conv_id),
                        ('direction', '=', 'outgoing'),
                        ('message_date', '>', trigger_log.message_date),
                    ], limit=1)
                    if later_outgoing:
                        return  # Employee manually replied after this message

                    # Skip if we already auto-replied to this exact message
                    already = env['wa.auto.reply'].search([
                        ('trigger_message_id', '=', log_id),
                    ], limit=1)
                    if already:
                        return

                    conv = env['wa.conversation'].browse(conv_id)
                    emp_session = env['wa.employee.session'].browse(emp_session_id)

                    # Re-check at fire time — user may have disabled auto-reply after scheduling
                    if not emp_session.exists() or not emp_session.auto_reply_enabled:
                        _logger.info("Auto-reply skipped (disabled at fire time) for conv %s", conv_id)
                        return

                    # Pass the specific triggering message's text so context is correct
                    from datetime import timedelta
                    cutoff = fields.Datetime.now() - timedelta(seconds=1)
                    env['wa.auto.reply']._check_conversation_for_message(
                        conv, emp_session, cutoff, trigger_log
                    )
                    cr.commit()
                    _logger.info("Auto-reply fired for conv %s, msg %s, after %ss timeout",
                                 conv_id, log_id, timeout_seconds)
                return True
            except Exception as e:
                pgcode = getattr(e, 'pgcode', None) or getattr(
                    getattr(e, 'orig', None), 'pgcode', None)
                if (pgcode in _PG_RETRY_CODES
                        and attempt < _AUTO_REPLY_ATTEMPTS):
                    # Somebody else's transaction touched the same row. This is
                    # ordinary under load - two customers finishing at once -
                    # and the work is safe to repeat because the guards above
                    # re-check whether a reply already went out.
                    wait = 0.25 * attempt + random.uniform(0, 0.25)
                    _logger.info(
                        "Auto-reply for conv %s lost a race (%s), attempt %s of "
                        "%s in %.2fs", conv_id, pgcode, attempt,
                        _AUTO_REPLY_ATTEMPTS, wait)
                    time.sleep(wait)
                    return False
                _logger.error("Scheduled auto-reply error (conv %s, msg %s): %s", conv_id, log_id, e)
                return True

        timer = threading.Timer(timeout_seconds, _fire)
        timer.daemon = True
        timer.start()
