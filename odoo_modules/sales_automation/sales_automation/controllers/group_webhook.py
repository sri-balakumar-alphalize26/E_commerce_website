"""Let group messages through, for the databases that asked for it.

whatsapp_gateway drops them at the door:

    remote_jid = str(key.get('remoteJid') or '')
    if remote_jid.endswith('@g.us'):
        return  # group traffic, same as the old handler ignored

That line is correct for every database that is not selling in groups, and the
gateway is shared - twelve databases here, plus the live server. So it is not
edited. Odoo builds its routing map per database from the installed modules
only, so subclassing the controller turns group traffic on exactly where
`sales_automation` is installed and nowhere else.

One-to-one messages are handed straight back to the parent, untouched.
"""

import logging

from odoo.addons.whatsapp_gateway.controllers.webhook import (
    WhatsAppWebhook, _text_of,
)
from odoo import _
from odoo.http import request

_logger = logging.getLogger(__name__)


# The Baileys keys for everything that is not text. A caption arrives as
# `imageMessage.caption` and is picked up by the gateway's `_text_of`, so
# reaching here means there was no caption either.
_SA_MEDIA_KEYS = (
    ('imageMessage', 'photo'),
    ('videoMessage', 'video'),
    ('stickerMessage', 'sticker'),
    ('documentMessage', 'file'),
    ('documentWithCaptionMessage', 'file'),
    ('audioMessage', 'voice note'),
    ('ptvMessage', 'video note'),
    ('contactMessage', 'contact card'),
    ('locationMessage', 'location'),
)


def _sa_media_kind(message):
    """What kind of non-text message this is, or '' when it is not one."""
    if not isinstance(message, dict):
        return ''
    for key, label in _SA_MEDIA_KEYS:
        # Presence, not truthiness. A location arrives as an empty
        # `locationMessage: {}` when the sender's coordinates are stripped,
        # and `.get(key)` read that as no media at all.
        if message.get(key) is not None:
            return label
    return ''


