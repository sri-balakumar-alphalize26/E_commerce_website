"""The name a person gave themselves in WhatsApp, and the live notice that a chat
has something new (24 Nov 2026)."""
import logging
import threading
import time

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import UserError
from odoo.modules.registry import Registry
from odoo.tools import config

_logger = logging.getLogger(__name__)

PRIVATE, GROUP, HIDDEN = '@s.whatsapp.net', '@g.us', '@lid'
AT_A_TIME = 200
_RUNNING = set()


def is_name(text):
    """A number is no name."""
    return any(c.isalpha() for c in text or '') or any(ord(c) > 0x2000 for c in text or '')


class WaPhoneName(models.Model):
    _name = 'wa.phone.name'
    _description = 'Name of a WhatsApp chat'

    session_id = fields.Many2one('whatsapp.session', required=True, ondelete='cascade', index=True)
    jid = fields.Char(required=True)
    name = fields.Char()
    open_jid = fields.Char('Open number', help="The number of one that WhatsApp hides.")

    _jid_once = models.UniqueIndex('(session_id, jid)')

    @api.model
    def _taught(self, session_id):
        """{jid: (name, open number)}; one that was asked and has none is in it."""
        self.flush_model()
        self.env.cr.execute('SELECT jid, name, open_jid FROM wa_phone_name WHERE session_id = %s', [session_id])
        return {jid: (name or '', open_jid or '') for jid, name, open_jid in self.env.cr.fetchall()}

    @api.model
    def _teach(self, session_id, rows):
        """rows: {jid: (name, open number)}. Only what is new is written."""
        known = self._taught(session_id)
        for jid, (name, open_jid) in sorted(rows.items()):
            before = known.get(jid)
            name = (name or '')[:120] if is_name(name) else ''
            if before and (not name or name == before[0]) and (not open_jid or open_jid == before[1]):
                continue
            self.env.cr.execute(
                """INSERT INTO wa_phone_name (session_id, jid, name, open_jid, create_uid, write_uid, create_date, write_date)
                   VALUES (%s, %s, %s, %s, %s, %s, now() at time zone 'utc', now() at time zone 'utc')
                   ON CONFLICT (session_id, jid) DO UPDATE SET
                       name = COALESCE(NULLIF(EXCLUDED.name, ''), wa_phone_name.name),
                       open_jid = COALESCE(NULLIF(EXCLUDED.open_jid, ''), wa_phone_name.open_jid),
                       write_date = EXCLUDED.write_date""",
                [session_id, jid, name or None, open_jid or None, SUPERUSER_ID, SUPERUSER_ID])
        self.invalidate_model()

    @api.model
    def _from_messages(self, messages):
        """What messages teach: never from our own, whose name is ours."""
        rows = {}
        for message in messages:
            key = message.get('key') or {}
            jid, alt = str(key.get('remoteJid') or ''), str(key.get('remoteJidAlt') or '')
            name = '' if key.get('fromMe') else str(message.get('pushName') or '')
            if jid.endswith(GROUP):
                who = str(key.get('participant') or message.get('participant') or '')
                other = str(key.get('participantAlt') or '')
                if not name or not who.endswith((PRIVATE, HIDDEN)):
                    continue
                jid, alt = who, other
            elif not jid.endswith((PRIVATE, HIDDEN)):
                continue
            hidden, opened = (jid, alt) if jid.endswith(HIDDEN) else (alt, jid)
            for one in (jid, alt):
                if one.endswith((PRIVATE, HIDDEN)) and (name or (hidden.endswith(HIDDEN) and opened.endswith(PRIVATE))):
                    before = rows.get(one, ('', ''))
                    rows[one] = (before[0] or name, opened if one == hidden and opened.endswith(PRIVATE) else before[1])
        return rows

    @api.model
    def _look_later(self, session, jids):
        """Names of chats that have none, read one after the other, not now."""
        key = (self.env.cr.dbname, session.id)
        if not jids or key in _RUNNING or config['test_enable']:
            return
        _RUNNING.add(key)
        db_name, session_id, todo = self.env.cr.dbname, session.id, list(jids)[:AT_A_TIME]

        def run():
            try:
                registry = Registry(db_name)
                for jid in todo:
                    with registry.cursor() as cr:
                        env = api.Environment(cr, SUPERUSER_ID, {})
                        if not env['wa.phone.name']._look(env['whatsapp.session'].browse(session_id), jid):
                            return
                    time.sleep(0.2)
            except Exception:  # noqa: BLE001 - a thread of its own
                _logger.exception("WA Tracker: names not read")
            finally:
                _RUNNING.discard(key)
        threading.Thread(target=run, daemon=True).start()

    @api.model
    def _look(self, session, jid):
        try:
            answer = session._gateway_call('POST', '/chat/findMessages/%s' % session.instance_name, {
                'where': {'key': {'remoteJid': jid}}, 'page': 1, 'offset': 50}, timeout=(3, 15))
        except UserError as err:
            _logger.info("WA Tracker: names not read now: %s", err)
            return False
        rows = self._from_messages(((answer or {}).get('messages') or {}).get('records') or [])
        rows.setdefault(jid, ('', ''))
        self._teach(session.id, rows)
        return True


class PhoneNameOpen(models.Model):
    _inherit = 'wa.phone.name'

    @api.model
    def _open_number(self, session_id, data):
        """The same message with the open number of a hidden one, when it is
        known from an earlier message (25 Nov 2026)."""
        key = data.get('key') or {}
        jid = str(key.get('remoteJid') or '')
        if not jid.endswith(HIDDEN) or str(key.get('remoteJidAlt') or '').endswith(PRIVATE):
            return data
        alt = self._taught(session_id).get(jid, ('', ''))[1]
        return dict(data, key=dict(key, remoteJidAlt=alt)) if alt else data


class WhatsAppSessionLive(models.Model):
    _inherit = 'whatsapp.session'

    def _tell_chat_view(self, jid):
        """The open Chat Views of the administrators; no text in it."""
        self.ensure_one()
        group = self.env.ref('base.group_system', raise_if_not_found=False)
        if group:
            group.sudo()._bus_send('wa_tracker_new', {'session': self.id, 'chat': jid})

    def _phone_new(self, data):
        """Something new in a chat, as the gateway says it."""
        self.ensure_one()
        jid = str(((data or {}).get('key') or {}).get('remoteJid') or '')
        if not jid.endswith((PRIVATE, GROUP, HIDDEN)):
            return
        self.env['wa.employee.session']._phone_touch(self, data)
        Name = self.env['wa.phone.name'].sudo()
        Name._teach(self.id, Name._from_messages([data]))
        self._tell_chat_view(jid)


class WhatsAppMessageLive(models.Model):
    _inherit = 'whatsapp.message'

    def _live(self):
        for rec in self.sudo():
            if rec.direction != 'outgoing' or rec.status not in ('sent', 'delivered', 'read') or not rec.session_id or not rec.phone:
                continue
            phone = rec.phone
            if '@' in phone and not phone.endswith((PRIVATE, GROUP)):
                continue
            jid = phone if '@' in phone else ''.join(c for c in phone if c.isdigit()) + PRIVATE
            rec.session_id._tell_chat_view(jid)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._live_safe(records)
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get('status') == 'sent':
            self._live_safe(self)
        return res

    @api.model
    def _live_safe(self, records):
        try:
            with self.env.cr.savepoint():
                records._live()
        except Exception as err:  # noqa: BLE001 - a message is never lost for a notice
            _logger.info("WA Tracker: no live notice: %s", err)
