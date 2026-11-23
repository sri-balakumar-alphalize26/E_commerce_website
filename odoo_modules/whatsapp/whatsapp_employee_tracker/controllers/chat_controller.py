import logging

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)


class WaChatController(http.Controller):

    def _staff(self):
        # auth='user' lets a customer's portal login in as well
        if not request.env.user._is_internal():
            raise AccessError("Only for employees.")

    @http.route('/wa_tracker/employee_sessions', type='jsonrpc', auth='user')
    def get_employee_sessions(self):
        """Every employee with the numbers they have and had."""
        self._staff()
        Log = request.env['wa.communication.log'].sudo()
        pretty = request.env['whatsapp.connect'].sudo()._pretty
        sessions = request.env['wa.employee.session'].sudo().with_context(active_test=False).search([])
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

    @http.route('/wa_tracker/conversations', type='jsonrpc', auth='user')
    def get_conversations(self, employee_session_id=None, employee_id=None):
        """Get conversations list for the chat panel."""
        self._staff()
        domain = [('total_messages', '>', 0)]
        if employee_session_id:
            domain.append(('employee_session_id', '=', int(employee_session_id)))
        elif employee_id:
            domain.append(('employee_id', '=', int(employee_id)))

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

    @http.route('/wa_tracker/messages', type='jsonrpc', auth='user')
    def get_messages(self, conversation_id):
        """Get messages for a conversation."""
        self._staff()
        logs = request.env['wa.communication.log'].sudo().search([
            ('conversation_id', '=', int(conversation_id)),
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
