"""Inbound WhatsApp, delivered by the gateway instead of a library callback.

Under neonize an incoming message arrived on a background thread as a protobuf
event. It now arrives here as an HTTP POST from Evolution. Everything
downstream - crm_call_recorder, whatsapp_employee_tracker's auto-reply and
nexgenn_wa_reporting - reads `whatsapp.message` records and
`wa.report.engine.handle_incoming()`, so this controller's job is to rebuild
exactly what the old `_on_message` built. Nothing else had to change.

Choosing the database
---------------------
This route is public, so there is no session cookie to say which database the
message belongs to. The gateway must send the header

    X-Odoo-Database: <database>

which Odoo resolves before routing. Configure it per instance, alongside the
webhook URL. A shared number can only feed one database; giving a tenant its
own instance is what lets its replies reach its own database.
"""

import json
import re
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Only these are acted on. Evolution offers a long list of events and enabling
# more would mean parsing traffic we have no use for.
HANDLED_EVENTS = {'messages.upsert'}


def _text_of(message):
    """Pull the reply out of a Baileys message object.

    A tapped button does not arrive as its label - it arrives as the id we set
    when sending, under one of several keys depending on which button style
    WhatsApp rendered. The auto-reply code matches on those ids, so all the
    forms have to be understood. Both the protobuf spelling and the JSON one
    are checked because the two differ in case.
    """
    if not isinstance(message, dict):
        return '', False

    def dig(*path):
        node = message
        for key in path:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
        return node

    for path in (
        ('buttonsResponseMessage', 'selectedButtonId'),
        ('buttonsResponseMessage', 'selectedButtonID'),
        ('templateButtonReplyMessage', 'selectedId'),
        ('templateButtonReplyMessage', 'selectedID'),
        ('listResponseMessage', 'singleSelectReply', 'selectedRowId'),
        ('listResponseMessage', 'singleSelectReply', 'selectedRowID'),
    ):
        value = dig(*path)
        if value:
            return str(value), False

    for key in ('paramsJson', 'paramsJSON'):
        params = dig('interactiveResponseMessage',
                     'nativeFlowResponseMessage', key)
        if params:
            try:
                chosen = json.loads(params or '{}').get('id', '')
            except (ValueError, TypeError):
                chosen = ''
            if chosen:
                return str(chosen), False

    # A location pin (attach > Location): carried as text so the sales flow
    # can save it on the customer's order (rider-app live test, 3 Oct 2026).
    for key in ('locationMessage', 'liveLocationMessage'):
        loc = message.get(key) or {}
        try:
            lat, lng = loc.get('degreesLatitude'), loc.get('degreesLongitude')
            if lat is not None and lng is not None:
                return '\U0001F4CD %.6f,%.6f' % (float(lat), float(lng)), False
        except (TypeError, ValueError):
            pass

    if message.get('conversation'):
        return str(message['conversation']), False
    extended = dig('extendedTextMessage', 'text')
    if extended:
        return str(extended), False
    if message.get('audioMessage'):
        return '', True
    return '', False


