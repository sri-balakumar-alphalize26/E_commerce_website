import json
import logging

from odoo import SUPERUSER_ID, api, http
from odoo.http import request
from odoo.addons.whatsapp_gateway.controllers.webhook import WhatsAppWebhook, _text_of

_logger = logging.getLogger(__name__)


class WhatsAppWebhookTyped(WhatsAppWebhook):

    @http.route()
    def inbound(self, secret, **kwargs):
        """Everything as before; the open Chat Views are told first, and what
        was typed on the phone itself is kept too."""
        data = self._wa_tracker_data()
        if data:
            self._wa_tracker_tell(secret, data)
        response = super().inbound(secret, **kwargs)
        try:
            if data and (data.get('key') or {}).get('fromMe'):
                session = request.env['whatsapp.session'].sudo().search(
                    [('webhook_secret', '=', secret), ('active', '=', True)], limit=1)
                Log = request.env['wa.communication.log'].sudo()
                if session:
                    data = request.env['wa.phone.name'].sudo()._open_number(session.id, data)
                values = session and Log._typed_values({'data': data}, _text_of(data.get('message') or {})[0])
                if values:
                    tail = data['_instance'].rpartition('-')[2]
                    Log._typed_later(session.id, tail if tail.isdigit() else '', values)
        except Exception:  # noqa: BLE001 - never an error to the gateway
            _logger.exception("WA Tracker: a message typed on the phone was not read")
        return response

    def _wa_tracker_data(self):
        try:
            payload = json.loads(request.httprequest.get_data() or b'{}')
            data = payload.get('data')
            if payload.get('event') == 'messages.upsert' and isinstance(data, dict):
                return dict(data, _instance=str(payload.get('instance') or ''))
        except (ValueError, TypeError, AttributeError):
            pass
        return None

    def _wa_tracker_tell(self, secret, data):
        """In a transaction of its own: at once, not after the bot's answer."""
        try:
            with request.env.registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                session = env['whatsapp.session'].search([('webhook_secret', '=', secret), ('active', '=', True)], limit=1)
                if session:
                    session._phone_new(data)
        except Exception:  # noqa: BLE001 - never an error to the gateway
            _logger.exception("WA Tracker: the Chat View was not told")
