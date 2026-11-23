# -*- coding: utf-8 -*-
"""Customer links: each one goes where the admin chose (owner, 21 Nov 2026).

A group order sends the customer links - the product details page, the address
form, the sign link, the payment link, live tracking, the rider's location, the
review link, the website's order page, the shop link - and the order and
invoice PDFs. For each of them the admin picks one place, in Sales Automation >
Configuration > Customer Links or on the 369 Mart console (WhatsApp tab):

* **Private chat** - the whole message goes to the customer's own chat and the
  group gets one short line ("💳 I've sent your payment link to your private
  chat 🔒", switchable);
* **Group** - it is posted in the group, marked "only for <name>".

Private that cannot be done (WhatsApp hides the number, or refuses the message)
falls back to the group the same way. Polls and taps always stay in the group,
where the order conversation runs.

It is decided in one place, `_say`, which every group message of this flow
passes through - including the delivery modules' messages for group orders.
Each link's kind is read from its address (`_sa_link_kind_of`) - the one table
here - so a new message carrying a known link follows the setting without
being listed. Pictures (product details) and PDFs are not texts and use
`_sa_private_target(kind)` / `_sa_send_doc`.
"""
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# the salesbot starts nothing in a private chat this long after a group order's link
PRIVATE_QUIET_HOURS = 6

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
    # The admin's choice per kind of link
    # ------------------------------------------------------------------
    def _sa_link_settings(self):
        return self.env['sa.ai.settings'].sudo().get_settings()

    def _sa_link_route(self, kind):
        """'private' or 'group' for this kind of link (Customer Links)."""
        try:
            return self._sa_link_settings()._sa_link_route(kind)
        except Exception:  # noqa: BLE001 - before the fields exist (upgrade)
            return 'group' if kind == 'shop' else 'private'

    def _sa_shop_url_param(self):
        return (self.env['ir.config_parameter'].sudo().get_param('sa.shop_url', '') or '').strip().rstrip('/')

    def _sa_link_kind_of(self, url):
        """Which customer link an address is - the one table of them."""
        low = (url or '').lower()
        shop = self._sa_shop_url_param().lower()
        if '%2fwa%2freview' in low or '/wa/review' in low:
            return 'review'
        if '/scoped_app/c?' in low or '%2fwa%2fconfirm' in low or '/wa/confirm' in low:
            return 'confirm'
        if '%2fwa%2faddress' in low or '/wa/address' in low:
            return 'address'
        if ('%2fwa%2fpay' in low or '/wa/pay' in low or 'payment%2fpay' in low or '/payment/pay' in low
                or 'payment_amount' in low):
            return 'pay'            # a confirmed order's pay link: its order page with an amount
        if '%2fmy%2forders' in low or '/my/orders' in low:
            return 'sign'
        if '%2fwa%2ftrack' in low or '/wa/track' in low:
            return 'track'
        if 'maps.google' in low or 'google.com/maps' in low:
            return 'map'
        if '/track/' in low or '/order/' in low:
            return 'web'            # the 369 Mart website's own order page (before the shop: same host)
        if shop and low.rstrip('/').startswith(shop):
            return 'shop'
        return 'link'

    # ------------------------------------------------------------------
    # What somebody types in the private chat is kept and not answered
    # ------------------------------------------------------------------
    def _sa_mark_private(self):
        self.sudo().write({'sa_private_sent_on': fields.Datetime.now()})

    @api.model
    def _sa_private_reply_request(self, digits, session):
        """The enquiry this number was sent something privately for, in the
        last few hours (Customer Links), on this WhatsApp session - else empty."""
        digits = ''.join(c for c in (digits or '') if c.isdigit())
        if len(digits) < 8 or not session:
            return self.browse()
        since = fields.Datetime.now() - timedelta(hours=PRIVATE_QUIET_HOURS)
        return self.sudo().search([
            ('requester_phone', 'like', digits[-9:]),
            ('sa_private_sent_on', '>=', since),
            ('group_id.session_id', '=', session.id),
        ], order='sa_private_sent_on desc, id desc', limit=1)

    # ------------------------------------------------------------------
    # Where it can go
    # ------------------------------------------------------------------
    def _sa_private_target(self, kind=None):
        """The customer's own number when this kind of link goes privately
        (and can: WhatsApp shows the number); '' means the group."""
        self.ensure_one()
        if self.env.context.get('sa_no_private'):
            return ''
        if kind and self._sa_link_route(kind) != 'private':
            return ''
        return self._sa_dm_target() or ''

    def _sa_in_group(self):
        self.ensure_one()
        return bool(self.group_id.group_jid) and self._sa_reply_to() == self.group_id.group_jid

    def _sa_private_footer(self):
        return _("\n\n_Only for you · answer in the group_")

    def _sa_group_marker(self):
        """The line under a personal link posted in the group."""
        self.ensure_one()
        who = (self.requester_name or '').strip() or _("the customer")
        return _("\n\n_\U0001F512 Only for %s_") % who

    def _sa_private_ref(self):
        self.ensure_one()
        return self.ref_code or (self.order_id.name if self.order_id else '') or ''

    def _sa_group_note_on(self):
        try:
            return bool(self._sa_link_settings().link_group_note)
        except Exception:  # noqa: BLE001
            return True

    # ------------------------------------------------------------------
    # Texts
    # ------------------------------------------------------------------
    def _sa_customer_links(self, body):
        """Every web link in a text, with its kind: [(url, kind)]."""
        out = []
        for url in _URL.findall(body or ''):
            url = url.rstrip(_URL_TAIL)
            out.append((url, self._sa_link_kind_of(url)))
        return out

    def _sa_private_note(self, links):
        """The line the group sees instead, by what the links are for.
        `links`: urls, or (url, kind) pairs."""
        self.ensure_one()
        kinds = []
        for item in links:
            kind = item[1] if isinstance(item, (list, tuple)) else self._sa_link_kind_of(item)
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
            'web': _("\U0001F310 I've sent your order page%s to your *private chat* \U0001F512") % order,
            'shop': _("\U0001F6D2 I've sent you our shop link in your *private chat* \U0001F512"),
            'link': _("\U0001F512 I've sent you a link%s in your *private chat* \U0001F4E9") % order,
        }
        return '\n'.join(lines.get(k, lines['link']) for k in kinds)

    def _sa_private_route(self, body):
        """Send `body` privately and the note to the group. True when done;
        False leaves the message to the group."""
        self.ensure_one()
        if not body or not self.group_id or not self._sa_in_group():
            return False
        links = self._sa_customer_links(body)
        if not links:
            return False
        # Private when any of its links is set to the private chat
        private_kinds = [k for _u, k in links if self._sa_link_route(k) == 'private']
        if not private_kinds:
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
        _logger.info("Sales Automation: enquiry %s - %s link sent privately", self.id, ','.join(private_kinds))
        if self._sa_group_note_on():
            self.with_context(sa_no_private=True)._say(self._sa_private_note(links))
        return True

    def _say(self, body, addressed=True):
        if not self.env.context.get('sa_no_private'):
            try:
                if self._sa_private_route(body):
                    return True
            except Exception:  # noqa: BLE001 - never lose the message
                _logger.exception("Sales Automation: enquiry %s - private route failed", self.id)
            # A personal link that stays in the group says whose it is
            try:
                if body and self.group_id and self._sa_in_group() and 'Only for ' not in body and any(
                        k not in ('shop', 'link') for _u, k in self._sa_customer_links(body)):
                    body = body + self._sa_group_marker()
            except Exception:  # noqa: BLE001 - the words still go out
                pass
        return super()._say(body, addressed=addressed)

    # ------------------------------------------------------------------
    # PDFs and pictures
    # ------------------------------------------------------------------
    def _sa_doc_dest(self):
        """(where, private) for the order and invoice PDFs (Customer Links)."""
        self.ensure_one()
        phone = self._sa_private_target('docs')
        if phone:
            return phone, True
        return self.group_id.group_jid, False

    def _sa_send_doc(self, send, note=''):
        """Run `send(destination)` privately when allowed, falling back to the
        group. Posts `note` in the group after a private send (when the group
        note is on). Returns 'private' or 'group'."""
        self.ensure_one()
        dest, private = self._sa_doc_dest()
        if private:
            try:
                if send(dest):
                    self._sa_mark_private()
                    if note and self._sa_group_note_on():
                        self.with_context(sa_no_private=True)._say(note)
                    return 'private'
            except Exception as err:  # noqa: BLE001 - the group gets it instead
                _logger.info("Sales Automation: enquiry %s - private document refused: %s", self.id, err)
        send(self.group_id.group_jid)
        return 'group'


class AutoReplyNotInAGroupOrder(models.Model):
    _inherit = 'wa.auto.reply'

    def _sa_private_quiet(self, conv, session):
        return bool(self.env['sa.group.request'].sudo()._sa_private_reply_request(conv.phone or '', session.session_id))

    def _check_conversation(self, conv, session, cutoff_time):
        if self._sa_private_quiet(conv, session):
            return None
        return super()._check_conversation(conv, session, cutoff_time)

    def _check_conversation_for_message(self, conv, session, cutoff, trigger_log=None):
        if self._sa_private_quiet(conv, session):
            return None
        return super()._check_conversation_for_message(conv, session, cutoff, trigger_log)
