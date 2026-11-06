"""Outbound HTTP endpoints for other systems to send through Odoo.

The QR endpoints that used to live here are gone. They served a QR held in a
module-level dict, which only ever worked when the polling request happened to
land on the same worker that owned the client - and pairing no longer happens
in Odoo at all.
"""

import base64
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WhatsAppController(http.Controller):

    def _pick_session(self, session_id=None):
        """The session to send through, preferring an explicit one."""
        Session = request.env['whatsapp.session']
        if session_id:
            session = Session.browse(int(session_id))
            return session if session.exists() else Session.browse()
        return Session.get_connected_session()

    @http.route('/whatsapp/send', type='jsonrpc', auth='user', methods=['POST'])
    def send_message(self, **kwargs):
        """POST {"phone": "...", "message": "...", "session_id": 1}"""
        phone = kwargs.get('phone', '')
        message = kwargs.get('message', '')
        if not phone or not message:
            return {'success': False, 'error': 'Phone and message are required'}
        try:
            session = self._pick_session(kwargs.get('session_id'))
            if not session:
                return {'success': False, 'error': 'No connected WhatsApp session'}
            # False means a policy rule stopped it - not an error, but the
            # caller must not be told the message was delivered.
            sent = session.send_message(phone, message)
            if not sent:
                return {'success': False, 'error': 'Blocked by opt-out, cap or duplicate rule'}
            return {'success': True, 'message': 'Message sent'}
        except Exception as err:  # noqa: BLE001
            return {'success': False, 'error': str(err)}

    @http.route('/whatsapp/send/document', type='jsonrpc', auth='user',
                methods=['POST'])
    def send_document(self, **kwargs):
        """POST {"phone", "file_base64", "filename", "caption", "session_id"}"""
        phone = kwargs.get('phone', '')
        file_b64 = kwargs.get('file_base64', '')
        filename = kwargs.get('filename', 'document')
        caption = kwargs.get('caption', '')
        if not phone or not file_b64:
            return {'success': False, 'error': 'Phone and file_base64 are required'}
        try:
            file_data = base64.b64decode(file_b64)
            session = self._pick_session(kwargs.get('session_id'))
            if not session:
                return {'success': False, 'error': 'No connected WhatsApp session'}
            sent = session.send_document(phone, file_data, filename, caption)
            if not sent:
                return {'success': False, 'error': 'Blocked by opt-out, cap or duplicate rule'}
            return {'success': True, 'message': 'Document sent'}
        except Exception as err:  # noqa: BLE001
            return {'success': False, 'error': str(err)}

    @http.route('/whatsapp/debug/status', type='http', auth='user',
                methods=['GET'])
    def debug_status(self, **kwargs):
        """What each session's gateway says right now.

        The old version dumped in-memory dictionaries, which is precisely the
        state that no longer exists. This asks the gateway instead, which is
        the only thing that actually knows.
        """
        sessions = request.env['whatsapp.session'].sudo().search([])
        info = {'sessions': []}
        for session in sessions:
            entry = {
                'id': session.id,
                'name': session.name,
                'gateway_url': session.gateway_url,
                'instance': session.instance_name,
                'db_status': session.status,
            }
            try:
                body = session._gateway_call(
                    'GET', '/instance/connectionState/%s' % session.instance_name,
                    timeout=(5, 10))
                entry['gateway_state'] = (
                    (body or {}).get('instance') or {}).get('state')
            except Exception as err:  # noqa: BLE001
                entry['gateway_state'] = 'unreachable'
                entry['error'] = str(err)
            info['sessions'].append(entry)

        return request.make_response(
            json.dumps(info, indent=2),
            headers=[('Content-Type', 'application/json')],
        )
