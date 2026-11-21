# -*- coding: utf-8 -*-
"""Personal links and PDFs go to the customer's private chat (owner, 21 Nov 2026).

A group order used to post every personal link in the shared group: the
product details page, the sign link, the payment link, live tracking, the
rider's location, the shop's order page - and the invoice and order PDFs.
Anyone in the group could see them and open them.

Now, when the setting "Send links & PDFs privately" is on (the default) and
WhatsApp shows the customer's number, the whole message goes to their private
chat and the group gets one short line - "💳 I've sent your payment link to
your private chat 🔒". Polls and taps stay in the group, where the order
conversation runs. With the number hidden, or the private message refused,
everything goes to the group exactly as before.

It is decided in one place, `_say`, which every group message of this flow
passes through - including the delivery modules' messages for group orders -
so a new link anywhere follows the rule without being listed here. The
pictures (product details) and PDFs are not texts and use `_sa_doc_dest`.
The generic shop link (`sa.shop_url`) is the same for everyone and stays.
"""
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# For this long after a link or document went to the customer's private chat,
# what they type there is answered with "please answer in the group" instead
# of the one-to-one salesbot (owner, 21 Nov 2026). After it, as before.
PRIVATE_REPLY_HOURS = 6
PRIVATE_REPLY_EVERY = 300   # seconds: at most one such answer per number

# links hold "_" (scoped_app, access_token): cut only WhatsApp's bold/italic
# marks and punctuation off the end
_URL = re.compile(r'https?://\S+', re.I)
_URL_TAIL = '*_~.,;:!?)]>\'"'


