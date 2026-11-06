"""Route Odoo's outgoing email through the gateway.

Every module that sends mail the ordinary Odoo way - whatsapp_email's
notifications, POS receipts, invoices, anything built on `mail.mail` - ends up
in `ir.mail_server.send_email()`. Overriding that one method puts all of it on
the vendor's mail account without editing a single one of those modules.

It also ends a split that had grown up: `whatsapp_email` was configuring its own
`ir.mail_server` records while WhatsApp went through the gateway, so the same
customer could be unsubscribed on one channel and still emailed on the other.
One place decides now.

When the gateway cannot be reached this raises MailDeliveryException, which is
what Odoo expects: `mail.mail` marks the message failed and keeps it for retry
rather than losing it. It deliberately does NOT fall back to direct SMTP -
falling back would send precisely the messages the opt-out list exists to stop.
"""

import base64
import logging

from odoo import _, api, models
from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class IrMailServer(models.Model):
    _inherit = 'ir.mail_server'

    @api.model
    def _wa_gateway_session(self):
        """The session that should carry Odoo's mail, or an empty recordset."""
        Session = self.env['whatsapp.session'].sudo()
        return Session.search([
            ('active', '=', True),
            ('route_odoo_mail', '=', True),
            ('gateway_api_key', '!=', False),
        ], limit=1)

    @staticmethod
    def _wa_parts(message):
        """Pull text, html and attachments out of an email.message.Message."""
        text, html, attachments = '', '', []
        for part in message.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            if 'attachment' in (part.get('Content-Disposition') or ''):
                attachments.append({
                    'filename': part.get_filename() or 'attachment',
                    'content': base64.b64encode(payload).decode(),
                    'mimetype': part.get_content_type(),
                })
                continue
            charset = part.get_content_charset() or 'utf-8'
            try:
                body = payload.decode(charset, 'replace')
            except LookupError:
                body = payload.decode('utf-8', 'replace')
            if part.get_content_type() == 'text/html':
                html = html or body
            elif part.get_content_type() == 'text/plain':
                text = text or body
        return text, html, attachments

    def _connect__(self, *args, **kwargs):  # noqa: PLW3201
        """No SMTP socket is needed when the gateway is carrying the mail.

        `mail.mail.send()` opens a connection first and only then calls
        send_email(), so without this an Odoo with no SMTP server configured
        fails at the connect step and never reaches the gateway at all.
        Returning None is a supported outcome - Odoo itself does exactly this
        in test mode, and the caller already guards `if smtp_session:`.
        """
        if self._wa_gateway_session():
            return None
        return super()._connect__(*args, **kwargs)

    def send_email(self, message, mail_server_id=None, smtp_server=None, **kwargs):
        session = self._wa_gateway_session()
        if not session:
            return super().send_email(
                message, mail_server_id=mail_server_id, smtp_server=smtp_server, **kwargs)

        recipients = []
        for header in ('To', 'Cc', 'Bcc'):
            recipients.extend([str(v) for v in (message.get_all(header) or []) if v])
        if not recipients:
            _logger.warning("Gateway mail: message %s has no recipient.",
                            message.get('Message-Id'))
            return message.get('Message-Id')

        text, html, attachments = self._wa_parts(message)
        try:
            sent = session.send_email(
                recipients[0],
                message.get('Subject') or '',
                body_html=html,
                body_text=text,
                cc=recipients[1:] or None,
                reply_to=message.get('Reply-To') or None,
                attachments=attachments or None,
            )
        except UserError as err:
            raise MailDeliveryException(_("Mail Delivery Failed"), str(err)) from err

        if not sent:
            # A rule stopped it: unsubscribed, blocked word, or over the cap.
            # Report it as a failure rather than returning quietly - returning
            # a message-id tells Odoo the mail went out, and it would sit in the
            # log marked "sent" having never left the building. Odoo puts it in
            # `exception` state with this reason, which is both visible and
            # true, and does not auto-retry it.
            _logger.info("Gateway mail: %s not sent (blocked by a rule).", recipients[0])
            raise MailDeliveryException(
                _("Not sent"),
                _("The gateway did not send this message. The recipient may have "
                  "unsubscribed, the content may have matched a blocked word, or "
                  "the daily cap may have been reached. Activity in the WhatsApp "
                  "panel shows which."))
        return message.get('Message-Id')