class WhatsAppWebhookGroups(WhatsAppWebhook):

    def _sa_conduct_gate(self, session, data, key, remote_jid, text,
                         participant, participant_lid):
        """True when the message was removed for its language and must go
        no further - no enquiry, no quote, no reply. This module never
        removes anything; `sales_automation_insights` overrides it."""
        return False

    # ---- human takeover -------------------------------------------------
    def _sa_takeover_from_me(self, session, data, key, remote_jid):
        """A `fromMe` message the assistant did not send is the shopkeeper
        typing on the shop phone: hold that chat."""
        env = request.env
        settings = env['sa.ai.settings'].sudo().get_settings()
        if not settings or not settings.takeover_enabled:
            return False
        Hold = env['sa.human.hold'].sudo()
        msg = data.get('message') or {}
        text, _audio = _text_of(msg)
        # A poll, or a message in the assistant's own wording, coming from our
        # number is a bot: this database's own send, or another server linked
        # to the same phone (seen 27 Sep 2026: two servers paired to one phone
        # answered "hi" twice, and the second poll held the group). A person
        # typing on the shop phone never produces these.
        t = text or ''
        if any(k.startswith('pollCreationMessage') for k in msg) \
                or (' Ref ' in t and '\U0001F447' in t) \
                or t.startswith('Hi \U0001F44B welcome') \
                or '\U0001F514 *This is an automated notification' in t:
            return False
        if not Hold.is_ours_unsent(session, str(key.get('id') or ''), text,
                                   Hold.chat_key_for(remote_jid)):
            return False
        Hold.hold(session, remote_jid, 'shop phone', text, settings)
        return True

    def _sa_takeover_gate(self, session, data, key, remote_jid, phase):
        """phase 'sender': the message is from a listed shopkeeper number ->
        hold the chat, True. phase 'held': the chat is held -> record the
        customer's message and True, so the assistant stays quiet."""
        env = request.env
        settings = env['sa.ai.settings'].sudo().get_settings()
        if not settings or not settings.takeover_enabled:
            return False
        Hold = env['sa.human.hold'].sudo()
        is_group = str(remote_jid).endswith('@g.us')
        if phase == 'sender':
            if is_group:
                participant, _lid, _is_lid = self._sa_sender_of(data, key)
                digits = ''.join(c for c in str(participant or '') if c.isdigit())
            else:
                digits = ''.join(c for c in str(remote_jid).split('@')[0] if c.isdigit())
            if not digits or not Hold.is_shopkeeper(digits, settings):
                return False
            text, _audio = _text_of(data.get('message') or {})
            Hold.hold(session, remote_jid, digits, text, settings)
            return True
        if Hold.is_held(remote_jid):
            text, is_audio = _text_of(data.get('message') or {})
            vals = {'session_id': session.id,
                    'phone': remote_jid if is_group else ''.join(c for c in str(remote_jid).split('@')[0] if c.isdigit()),
                    'message': text or ('[voice note]' if is_audio else '[media]'),
                    'direction': 'incoming', 'status': 'received',
                    'wa_message_id': str(key.get('id') or ''),
                    'push_name': str(data.get('pushName') or '')}
            if is_group:
                participant, participant_lid, is_lid = self._sa_sender_of(data, key)
                vals.update({'group_jid': remote_jid, 'participant_phone': participant,
                             'participant_lid': participant_lid, 'participant_is_lid': is_lid})
            held_msg = env['whatsapp.message'].sudo().create(vals)
            Hold.attach_pending(remote_jid, held_msg)
            _logger.info("Takeover: %s held - message from %s recorded, not answered",
                         remote_jid, vals.get('participant_phone') or vals['phone'])
            return True
        return False

    def _handle_message(self, session, payload):
        data = payload.get('data') or {}
        key = data.get('key') or {}
        remote_jid = str(key.get('remoteJid') or '')

        # Evolution redelivers an event when the first handling is slow - on
        # 5 Sep a "yes" arrived twice three seconds apart, both copies ran,
        # the customer was quoted twice and the second request died on a
        # serialization failure. The guard table commits on its own
        # connection, so the second copy sees the claim even while the first
        # is still mid-transaction, and is answered 200 with nothing done.
        wa_id = str(key.get('id') or '')
        if wa_id and not key.get('fromMe'):
            guard = request.env['sa.outbox.guard'].sudo()
            if not guard.claim('in|%s' % wa_id, 600):
                _logger.info("WhatsApp: message %s delivered again - ignored",
                             wa_id)
                return
            # The claim is committed on its own connection, so it outlives a
            # rollback of THIS transaction - and then Odoo's retry is waved
            # through as a duplicate and the message is never handled at all.
            # That is how a customer came to be sent a finder poll belonging
            # to an enquiry that no longer existed: the sends had already
            # left, the record had not. Handing the claim back on rollback
            # keeps duplicate-suppression for concurrent copies while letting
            # a failed attempt be retried.
            request.env.cr.postrollback.add(
                lambda: request.env['sa.outbox.guard'].sudo().release(
                    'in|%s' % wa_id))

        if not remote_jid.endswith('@g.us'):
            # A poll vote carries no text. In a private chat that made a tap
            # on Yes / No invisible to the tracker, so the chosen label is
            # written where the text would be before anyone reads it.
            message = data.get('message') or {}
            if not _text_of(message)[0]:
                choice = self._sa_poll_choice(message)
                if choice:
                    # A supplier's tap on OUR YES/NO poll, matched by the
                    # poll's own id - before any customer logic. On 8 Sep a
                    # number that was both a supplier and a customer tapped
                    # YES on "do you have this?", "whoever asked last" read
                    # it as "yes, confirm my order", and they were sent a
                    # payment poll.
                    if self._sa_vendor_poll_vote(session, data, remote_jid,
                                                 choice):
                        return
                    # A tap on one of the finder's polls is the finder's to
                    # answer; the tracker must never see the label.
                    if self._sa_finder_vote(session, data, remote_jid, choice):
                        return
                    # A quantity *range* is answered here with the exact
                    # numbers; the tracker would read "11-15" as nonsense.
                    if self._sa_quantity_range(session, remote_jid, choice):
                        return
                    data['message'] = {'conversation': choice}
                    payload['data'] = data
            if key.get('fromMe'):
                self._sa_takeover_from_me(session, data, key, remote_jid)
            elif self._sa_takeover_gate(session, data, key, remote_jid, 'sender'):
                return
            # Language first: a supplier's or customer's abuse is removed and
            # remarked before any of it can be read as a code or a price.
            if not key.get('fromMe'):
                p_text, _p_audio = _text_of(data.get('message') or {})
                p_digits = ''.join(c for c in remote_jid.split('@')[0] if c.isdigit())
                if self._sa_conduct_gate(session, data, key, remote_jid, p_text,
                                         p_digits, ''):
                    return
            # A customer who tapped a link is answering a group enquiry from
            # their own chat. Checked before the vendor branch because the same
            # number can be both here, and a coded reply is unambiguous.
            if self._sa_customer_code_reply(session, payload, remote_jid):
                return
            # A vendor answering a price check is not a customer. Their reply
            # has to be read as a quote and kept away from the tracker's
            # auto-reply, which would otherwise greet a supplier and try to
            # sell them something.
            if self._sa_capture_vendor_reply(session, payload, remote_jid):
                return
            if not key.get('fromMe') and self._sa_takeover_gate(
                    session, data, key, remote_jid, 'held'):
                return
            # Written in the private chat that only carries a group order's
            # links and documents: pointed back to the group, not answered by
            # the salesbot (owner, 21 Nov 2026; models/sa_private_links.py).
            return super()._handle_message(session, payload)

        if key.get('fromMe'):
            self._sa_takeover_from_me(session, data, key, remote_jid)
            return  # our own reply coming back around
        if self._sa_takeover_gate(session, data, key, remote_jid, 'sender'):
            return

        participant, participant_lid, is_lid = self._sa_sender_of(data, key)
        text, is_audio = _text_of(data.get('message') or {})

        # A poll answer carries no message text at all - the choice sits in
        # pollUpdateMessage.vote.selectedOptions, already decrypted by
        # Evolution. Without this the tap arrives as an empty message and is
        # dropped as noise.
        if not text:
            text = self._sa_poll_choice(data.get('message') or {}) or text
        # Which poll was voted on. WhatsApp lets every member of a group vote
        # in every poll, so without this a tap is just a bare YES or NO from
        # whoever tapped - and it lands on whatever that person happens to have
        # open. On 31 Aug angitha voted NO on a poll addressed to
        # soniakuriakose and cancelled her own deal with it.
        poll_ref = self._sa_poll_ref(data.get('message') or {})

        if is_audio:
            text = self._sa_transcribe(session, data) or text

        # Language first, before the message is recorded or read by anyone.
        if self._sa_conduct_gate(session, data, key, remote_jid, text,
                                 participant, participant_lid):
            return
        # A shopkeeper is in this chat: recorded, not answered.
        if self._sa_takeover_gate(session, data, key, remote_jid, 'held'):
            return

        # A photo, video, sticker or document with no caption carries nothing
        # readable, so it is never an enquiry. What happens to it is a setting:
        # the default keeps the record and says nothing, which is what a
        # tester read as the assistant being unresponsive.
        kind = _sa_media_kind(data.get('message') or {}) if not text else ''
        if kind and self._sa_customer_group(session, remote_jid):
            action = request.env['sa.ai.settings'].sudo(
                ).get_settings().media_action or 'ignore'
            if action == 'discard':
                _logger.info("WhatsApp group %s: %s from %s discarded "
                             "unrecorded", remote_jid, kind,
                             participant or '(hidden)')
                return
            if action == 'reply':
                self._sa_answer_media(session, remote_jid,
                                      participant or participant_lid, kind)

        message = request.env['whatsapp.message'].sudo().create({
            'session_id': session.id,
            'phone': remote_jid,
            'message': text or ('[voice note]' if is_audio else ''),
            'direction': 'incoming',
            'status': 'received',
            'wa_message_id': str(key.get('id') or ''),
            'group_jid': remote_jid,
            'participant_phone': participant,
            'participant_lid': participant_lid,
            'participant_is_lid': is_lid,
            'quoted_wa_message_id': self._sa_quoted_id(data.get('message') or {}),
            'push_name': str(data.get('pushName') or ''),
        })

        _logger.info("WhatsApp group message in %s from %s: %r",
                     remote_jid, participant or '(hidden)', (text or '')[:60])

        try:
            request.env['sa.group.request'].sudo().with_context(
                sa_poll_ref=poll_ref)._on_group_message(message)
        except Exception as err:  # noqa: BLE001 - the webhook must answer 200
            _logger.exception("Sales Automation: group message %s failed: %s",
                              message.id, err)

    def _sa_customer_group(self, session, remote_jid):
        """The enabled customer group this message arrived in, if any.

        Both media rules are scoped to it. A vendor group is a working
        channel, and a group nobody has ticked is none of our business -
        discarding messages from either would be taking a decision the
        configuration never asked for.
        """
        return request.env['sa.sales.group'].sudo().search([
            ('session_id', '=', session.id),
            ('group_jid', '=', remote_jid),
            ('enabled', '=', True),
            ('group_type', '!=', 'vendor'),
        ], limit=1)

    def _sa_answer_media(self, session, remote_jid, who, kind):
        """Tell the sender we cannot read a picture, at most once a minute.

        Rate limited per person: a phone gallery share arrives as eight
        separate messages, and eight identical replies would be worse than
        the silence being complained about - the gateway would drop seven of
        them as duplicates anyway.
        """
        env = request.env
        settings = env['sa.ai.settings'].sudo().get_settings()
        body = (settings.media_reply_text or '').strip()
        if not body:
            return False
        if not env['sa.outbox.guard'].sudo().claim(
                'media|%s|%s' % (remote_jid, who or 'anon'), 60):
            return False
        try:
            session.send_message(remote_jid, body)
            _logger.info("WhatsApp group %s: answered a %s from %s",
                         remote_jid, kind, who or '(hidden)')
        except Exception as err:  # noqa: BLE001 - never break the webhook
            _logger.warning("Sales Automation: could not answer a %s in %s: %s",
                            kind, remote_jid, err)
        return True

    def _sa_customer_code_reply(self, session, payload, remote_jid):
        """A customer answering a group enquiry from their own chat.

        The tap-links on a quote pre-fill "#5Q ACCEPT" or "#5Q 1128.00", so the
        reply names the deal it belongs to. Without this there is no path for
        it at all: `_sa_request_for_conversation` only picks up an enquiry once
        it is `handed_off`, and a tap arrives while it is still `quoted`.

        Returns True when this was ours, so the salesbot never sees it.
        """
        data = payload.get('data') or {}
        key = data.get('key') or {}
        if key.get('fromMe'):
            return False

        digits = ''.join(c for c in str(remote_jid).split('@')[0]
                         if c.isdigit())
        if len(digits) < 8:
            return False
        text, _is_audio = _text_of(data.get('message') or {})
        if not text:
            return False

        import re
        found = re.search(r'#\s*([0-9A-Za-z]{1,6})', text)
        if not found:
            return False
        code = found.group(1).upper()

        env = request.env
        Request = env['sa.group.request'].sudo()
        # Scoped to the sender, always. A code is printed in a shared group,
        # so anyone can read one - and without this check they could drive
        # somebody else's deal from their own chat.
        enquiry = Request.search([
            ('ref_code', '=', code),
            ('requester_phone', 'like', digits[-9:]),
            # `handed_off` included: the tap-links stay in the chat after
            # the deal moves to a private conversation, and "#6N ACCEPT" fell
            # through to the salesbot, which answered a settled 550.00 deal
            # with a counter-offer of 525.00.
            ('state', 'in', ('sourcing', 'awaiting_vendor_pick',
                             'quoted', 'negotiating',
                             'awaiting_qty', 'awaiting_order_confirm',
                             'awaiting_confirm', 'finding', 'handed_off')),
            ('write_date', '>=', Request._sa_still_warm()),
        ], order='id desc', limit=1)
        if not enquiry:
            return False

        # One number, two hats. A supplier who is also the customer on this
        # very enquiry would otherwise have their quote filed as their own
        # wishful price - which is exactly what happened to G3.
        if enquiry.state == 'sourcing':
            tail = digits[-9:]
            asked = [(p.phone or '').strip() for p in enquiry.sourcing_vendor_ids]
            if any(tail and tail in (v or '') for v in asked):
                _logger.info(
                    "Sales Automation: %s is both the customer and a supplier "
                    "asked on %s - reading %r as a vendor price, not a "
                    "counter-offer", digits, enquiry.ref_code, text[:24])
                return False        # let the vendor capture take it

        message = env['whatsapp.message'].sudo().create({
            'session_id': session.id,
            'phone': digits,
            'message': text,
            'direction': 'incoming',
            'status': 'received',
            'wa_message_id': str(key.get('id') or ''),
            'participant_phone': digits,
            'push_name': str(data.get('pushName') or ''),
        })

        # Everything after the code is the answer: "ACCEPT", "30", "QTY 5".
        answer = re.sub(r'#\s*%s' % re.escape(code), ' ', text,
                        flags=re.IGNORECASE).strip()
        answer = re.sub(r'^(?:QTY|QUANTITY)\b', '', answer,
                        flags=re.IGNORECASE).strip()
        _logger.info("Sales Automation: %s answered enquiry %s privately: %r",
                     digits, enquiry.id, answer[:40])

        # Reply where they wrote, not in the group: their price is their
        # business, and answering the group would leave them with silence.
        enquiry = enquiry.with_context(sa_reply_to=digits,
                                       sa_trigger_msg=(
                                           message.wa_message_id
                                           or ('row%s' % message.id)))
        try:
            if enquiry.state == 'awaiting_confirm':
                verdict = Request._read_yes_no(answer)
                if verdict is True:
                    enquiry._on_confirmed()
                elif verdict is False:
                    enquiry._reject_match()
                return True
            enquiry._on_deal_reply(answer)
        except Exception as err:  # noqa: BLE001 - never 500 the webhook
            _logger.exception("Sales Automation: private reply to enquiry %s "
                              "failed: %s", enquiry.id, err)
        return True

    def _sa_capture_vendor_reply(self, session, payload, remote_jid):
        """Record a vendor's private price. True when it was ours to handle.

        Matching is by phone alone, and that is enough: the vendor was asked in
        a one-to-one chat, so whatever they send back can only belong to the
        request they were asked about. This is the whole reason for messaging
        vendors directly instead of posting in a shared group.
        """
        data = payload.get('data') or {}
        key = data.get('key') or {}
        if key.get('fromMe'):
            return False

        digits = ''.join(c for c in str(remote_jid).split('@')[0] if c.isdigit())
        if len(digits) < 8:
            return False

        env = request.env
        Request = env['sa.group.request'].sudo()
        text, _is_audio = _text_of(data.get('message') or {})
        if not text:
            return False

        from datetime import timedelta
        from odoo import fields as odoo_fields

        # A number stored with a space inside its last nine digits
        # ('+91 93612 19598') matched nothing here, so that supplier's
        # every reply fell through to the sales tracker. Try the sanitized
        # form as well.
        mine = ['|', ('sourcing_vendor_ids.phone', 'like', digits[-9:]),
                ('sourcing_vendor_ids.phone_sanitized', 'like', digits[-9:])]
        # A week, not a day. Suppliers answer when they get round to it, and by
        # then their chat has scrolled past the question - which is the whole
        # reason the code is in the message.
        cutoff = odoo_fields.Datetime.now() - timedelta(days=7)

        # Everything this supplier could still be answering. Not only what is
        # open: a one-minute window closes while a human is still typing, and
        # on 31 Aug a price landed 31 seconds after the last question timed
        # out. Losing that and then offering the supplier a product catalogue
        # is the worst of both.
        askable = Request.search(
            ['&', ('create_date', '>=', cutoff),
             '|', ('state', '=', 'sourcing'),
             '&', ('state', '=', 'dropped'),
             ('drop_reason', '=', 'no_vendor_reply')] + mine,
            order='id desc')
        if not askable:
            return False

        # The same number can be a customer as well as a supplier, and then
        # matching on the phone alone is not enough to say which hat they have
        # on. Whoever asked last owns the reply: a customer thread opened after
        # the newest outstanding vendor question is answering us, so their
        # message belongs to the sales flow and not here.
        if Request._sa_customer_outranks_vendor(digits):
            mine_as_customer = Request.search(
                [('requester_phone', 'like', digits[-9:]),
                 ('state', 'in', Request._SA_CUSTOMER_STATES)],
                order='id desc', limit=1)
            _logger.info(
                "Sales Automation: %s is a vendor, but their own enquiry %s is "
                "newer than any question we asked them - reading this as a "
                "customer reply.", digits[-9:], mine_as_customer.id)
            return False

        # 0. A swipe-reply to one of our messages names the question: the
        #    price checks carry no code to type any more (owner, 22 Nov
        #    2026), and the message they replied to is tagged with its
        #    enquiry (`_sa_tag_last_outgoing`).
        open_request = Request.browse()
        quoted = self._sa_quoted_id(data.get('message') or {})
        if quoted:
            sent = env['whatsapp.message'].sudo().search(
                [('wa_message_id', '=', quoted), ('direction', '=', 'outgoing'),
                 ('sa_request_id', '!=', False)], order='id desc', limit=1)
            if sent and sent.sa_request_id in askable:
                open_request = sent.sa_request_id.sudo()

        # 1. A code names the question outright.
        if not open_request:
            open_request = self._sa_request_by_ref(Request, text, mine)

        # 2. Failing that, the product named in the reply.
        if not open_request:
            open_request = self._sa_request_by_name(askable, text)

        # 3. Failing that, the only question there is.
        if not open_request and len(askable) == 1:
            open_request = askable

        # 3b. Or the only question whose window is still open. `askable`
        #     reaches back a week for late answers, so a supplier replying
        #     within the minute was being asked to pick between the live
        #     question and two that gave up days ago. Nothing to choose.
        if not open_request:
            live = askable.filtered(
                lambda r: r.state == 'sourcing' and r.sourcing_deadline
                and r.sourcing_deadline > odoo_fields.Datetime.now())
            if len(live) == 1:
                open_request = live

        # 4. Several to choose from and nothing to tell them apart. Guessing
        #    puts the wrong price on a customer's quotation, so ask instead -
        #    and answer either way, because falling through from here is how
        #    the salesbot ended up offering our supplier a catalogue.
        if not open_request:
            if not self._sa_is_pleasantry(text):
                self._sa_ask_which(session, digits, askable)
            return True

        self._sa_revive(open_request)

        # Step one's answer. A tapped poll option arrives here as ordinary
        # text (the non-group branch above rewrites it), so YES and NO are
        # read the same whether they were tapped or typed. Checked before the
        # price parser: "NO" carries no number, and a bare "yes" would
        # otherwise be logged as "replied with no price" and left there.
        verdict = Request._read_yes_no(text, numbered=False)
        if verdict is not None and not any(ch.isdigit() for ch in text):
            # The same match the price gate below uses, or a YES from a
            # number stored with spaces would never count as one.
            partner = open_request._sa_vendor_by_phone(digits) or env['res.partner'].sudo().search(
                [('phone', 'like', digits[-9:])], limit=1)
            env['whatsapp.message'].sudo().create({
                'session_id': session.id, 'phone': digits, 'message': text,
                'direction': 'incoming', 'status': 'received',
                'wa_message_id': str(key.get('id') or ''),
                'participant_phone': digits,
                'push_name': str(data.get('pushName') or ''),
            })
            if verdict:
                if partner:
                    open_request.sudo().write(
                        {'sa_vendor_yes_ids': [(4, partner.id)]})
                open_request._sa_ask_vendor_price(session, digits)
            else:
                open_request._sa_vendor_has_none(session, digits, partner)
            return True

        message = env['whatsapp.message'].sudo().create({
            'session_id': session.id,
            'phone': digits,
            'message': text,
            'direction': 'incoming',
            'status': 'received',
            'wa_message_id': str(key.get('id') or ''),
            'participant_phone': digits,
            'push_name': str(data.get('pushName') or ''),
        })
        # A price counts only from a vendor who said they have it (ACCEPT on
        # the page, or YES). On 31 Oct a vendor who had pressed nothing typed
        # "15 min" and it went to the counter as a 15.00 quote. Anyone else is
        # pointed back to the link; their message stays logged above.
        if not open_request._sa_vendor_confirmed(digits):
            open_request._sa_vendor_confirm_first(session, digits)
            return True
        quote = env['sa.vendor.quote'].sudo()._capture_direct(
            message, open_request)
        # Late, but real: an enquiry the shop was told about closes on it.
        open_request._sa_vendor_price_in(quote)
        # In a currency with no current rate: the counter has it, and the
        # supplier hears that it arrived (sa_vendor_money.py).
        held = {} if quote else next(
            (h for h in open_request._sa_held().values() if h.get('ref') == str(message.id)), {})
        if held:
            self._sa_thank_vendor(session, digits, open_request, quote, held=held, message=message)
            return True
        if quote:
            # Tell them it landed. A supplier who answers a price check and
            # hears nothing back has no idea whether it arrived, and the next
            # thing they used to get was the salesbot offering to find them a
            # product - which is worse than silence.
            self._sa_thank_vendor(session, digits, open_request, quote)
        if not quote:
            # Not a price - "checking", "no stock". Still ours: the tracker
            # must not answer a supplier as though they were buying.
            _logger.info("Sales Automation: %s replied to enquiry %s with no "
                         "price: %r", digits, open_request.id, text[:60])
        return True

    @staticmethod
    def _sa_thank_vendor(session, phone, request, quote, held=None, message=None):
        """Short acknowledgement of a price. Never raises."""
        name = (request.product_id.name or request.ai_search_term
                or _('this item'))
        # No delivery line back to the vendor: they told us the lead time, so
        # repeating it says nothing, and the price is echoed only so a
        # mis-parsed number is caught by the person who quoted it. Nothing is
        # promised - whether we buy is the sales team's call, not the bot's.
        body = _("\U0001F44D Okay, noted *%(price)s* for *%(product)s* "
                 "\u2014 our salesman will contact you soon.",
                 price=('%s %.2f' % (held['code'], held['amount'])) if held else quote._sa_typed_text(),
                 product=name)
        # Keyed on WhatsApp's own id for the supplier's message, which is
        # the same on every attempt when Odoo replays the request after a
        # serialization failure. Without it the same "Thanks, noted 4500.00"
        # went out twice, seconds apart, off one reply.
        trigger = (quote.message_id.wa_message_id
                   or 'q%s' % quote.id) if quote else (
                       (message.wa_message_id or 'm%s' % message.id) if message else 'q0')
        if not request.env['sa.outbox.guard'].sudo().claim(
                '%s|thanks|%s' % (trigger, phone)):
            return
        try:
            session.send_message(phone, body)
        except Exception as err:  # noqa: BLE001 - the price is already recorded
            _logger.info("Sales Automation: could not acknowledge %s (%s)",
                         phone, err)

    def _sa_vendor_poll_vote(self, session, data, remote_jid, choice):
        """A supplier answering our "do you have this?" poll.

        Routed by the poll id, never by guessing whose turn it is. Returns
        True when handled - and stamps the id the way the finder does, so the
        tracker's own hook on the logged row stays silent instead of trying
        to sell the supplier something.
        """
        key = (data or {}).get('key') or {}
        message = (data or {}).get('message') or {}
        digits = ''.join(c for c in str(remote_jid).split('@')[0]
                         if c.isdigit())
        poll_ref = self._sa_poll_ref(message)
        if not poll_ref or len(digits) < 8:
            return False
        Request = request.env['sa.group.request'].sudo()
        enquiry = Request._sa_by_vendor_poll(poll_ref, digits)
        if not enquiry:
            return False
        verdict = Request._read_yes_no(choice, numbered=False)
        if verdict is None:
            return False

        wa_id = str(key.get('id') or '')
        if wa_id:
            # Same stamp the finder uses: `_sa_was_finder_vote` reads it and
            # the salesbot does not answer this row.
            request.env['sa.outbox.guard'].sudo().claim(
                'finder_vote|%s' % wa_id, 900)
        request.env['whatsapp.message'].sudo().create({
            'session_id': session.id,
            'phone': digits,
            'message': choice,
            'direction': 'incoming',
            'status': 'received',
            'wa_message_id': wa_id,
            'participant_phone': digits,
            'push_name': str((data or {}).get('pushName') or ''),
        })
        partner = enquiry.sourcing_vendor_ids.filtered(
            lambda p: ''.join(ch for ch in (p.phone or '')
                              if ch.isdigit()).endswith(digits[-9:]))[:1]
        try:
            if verdict:
                if partner:
                    enquiry.write({'sa_vendor_yes_ids': [(4, partner.id)]})
                enquiry._sa_ask_vendor_price(session, digits)
            else:
                enquiry._sa_vendor_has_none(session, digits, partner)
        except Exception as err:  # noqa: BLE001 - the webhook answers 200
            _logger.exception("Sales Automation: supplier vote %r on enquiry "
                              "%s failed: %s", choice, enquiry.id, err)
        _logger.info("Sales Automation: supplier %s tapped %r on enquiry %s",
                     digits, choice, enquiry.id)
        return True

    def _sa_finder_vote(self, session, data, remote_jid, choice):
        """A vote on a guided-finder poll, answered by the finder.

        The poll is named by the vote (`pollCreationMessageKey`), and the
        enquiry remembers the id of the poll it last sent, so the tap is tied
        to the exact question - not to whatever this person has open. Falls
        back to their newest warm finder when the id is missing.
        """
        key = (data or {}).get('key') or {}
        message = (data or {}).get('message') or {}
        digits = ''.join(c for c in str(remote_jid).split('@')[0]
                         if c.isdigit())
        if len(digits) < 8:
            return False
        Request = request.env['sa.group.request'].sudo()
        warm = Request._sa_still_warm()
        poll_ref = self._sa_poll_ref(message)
        finder = Request.browse()
        if poll_ref:
            finder = Request.search([
                ('poll_wa_id', '=', poll_ref),
                ('requester_phone', 'like', digits[-9:]),
                '|', ('state', '=', 'finding'), ('finder_locked', '=', True),
            ], order='id desc', limit=1)
        if not finder:
            finder = Request.search([
                ('requester_phone', 'like', digits[-9:]),
                ('state', '=', 'finding'),
                ('finder_asked_on', '>=', warm),
            ], order='id desc', limit=1)
        if not finder:
            return False

        # Stamped before the row exists: the tracker schedules its reply on
        # create, and `_sa_was_finder_vote` has to find the stamp first.
        wa_id = str(key.get('id') or '')
        if wa_id:
            request.env['sa.outbox.guard'].sudo().claim(
                'finder_vote|%s' % wa_id, 900)
        request.env['whatsapp.message'].sudo().create({
            'session_id': session.id,
            'phone': digits,
            'message': choice,
            'direction': 'incoming',
            'status': 'received',
            'wa_message_id': wa_id,
            'participant_phone': digits,
            'push_name': str((data or {}).get('pushName') or ''),
        })
        try:
            finder.with_context(
                sa_reply_to=digits,
                sa_trigger_msg=str(key.get('id') or ''),
            )._finder_answer(choice)
        except Exception as err:  # noqa: BLE001 - the webhook answers 200
            _logger.exception("Sales Automation: finder vote %r on enquiry %s "
                              "failed: %s", choice, finder.id, err)
        _logger.info("Sales Automation: %s tapped %r on finder %s", digits,
                     choice, finder.id)
        return True

    def _sa_quantity_range(self, session, remote_jid, choice):
        """Second poll for a range tapped in the quantity poll, or False."""
        import re
        label = (choice or '').strip()
        digits = ''.join(c for c in str(remote_jid).split('@')[0] if c.isdigit())
        found = re.match(r'^(\d{1,3})\s*-\s*(\d{1,3})$', label)
        above = label.lower().startswith('above')
        if not found and not above:
            return False
        req = request.env['sa.group.request'].sudo().search(
            [('requester_phone', '=', digits),
             ('state', 'in', ('handed_off', 'order_created'))],
            order='id desc', limit=1)
        ref = (' (Ref %s)' % req.ref_code) if req and req.ref_code else ''
        try:
            if above:
                session.send_message(digits, _(
                    "Please type the exact quantity you need - for example "
                    "*25*.%s", ref))
            else:
                lo, hi = int(found.group(1)), int(found.group(2))
                if hi < lo or hi - lo > 11:
                    return False
                session.sa_send_poll(
                    digits, _("Exactly how many?%s", ref),
                    [str(n) for n in range(lo, hi + 1)])
        except Exception as err:  # noqa: BLE001 - never break the webhook
            _logger.warning("Sales Automation: quantity follow-up to %s not "
                            "sent: %s", digits, err)
        _logger.info("Sales Automation: %s tapped quantity range %r", digits,
                     label)
        return True

    @staticmethod
    def _sa_poll_choice(message):
        """The option a member tapped in a poll, or ''."""
        vote = ((message or {}).get('pollUpdateMessage') or {}).get('vote') or {}
        chosen = vote.get('selectedOptions') or []
        if isinstance(chosen, list) and chosen:
            return str(chosen[0] or '')
        return ''

    @staticmethod
    def _sa_is_pleasantry(text):
        """Nothing to answer - "ok", "thanks". Everything else gets a reply."""
        stripped = (text or '').strip().lower().strip('.!? ')
        return stripped in (
            'ok', 'okay', 'k', 'thanks', 'thank you', 'ty', 'welcome',
            'hi', 'hello', 'hey', 'yes', 'no', 'sure', 'noted', 'done',
            'good morning', 'good evening', 'good night', '')

    @staticmethod
    def _sa_revive(hit):
        """Put an enquiry that gave up waiting back on the fire - if the
        customer is still waiting for it.

        The price is recorded either way. What this decides is whether the
        customer hears about it again, and there are two reasons not to:

        The customer has moved on. On 1 Sep a supplier answered `#6A` fifty-one
        minutes late; by then its owner had asked again, settled at 550.00 and
        gone to a private chat to finish the order. Reopening put a second
        ACCEPT poll for the same charger back in the group at a different
        price, which is exactly the confusion the codes exist to prevent.

        Or it has simply gone cold. An hour-old request that the customer has
        given up on is not improved by answering it out of the blue.
        """
        from odoo import fields as odoo_fields
        if hit.state != 'dropped' or hit.drop_reason != 'no_vendor_reply':
            return
        superseded = hit.search_count([
            ('id', '>', hit.id),
            ('group_id', '=', hit.group_id.id),
            ('requester_phone', '=', hit.requester_phone),
            ('state', '!=', 'dropped'),
        ])
        if superseded:
            _logger.info("Sales Automation: enquiry %s answered late, but its "
                         "customer has since moved on - price kept, not "
                         "re-quoted", hit.id)
            return
        if hit.write_date < hit._sa_still_warm():
            _logger.info("Sales Automation: enquiry %s answered too late to "
                         "reopen - price kept, not re-quoted", hit.id)
            return
        _logger.info("Sales Automation: enquiry %s gave up waiting but the "
                     "supplier answered - reopening", hit.id)
        hit.write({'state': 'sourcing', 'drop_reason': False,
                   'answered_late': True,
                   'sourcing_deadline': odoo_fields.Datetime.now()})

    @classmethod
    def _sa_request_by_ref(cls, Request, text, extra_domain):
        """The enquiry whose code the vendor quoted, if any.

        A late answer is still worth having - the vendor took three minutes and
        the one-minute window had closed - so a coded reply is accepted for a
        day, and an enquiry that gave up waiting is put back on the fire.
        """
        import re
        from datetime import timedelta
        from odoo import fields as odoo_fields

        codes = []
        found = re.search(r'#\s*([0-9A-Za-z]{1,6})', text or '')
        if found:
            codes.append(found.group(1).upper())
        # People drop the hash. "4R 369" is unmistakably a code and a price, so
        # a bare token counts too - but only one carrying a letter, so a plain
        # number is never mistaken for a reference.
        for token in re.findall(r'[0-9A-Za-z]{1,6}', text or ''):
            token = token.upper()
            if any(ch.isalpha() for ch in token) and token not in codes:
                codes.append(token)
        if not codes:
            return Request.browse()
        # Every look-alike spelling of what they typed: a phone keyboard
        # offers 1 for I and 0 for O far more readily than it offers a
        # correction. Scoped to this supplier's own asks (extra_domain), so a
        # near-miss cannot land on a stranger's enquiry.
        codes = cls._sa_code_lookalikes(codes)
        cutoff = odoo_fields.Datetime.now() - timedelta(days=7)
        return Request.search(
            [('ref_code', 'in', codes),
             ('create_date', '>=', cutoff)] + extra_domain,
            order='id desc', limit=1)

    _SA_LOOKALIKES = {'1': 'I', 'I': '1', 'L': '1', '0': 'O', 'O': '0',
                      '5': 'S', 'S': '5', '8': 'B', 'B': '8', '2': 'Z',
                      'Z': '2', '6': 'G', 'G': '6'}

    @classmethod
    def _sa_code_lookalikes(cls, codes):
        """The codes as typed plus every spelling a keyboard confuses.

        Capped: a six-character code with every position ambiguous is 64
        spellings, which is nothing to a `ref_code in (...)` query; anything
        larger is cut rather than allowed to grow.
        """
        from itertools import product
        out = []
        for code in codes:
            options = [(ch, cls._SA_LOOKALIKES[ch]) if ch in cls._SA_LOOKALIKES
                       else (ch,) for ch in code.upper()]
            for combo in list(product(*options))[:128]:
                spelt = ''.join(combo)
                if spelt not in out:
                    out.append(spelt)
        return out

    @staticmethod
    def _sa_request_by_name(open_requests, text):
        """The open enquiry whose product the vendor named in their reply."""
        import re
        # Split on anything that is not a letter or digit. Splitting on spaces
        # left "TP-Link Wi-Fi Router" as one unmatchable token, so a supplier
        # writing "tp link router 450" was told we could not tell which.
        said = set(re.findall(r'[a-z0-9]+', (text or '').lower()))
        best, score = open_requests.browse(), 0
        for candidate in open_requests:
            name = (candidate.product_id.name or candidate.ai_search_term or '')
            words = {w for w in re.findall(r'[a-z0-9]+', name.lower())
                     if len(w) > 2}
            hits = len(words & said)
            if hits > score:
                best, score = candidate, hits
        return best if score >= 2 else open_requests.browse()

    def _sa_ask_which(self, session, phone, open_requests):
        """Ask the vendor which price check their number was for."""
        lines = [_("Thanks! Which one is that for?"), '']
        for candidate in open_requests[:8]:
            when = candidate.create_date
            lines.append('*#%s* - %s%s' % (
                candidate.ref_code,
                candidate.product_id.name or candidate.ai_search_term or '',
                when and when.strftime('  (%d %b)') or ''))
        lines.append('')
        lines.append(_("Just send the code and your price:"))
        lines.append('*#%s 450*' % open_requests[0].ref_code)
        lines.append(_("Add the days if you can: *#%(ref)s 450 3 days*",
                       ref=open_requests[0].ref_code))
        body = '\n'.join(lines)
        if not open_requests.env['sa.outbox.guard'].sudo().claim(
                '%s|which|%s' % (phone, body), seconds=120):
            return
        try:
            session.send_message(phone, body)
        except Exception as err:  # noqa: BLE001 - never lose the price
            _logger.info("Sales Automation: could not ask %s which price "
                         "check (%s)", phone, err)

    @staticmethod
    def _sa_poll_ref(message):
        """The id of the poll a vote answers, or ''.

        Baileys names the poll it belongs to in `pollCreationMessageKey`, which
        is the only way to tell whose question was answered - the vote itself
        carries nothing but the chosen label.
        """
        update = (message or {}).get('pollUpdateMessage') or {}
        if not update:
            return ''
        for field in ('pollCreationMessageKey', 'pollCreationMessageKeyV2'):
            key = update.get(field)
            if isinstance(key, dict) and key.get('id'):
                return str(key['id'])
        # Evolution does not always hand it over under that name, so anything
        # inside the vote that looks like a message key is taken. The shape is
        # logged when nothing is found, because the alternative is guessing.
        stack, seen = [update], 0
        while stack and seen < 40:
            node = stack.pop()
            seen += 1
            if not isinstance(node, dict):
                continue
            for name, value in node.items():
                if not isinstance(value, dict):
                    continue
                if 'key' in name.lower() and str(value.get('id') or ''):
                    return str(value['id'])
                stack.append(value)
        _logger.info("Sales Automation: poll vote carried no poll id; keys "
                     "were %s", sorted(update.keys()))
        return ''

    @staticmethod
    def _sa_quoted_id(message):
        """The id of the message this one replied to, or ''.

        A vendor pricing a request replies to our broadcast, and WhatsApp
        carries that as `contextInfo.stanzaId`. Nothing in whatsapp_gateway
        reads contextInfo, so it is dug out here. It hangs off whichever
        message variant was sent - text, extended text, image caption - so the
        payload is walked rather than guessed at.
        """
        stack = [message]
        seen = 0
        while stack and seen < 40:
            node = stack.pop()
            seen += 1
            if not isinstance(node, dict):
                continue
            context = node.get('contextInfo')
            if isinstance(context, dict):
                stanza = context.get('stanzaId') or context.get('stanzaID')
                if stanza:
                    return str(stanza)
            stack.extend(v for v in node.values() if isinstance(v, dict))
        return ''

    @staticmethod
    def _sa_sender_of(data, key):
        """(digits, lid, hidden) for the member who typed.

        In a group `remoteJid` is the group, so the human is only ever in the
        participant keys - and WhatsApp increasingly addresses group members by
        an `@lid` alias instead of their number:

            "participant":    "132040229945495@lid",
            "addressingMode": "lid",
            "participantAlt": "917010616092@s.whatsapp.net"

        The number is still there, under **participantAlt**. Missing that key
        was enough to break the whole flow: every sender looked hidden, so the
        confirmation step had no one to match a YES against and treated it as a
        fresh enquiry. The @lid is returned as well, because it identifies the
        person even in the groups where no number is offered at all.
        """
        lid = ''
        for source in (key, data):
            for field in ('participant', 'sender'):
                value = str((source or {}).get(field) or '')
                if '@lid' in value:
                    lid = value.split('@')[0]
                    break

        for candidate in (key.get('participantAlt'), data.get('senderAlt'),
                          key.get('participantPn'), data.get('senderPn'),
                          key.get('participant'), data.get('participant')):
            candidate = str(candidate or '')
            if not candidate or '@lid' in candidate:
                continue
            digits = candidate.split('@')[0].split(':')[0]
            if digits.isdigit() and len(digits) >= 7:
                return digits, lid, False
        return '', lid, bool(lid)

    def _sa_transcribe(self, session, data):
        """Voice note in a group, as text. Best effort, never raises."""
        env = request.env
        if 'wa.report.engine' not in env:
            return ''
        try:
            audio = self._fetch_media(session, data)
            if not audio:
                return ''
            return env['wa.report.engine'].sudo().transcribe_audio_bytes(audio) or ''
        except Exception as err:  # noqa: BLE001
            _logger.warning("Sales Automation: group voice note not "
                            "transcribed: %s", err)
            return ''
