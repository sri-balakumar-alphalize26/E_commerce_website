"""What the employee types on the phone itself (24 Nov 2026).

Odoo never sent it, so it was in no list. It goes to the chat log only, never to
whatsapp.message: the daily cap, the "same text twice" check and the bot look
there, and none of them is about what a person typed."""
import logging
import threading
from datetime import datetime, timedelta

from odoo import SUPERUSER_ID, api, fields, models
from odoo.modules.registry import Registry

from .phone_digits import digits

_logger = logging.getLogger(__name__)

# What Odoo sends comes back the same way, perhaps before it is in the log.
WAIT_SECONDS = 12
MEDIA = {'imageMessage': '\U0001F4F7 Image', 'videoMessage': '\U0001F3AC Video', 'audioMessage': '\U0001F3A4 Voice note',
         'documentMessage': '\U0001F4C4 Document', 'stickerMessage': 'Sticker', 'contactMessage': 'Contact'}


class CommunicationLogTyped(models.Model):
    _inherit = 'wa.communication.log'

    message_id = fields.Many2one(required=False)
    typed_wa_id = fields.Char('Typed on the phone', index=True, readonly=True, copy=False)

    @api.model
    def _typed_values(self, payload, text):
        """(WhatsApp id, the customer's number, text, time) or None."""
        data = payload.get('data') or {}
        key = data.get('key') or {}
        wa_id = str(key.get('id') or '')
        if not key.get('fromMe') or not wa_id:
            return None
        phone = ''
        for jid in (key.get('remoteJid'), key.get('remoteJidAlt'), key.get('recipientPn'), data.get('recipientPn')):
            if str(jid or '').endswith('@s.whatsapp.net'):
                phone = digits(str(jid).split('@')[0].split(':')[0])
                break
        if not phone:
            return None             # a group, a status, or a hidden number
        message = data.get('message') or {}
        if not text:
            for kind, label in MEDIA.items():
                if message.get(kind):
                    caption = message[kind].get('caption') if isinstance(message[kind], dict) else ''
                    text = '%s: %s' % (label, caption) if caption else label
                    break
        if not text:
            return None             # a reaction, an edit, a poll of the bot
        try:
            when = datetime.utcfromtimestamp(int(data['messageTimestamp']))
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            when = fields.Datetime.now()
        return wa_id, phone, text, when

    @api.model
    def _typed_later(self, session_id, number, values):
        db_name = self.env.cr.dbname

        def run():
            try:
                with Registry(db_name).cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    env['wa.communication.log']._typed_store(session_id, number, values)
            except Exception:  # noqa: BLE001 - a thread of its own
                _logger.exception("WA Tracker: a message typed on the phone was not stored")
        timer = threading.Timer(WAIT_SECONDS, run)
        timer.daemon = True
        timer.start()

    @api.model
    def _typed_store(self, session_id, number, values):
        wa_id, phone, text, when = values
        Message = self.env['whatsapp.message'].sudo()
        if self.sudo().search_count([('typed_wa_id', '=', wa_id)], limit=1) \
                or Message.search_count([('wa_message_id', '=', wa_id)], limit=1):
            return self.browse()
        same = Message.search([('session_id', '=', session_id), ('direction', '=', 'outgoing'), ('phone', 'like', phone[-9:]),
                               ('create_date', '>=', when - timedelta(minutes=3)),
                               ('create_date', '<=', when + timedelta(minutes=3))])
        if any((m.message or '').strip() == text.strip() for m in same):
            return self.browse()
        session = self.env['whatsapp.session'].sudo().browse(session_id).exists()
        link = session and self.env['wa.employee.session'].sudo()._of_message(session, number)
        if not link or not link.monitoring_enabled:
            return self.browse()
        conversation = self.env['wa.conversation'].sudo()._get_or_create(link, phone)
        log = self.sudo().create({
            'employee_session_id': link.id, 'typed_wa_id': wa_id, 'phone': phone, 'message_text': text,
            'partner_id': conversation.partner_id.id if conversation else False,
            'direction': 'outgoing', 'message_date': when, 'status': 'sent', 'word_count': len(text.split()),
            'conversation_id': conversation.id if conversation else False})
        if conversation:
            conversation._update_stats()
        for check in (lambda: self.env['wa.keyword.alert.log'].sudo()._check_message(log, link),
                      lambda: self.env['wa.message.tone'].sudo().create_or_update_for_message(log.id)):
            try:
                with self.env.cr.savepoint():
                    check()
            except Exception as err:  # noqa: BLE001 - the message is kept either way
                _logger.info("WA Tracker: %s", err)
        link._compute_stats()
        return log

    @api.model
    def _cron_sync_messages(self):
        """One that Odoo sent after all (slow to write it down) is not shown twice."""
        typed = self.sudo().search([('typed_wa_id', '!=', False), ('message_id', '=', False),
                                    ('create_date', '>=', fields.Datetime.now() - timedelta(hours=1))])
        ours = set(self.env['whatsapp.message'].sudo().search(
            [('wa_message_id', 'in', typed.mapped('typed_wa_id'))]).mapped('wa_message_id'))
        twice = typed.filtered(lambda r: r.typed_wa_id in ours)
        chats = twice.conversation_id
        twice.unlink()
        for chat in chats:
            chat._update_stats()
        return super()._cron_sync_messages()


class EmployeeSessionTyped(models.Model):
    _inherit = 'wa.employee.session'

    def _typed(self, extra=()):
        self.ensure_one()
        if not isinstance(self.id, int):
            return 0
        return self.env['wa.communication.log'].sudo().search_count(
            [('employee_session_id', '=', self.id), ('message_id', '=', False)] + list(extra))

    @api.depends('session_id')
    def _compute_stats(self):
        super()._compute_stats()
        for rec in self:
            typed = rec._typed()
            if typed:
                rec.total_sent += typed
                rec.total_messages += typed

    def _compute_today_stats(self):
        super()._compute_today_stats()
        start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        for rec in self:
            rec.today_sent += rec._typed([('message_date', '>=', start)])

    def _compute_last_activity(self):
        super()._compute_last_activity()
        for rec in self:
            last = self.env['wa.communication.log'].sudo().search(
                [('employee_session_id', '=', rec.id), ('message_id', '=', False)], order='message_date desc', limit=1) \
                if isinstance(rec.id, int) else False
            if last and (not rec.last_activity or last.message_date > rec.last_activity):
                rec.last_activity = last.message_date

    @api.model
    def numbers_without_employee(self):
        """Numbers of this database that have no card: nobody has them yet."""
        if not self.env.user._is_internal():
            return []
        given = self.sudo().search([]).session_id
        admin = self.env.user.has_group('base.group_system')
        pretty = self.env['whatsapp.connect'].sudo()._pretty
        sessions = self.env['whatsapp.session'].sudo().search([
            ('active', '=', True), ('id', 'not in', given.ids), ('company_id', 'in', [False] + self.env.companies.ids)])
        return [{'id': s.id, 'name': s.name or '', 'number': pretty(s.authorized_number) if s.authorized_number else '',
                 'status': s.status or '', 'can_give': admin} for s in sessions]