class WhatsAppWebhook(http.Controller):

    @http.route(
        '/whatsapp/webhook/<string:secret>',
        type='http', auth='public', methods=['POST'], csrf=False, save_session=False,
    )
    def inbound(self, secret, **kwargs):
        """Receive one gateway event.

        Always answers 200. A webhook that returns an error makes Evolution
        retry with backoff for hours, and a message we could not parse will not
        parse on the tenth attempt either - it would only bury the real traffic.
        Failures are logged here instead.
        """
        try:
            payload = json.loads(request.httprequest.get_data() or b'{}')
        except (ValueError, TypeError):
            _logger.warning("WhatsApp webhook: body was not JSON.")
            return request.make_json_response({'ok': False, 'error': 'bad json'})

        session = request.env['whatsapp.session'].sudo().search(
            [('webhook_secret', '=', secret), ('active', '=', True)], limit=1)
        if not session:
            # Wrong or stale secret. Say nothing useful about why.
            _logger.warning("WhatsApp webhook: unknown secret.")
            return request.make_json_response({'ok': False}, status=404)

        event = payload.get('event') or ''
        if event not in HANDLED_EVENTS:
            return request.make_json_response({'ok': True, 'ignored': event})

        # The number it arrived on: one that waited in the panel while the
        # session became another number still belongs to the old one.
        own = re.search(r'-([0-9]{8,15})$', str(payload.get('instance') or ''))
        if own:
            request.update_context(wa_own_number=own.group(1))
            session = session.with_env(request.env(su=True))

        try:
            self._handle_message(session, payload)
        except Exception as err:  # noqa: BLE001 - never retry-storm the gateway
            _logger.exception("WhatsApp webhook: failed to handle %s: %s",
                              event, err)
            return request.make_json_response({'ok': False})
        return request.make_json_response({'ok': True})

    def _handle_message(self, session, payload):
        data = payload.get('data') or {}
        key = data.get('key') or {}

        if key.get('fromMe'):
            return
        remote_jid = str(key.get('remoteJid') or '')
        if remote_jid.endswith('@g.us'):
            return  # group traffic, same as the old handler ignored

        # A LID-addressed sender hides the real number in remoteJid; the
        # gateway puts the usable one in senderPn / participant when it has it.
        phone = ''
        for candidate in (data.get('senderPn'), key.get('senderPn'),
                          key.get('participantPn'), remote_jid):
            candidate = str(candidate or '')
            if candidate and '@lid' not in candidate:
                phone = candidate.split('@')[0].split(':')[0]
                break
        if not phone:
            _logger.info("WhatsApp webhook: no usable number in %s", remote_jid)
            return

        text, is_audio = _text_of(data.get('message') or {})

        env = request.env
        engine = env['wa.report.engine'].sudo() if 'wa.report.engine' in env else None

        if is_audio:
            audio = self._fetch_media(session, data)
            if audio and engine is not None:
                try:
                    text = engine.transcribe_audio_bytes(audio) or ''
                except Exception as err:  # noqa: BLE001
                    _logger.error("WhatsApp transcription failed: %s", err)

        _logger.info("WhatsApp incoming from %s (audio=%s): %r",
                     phone, is_audio, (text or '')[:60])

        env['whatsapp.message'].sudo().create({
            'session_id': session.id,
            'phone': phone,
            'message': text or ('[voice note]' if is_audio else ''),
            'direction': 'incoming',
            'status': 'received',
            'wa_message_id': str(key.get('id') or ''),
        })

        # Honour a stop before anything replies to it. Doing this after the
        # auto-reply would answer someone who just asked to be left alone.
        if env['whatsapp.optout'].sudo().is_stop_word(text):
            env['whatsapp.optout'].sudo().record(phone, source='inbound')
            return

        if engine is None:
            return
        try:
            config = env['wa.reporting.config'].sudo().get_config()
            if not (config and config.is_phone_allowed(phone)):
                return
            if text:
                engine.handle_incoming(phone, text)
            elif is_audio:
                engine.send_wa_text(phone, (
                    "Sorry, I couldn't understand the voice note. "
                    "Please type your request or send a clearer one."))
        except Exception as err:  # noqa: BLE001
            _logger.error("WhatsApp reporting forward failed: %s", err)

    def _fetch_media(self, session, data):
        """Ask the gateway to decrypt and hand back a voice note."""
        try:
            body = session._gateway_call(
                'POST',
                '/chat/getBase64FromMediaMessage/%s' % session.instance_name,
                {'message': data, 'convertToMp4': False},
                timeout=(5, 60))
        except Exception as err:  # noqa: BLE001
            _logger.error("WhatsApp: could not download media: %s", err)
            return b''
        import base64
        raw = (body or {}).get('base64') or ''
        try:
            return base64.b64decode(raw) if raw else b''
        except (ValueError, TypeError):
            return b''
