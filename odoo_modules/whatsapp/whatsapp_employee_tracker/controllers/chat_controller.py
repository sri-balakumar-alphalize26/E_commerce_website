import logging

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class WaChatController(http.Controller):

    def _staff(self):
        # auth='user' lets a customer's portal login in as well
        if not request.env.user._is_internal():
            raise AccessError("Only for employees.")

    def _mine(self):
        """Whose chats: all, the department's, or one's own."""
        user = request.env.user
        if user.has_group('whatsapp_employee_tracker.group_wa_tracker_manager'):
            return []
        own = [('employee_id.user_id', '=', user.id)]
        if user.has_group('whatsapp_employee_tracker.group_wa_tracker_dept_head'):
            return ['|', ('employee_id.department_id.manager_id.user_id', '=', user.id)] + own
        return own

    @http.route('/wa_tracker/employee_sessions', type='jsonrpc', auth='user')
    def get_employee_sessions(self):
        """Every employee with the numbers they have and had."""
        self._staff()
        Log = request.env['wa.communication.log'].sudo()
        pretty = request.env['whatsapp.connect'].sudo()._pretty
        sessions = request.env['wa.employee.session'].sudo().with_context(active_test=False).search(self._mine())
        stats = {s.id: (count, first, last) for s, count, first, last in Log._read_group(
            [('employee_session_id', 'in', sessions.ids)], ['employee_session_id'],
            ['__count', 'message_date:min', 'message_date:max'])}
        people = {}
        for s in sessions:
            count, first, last = stats.get(s.id, (0, None, None))
            if not s.active and not count:
                continue
            person = people.setdefault(s.employee_id.id, {'id': s.employee_id.id, 'name': s.employee_id.name or '', 'numbers': []})
            person['numbers'].append({
                'id': s.id, 'number': pretty(s.own_number) or s.phone_number or '', 'current': s.active, 'count': count,
                'first': str(first) if first else '', 'last': str(last) if last else ''})
        for person in people.values():
            person['numbers'].sort(key=lambda n: (n['current'], n['last']), reverse=True)
        return sorted(people.values(), key=lambda p: p['name'].lower())

    @http.route('/wa_tracker/reply_status', type='jsonrpc', auth='user')
    def get_reply_status(self):
        """How each employee replies, on the number they have now."""
        self._staff()
        cards = request.env['wa.employee.session'].sudo().search(
            self._mine() + [('active', '=', True), ('session_id.active', '=', True)])
        found, today, replies = cards._reply_status(), cards._figures(cards._today_start()), cards._reply_today()
        text = lambda at: str(at)[:19] if at else ''  # noqa: E731
        rows = [{'id': c.id, 'employee_id': c.employee_id.id, 'name': c.employee_id.name or '',
                 'connected': c.session_id.status == 'connected', 'last': text(found[c.id]['last']),
                 'waiting': found[c.id]['waiting'], 'oldest': text(found[c.id]['oldest']),
                 'waits': {who: text(at) for who, at in found[c.id]['waits'].items()},
                 'sent': today.get(c.id, (0, 0, 0))[0], 'received': today.get(c.id, (0, 0, 0))[1],
                 'replies': replies.get(c.id, (0, 0))[0], 'average': round(replies.get(c.id, (0, 0))[1], 1)} for c in cards]
        # who keeps somebody waiting longest comes first
        return {'rows': sorted(rows, key=lambda r: (not r['waiting'], r['oldest'], r['name'].lower()))}

    @http.route('/wa_tracker/home', type='jsonrpc', auth='user')
    def get_home(self):
        """Every present number's chats. Administrators, as the
        phone's chats are."""
        self._staff()
        if not request.env.user.has_group('base.group_system'):
            return {'chats': False}
        cards = request.env['wa.employee.session'].search(
            self._mine() + [('active', '=', True), ('session_id.active', '=', True)])
        own = {''.join(c for c in (s.session_id.authorized_number or '') if c.isdigit())[-9:] for s in cards.sudo()} - {''}
        chats, down = [], []
        for card in cards:
            try:
                chats += card._home_chats(own)
            except UserError as err:
                _logger.info("WA Tracker: chats of %s not read: %s", card.id, err)
                down.append(card.id)
        return {'chats': chats, 'down': down}

    @http.route('/wa_tracker/check_number', type='jsonrpc', auth='user')
    def check_number(self, employee_session_id):
        """Ask the panel now whether this number is connected."""
        self._staff()
        card = request.env['wa.employee.session'].sudo().search(
            self._mine() + [('id', '=', int(employee_session_id or 0)), ('active', '=', True)])
        if not card:
            raise AccessError("Not one of your numbers.")
        card.session_id._refresh_state(force=True)
        return {'connected': card.session_id.status == 'connected'}

    @http.route('/wa_tracker/conversations', type='jsonrpc', auth='user')
    def get_conversations(self, employee_session_id=None, employee_id=None):
        """Get conversations list for the chat panel."""
        self._staff()
        domain = [('total_messages', '>', 0)] + self._mine()
        if employee_session_id:
            domain.append(('employee_session_id', '=', int(employee_session_id)))
        elif employee_id:
            domain.append(('employee_id', '=', int(employee_id)))
        else:
            # everybody: the numbers of now; an old one is chosen by its employee
            domain.append(('employee_session_id.active', '=', True))

        convs = request.env['wa.conversation'].sudo().with_context(active_test=False).search(
            domain, order='last_message_date desc'
        )
        pretty = request.env['whatsapp.connect'].sudo()._pretty
        # Pre-fetch push_names for all phones in one query
        phones = [c.phone for c in convs if c.phone]
        push_name_map = {}
        if phones:
            msgs = request.env['whatsapp.message'].sudo().search([
                ('phone', 'in', phones),
                ('push_name', '!=', False),
                ('push_name', '!=', ''),
            ], order='create_date desc')
            for m in msgs:
                if m.phone not in push_name_map:
                    push_name_map[m.phone] = m.push_name

        result = []
        for c in convs:
            # Use push_name > contact_name > phone as display name
            raw_phone = c.phone or ''
            push_name = push_name_map.get(raw_phone, '')
            # Strip non-digit chars to detect if contact_name is just a phone fallback
            digits_only = ''.join(filter(str.isdigit, c.contact_name or ''))
            contact_name = push_name or (c.contact_name if digits_only != (c.contact_name or '').strip('+') else '') or c.contact_name or 'Unknown'
            # Format phone: extract digits and add + prefix
            phone_digits = ''.join(filter(str.isdigit, raw_phone))
            formatted_phone = ('+' + phone_digits) if phone_digits else raw_phone
            own = c.employee_session_id
            result.append({
                'id': c.id,
                'contact_name': contact_name,
                'phone': formatted_phone,
                'total_messages': c.total_messages,
                'sent_count': c.sent_count,
                'received_count': c.received_count,
                'avg_response_minutes': c.avg_response_minutes,
                'last_message_date': str(c.last_message_date) if c.last_message_date else '',
                'is_active_today': c.is_active_today,
                'last_message_preview': c.last_message_preview or '',
                'employee_name': c.employee_id.name or '',
                'employee_session_id': own.id or None,
                'own_number': pretty(own.own_number) or own.phone_number or '',
                'own_current': own.active,
            })
        return result

    # ---- as the phone has it (24 Nov 2026): administrators, the present number
    def _phone(self, employee_session_id):
        self._staff()
        link = request.env['wa.employee.session'].browse(int(employee_session_id or 0)).exists()
        if not link or not request.env.user.has_group('base.group_system'):
            return None
        return link if link.active and link.sudo().session_id.active else None

    @http.route('/wa_tracker/phone_chats', type='jsonrpc', auth='user')
    def get_phone_chats(self, employee_session_id=None):
        link = self._phone(employee_session_id)
        if not link:
            return {'phone': False}
        try:
            return {'phone': True, 'chats': link.phone_chats()}
        except UserError as err:
            _logger.info("WA Tracker: phone chats: %s", err)
            return {'phone': True, 'down': True}

    @http.route('/wa_tracker/phone_messages', type='jsonrpc', auth='user')
    def get_phone_messages(self, employee_session_id, chat_id, page=1):
        link = self._phone(employee_session_id)
        if not link:
            return {'messages': [], 'more': False}
        try:
            return link.phone_messages(str(chat_id), page)
        except AccessError:
            raise
        except UserError as err:
            _logger.info("WA Tracker: phone messages: %s", err)
            return {'down': True}

    @http.route('/wa_tracker/phone_reply', type='jsonrpc', auth='user')
    def phone_reply(self, employee_session_id, chat_id, text):
        link = self._phone(employee_session_id)
        if not link:
            raise AccessError("Only an administrator, on the present number.")
        try:
            return link.phone_reply(str(chat_id), text)
        except AccessError:
            raise
        except UserError as err:
            return {'error': str(err.args[0] if err.args else err).strip()[:400]}

    @http.route('/wa_tracker/phone_media/<int:employee_session_id>/<string:message_id>', type='http', auth='user', methods=['GET'])
    def get_phone_media(self, employee_session_id, message_id, **kw):
        """A picture, a voice note or a file, when it is tapped. Nothing is kept."""
        link = self._phone(employee_session_id)
        if not link:
            raise request.not_found()
        try:
            data, kind, name, inline = link.phone_media(message_id)
        except UserError as err:
            _logger.info("WA Tracker: media: %s", err)
            raise request.not_found() from err
        return request.make_response(data, [
            ('Content-Type', kind if inline else 'application/octet-stream'), ('Content-Length', str(len(data))),
            ('Content-Disposition', http.content_disposition(name, 'inline' if inline else 'attachment')),
            ('X-Content-Type-Options', 'nosniff'), ('Content-Security-Policy', "default-src 'none'; sandbox"),
            ('Cache-Control', 'private, max-age=600')])

    @http.route('/wa_tracker/messages', type='jsonrpc', auth='user')
    def get_messages(self, conversation_id):
        """Get messages for a conversation."""
        self._staff()
        chat = request.env['wa.conversation'].sudo().with_context(active_test=False).search(
            [('id', '=', int(conversation_id))] + self._mine())
        logs = request.env['wa.communication.log'].sudo().search([
            ('conversation_id', 'in', chat.ids),
        ], order='message_date asc')

        result = []
        for log in logs:
            result.append({
                'id': log.id,
                'message_text': log.message_text or '',
                'direction': log.direction,
                'message_date': str(log.message_date) if log.message_date else '',
                'status': log.status or '',
                'is_flagged': log.is_flagged,
            })
        return result
