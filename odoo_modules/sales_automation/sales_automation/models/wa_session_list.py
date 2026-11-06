"""A tappable list prompt, which is the only one that works in a group.

`send_buttons` exists on the session already, but in a group its message is
*accepted* by Evolution and then arrives as "This message couldn't load. Open
the message on your phone to view it." Because the call succeeded, the built-in
numbered-text fallback never fires - so the customer is left with an unreadable
message and nothing to tap.

A `sendList` renders properly in the same group, so that is what a question in a
group uses. It is added here rather than in whatsapp_gateway because the gateway
is shared by twelve databases plus the live server, and none of the others sends
lists.

A tapped row comes back through the gateway's own `_text_of`, which already
reads `listResponseMessage.singleSelectReply.selectedRowId`. So the reply
arrives as whatever `rowId` was set when sending - not the visible label - and
the caller matches on that id.
"""

import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class WhatsAppSession(models.Model):
    _inherit = 'whatsapp.session'

    def sa_send_list(self, phone, body, rows, button_text=None, title=None):
        """Send a single-select list. `rows` is [{'id', 'title', 'subtitle'}].

        Returns True when it went out (or was queued), False when the session
        is switched off. Raises the same way `send_message` does, so callers
        can fall back to plain text.
        """
        self.ensure_one()
        if not self.use_whatsapp:
            _logger.info("WhatsApp is switched off for session '%s'.", self.name)
            return False
        destination = self._clean_phone(phone)
        if not destination:
            raise UserError(_("No recipient provided."))
        if not rows:
            raise UserError(_("A list needs at least one row."))

        # Every one of these must be a non-empty string. A list with an empty
        # title is accepted by Evolution, logged as sent, and then simply never
        # appears in the chat - no error anywhere, on either side. The panel
        # warns about the same trap for buttons ("an absent title reaches the
        # recipient as the literal text *undefined*"); for a list it is worse,
        # because nothing arrives at all.
        payload = {
            'number': destination,
            'title': title or _("Please choose"),
            'description': body,
            'buttonText': button_text or _("Choose"),
            'footerText': self.tenant_label or self.name or ' ',
            'sections': [{
                'title': _("Answer"),
                'rows': [{
                    'title': row['title'],
                    'description': row.get('subtitle') or '',
                    'rowId': row['id'],
                } for row in rows],
            }],
            'delay': self.send_delay_ms,
        }
        return self._send_payload('sendList', payload, destination, body)

    def _send_payload(self, endpoint, payload, phone, log_text,
                      queue_on_failure=True, retry=None):
        """`sa_link_preview` in the context asks Evolution for the link's
        preview card under a text message (the shop link on the menu)."""
        if endpoint == 'sendText' and self.env.context.get('sa_link_preview'):
            payload = dict(payload, linkPreview=True)
        return super()._send_payload(endpoint, payload, phone, log_text,
                                     queue_on_failure=queue_on_failure, retry=retry)

    def sa_send_text_mentioning(self, phone, message, mention):
        """Send text that @mentions one group member.

        Verified against the live panel: it forwards `mentioned` through to
        Evolution and the mention renders and notifies. It lives here rather
        than in whatsapp_gateway for the same reason `sendList` does - that
        module is shared by twelve databases and none of the others needs it.

        `mention` is bare digits. The caller must also put the literal
        @<digits> token in the text, or WhatsApp renders an ordinary message:
        the array marks who is mentioned, the token is what is highlighted.

        Falls back to `send_message` when there is nobody to mention, so
        callers do not need two code paths.
        """
        self.ensure_one()
        digits = ''.join(ch for ch in str(mention or '') if ch.isdigit())
        if not digits:
            return self.send_message(phone, message)
        if not self.use_whatsapp:
            _logger.info("WhatsApp is switched off for session '%s'.", self.name)
            return False
        destination = self._clean_phone(phone)
        if not destination:
            raise UserError(_("No recipient provided."))

        body = self._sign(message)
        # Same policy gate as send_message: a mention must not become a way
        # around an opt-out or the daily cap.
        reason = self._policy_block(destination, body)
        if reason:
            _logger.info("WhatsApp to %s blocked: %s", destination, reason)
            self._log(destination, body, 'blocked')
            return False

        return self._send_payload('sendText', {
            'number': destination,
            'text': body,
            'delay': self.send_delay_ms,
            'mentioned': ['%s@s.whatsapp.net' % digits],
        }, destination, body)

    def sa_send_poll(self, phone, question, options):
        """Ask a question as a WhatsApp poll. `options` is a list of labels.

        The poll is the only tappable prompt confirmed to render in a group on
        this transport: `sendButtons` arrives as "This message couldn't load",
        and `sendList` can be accepted, stored and reported sent while WhatsApp
        silently displays nothing.

        The answer comes back as a `pollUpdateMessage`, and Evolution decrypts
        it for us - `vote.selectedOptions` holds the chosen labels in clear, so
        no key handling is needed here. It arrives with empty message text
        though, which is why the webhook has to look for it explicitly.
        """
        self.ensure_one()
        if not self.use_whatsapp:
            _logger.info("WhatsApp is switched off for session '%s'.", self.name)
            return False
        destination = self._clean_phone(phone)
        if not destination:
            raise UserError(_("No recipient provided."))
        if len(options) < 2:
            raise UserError(_("A poll needs at least two options."))

        return self._send_payload('sendPoll', {
            'number': destination,
            'name': question,
            'selectableCount': 1,
            'values': list(options),
            'delay': self.send_delay_ms,
        }, destination, question)