class SaGroupRequestPrivateLinks(models.Model):
    _inherit = 'sa.group.request'

    sa_private_sent_on = fields.Datetime(
        'Last Sent Privately', readonly=True, copy=False,
        help="When a link or document of this enquiry last went to the "
             "customer's private chat. For a few hours after it, what they "
             "type there is pointed back to the group.")

    # ------------------------------------------------------------------
    # The private chat answers "please answer in the group"
    # ------------------------------------------------------------------
    def _sa_mark_private(self):
        self.sudo().write({'sa_private_sent_on': fields.Datetime.now()})

    @api.model
    def _sa_private_reply_request(self, digits, session):
        """The enquiry this number was sent something privately for, in the
        last few hours, on this WhatsApp session - else empty."""
        digits = ''.join(c for c in (digits or '') if c.isdigit())
        if len(digits) < 8 or not session:
            return self.browse()
        since = fields.Datetime.now() - timedelta(hours=PRIVATE_REPLY_HOURS)
        return self.sudo().search([
            ('requester_phone', 'like', digits[-9:]),
            ('sa_private_sent_on', '>=', since),
            ('group_id.session_id', '=', session.id),
        ], order='sa_private_sent_on desc, id desc', limit=1)

    def _sa_private_redirect_reply(self, digits):
        """Answer a message typed in the private chat: this chat only carries
        links and documents, the conversation is in the group. Once every few
        minutes at most; True either way (the salesbot stays out)."""
        self.ensure_one()
        if not self.env['sa.outbox.guard'].sudo().claim('privreply|%s' % digits, PRIVATE_REPLY_EVERY):
            return True
        group = self.group_id.sudo()
        invite = group._sa_back_url() if hasattr(group, '_sa_back_url') else ''
        invite = ('\n\U0001F449 %s' % invite) if invite.startswith('https://chat.whatsapp.com/') else ''
        text = _("\U0001F512 This chat only sends you your links and documents.\n"
                 "Please answer in the group *%(group)s* \U0001F64F%(invite)s",
                 group=group.name or _("your WhatsApp group"), invite=invite)
        try:
            group.session_id.send_message(digits, text)
        except Exception as err:  # noqa: BLE001 - nothing else to do with it
            _logger.info("Sales Automation: enquiry %s - private reply not sent: %s", self.id, err)
        return True

    # ------------------------------------------------------------------
    # Where it can go
    # ------------------------------------------------------------------
    def _sa_private_target(self):
        """The customer's own number, when personal things go privately."""
        self.ensure_one()
        if self.env.context.get('sa_no_private'):
            return ''
        try:
            if not self._settings().private_links:
                return ''
        except Exception:  # noqa: BLE001 - before the field exists (upgrade)
            return ''
        return self._sa_dm_target() or ''

    def _sa_in_group(self):
        self.ensure_one()
        return bool(self.group_id.group_jid) and self._sa_reply_to() == self.group_id.group_jid

    def _sa_private_footer(self):
        return _("\n\n_Only for you · answer in the group_")

    def _sa_private_ref(self):
        self.ensure_one()
        return self.ref_code or (self.order_id.name if self.order_id else '') or ''

    # ------------------------------------------------------------------
    # Texts
    # ------------------------------------------------------------------
    def _sa_customer_links(self, body):
        """The personal links in a text: every web link but the shop's own."""
        shop = (self.env['ir.config_parameter'].sudo().get_param('sa.shop_url', '') or '').strip().rstrip('/')
        links = []
        for url in _URL.findall(body or ''):
            url = url.rstrip(_URL_TAIL)
            if shop and url.rstrip('/').lower().startswith(shop.lower()):
                continue
            links.append(url)
        return links

    def _sa_private_note(self, links):
        """The line the group sees instead, by what the link is for."""
        self.ensure_one()
        kinds = []
        for url in links:
            low = url.lower()
            if '%2fwa%2freview' in low or '/wa/review' in low:
                kind = 'review'
            elif '/scoped_app/c' in low or '%2fwa%2fconfirm' in low or '/wa/confirm' in low:
                kind = 'confirm'
            elif ('%2fwa%2fpay' in low or '/wa/pay' in low or 'payment%2fpay' in low or '/payment/pay' in low
                  or 'payment_amount' in low):
                # a confirmed order's pay link is its order page with an amount
                kind = 'pay'
            elif '%2fmy%2forders' in low or '/my/orders' in low:
                kind = 'sign'
            elif '%2fwa%2ftrack' in low or '/wa/track' in low or '/track/' in low:
                kind = 'track'
            elif 'maps.google' in low or 'google.com/maps' in low:
                kind = 'map'
            elif '%2fwa%2faddress' in low or '/wa/address' in low:
                kind = 'address'
            else:
                kind = 'link'
            if kind not in kinds:
                kinds.append(kind)
        ref = self._sa_private_ref()
        order = (_(" for order *#%s*") % ref) if ref else ''
        lines = {
            'confirm': _("\U0001F4E6 I've sent the product photo and details%s to your *private chat* "
                         "\U0001F512 Press ACCEPT there.") % order,
            'sign': _("✍️ I've sent the link to sign %s to your *private chat* "
                      "\U0001F512") % ((_("order *#%s*") % ref) if ref else _("your order")),
            'pay': _("\U0001F4B3 I've sent your payment link%s to your *private chat* \U0001F512") % order,
            'track': _("\U0001F4E6 I've sent your live tracking link%s to your *private chat* "
                       "\U0001F512") % order,
            'map': _("\U0001F6F5 I've sent the rider's location%s to your *private chat* \U0001F512") % order,
            'address': _("\U0001F4E9 I've sent you a form%s in your *private chat* \U0001F512") % order,
            'review': _("⭐ I've sent you a link to rate your products%s to your *private chat* "
                        "\U0001F512") % order,
            'link': _("\U0001F512 I've sent you a link%s in your *private chat* \U0001F4E9") % order,
        }
        return '\n'.join(lines[k] for k in kinds)

    def _sa_private_route(self, body):
        """Send `body` privately and the note to the group. True when done;
        False leaves the message to the group, as before."""
        self.ensure_one()
        if not body or not self.group_id or not self._sa_in_group():
            return False
        links = self._sa_customer_links(body)
        if not links:
            return False
        phone = self._sa_private_target()
        if not phone:
            return False
        if not self.env['sa.outbox.guard'].sudo().claim('priv|%s|%s' % (phone, body), 300):
            return True     # the same message went privately moments ago
        try:
            sent = self.group_id.session_id.send_message(phone, body + self._sa_private_footer())
        except Exception as err:  # noqa: BLE001 - the group gets it instead
            _logger.info("Sales Automation: enquiry %s - private message refused: %s", self.id, err)
            sent = False
        if not sent:
            return False
        self._sa_stamp_asked()
        self._sa_mark_private()
        _logger.info("Sales Automation: enquiry %s - link sent privately", self.id)
        self.with_context(sa_no_private=True)._say(self._sa_private_note(links))
        return True

    def _say(self, body, addressed=True):
        if not self.env.context.get('sa_no_private'):
            try:
                if self._sa_private_route(body):
                    return True
            except Exception:  # noqa: BLE001 - never lose the message
                _logger.exception("Sales Automation: enquiry %s - private route failed", self.id)
        return super()._say(body, addressed=addressed)

    # ------------------------------------------------------------------
    # PDFs and pictures
    # ------------------------------------------------------------------
    def _sa_doc_dest(self):
        """(where, private): the customer's number when PDFs go privately,
        else the group."""
        self.ensure_one()
        phone = self._sa_private_target()
        if phone:
            return phone, True
        return self.group_id.group_jid, False

    def _sa_send_doc(self, send, note=''):
        """Run `send(destination)` privately when allowed, falling back to the
        group. Posts `note` in the group after a private send. Returns
        'private', 'group' or False."""
        self.ensure_one()
        dest, private = self._sa_doc_dest()
        if private:
            try:
                if send(dest):
                    self._sa_mark_private()
                    if note:
                        self.with_context(sa_no_private=True)._say(note)
                    return 'private'
            except Exception as err:  # noqa: BLE001 - the group gets it instead
                _logger.info("Sales Automation: enquiry %s - private document refused: %s", self.id, err)
        send(self.group_id.group_jid)
        return 'group'
