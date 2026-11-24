"""The chats of a number as its WhatsApp has them (24 Nov 2026).

Read from the gateway when somebody looks; nothing is copied into the database.
Only administrators: it is everything on that phone, groups as well."""
import logging
import time
from datetime import datetime

from odoo import api, models
from odoo.exceptions import AccessError, UserError
from odoo.addons.whatsapp_gateway.controllers.webhook import _text_of

from .phone_digits import digits
from .phone_name import is_name
from .phone_typed import MEDIA

_logger = logging.getLogger(__name__)

PAGE = 50
KEEP_LIST, KEEP_NAMES = 20, 600
PRIVATE, GROUP, HIDDEN = '@s.whatsapp.net', '@g.us', '@lid'
RANK = {'PENDING': (0, 'pending'), 'SERVER_ACK': (1, 'sent'), 'DELIVERY_ACK': (2, 'delivered'), 'READ': (3, 'read'),
        'PLAYED': (4, 'read'), 'ERROR': (5, 'failed')}
_MEMO = {}


def _kept(key, seconds, make):
    now = time.monotonic()
    at, value = _MEMO.get(key, (None, None))
    if at is None or now - at > seconds:
        value = make()
        _MEMO[key] = (time.monotonic(), value)
    return value


class EmployeeSessionPhone(models.Model):
    _inherit = 'wa.employee.session'

    def _phone_check(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._("Only an administrator sees the whole phone."))
        session = self.sudo().session_id
        if not self.active or not session.active:
            raise UserError(self.env._("This number is not the present one."))
        return session

    @api.model
    def _phone_text(self, message):
        body = message.get('message') or {}
        if not isinstance(body, dict):
            return ''
        text = _text_of(body)[0]
        if text:
            return text
        for kind, label in MEDIA.items():
            if body.get(kind):
                caption = body[kind].get('caption') if isinstance(body[kind], dict) else ''
                return '%s: %s' % (label, caption) if caption else label
        for kind, poll in body.items():
            if kind.startswith('pollCreationMessage') and isinstance(poll, dict):
                options = [str(o.get('optionName') or '') for o in poll.get('options') or [] if isinstance(o, dict)]
                return '\n'.join(['\U0001F4CA %s' % (poll.get('name') or '')] + ['○ %s' % o for o in options if o])
        return ''

    @api.model
    def _phone_when(self, message):
        try:
            return str(datetime.utcfromtimestamp(int(message.get('messageTimestamp') or 0)))
        except (TypeError, ValueError, OverflowError, OSError):
            return ''

    def _phone_key(self, what):
        session = self.sudo().session_id
        return self.env.cr.dbname, session.id, session.instance_name, what

    def _phone_names(self, session):
        """{jid: the name WhatsApp has}"""
        def ask():
            try:
                rows = session._gateway_call('POST', '/chat/findContacts/%s' % session.instance_name, {}, timeout=(3, 15))
            except UserError as err:
                _logger.info("WA Tracker: names of %s not read: %s", session.name, err)
                return {}
            return {r['remoteJid']: r['pushName'] for r in rows or [] if isinstance(r, dict) and r.get('remoteJid') and r.get('pushName')}
        names = dict(_kept(self._phone_key('names'), KEEP_NAMES, ask))
        if 'sa.sales.group' in self.env:
            for group in self.env['sa.sales.group'].sudo().search([('session_id', '=', session.id)]):
                names[group.group_jid] = group.name
        return names

    @api.model
    def _phone_touch(self, session, data):
        """The kept list has the new message at once, without asking the gateway."""
        key = (self.env.cr.dbname, session.id, session.instance_name, 'chats')
        rows = _MEMO.get(key, (None, None))[1]
        if not isinstance(rows, list):
            return
        jid, mine = data['key'].get('remoteJid'), data['key'].get('fromMe')
        if not self._phone_text(data):
            return                      # a vote, a reaction: not a message of the list
        row = next((r for r in rows if isinstance(r, dict) and r.get('remoteJid') == jid), None)
        if not row:
            row = {'remoteJid': jid, 'unreadCount': 0}
            rows.append(row)
        row['lastMessage'] = {k: data.get(k) for k in ('key', 'pushName', 'message', 'messageTimestamp', 'participant')}
        row['unreadCount'] = 0 if mine else int(row.get('unreadCount') or 0) + 1

    def _phone_rows(self, session):
        rows = _kept(self._phone_key('chats'), KEEP_LIST, lambda: session._gateway_call(
            'POST', '/chat/findChats/%s' % session.instance_name, {}, timeout=(3, 20)))
        return [r for r in rows if isinstance(r, dict) and str(r.get('remoteJid') or '').endswith((PRIVATE, GROUP, HIDDEN))
                and r.get('lastMessage')] if isinstance(rows, list) else []

    def _phone_chats(self):
        """Every chat, the newest first; one that has a hidden and an open
        number is one chat."""
        session = self._phone_check()
        rows, names = self._phone_rows(session), self._phone_names(session)
        Name = self.env['wa.phone.name'].sudo()
        Name._teach(session.id, Name._from_messages([r['lastMessage'] for r in rows]))
        taught = Name._taught(session.id)
        chats = {}
        for row in sorted(rows, key=lambda r: -int(r['lastMessage'].get('messageTimestamp') or 0)):
            jid, last = row['remoteJid'], row['lastMessage']
            key = last.get('key') or {}
            alt = str(key.get('remoteJidAlt') or '') or taught.get(jid, ('', ''))[1]
            main = alt if jid.endswith(HIDDEN) and alt.endswith(PRIVATE) else jid
            chat = chats.get(main)
            if chat:
                chat['jids'].append(jid)
                chat['unread'] += int(row.get('unreadCount') or 0)
                continue
            phone = digits(main.split('@')[0]) if main.endswith(PRIVATE) else ''
            chats[main] = {
                'id': main, 'jids': list(dict.fromkeys([main, jid])), 'phone': '+' + phone if phone else '',
                'group': main.endswith(GROUP), 'name': '', 'push': '' if key.get('fromMe') else (last.get('pushName') or ''),
                'from_me': bool(key.get('fromMe')), 'preview': self._phone_text(last)[:80], 'date': self._phone_when(last),
                'unread': int(row.get('unreadCount') or 0), 'row_name': row.get('pushName') or ''}
        partners = {}
        tails = [c['phone'][-9:] for c in chats.values() if len(c['phone']) > 9]
        if tails:
            for conv in self.env['wa.conversation'].sudo().search([('partner_id', '!=', False), ('employee_session_id', '=', self.id)]):
                if is_name(conv.partner_id.name):
                    partners[digits(conv.phone)[-9:]] = conv.partner_id.name
        unnamed = []
        for chat in chats.values():
            named = next((names[j] for j in chat['jids'] if is_name(names.get(j))), '')
            own = next((taught[j][0] for j in chat['jids'] if taught.get(j, ('', ''))[0]), '')
            chat['name'] = (partners.get(chat['phone'][-9:]) if chat['phone'] else '') or named \
                or (chat['row_name'] if chat['group'] else chat['push'] or own) \
                or chat['phone'] or (self.env._("Group") if chat['group'] else self.env._("Hidden number"))
            if not chat['group'] and not named and not own and not chat['push'] and not any(j in taught for j in chat['jids']):
                unnamed.append(chat['jids'][-1])
        Name._look_later(session, unnamed)
        return list(chats.values())

    def phone_chats(self):
        chats = self._phone_chats()
        keep = ('id', 'phone', 'group', 'name', 'from_me', 'preview', 'date', 'unread')
        return [{k: c[k] for k in keep} for c in chats]

    def phone_messages(self, chat_id, page=1):
        """One page of one chat of this number, the oldest of the page first."""
        session = self._phone_check()
        chat = next((c for c in self._phone_chats() if c['id'] == chat_id), None)
        if not chat:
            raise AccessError(self.env._("That chat is not on this number."))
        page = max(1, int(page or 1))
        names = self._phone_names(session) if chat['group'] else {}
        Name = self.env['wa.phone.name'].sudo()
        taught = Name._taught(session.id) if chat['group'] else {}
        found, more = {}, False
        for jid in chat['jids']:
            answer = session._gateway_call('POST', '/chat/findMessages/%s' % session.instance_name, {
                'where': {'key': {'remoteJid': jid}}, 'page': page, 'offset': PAGE}, timeout=(3, 20))
            box = (answer or {}).get('messages') or {}
            more = more or int(box.get('pages') or 0) > page
            Name._teach(session.id, Name._from_messages(box.get('records') or []))
            for message in box.get('records') or []:
                key = message.get('key') or {}
                if key.get('remoteJid') != jid or not key.get('id'):
                    continue
                text = self._phone_text(message)
                if not text:
                    continue            # a vote, a reaction, an edit
                mine = bool(key.get('fromMe'))
                status = 'received'
                if mine:
                    states = [RANK[u.get('status')] for u in message.get('MessageUpdate') or []
                              if isinstance(u, dict) and u.get('status') in RANK]
                    states += [RANK[message['status']]] if message.get('status') in RANK else []
                    status = max(states)[1] if states else 'sent'
                who = ''
                if chat['group'] and not mine:
                    part = str(key.get('participant') or message.get('participant') or '')
                    who = message.get('pushName') or names.get(part) or taught.get(part, ('', ''))[0] \
                        or ('+' + digits(part.split('@')[0]) if part.endswith(PRIVATE) else '')
                found[key['id']] = {'id': key['id'], 'message_text': text, 'direction': 'outgoing' if mine else 'incoming',
                                    'message_date': self._phone_when(message), 'status': status, 'is_flagged': False, 'sender': who}
        return {'messages': sorted(found.values(), key=lambda m: m['message_date']), 'more': more}
