"""One product enquiry, from a group message to a sale order.

The path an enquiry takes:

    customer posts  ->  classified  ->  "did you mean X?"  ->  YES
                    ->  in stock?  ->  quote from the catalog
                        out of stock?  ->  posted to the vendor group that
                        covers the product's category  ->  vendors reply with
                        prices for a few minutes  ->  cheapest + margin is
                        quoted back in the customer group

From there the customer's next *direct* message is owned by
whatsapp_employee_tracker's existing engine: bargaining, quantity, the sale
order, the address, payment and the invoice. None of that is reimplemented
here; the handoff is a seeded `wa.auto.reply` row.

The price is posted in the group, by configuration - so the order still has to
be closed privately, because the tracker's engine works on one-to-one threads.
Hence the quote says "message me to order": public price, private order.

Every enquiry is recorded, including the ones that are dropped. A group where
the assistant stays silent is the normal case, and being able to see *why* it
stayed silent is the difference between trusting it and turning it off.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.addons.whatsapp_gateway.models.whatsapp_session import WhatsAppQueued

_logger = logging.getLogger(__name__)

_YES = {'yes', 'y', 'ok', 'okay', 'yeah', 'yep', 'correct', 'right', 'confirm',
        'confirmed', 'sure', 'haan', 'han', 'ha', 'sari', 'sim', 'aye'}
_NO = {'no', 'n', 'nope', 'wrong', 'not', 'incorrect', 'cancel', 'nahi', 'nai'}


class SaGroupRequest(models.Model):
    _name = 'sa.group.request'
    _description = 'WhatsApp Group Product Enquiry'
    _order = 'create_date desc, id desc'
    _rec_name = 'display_name_custom'

    # ---- Where it came from ----
    group_id = fields.Many2one(
        'sa.sales.group', string='Group',
        required=True, ondelete='cascade', index=True,
    )
    session_id = fields.Many2one(
        related='group_id.session_id', store=True, string='WhatsApp Session',
    )
    employee_session_id = fields.Many2one(
        related='group_id.employee_session_id', store=True,
        string='Employee Session',
    )
    message_id = fields.Many2one(
        'whatsapp.message', string='Group Message',
        ondelete='set null', index=True,
    )
    conversation_id = fields.Many2one(
        'wa.conversation', string='Private Chat',
        ondelete='set null', index=True,
        help="The one-to-one thread the order is closed in.",
    )

    # ---- Who asked ----
    requester_phone = fields.Char('Requester', index=True)
    requester_name = fields.Char('Requester Name')
    requester_lid = fields.Char(
        'Requester LID', index=True,
        help="WhatsApp's alias for this member. Used to match their answer "
             "when the group exposes no phone number.",
    )
    requester_is_lid = fields.Boolean(
        'Number Hidden',
        help="WhatsApp hid this member's number, so no private chat can be "
             "opened with them.",
    )
    requester_partner_id = fields.Many2one('res.partner', string='Contact')

    # ---- What they said ----
    raw_text = fields.Text('Message', readonly=True)
    ai_is_product = fields.Boolean('Product Enquiry', readonly=True)
    ai_search_term = fields.Char('Detected Product', readonly=True)
    ai_confidence = fields.Float('Confidence', readonly=True, digits=(3, 2))
    ai_source = fields.Char(
        'Decided By', readonly=True,
        help="prefilter, the AI provider's name, or catalog when keyword "
             "matching stood in for an unavailable AI.",
    )

    # ---- What we found ----
    product_id = fields.Many2one('product.template', string='Product')
    qty = fields.Float('Quantity Asked', digits='Product Unit of Measure')
    candidate_product_ids = fields.Many2many(
        'product.template', 'sa_request_candidate_rel', 'request_id',
        'product_id', string='Products Offered',
        help="Shown to the customer to choose from when more than one product "
             "fitted what they asked for.",
    )
    rejected_product_ids = fields.Many2many(
        'product.template', 'sa_request_rejected_rel', 'request_id',
        'product_id', string='Products Rejected', readonly=True,
        help="Products this customer has already said no to. They are kept "
             "out of the next few suggestions, so asking the same question a "
             "second time does not produce the same wrong answer.",
    )
    stock_status = fields.Selection([
        ('in_stock', 'In Stock'),
        ('on_order', 'Available on Order'),
        ('unavailable', 'Unavailable'),
    ], string='Availability', index=True)
    available_qty = fields.Float('On Hand', digits='Product Unit of Measure')

    # ---- Sourcing ----
    sourcing_group_id = fields.Many2one(
        'sa.sales.group', string='Vendor Group', index=True,
        help="Left over from the vendor-group flow. Vendors are messaged "
             "privately now.",
    )
    sourcing_vendor_ids = fields.Many2many(
        'res.partner', 'sa_request_vendor_rel', 'request_id', 'partner_id',
        string='Vendors Asked',
        help="The suppliers messaged for a price on this enquiry.",
    )
    broadcast_wa_message_id = fields.Char(
        'Broadcast Message ID', index=True, readonly=True,
        help="The WhatsApp id of our message in the vendor group. A vendor who "
             "replies to it is matched to this enquiry exactly.",
    )
    sourcing_deadline = fields.Datetime(
        'Quotes Close At', index=True,
        help="Vendor prices arriving after this are recorded but do not change "
             "what the customer was quoted.",
    )
    # ---- Held at the counter for a human to choose vendors ----
    shop_pick_deadline = fields.Datetime(
        'Shop Must Choose By', index=True, copy=False,
        help="When this passes with nobody at the counter, every candidate "
             "vendor is asked automatically.")
    shop_pick_vendor_ids = fields.Many2many(
        'res.partner', 'sa_request_shop_pick_vendor_rel', 'request_id',
        'partner_id', string='Candidate Vendors', copy=False,
        help="Who the shopkeeper may choose from. Snapshotted when the "
             "enquiry is parked, so the screen shows the list as it was and "
             "not as somebody has since edited the catalog.")
    shop_pick_user_id = fields.Many2one(
        'res.users', string='Chosen By', readonly=True, copy=False)
    shop_pick_done_on = fields.Datetime('Chosen On', readonly=True, copy=False)
    shop_pick_auto = fields.Boolean(
        'Sent by Timeout', readonly=True, copy=False,
        help="Nobody was at the counter, so every candidate was asked.")
    shop_pick_no_categ = fields.Boolean(
        'Product Has No Category', readonly=True, copy=False,
        help="Vendors are routed by product category. Without one the "
             "shopkeeper is shown a fallback list, which is worth fixing.")

    quote_ids = fields.One2many('sa.vendor.quote', 'request_id', string='Vendor Quotes')
    quote_count = fields.Integer('Quotes', compute='_compute_quote_count')
    best_quote_id = fields.Many2one('sa.vendor.quote', string='Winning Quote')

    supplierinfo_id = fields.Many2one('product.supplierinfo', string='Vendor Line')
    vendor_id = fields.Many2one(
        related='supplierinfo_id.partner_id', store=True, string='Vendor',
    )
    vendor_price = fields.Monetary(
        'Cost', currency_field='currency_id',
        help="What the product costs us - the winning vendor quote, or the "
             "vendor price list when nobody replied.",
    )
    vendor_delay = fields.Integer('Lead Time (days)')
    quoted_price = fields.Monetary('Quoted Price', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id,
    )

    bargain_count = fields.Integer(
        'Bargaining Rounds', readonly=True,
        help="How many times the price has already come down for this enquiry.",
    )
    target_price = fields.Monetary(
        'Customer Asked For', currency_field='currency_id', readonly=True,
        help="The price the customer named themselves. Kept even when it "
             "arrives before we have a price of our own, so the first quote "
             "can answer it instead of ignoring it.",
    )
    agreed_price = fields.Monetary(
        'Agreed Price', currency_field='currency_id',
        help="What the customer actually settled on, which is what the "
             "quotation is priced at - not necessarily the price first quoted.",
    )
    order_id = fields.Many2one('sale.order', string='Sale Order', index=True)
    profile_step = fields.Selection([
        ('name', 'Asking the Name'),
        ('address', 'Asking the Address'),
        ('pin', 'Asking the Pincode'),
        ('confirm', 'Waiting for Confirmation'),
        ('done', 'Confirmed'),
    ], string='Customer Details Step', readonly=True,
        help="Where the private chat has got to in collecting who the "
             "customer is. The quotation is not handed over until this "
             "reaches Confirmed.")
    ref_code = fields.Char(
        'Reference', compute='_compute_ref_code', store=True, index=True,
        help="Short code quoted in the price check so a vendor with several "
             "open questions can say which one they are answering.")
    poll_wa_id = fields.Char(
        'Last Poll Message Id', readonly=True, index=True,
        help="The WhatsApp id of the poll last posted for this enquiry. A vote "
             "names the poll it answers, which is the only way to tell whose "
             "question was tapped - everyone in a group can vote in every "
             "poll.")
    answered_poll_wa_ids = fields.Char(
        'Answered Poll Ids', readonly=True, copy=False,
        help="Polls this enquiry has already acted on. A vote can be changed "
             "on WhatsApp long after it was cast, and each change arrives as "
             "a fresh vote - so ACCEPT followed by a switch to CANCEL used to "
             "cancel the order that had just been placed.")
    poll_wa_ids = fields.Char(
        'Poll Message Ids', readonly=True, index=True,
        help="Every recent poll this enquiry asked, newest first. A single "
             "id was overwritten by each new question, so a customer who "
             "scrolled up and tapped an earlier poll answered nothing - the "
             "vote fell through and was applied to whatever they had open "
             "instead. The finder overwrites it at every step, so this "
             "matters most there.")
    profile_restarted = fields.Boolean(
        'Details Being Re-entered', readonly=True,
        help="Set when the customer answered NO to the summary. The first "
             "question afterwards has to be worded differently from the "
             "original - an identical message inside three minutes is "
             "suppressed as a duplicate and arrives as silence.")
    # ---- Nobody answered, so a person has to price it ----
    sa_price_stalled = fields.Boolean(
        'Waiting for a Hand-Entered Price', index=True, copy=False,
        help="Every vendor asked stayed silent. The enquiry is held open and "
             "the shop is asked to phone round and type the price in.")
    sa_price_asked_on = fields.Datetime(
        'Shop Asked On', readonly=True, copy=False)
    sa_price_token = fields.Char(
        'Price Entry Token', readonly=True, copy=False,
        groups='base.group_user',
        help="Secret in the link the shop is sent. The link is the only "
             "credential, so it is long and compared in constant time.")
    sa_price_by_id = fields.Many2one(
        'res.users', string='Price Entered By', readonly=True, copy=False)
    # ---- Vendor price differs from the product page: the shop chooses ----
    sa_price_choice_pending = fields.Boolean(
        'Waiting for the Shop to Approve the Price', index=True, copy=False,
        help="The vendor's quote plus margin differs from the product page "
             "price. The customer is not quoted until somebody at the counter "
             "picks which price to use.")
    sa_price_choice_quote_id = fields.Many2one(
        'sa.vendor.quote', string='Quote Awaiting Approval', copy=False)
    sa_price_page = fields.Monetary(
        'Product Page Price', currency_field='currency_id', copy=False)
    sa_price_vendor = fields.Monetary(
        'Vendor-Based Price', currency_field='currency_id', copy=False,
        help="The vendor's cost plus the margin, as the bot would have quoted.")
    sa_price_choice = fields.Selection([
        ('page', 'Product page price'),
        ('vendor', 'Vendor price + margin'),
        ('typed', 'Typed at the counter'),
    ], 'Approved Price', readonly=True, copy=False)
    sa_price_choice_by = fields.Char('Approved By', readonly=True, copy=False)

    # ---- Waiting on the customer ----
    customer_asked_on = fields.Datetime(
        'Last Asked the Customer', readonly=True, copy=False,
        help="When we last sent this customer anything. Every message "
             "restarts their clock.")
    customer_deadline = fields.Datetime(
        'Customer Must Reply By', readonly=True, copy=False, index=True,
        help="Empty when the timeout is off, so the cron's domain simply "
             "never matches - NULL fails `<=`.")

    sa_vendor_yes_ids = fields.Many2many(
        'res.partner', 'sa_request_vendor_yes_rel', 'request_id', 'partner_id',
        string='Suppliers Who Have It', copy=False,
        help="Answered YES to \"do you have this?\" and were asked for a "
             "price. Until that price arrives they are neither silent nor "
             "out - a shopkeeper ringing round should call these first.")
    vendor_poll_wa_ids = fields.Char(
        'Supplier Poll Ids', copy=False,
        help="WhatsApp ids of the YES/NO polls sent to suppliers, newest "
             "first. A vote names the poll it answers, so a supplier who is "
             "also a customer is never guessed at.")
    sa_vendor_no_ids = fields.Many2many(
        'res.partner', 'sa_request_vendor_no_rel', 'request_id', 'partner_id',
        string='Suppliers Without It', copy=False,
        help="Asked and answered NO. Kept apart from silence: a shopkeeper "
             "ringing round needs to know who has already said they cannot "
             "supply it.")

    answered_late = fields.Boolean(
        'Answered After Giving Up', readonly=True,
        help="The customer was told we could not get a price, and then a "
             "supplier answered. The quote that follows says so, rather than "
             "contradicting the message before it.")
    profile_asked_on = fields.Datetime(
        'Form Question Sent', readonly=True,
        help="When the details form last put a question to the customer. "
             "A form that has not asked anything recently no longer claims "
             "their replies - nine abandoned forms were between them "
             "intercepting every private message in two conversations.")
    profile_last_bad = fields.Char(
        'Last Unreadable Answer', readonly=True,
        help="What the customer sent that could not be used. Quoted back to "
             "them so a second bad answer gets a different message - an "
             "identical one inside three minutes is suppressed as a duplicate "
             "and arrives as silence.")
    profile_retry = fields.Integer(
        'Details Re-asked', readonly=True,
        help="How many times the current question had to be repeated because "
             "the answer could not be read.")

    # ---- How it went ----
    state = fields.Selection([
        ('new', 'New'),
        ('awaiting_confirm', 'Awaiting Confirmation'),
        ('finding', 'Guided Finder'),
        ('sourcing', 'Asking Vendors'),
        ('awaiting_vendor_pick', 'Waiting for the Shop'),
        ('quoted', 'Quoted'),
        ('negotiating', 'Bargaining'),
        ('awaiting_qty', 'Awaiting Quantity'),
        ('awaiting_order_confirm', 'Awaiting Order Confirmation'),
        ('answered', 'Answered in Group'),
        ('handed_off', 'Handed to Private Chat'),
        ('order_created', 'Order Created'),
        ('dropped', 'Dropped'),
    ], string='Status', default='new', required=True, index=True)
    drop_reason = fields.Selection([
        ('not_product', 'Not a Product Enquiry'),
        ('low_confidence', 'Below Confidence Threshold'),
        ('no_product', 'No Matching Product'),
        ('not_confirmed', 'Customer Said No'),
        ('declined', 'Customer Declined the Price'),
        ('no_vendor_group', 'No Vendor Group for This Category'),
        ('no_vendor_reply', 'No Vendor Replied'),
        ('unavailable', 'No Stock and No Vendor'),
        ('lid_no_dm', 'Requester Number Hidden'),
        ('no_employee_session', 'No Employee Session on Group'),
        ('duplicate', 'Already Being Priced'),
        ('need_clarification', 'Waiting for the Exact Product Name'),
        ('stale', 'Abandoned'),
        ('customer_timeout', 'Customer Did Not Reply'),
        ('error', 'Error'),
    ], string='Reason', index=True)
    error = fields.Text('Error Details')

    display_name_custom = fields.Char(compute='_compute_display_name_custom')

    def _compute_display_name_custom(self):
        for rec in self:
            who = rec.requester_name or rec.requester_phone or 'Unknown'
            what = rec.product_id.name or rec.ai_search_term or (rec.raw_text or '')[:30]
            rec.display_name_custom = '%s: %s' % (who, what)

    def _compute_quote_count(self):
        for rec in self:
            rec.quote_count = len(rec.quote_ids)

    # ==========================================================
    # Entry point - called by the group webhook
    # ==========================================================
    @api.model
    def _on_group_message(self, message):
        """Route one inbound group message. Never raises."""
        # Carry the inbound message id through every send this turn makes.
        # The outbox guard needs it to tell a replayed request from a customer
        # who really did send the same thing again: a replay re-processes this
        # same id, while a second "30" arrives with a new one. Without it the
        # guard answered a repeated push with silence.
        # WhatsApp's own id, not the database row's. The row is created
        # inside this transaction, so a replay after SERIALIZATION_FAILURE
        # rolls it back and the next attempt gets a fresh id - which made the
        # guard key different every time and let the same message go out three
        # times. WhatsApp's id is the same on every attempt.
        self = self.with_context(
            sa_trigger_msg=message.wa_message_id or ('row%s' % message.id))
        # Scoped to the session the message arrived on. Without it, two Odoo
        # session records pointing at the same WhatsApp instance - which is how
        # this database is set up - let one group exist twice, and `limit=1`
        # then picks whichever sorts first. A group configured as a customer
        # group on one session and a vendor group on the other would route by
        # sort order rather than by intent.
        group = self.env['sa.sales.group'].sudo().search([
            ('session_id', '=', message.session_id.id),
            ('group_jid', '=', message.group_jid),
            ('enabled', '=', True),
        ], limit=1)
        if not group:
            return False  # unlinked or unticked group: read nothing, say nothing

        text = (message.message or '').strip()
        if not text:
            return False

        # A vendor group is not a place enquiries come from. Every message here
        # is read as a price against an open request, and never answered.
        if group.group_type == 'vendor':
            return self.env['sa.vendor.quote'].sudo()._capture(message, group)

        # A returning customer saying hello is shown their orders in flight -
        # track the paid one, sign or pay the waiting one, or start afresh.
        try:
            if self._sa_is_greeting(text) and self._sa_returning_menu(message, group):
                return True
        except Exception as err:  # noqa: BLE001 - never lose the message over a menu
            _logger.warning("Sales Automation: returning menu failed: %s", err)

        # Someone mid-deal is answering us, not starting again. Checked before
        # the confirmation step so a bargaining reply is never read as a fresh
        # enquiry - which is how "can you reduce" would otherwise be classified
        # as chatter and dropped.
        # One person can be waiting on two things at once - a price still
        # being sourced, and a "did you mean X?" they were just asked. Checking
        # the deal first meant their YES was swallowed by the older enquiry and
        # answered "Still checking on that", so the confirmation sat there and
        # they asked again. Whichever we spoke to them about most recently is
        # the one they are replying to.
        # A vote names the poll it answers. If that poll was asked of
        # somebody else, this is a bystander tapping - and acting on it means
        # answering the wrong person and, worse, applying their answer to the
        # voter's own open deal.
        poll_ref = self.env.context.get('sa_poll_ref')
        if poll_ref:
            asked = self._sa_by_poll(poll_ref)
            if asked and not asked._sa_asked_of(message):
                _logger.info("Sales Automation: %s voted on the poll asked of "
                             "%s - ignored", message.participant_phone
                             or message.participant_lid,
                             asked.requester_name or asked.requester_phone)
                asked._sa_tell_bystander(message)
                return False
            if asked and asked._sa_poll_answered(poll_ref, text):
                # A vote changed on WhatsApp arrives as a new vote. ACCEPT
                # and then a switch to CANCEL cancelled a placed order; the
                # first answer stands, and a change has to be typed.
                _logger.info("Sales Automation: %s changed their vote on a "
                             "poll already answered (enquiry %s) - ignored",
                             message.participant_phone or message.participant_lid,
                             asked.id)
                return asked._sa_tell_poll_spent(text)
            if asked:
                # Their own poll - but not necessarily their newest enquiry.
                # Someone with several quotes open scrolls back and taps one,
                # and falling through to `_active_deal` from here applied that
                # tap to whichever deal happened to be latest. The vote names
                # its own question, so answer that one and nothing else.
                answered = asked._sa_answer_poll(text)
                if answered is not None:
                    asked._sa_mark_poll_answered(poll_ref)
                    return answered

        # A cancel has to reach a deal that has already moved to the private
        # chat - `handed_off` is in no other lookup, so the word was being
        # discarded while the seeded order flow carried on.
        # An explicit reference beats every heuristic below it. The bot
        # prints "Ref GH" on everything it says, so a customer with two
        # enquiries open - or one answering while three other people are
        # mid-conversation - can always say which they mean.
        by_ref = self._sa_ref_in_group(group, message, text)
        if by_ref is not None:
            return by_ref

        if self._sa_is_cancel(text):
            leaving = self._sa_cancellable(group, message)
            if leaving:
                return leaving._sa_cancel_deal()

        # A finder option is answered by tapping it, and the tap arrives as
        # ordinary text. Matching it to the poll we sent is the precise route
        # and stays first - but it needs that poll's id, and the id is missing
        # whenever the send was rolled back or the gateway returned none. When
        # that happened the tap was read as a brand-new enquiry, classified as
        # chatter, and dropped without a word: the customer tapped an option
        # and the conversation simply stopped.
        #
        # `_finder_answer` returns False when the text is genuinely a new
        # request, so the ordinary path below still runs for those.
        finding = self._sa_open_finder(group, message)
        if finding:
            # What the finder looked like before it read this message.
            was = (finding.finder_step, finding.finder_type,
                   finding.finder_brand, finding.finder_model, finding.state)
            if finding._finder_answer(text):
                return True
            # `_finder_answer` answers False both for "this text is not mine"
            # and when the reply could not be delivered - and only the first
            # means the message should be read as a new enquiry. With the
            # gateway briefly down, the second was closing the very enquiry
            # the customer was answering. If the finder moved, the tap was
            # its answer whatever WhatsApp did with the reply.
            finding.invalidate_recordset()
            if was != (finding.finder_step, finding.finder_type,
                       finding.finder_brand, finding.finder_model,
                       finding.state):
                _logger.info("Sales Automation: finder %s consumed %r but "
                             "the reply did not go out - not reading it as a "
                             "new enquiry", finding.id, (text or '')[:40])
                return True

        # A typed answer to a question a module asked (e.g. "type the
        # capacity you need"): consumed there, never read as a new enquiry.
        typed = self._sa_typed_answer_hook(group, message, text)
        if typed is not None:
            return typed

        deal = self._active_deal(group, message)
        pending = self._pending_confirmation(group, message)
        if deal and pending and pending.id > deal.id:
            deal = self.browse()

        if deal:
            handled = deal._on_deal_reply(text)
            if handled:
                return deal

        # A short yes/no from someone we asked to confirm resolves that
        # enquiry, rather than starting a new one.
        if pending:
            if pending.candidate_product_ids:
                chosen = pending._match_candidate(text)
                if chosen is not None:
                    return pending._on_candidate_chosen(chosen)
            answer = self._read_yes_no(text)
            if answer is True:
                return pending._on_confirmed()
            if answer is False:
                # The match was wrong, not the request. Asking for "iPhone 15
                # Pro Max Screen" and being offered "iPhone 15 Screen" is a
                # near miss by the keyword matcher, and dropping here would
                # send the customer away over our mistake. Forget the guess and
                # price what they actually asked for.
                return pending._reject_match()
            # Neither: treat it as a fresh enquiry and let the old one expire.

        # An exact option from a poll that is open for somebody else. Poll
        # votes arrive as the option's own words, so "Redmi Note 13 Pro Camera"
        # from a bystander is indistinguishable from a fresh request - and it
        # was becoming one, complete with its own "did you mean" question.
        # Checked before the AI, which would happily classify it as an enquiry.
        stolen = self._sa_poll_option_of_another(group, message, text)
        if stolen:
            _logger.info("Sales Automation: %s tapped an option on the poll "
                         "asked of %s - ignored", message.participant_phone
                         or message.participant_lid,
                         stolen.requester_name or stolen.requester_phone)
            return False

        # A bare yes/no/number with nothing of this person's open is almost
        # always someone answering a question that was asked of another member.
        # Classifying it spends an AI call and leaves a dropped enquiry behind
        # for every stray ACCEPT - five of them in one afternoon.
        if self._sa_is_bare_answer(text):
            _logger.info("Sales Automation: %r from %s answers nothing open "
                         "for them - ignored", text[:24],
                         message.participant_phone or message.participant_lid)
            return False

        # One live enquiry each. A customer who asks again before
        # finishing used to be left with two open questions that look
        # identical in the group, and their next word - a YES, a number, a
        # price - could land on either. Their earlier one is closed here, so
        # there is only ever one thing their next message can mean.
        # `handed_off` and `order_created` are deliberately left alone: those
        # have moved to the private chat and are still going.
        self._sa_close_previous(group, message)

        request = self.sudo().create({
            'group_id': group.id,
            'message_id': message.id,
            'requester_phone': message.participant_phone or '',
            'requester_lid': message.participant_lid or '',
            'requester_name': message.push_name or '',
            'requester_is_lid': message.participant_is_lid,
            'raw_text': text,
            'currency_id': self._company_for(group).currency_id.id,
        })
        request._sa_tag_message(message)
        try:
            request._process()
        except Exception as err:  # noqa: BLE001 - the webhook must still answer 200
            _logger.exception("Sales Automation: enquiry %s failed", request.id)
            request.write({
                'state': 'dropped', 'drop_reason': 'error',
                'error': str(err)[:2000],
            })
        return request

    _SA_REF_RE = None

    @api.model
    def _sa_ref_in_group(self, group, message, text):
        """Route `#GH ...` to enquiry GH, if the sender owns it.

        Returns the enquiry when it handled the message, False when the code
        was recognised but is not theirs (silently - a group is public, so a
        code is readable by everyone and must not be usable by them), and None
        when there is no code, so the ordinary routing carries on.
        """
        import re
        if self._SA_REF_RE is None:
            type(self)._SA_REF_RE = re.compile(r'#\s*([0-9A-Za-z]{1,6})')
        found = self._SA_REF_RE.search(text or '')
        if not found:
            return None
        code = found.group(1).upper()

        enquiry = self.sudo().search([
            ('group_id', '=', group.id),
            ('ref_code', '=', code),
            ('state', 'in', ('sourcing', 'awaiting_vendor_pick', 'finding',
                             'quoted', 'negotiating', 'awaiting_qty',
                             'awaiting_order_confirm', 'awaiting_confirm')),
            ('write_date', '>=', self._sa_still_warm()),
        ], order='id desc', limit=1)
        if not enquiry:
            return None

        if not enquiry._sa_asked_of(message):
            _logger.info("Sales Automation: %s quoted %s's code %s - ignored",
                         message.participant_phone or message.participant_lid,
                         enquiry.requester_name or enquiry.requester_phone,
                         code)
            return False

        enquiry._sa_learn_identity(message)
        # Strip the code and the QTY hint the tap-links carry, so what is
        # left is the answer itself - "450", "yes", "4".
        answer = self._SA_REF_RE.sub('', text or '', count=1).strip()
        if answer.lower().startswith('qty'):
            answer = answer[3:].strip()
        if not answer:
            return False
        _logger.info("Sales Automation: %s answered %s in the group: %r",
                     message.participant_phone or message.participant_lid,
                     code, answer[:40])
        if enquiry.state == 'finding':
            return enquiry._finder_answer(answer) and enquiry or False
        handled = enquiry._on_deal_reply(answer)
        return enquiry if handled else False

    @api.model
    def _sa_poll_option_of_another(self, group, message, text):
        """The enquiry whose poll options include this exact text, if it is
        somebody else's.

        Returns an empty recordset when the words are this person's own
        business - their own poll, or simply a request that happens to read
        like a product name.
        """
        stripped = (text or '').strip().lower()
        if not stripped:
            return self.browse()
        waiting = self.sudo().search([
            ('group_id', '=', group.id),
            ('state', 'in', ('awaiting_confirm', 'quoted', 'negotiating')),
        ], order='id desc', limit=20)
        for enquiry in waiting:
            if enquiry._sa_asked_of(message):
                return self.browse()    # their own question - let it through
            options = {(p.name or '').strip().lower()
                       for p in enquiry.candidate_product_ids}
            options.discard('')
            if enquiry.product_id:
                options.add((enquiry.product_id.name or '').strip().lower())
            if stripped in options:
                return enquiry
        return self.browse()

    @api.model
    def _sa_is_bare_answer(self, text):
        """True when the message is only an answer token, carrying no request."""
        stripped = (text or '').strip().lower().strip('.!*? ')
        if not stripped:
            return True
        # 'cancel' and 'stop' are deliberately absent: they used to be
        # swallowed here, so a customer cancelling after the handoff got no
        # reply at all while the order went ahead in their private chat.
        if stripped in ('yes', 'y', 'no', 'n', 'ok', 'okay', 'sure', 'accept',
                        'none', 'none of these', 'other',
                        'sa_yes', 'sa_no', 'sa_none', 'confirm', 'done'):
            return True
        return stripped.isdigit() and len(stripped) <= 2

    def _pending_confirmation(self, group, message):
        """The enquiry this person was last asked to confirm, if any.

        Matched on the phone when there is one and on the @lid otherwise. In a
        group that addresses members by lid there is no number to match, and
        keying on the phone alone made every confirmation look like a brand new
        message - which is how a "YES" ended up classified as chatter and
        silently dropped.
        """
        domain = [('group_id', '=', group.id),
                  ('state', '=', 'awaiting_confirm'),
                  ('write_date', '>=', self._sa_still_warm())]
        if message.participant_phone:
            domain.append(('requester_phone', '=', message.participant_phone))
        elif message.participant_lid:
            domain.append(('requester_lid', '=', message.participant_lid))
        else:
            return self.browse()
        return self.sudo().search(domain, order='id desc', limit=1)

    @api.depends('create_date')
    def _compute_ref_code(self):
        """A short, typable code. Base 36 of the id, so it is unique for free.

        Vendors are asked in a one-to-one chat, and that used to be enough:
        whatever came back could only belong to the one thing they were asked.
        It stops being true the moment two price checks are open at once - a
        bare "345" then attaches to whichever happens to be newest, which is a
        coin toss with a customer's quotation on it.
        """
        digits = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        for record in self:
            number, code = record.id or 0, ''
            while number:
                number, remainder = divmod(number, 36)
                code = digits[remainder] + code
            record.ref_code = code or '0'

    @api.model
    def _sa_still_warm(self):
        """The cutoff for treating a reply as an answer to something.

        Without one, an enquiry sits in `awaiting_confirm` for ever and the
        next YES from that person resolves it - however long ago it was asked.
        On 31 Aug a tap resolved a question from 88 minutes earlier and the
        customer was quoted an iPhone charging port they had never mentioned,
        while the thing they had just asked about waited its turn.
        """
        minutes = self.env['sa.ai.settings'].sudo().get_settings(
            ).stale_after_minutes or 60
        return fields.Datetime.subtract(fields.Datetime.now(),
                                        minutes=max(1, minutes))

    _SA_CUSTOMER_STATES = ('finding', 'quoted', 'negotiating', 'awaiting_qty',
                           'awaiting_order_confirm', 'handed_off',
                           'order_created')

    @api.model
    def _sa_customer_outranks_vendor(self, digits):
        """True when this number is answering us as a customer right now.

        The same number can be both a supplier and a buyer, and matching on
        the phone alone cannot say which hat they have on. Whoever asked last
        owns the reply: an enquiry of their own opened after the newest price
        question we put to them means this message belongs to the sales flow.

        `digits` is the bare number; the last nine are compared, as everywhere
        else here, because country prefixes are written half a dozen ways.
        """
        tail = (digits or '')[-9:]
        if len(tail) < 8:
            return False
        mine = self.sudo().search(
            [('requester_phone', 'like', tail),
             ('state', 'in', self._SA_CUSTOMER_STATES)],
            order='id desc', limit=1)
        if not mine:
            return False
        # Sanitized as well as typed - see _sa_by_vendor_poll.
        asked = self.sudo().search(
            ['|', ('sourcing_vendor_ids.phone', 'like', tail),
             ('sourcing_vendor_ids.phone_sanitized', 'like', tail)],
            order='id desc', limit=1)
        return not asked or mine.create_date > asked.create_date

    @api.model
    def _sa_close_previous(self, group, message):
        """Close this person's earlier unfinished enquiry in this group.

        Scoped to the one person - everybody else's stays exactly as it was,
        which is the whole point when several people are asking at once.
        """
        domain = [('group_id', '=', group.id),
                  ('state', 'in', ('awaiting_confirm', 'finding', 'sourcing',
                                   'awaiting_vendor_pick',
                                   'quoted', 'negotiating'))]
        if message.participant_phone:
            domain.append(('requester_phone', '=', message.participant_phone))
        elif message.participant_lid:
            domain.append(('requester_lid', '=', message.participant_lid))
        else:
            return False
        stale = self.sudo().search(domain)
        if not stale:
            return False
        _logger.info("Sales Automation: %s asked again - closing their open "
                     "enquiry/enquiries %s", message.participant_phone
                     or message.participant_lid, stale.ids)
        stale.write({'state': 'dropped', 'drop_reason': 'not_confirmed'})
        return True

    def _sa_answer_poll(self, text):
        """Apply a vote to the enquiry whose poll was tapped.

        Returns None when this enquiry has nothing left to answer - a poll from
        a deal that has since been closed or handed off - so the caller carries
        on and treats the words as an ordinary message rather than swallowing
        them.
        """
        self.ensure_one()
        if self.state == 'awaiting_confirm':
            if self.candidate_product_ids:
                chosen = self._match_candidate(text)
                if chosen is not None:
                    return self._on_candidate_chosen(chosen)
            answer = self._read_yes_no(text)
            if answer is True:
                return self._on_confirmed()
            if answer is False:
                return self._reject_match()
            return None
        if self.state == 'finding':
            # Without this a finder poll tapped in the group answered
            # nothing: the vote fell through the router and was read as a
            # brand-new enquiry, so the customer was asked the same question
            # again and again.
            return self._finder_answer(text)
        if self.state in ('quoted', 'negotiating', 'awaiting_order_confirm',
                          'awaiting_qty'):
            # The order-summary poll (CONFIRM / CHANGE) and a quantity poll
            # are answered here too, so the vote is marked as answered
            # instead of falling through the router.
            return self._on_deal_reply(text) or None
        _logger.info("Sales Automation: vote on enquiry %s, which is %s - "
                     "nothing to answer", self.id, self.state)
        return None

    @staticmethod
    def _sa_id_tail(value):
        """The last nine digits, which is how every other lookup compares.

        `_sa_sender_of` reads the sender from six different payload keys and
        they do not agree on the country code, so exact equality rejected the
        real owner - who was then told the price was somebody else's.
        """
        digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
        return digits[-9:] if len(digits) >= 9 else digits

    def _sa_asked_of(self, message):
        """True when this message comes from the person this enquiry is for.

        Fails CLOSED. It used to return True whenever it had nothing to
        compare, which is the ordinary case in a group where one member is
        addressed by number and another by @lid - and a bystander's tap then
        drove a stranger's enquiry, up to accepting their price. Refusing an
        unprovable claim costs that person one repeat; accepting it spends
        somebody else's deal.
        """
        self.ensure_one()
        mine = self._sa_id_tail(self.requester_phone)
        theirs = self._sa_id_tail(message.participant_phone)
        if mine and theirs:
            return mine == theirs
        if self.requester_lid and message.participant_lid:
            return self.requester_lid == message.participant_lid
        return False

    def _sa_learn_identity(self, message):
        """Fill in the identifier this enquiry does not have yet.

        WhatsApp gives us a number on one message from a person and only an
        @lid on the next. Storing whichever arrives keeps one human from
        becoming two enquiries - which is what `_sa_close_previous` exists to
        prevent and could not do while the two identities never met.
        """
        self.ensure_one()
        vals = {}
        if not self.requester_phone and message.participant_phone:
            vals['requester_phone'] = message.participant_phone
        if not self.requester_lid and message.participant_lid:
            vals['requester_lid'] = message.participant_lid
        if vals:
            self.sudo().write(vals)
        return bool(vals)

    @api.model
    def _sa_cancellable(self, group, message):
        """This person's most recent enquiry that a cancel should still stop.

        Wider than `_active_deal` on purpose: it includes `handed_off`, where
        the order is being finished in a private chat and is exactly what the
        customer means to stop.
        """
        domain = [('group_id', '=', group.id),
                  ('state', 'in', ('sourcing', 'awaiting_vendor_pick',
                                   'quoted', 'negotiating',
                                   'awaiting_qty', 'awaiting_order_confirm',
                                   'awaiting_confirm', 'finding', 'handed_off')),
                  ('write_date', '>=', self._sa_still_warm())]
        if message.participant_phone:
            domain.append(('requester_phone', '=', message.participant_phone))
        elif message.participant_lid:
            domain.append(('requester_lid', '=', message.participant_lid))
        else:
            return self.browse()
        return self.sudo().search(domain, order='id desc', limit=1)

    @api.model
    def _sa_open_finder(self, group, message):
        """This person's finder in this group, if one is still open.

        Scoped exactly like `_active_deal` - same group, same sender, still
        warm - because a finder belongs to one person and answering somebody
        else's list is how a bystander's tap drove a stranger's enquiry.
        """
        domain = [('group_id', '=', group.id),
                  ('state', '=', 'finding'),
                  ('finder_locked', '=', False),
                  ('write_date', '>=', self._sa_still_warm())]
        if message.participant_phone:
            domain.append(('requester_phone', '=', message.participant_phone))
        elif message.participant_lid:
            domain.append(('requester_lid', '=', message.participant_lid))
        else:
            return self.browse()
        return self.sudo().search(domain, order='id desc', limit=1)

    def _active_deal(self, group, message):
        """This person's live deal in this group, if they have one."""
        # `sourcing` is in this list deliberately. A customer who names a
        # price while waiting - "Price 110" - is bargaining, but if that
        # message is not recognised as part of the deal it becomes a brand new
        # enquiry, gets classified as chatter, and is dropped without a word.
        # That is exactly what happened to enquiry 69: the number vanished and
        # the quote that arrived a minute later ignored it.
        domain = [('group_id', '=', group.id),
                  ('state', 'in', ('sourcing', 'awaiting_vendor_pick',
                                   'quoted', 'negotiating',
                                   'awaiting_qty', 'awaiting_order_confirm')),
                  ('write_date', '>=', self._sa_still_warm())]
        if message.participant_phone:
            domain.append(('requester_phone', '=', message.participant_phone))
        elif message.participant_lid:
            domain.append(('requester_lid', '=', message.participant_lid))
        else:
            return self.browse()
        return self.sudo().search(domain, order='id desc', limit=1)

    def _on_deal_reply(self, text):
        """One turn of the conversation after a price has been quoted.

        Returns True when the message was consumed. False lets it fall through
        and be treated as a brand new enquiry, which is what should happen when
        somebody asks about a different product mid-deal.
        """
        self.ensure_one()
        # Whatever the outcome below, this message was about this enquiry.
        # `sa_trigger_msg` carries WhatsApp's own id - a string like
        # "3EB0AC4971FD62" - not a database id. Handing that to browse() made
        # Odoo read it as a list of ids, one per character, and the resulting
        # bad query aborted the whole webhook transaction.
        trigger = self.env.context.get('sa_trigger_msg')
        if isinstance(trigger, int) and trigger:
            self._sa_tag_message(
                self.env['whatsapp.message'].sudo().browse(trigger))
        elif isinstance(trigger, str) and trigger and not trigger.startswith('row'):
            found = self.env['whatsapp.message'].sudo().search(
                [('wa_message_id', '=', trigger)], limit=1)
            if found:
                self._sa_tag_message(found)
        # Checked before anything else, in every state. A cancel is not a
        # bargaining move, not a product name, and not an answer to whatever
        # was last asked.
        if self._sa_is_cancel(text):
            return self._sa_cancel_deal()
        # Before `_read_yes_no` and before the offer parser: the label is
        # neither a yes nor a no, and a message with "price" in it has been
        # read as the name of a different product before now.
        if self._sa_wants_better_price(text):
            return self._ask_their_price()
        answer = self._read_yes_no(text)

        # Parked at the counter counts as waiting: the customer talking
        # while a shopkeeper decides is the same situation as talking while
        # vendors think, and _on_waiting_reply already handles it.
        if self.state in ('sourcing', 'awaiting_vendor_pick'):
            return self._on_waiting_reply(text, answer)

        # Goods arrived for an order that was never paid: CONFIRM sends the
        # pay link into the group, CANCEL drops the deal.
        if (self.state == 'awaiting_order_confirm' and self.sa_stock_confirm_on
                and not self.sa_stock_confirmed and self.order_id):
            if answer is True:
                return self._sa_send_group_pay_link()
            if answer is False:
                return self._sa_stock_declined()
            return self._sa_ask_stock_confirm(repeat=True)

        if self.state == 'awaiting_order_confirm':
            if answer is True:
                return self._place_order()
            if answer is False:
                # CHANGE, not cancel - the poll's second option here is
                # labelled CHANGE. An actual cancel was caught above.
                # Buttons, not free typing (sa_group_oos._sa_change_menu):
                # what to change - quantity, price, keep, or cancel.
                return self._sa_change_menu()
            return self._ask_quantity(repeat=True)

        # `sa_qty_before_deal`: the quantity was asked before the deal (a
        # product with quantity ranges). The callers of `_announce_price`
        # write state='quoted' right after it, so the state alone cannot be
        # trusted here - "1" was then read as a yes and the quantity asked
        # twice.
        if self.state == 'awaiting_qty' or (self.sa_qty_before_deal and not self.qty):
            qty = self._parse_quantity(text)
            if qty:
                self.qty = qty
                if self.sa_qty_before_deal:
                    # Asked before the deal (quantity ranges): now offer it.
                    return self._sa_offer_after_qty()
                return self._ask_order_confirm()
            if answer is False:
                return self._sa_cancel_deal()
            if self._sa_is_qty_other(text):
                self._say(_("\u270F\uFE0F Type the number you need - like *15* \U0001F447"))
                return True
            self._sa_ask_qty_poll(_("How many do you need? Tap one, or type the number \U0001F447"))
            return True

        # quoted / negotiating
        if answer is True:
            self.agreed_price = self.agreed_price or self.quoted_price
            # Continue in the group. `_ask_quantity` already owns the rest of
            # the ladder there - quantity, order summary, order - so there is
            # nothing to move anywhere.
            return self._ask_quantity()
        if answer is False:
            return self._sa_cancel_deal()
        # Naming another product comes first. "Redmi Note 12 Pro Camera"
        # carries a 12, and reading that as an offer of 12.00 answered a fresh
        # request with a counter-offer on the deal already open - three times
        # in a row, while the customer sat waiting for a price on something
        # else entirely.
        if self._names_another_product(text):
            return False

        if not self._settings().bargain_enabled:
            return False
        if self._counter_offer(text):
            return True
        # Not price talk and not another product - so it is about this deal
        # even if the words are not on any keyword list. "Still high" and "no
        # good" are bargaining to everyone except a lookup table, and answering
        # those with silence is the worst outcome available.
        return self._say_current_offer(text)

    def _on_waiting_reply(self, text, answer):
        """A message from the customer while vendors are still being asked.

        Nothing can be negotiated yet - we have no price of our own - so the
        job here is to keep the number rather than argue with it. It is applied
        the moment the quote is ready, in `_quote_customer`.

        Returns False only when they have moved on to a different product,
        which genuinely is a new enquiry.
        """
        self.ensure_one()
        if answer is False:
            return self._sa_cancel_deal()

        # Same order as mid-deal: naming another product wins over anything
        # that looks like a number in it. "Oppo Reno 11 Pro Camera" was being
        # read as an offer of 11.00 while a different price check was running.
        if self._names_another_product(text):
            return False

        target = self._customer_price(text)
        if target and target > 0:
            self.target_price = target
            _logger.info("Sales Automation: enquiry %s - customer asked for "
                         "%.2f while we were still sourcing", self.id, target)
            self._say(_("Noted \U0001F44D *%(price).2f*.\n\nI'm getting you "
                        "the best price and will come back in a moment.",
                        price=target))
            return True

        # "any discount?" with no number is still about this deal, not a new
        # one, and answering it with silence is what makes the assistant look
        # broken while the customer sits waiting.
        if self.env['wa.auto.reply'].sudo()._detect_bargain_intent(text):
            self._say(_("I'm working on the best price for you \u23F3 - one "
                        "moment."))
            return True

        self._say(_("Still checking on that \u23F3"))
        return True

    def _sa_unused_of(self, options, subject):
        """Alternate between phrasings so a repeat is never word-for-word.

        The gateway drops any message identical to one it sent to the same
        place in the last five minutes, so a customer who sends two bad
        numbers in a row would get an answer to the first and silence to the
        second - which is exactly when they most need one.
        """
        self.ensure_one()
        guard = self.env['sa.outbox.guard'].sudo()
        for index, body in enumerate(options):
            if guard.claim('phrasing|%s|%s|%s' % (
                    self.group_id.id, subject, index), 300):
                return body
        return options[-1]

    def _customer_price(self, text):
        """The price a customer named, in whatever way they wrote it.

        `_parse_price` takes the first number in the message, which is right
        for a bare "110" and wrong for "2 pcs at 110" or "5000mAh 110". So a
        number introduced by a price word wins, a number carrying a unit is
        skipped, and the plain first number is only the fallback.
        """
        import re
        raw = (text or '').replace(',', '')
        cleaned = raw.strip()
        if not cleaned:
            return None

        # Our own reference syntax, stripped before anything is read as
        # money. The tap-links we print say "#7U 450.00" - a code and
        # then a price - so the code has to come off rather than the
        # message being refused outright. What is left of a bare "#500"
        # is nothing, and nothing is not an offer of 500: it was read as
        # one and answered "500.00 - that works" against a deal the
        # customer had not mentioned.
        cleaned = re.sub(r'^#\s*[0-9A-Za-z]{1,6}\b', '',
                         cleaned).strip()
        if not cleaned:
            return None
        raw = cleaned

        # A negative is not an offer. "-400" was read as 400 and
        # bargained against a number the customer never named.
        if re.match(r'^-\s*\d', cleaned):
            return None
        # Symbol debris around the number. "@450" stays valid - it is how
        # a price is written in trade, "at 450" - but "@@450" and
        # "450@" are not, on the same reasoning that stops "@6" being
        # read as a quantity. Only symbols touching the digits count, so
        # "450 \U0001F64F" is still an offer.
        if re.search(r'[^\w\s]{2,}\s*\d', cleaned):
            return None
        if re.search(r'\d[^\w\s.,?!]', cleaned):
            return None
        # "price 110", "rate: 110", "@110", "for 110", "rs 110", "last 110"
        cue = re.search(
            r'(?:\b(?:price|rate|rs\.?|inr|aed|sar|qar|for|at|give|do|make|'
            r'last|final|best|pay|only)\b|[\u20b9$@])'
            r'\s*[:\-]?\s*(\d+(?:\.\d+)?)', raw, re.IGNORECASE)
        if cue:
            return float(cue.group(1))
        # Skip numbers that are plainly not money.
        # "12 pro", "15 max", "note 13" - a number wearing one of these is
        # part of a product name, not money.
        # `k`, `lakh` and `cr` are here for the opposite reason to the
        # rest: they are money, but not the amount written next to them.
        # "450k" read as 450 is off by a factor of a thousand.
        unit = (r'(?:pcs?|nos?|units?|qty|mah|gb|mb|tb|mm|cm|inch|w|v|day|days'
                r'|pro|max|plus|ultra|lite|mini|note|se|series|gen'
                r'|k|lakh|lakhs|lac|lacs|cr|crore|crores|m|bn)')
        for match in re.finditer(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(\w*)', raw):
            if re.fullmatch(unit, match.group(2) or '', re.IGNORECASE):
                continue
            try:
                return float(match.group(1))
            except ValueError:
                break
        # Every number in the message was wearing a unit or a model suffix.
        # Falling back to "first number in the string" here handed back the 12
        # from "Redmi Note 12 Pro Camera" that the loop had just thrown out.
        return None

    def _names_another_product(self, text):
        """True when the message is about some other product entirely."""
        self.ensure_one()
        # A bare number is a price. The catalog holds "GO Ease (30 min)", so
        # searching it for "30" finds a product - and a customer bargaining
        # with "30" had their offer read as a request for a spa package, then
        # discarded as a stray answer, with no reply at all.
        if not any(ch.isalpha() for ch in (text or '')):
            return False
        found = self.env['wa.auto.reply'].sudo()._search_products(text, 1)
        if found:
            return found[0] != self.product_id
        # Nothing in the catalog matched, which is not the same as "not a
        # product". "Samsung Galaxy S23 Ultra Screen Protector" is plainly a
        # new request even though we do not stock it - and the old behaviour
        # answered it by repeating the iPhone deal that was still open, which
        # is the worst reply available: the customer asked for one thing and
        # was shown another, priced and marked final.
        return self.env['sa.ai.classifier'].sudo()._looks_like_product_request(
            text)

    # Bare pleasantries. Long enough to recognise, short enough that a real
    # message is never mistaken for one.
    _SA_GREETINGS = frozenset((
        'hi', 'hii', 'hiii', 'hello', 'helo', 'hey', 'hai', 'yo', 'sup',
        'howdy', 'greetings', 'good morning', 'good evening', 'good night',
        'good afternoon', 'gm', 'ge', 'namaste', 'salam', 'assalamu alaikum',
    ))

    @api.model
    def _sa_is_greeting(self, text):
        """A message that is nothing but a hello."""
        stripped = (text or '').strip().lower().strip('.!?, ')
        return bool(stripped) and stripped in self._SA_GREETINGS

    def _say_current_offer(self, text=''):
        """Answer a message we could not place, without asking again.

        Text, never a second poll. Re-posting the poll for anything the
        keyword lists did not recognise meant a customer who typed "hello"
        while a quote was open got the whole ACCEPT/CANCEL question again -
        and worse, the new poll overwrote `poll_wa_id`, so a tap on the
        *first* poll no longer matched this enquiry and was read as some
        bystander's vote.

        The instruction is spelled out rather than pointing at another
        message. "Tap ACCEPT on the message above" assumed the poll is the
        thing above, and it often is not - the wa.me link is posted after it,
        and after two rounds of bargaining the poll is several messages back.
        A word the customer can type works from anywhere in the thread.
        """
        self.ensure_one()
        price = self.agreed_price or self.quoted_price
        floor = self._bargain_floor()
        name = self.product_id.name or self.ai_search_term or _("this item")
        spent = (price <= floor + 0.001 or self.bargain_count >= (
            self._settings().bargain_max_steps or 0))
        if spent:
            body = _("\U0001F4E6 *%(product)s*\n\U0001F4B0 *%(price).2f* - "
                     "that is our final price. \U0001F64F",
                     product=name, price=price)
        else:
            body = _("\U0001F4E6 *%(product)s*\n\U0001F4B0 *%(price).2f*",
                     product=name, price=price)
        if self._sa_is_greeting(text):
            body = '%s\n\n%s' % (_("Hi \U0001F44B"), body)
        # This used to be text on purpose: a second poll overwrote the one
        # poll id the enquiry could remember, so a tap on the earlier poll
        # stopped matching and was read as a bystander's vote. `poll_wa_ids`
        # keeps the last eight now, so the reason is gone - and this is the
        # message a customer most often has in front of them, which made it
        # the one place with no buttons at all. `_ask` spells the choices out
        # in words wherever the poll does not render, and its outbox guard
        # stops a customer saying "hi" twice from getting two polls.
        self._ask(body, self._sa_deal_options(allow_bargain=not spent))
        return True

    def _counter_offer(self, text, tapped=False):
        """Answer a bargaining message by stepping the price down once.

        Stepped rather than split-the-difference. Each push takes a fixed
        percentage off the *originally quoted* price, and once the configured
        number of steps is used up the answer is simply that this is final.
        Meeting a customer halfway every time never converges, and it teaches
        them that one more push is always worth making.

        Two things end the haggling - the step count and the floor - and
        whichever is reached first wins, so a generous step count still cannot
        dig into the margin.
        """
        self.ensure_one()
        settings = self._settings()
        AutoReply = self.env['wa.auto.reply'].sudo()
        target = self._customer_price(text)

        # The product's own quantity table replaces the flat step entirely.
        if self._sa_qty_tiered():
            return self._sa_tier_offer(text, tapped=tapped)

        # A number we could not read is not the same as no number at all.
        # "-400" was answered by posting the final price again, which reads as
        # the offer having been understood and declined; the customer has no
        # way to tell that the minus sign was the problem. Letters mean it is
        # words rather than a botched number, and those already have their own
        # paths - a product name, a greeting, a bargaining phrase.
        if target is None and text and text.strip() and not any(
                ch.isalpha() for ch in text):
            said = text.strip()[:16]
            self._say(self._sa_unused_of([
                _("*%(said)s* is not a price I can use. Tell me the number "
                  "you'd like to pay - like *450*.", said=said),
                _("I couldn't read *%(said)s* as a price. Send just the "
                  "amount, such as *450*.", said=said),
            ], said))
            return True

        # `tapped`: the customer pressed BETTER PRICE. That is the intent,
        # stated as plainly as it can be - the keyword detector is for typed
        # text and does not even list "better price".
        if (target is None and not tapped
                and not AutoReply._detect_bargain_intent(text)):
            return False        # not about price - let it start a new enquiry

        floor = self._bargain_floor()
        current = self.agreed_price or self.quoted_price or floor

        # A number at or above what we are already asking is not a bargaining
        # move, and stepping down in answer to one is the assistant
        # undercutting itself: quoted 627.60, the customer said 700, then 650,
        # and it walked the price down to 568.62 - giving away margin nobody
        # asked for. Hold the price and let them confirm it.
        if target is not None and target >= current - 0.001:
            name = self.product_id.name or self.ai_search_term or _("this item")
            self._ask(
                _("\U0001F4E6 *%(product)s*"
                  "\n\U0001F4B0 *%(price).2f* - that works \U0001F44D"
                  "\n\nTap *ACCEPT* to confirm.",
                  product=name, price=current),
                [{'id': 'sa_yes', 'title': _('ACCEPT')},
                 {'id': 'sa_no', 'title': _('CANCEL')}])
            self.state = 'negotiating'
            return True

        steps_left = max(
            0, (settings.bargain_max_steps or 0) - self.bargain_count)

        if steps_left <= 0 or current <= floor + 0.001:
            return self._say_final(current, floor)

        step = ((self.quoted_price or current)
                * (settings.bargain_step_percent or 0.0) / 100.0)
        offer = max(floor, current - step)
        # A customer asking for less of a discount than we were about to give
        # gets their own number - there is no sense undercutting ourselves.
        if target is not None and floor <= target < current and target > offer:
            offer = target

        self.write({'agreed_price': offer,
                    'bargain_count': self.bargain_count + 1,
                    'state': 'negotiating'})

        spent = self.bargain_count >= (settings.bargain_max_steps or 0)
        if spent or offer <= floor + 0.001:
            return self._say_final(offer, floor)

        name = self.product_id.name or self.ai_search_term or _("this item")
        rendered = self._ask(
            _("\U0001F4E6 *%(product)s*\n\U0001F4B0 Special price for you: "
              "*%(price).2f*", product=name, price=offer),
            self._sa_deal_options())
        if rendered != 'poll':
            self._say(self._sa_price_taps(offer))
        return True

    def _say_final(self, price, floor):
        """No steps left. Say so plainly and offer only accept or cancel."""
        self.ensure_one()
        self.write({'agreed_price': price, 'state': 'negotiating'})
        name = self.product_id.name or self.ai_search_term or _("this item")
        # No bargain option here: there is nothing left to give, and a
        # button that can only be refused reads as a tease.
        rendered = self._ask(
            _("\U0001F4E6 *%(product)s*\n\U0001F4B0 *%(price).2f* - that is "
              "our final price. \U0001F64F", product=name, price=price),
            self._sa_deal_options(allow_bargain=False))
        if rendered != 'poll':
            self._say(self._sa_price_taps(price, accept_only=True))
        return True

    # ------------------------------------------------------------------
    # Who is the customer?
    # ------------------------------------------------------------------
    def _sa_profile_complete(self, partner):
        """True when we already know enough not to ask again.

        A name auto-invented from the phone number does not count - the
        tracker files unknown numbers as "WhatsApp Customer (9170...)", and
        putting that on a quotation is worse than asking.
        """
        self.ensure_one()
        if not partner or not partner.street or not partner.zip:
            return False
        return bool(partner._sa_real_name())

    # Postcode shapes by country: (pattern, example). An empty pattern means
    # the country issues no postcodes at all, so the question is skipped rather
    # than asked and failed. Anything not listed falls back to a loose shape -
    # better to accept an unusual postcode than to refuse a real customer.
    _SA_PIN_FORMATS = {
        'IN': (r'[1-9][0-9]{5}', '691001'),
        'OM': (r'[0-9]{3}', '111'),
        'SA': (r'[0-9]{5}(-[0-9]{4})?', '11564'),
        'KW': (r'[0-9]{5}', '12345'),
        'BH': (r'[0-9]{3,4}', '317'),
        'JO': (r'[0-9]{5}', '11118'),
        'EG': (r'[0-9]{5}', '11511'),
        'US': (r'[0-9]{5}(-[0-9]{4})?', '90210'),
        'CA': (r'[A-Z][0-9][A-Z] ?[0-9][A-Z][0-9]', 'K1A 0B1'),
        'GB': (r'[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}', 'SW1A 1AA'),
        'IE': (r'[A-Z][0-9][0-9W] ?[A-Z0-9]{4}', 'D02 AF30'),
        'DE': (r'[0-9]{5}', '10115'),
        'FR': (r'[0-9]{5}', '75001'),
        'ES': (r'[0-9]{5}', '28001'),
        'IT': (r'[0-9]{5}', '00100'),
        'NL': (r'[0-9]{4} ?[A-Z]{2}', '1012 AB'),
        'BE': (r'[0-9]{4}', '1000'),
        'CH': (r'[0-9]{4}', '8001'),
        'AT': (r'[0-9]{4}', '1010'),
        'PL': (r'[0-9]{2}-?[0-9]{3}', '00-001'),
        'SE': (r'[0-9]{3} ?[0-9]{2}', '111 22'),
        'AU': (r'[0-9]{4}', '2000'),
        'NZ': (r'[0-9]{4}', '6011'),
        'SG': (r'[0-9]{6}', '018956'),
        'MY': (r'[0-9]{5}', '50450'),
        'TH': (r'[0-9]{5}', '10200'),
        'ID': (r'[0-9]{5}', '10110'),
        'PH': (r'[0-9]{4}', '1000'),
        'CN': (r'[0-9]{6}', '100000'),
        'JP': (r'[0-9]{3}-?[0-9]{4}', '100-0001'),
        'KR': (r'[0-9]{5}', '04524'),
        'LK': (r'[0-9]{5}', '10100'),
        'BD': (r'[0-9]{4}', '1000'),
        'NP': (r'[0-9]{5}', '44600'),
        'PK': (r'[0-9]{5}', '44000'),
        'BR': (r'[0-9]{5}-?[0-9]{3}', '01310-100'),
        'MX': (r'[0-9]{5}', '06000'),
        'ZA': (r'[0-9]{4}', '0002'),
        'NG': (r'[0-9]{6}', '100001'),
        'KE': (r'[0-9]{5}', '00100'),
        'RU': (r'[0-9]{6}', '101000'),
        'TR': (r'[0-9]{5}', '34000'),
        # These issue no postcode. Asking is a question with no right answer.
        'AE': ('', ''),
        'QA': ('', ''),
        'HK': ('', ''),
        'MO': ('', ''),
        'PA': ('', ''),
        'FJ': ('', ''),
    }
    # Anything unlisted: three to ten letters and digits. Loose on purpose -
    # refusing a real customer over an unrecognised format is the worse error.
    _SA_PIN_FALLBACK = r'[A-Z0-9][A-Z0-9 -]{1,8}[A-Z0-9]'

    def _sa_looks_like_name(self, text):
        """A person's name, for printing on a quotation.

        Two rules, both learned from testers. It needs **letters** - counting
        characters let "@@@" through. And it may not contain **digits** -
        counting letters then let "1Sonia" through. Apostrophes, hyphens, dots
        and spaces are left alone so "O'Brien" and "Mary-Jane" still work.
        """
        stripped = (text or '').strip()
        if sum(1 for ch in stripped if ch.isalpha()) < 2:
            return False
        return all(ch.isalpha() or ch in " '-." for ch in stripped)

    # The words that make a line an address rather than three words. Kinds of
    # place, not place names - there is no finite list of those.
    _SA_ADDRESS_WORDS = frozenset("""
    road rd street st lane ln cross main avenue ave way highway
    nagar colony layout sector block phase ward area locality
    house home flat apartment apartments apt villa building bldg tower
    floor door plot gate quarters residency residence
    town city village district dist taluk mandal po post office
    near opp opposite behind beside above below front back
    market bazaar junction circle park garden society complex plaza
    centre center mall industrial estate campus
    """.split())

    def _sa_looks_like_address(self, text):
        """Enough of an address to put on a delivery note.

        Three rules, each added after a tester walked past the last one.
        Length alone let "000 000" through. Counting letters then let
        "Abc 000" through. Counting words let "Abc Defg Hijk" through - three
        real words that name nowhere at all.

        So an address must also carry something that identifies a place: a
        number - a door, plot or building number, which nearly every address
        has - or a word that says what kind of place it is. Words, not place
        names: there is no finite list of those, and demanding one would
        refuse half the world.
        """
        import re
        cleaned = (text or '').strip()
        named = [word for word in re.split(r'[^0-9A-Za-z]+', cleaned)
                 if any(ch.isalpha() for ch in word)]
        letters = sum(1 for ch in cleaned if ch.isalpha())
        if len(named) < 2 or letters < 6:
            return False
        if any(ch.isdigit() for ch in cleaned):
            return True
        words = {w.lower() for w in re.split(r'[^0-9A-Za-z]+', cleaned) if w}
        return bool(words & self._SA_ADDRESS_WORDS)

    # International dialling codes for the countries we hold a postcode
    # format for. Longest match wins, so 971 is not read as 97.
    _SA_DIAL_CODES = {
        '91': 'IN', '968': 'OM', '971': 'AE', '966': 'SA', '974': 'QA',
        '965': 'KW', '973': 'BH', '962': 'JO', '20': 'EG', '44': 'GB',
        '1': 'US', '61': 'AU', '64': 'NZ', '65': 'SG', '60': 'MY',
        '66': 'TH', '62': 'ID', '63': 'PH', '86': 'CN', '81': 'JP',
        '82': 'KR', '94': 'LK', '880': 'BD', '977': 'NP', '92': 'PK',
        '49': 'DE', '33': 'FR', '34': 'ES', '39': 'IT', '31': 'NL',
        '32': 'BE', '41': 'CH', '43': 'AT', '48': 'PL', '46': 'SE',
        '353': 'IE', '55': 'BR', '52': 'MX', '27': 'ZA', '234': 'NG',
        '254': 'KE', '7': 'RU', '90': 'TR',
    }

    def _sa_pin_country(self, partner):
        """Whose postcode rules apply.

        The contact first, then the address they just gave, then the number
        they are writing from, and only then the configured default.

        The address step matters because the two below it are guesses and it
        is not. A customer on an Indian number typed "Muscat Oman 5789" and
        was told "I need a postcode for India, like 691001" - the dialling
        code had decided the country while the customer's own words said
        otherwise. Where somebody lives and where their phone was bought are
        different facts.

        The number is still the step under it: 223 of the 224 customer
        contacts here have no country, so without it everyone was judged by
        the default - Oman, three digits - and a real Indian pincode like
        691001 was refused.
        """
        self.ensure_one()
        if partner.country_id:
            return partner.country_id
        named = self._sa_country_in_address(partner.street or '')
        if named:
            return named
        digits = ''.join(c for c in (
            partner.phone or partner.phone_sanitized or self.requester_phone
            or (self.conversation_id.phone if self.conversation_id else '')
            or '') if c.isdigit())
        for length in (3, 2, 1):
            code = self._SA_DIAL_CODES.get(digits[:length])
            if code:
                country = self.env['res.country'].sudo().search(
                    [('code', '=', code)], limit=1)
                if country:
                    return country
        return self._settings().pincode_country_id

    # Short forms people write instead of the official name. Odoo knows
    # "United Arab Emirates"; nobody types that on WhatsApp.
    _SA_COUNTRY_ALIASES = {
        'uae': 'AE', 'u.a.e': 'AE', 'emirates': 'AE',
        'uk': 'GB', 'u.k': 'GB', 'britain': 'GB', 'england': 'GB',
        'scotland': 'GB', 'wales': 'GB',
        'usa': 'US', 'u.s.a': 'US', 'america': 'US',
        'ksa': 'SA', 'saudi': 'SA',
        'bharat': 'IN', 'hindustan': 'IN',
    }

    # Country names that are also ordinary words, street names or US states.
    # Skipped rather than risked: somebody genuinely in Jordan is on a +962
    # number and gets Jordan from the dialling code anyway, whereas "Jersey
    # Street" would otherwise move a Kerala address to the Channel Islands.
    _SA_COUNTRY_AMBIGUOUS = frozenset((
        'georgia', 'jersey', 'turkey', 'chad', 'jordan', 'guinea', 'niger',
        'guernsey', 'reunion', 'martinique',
    ))

    # Cities, for the countries this business actually delivers to.
    #
    # Odoo ships countries and states but no cities, and it has *no* states at
    # all for Oman, Qatar, Kuwait or Bahrain - so "Building #12, Street 45,
    # Muscat" could not be placed from Odoo's own data, and the postcode was
    # judged by the dialling code of an Indian phone.
    #
    # Deliberately not a world gazetteer: the Gulf, plus the Indian cities and
    # Kerala towns this catalogue sells into. Anything not here still gets the
    # question added in 19.0.92.0.0 - "send me the country name" - so a gap in
    # this list is a slower path, never a wrong answer.
    _SA_CITY_COUNTRY = {
        # Oman
        'muscat': 'OM', 'muttrah': 'OM', 'mutrah': 'OM', 'seeb': 'OM',
        'salalah': 'OM', 'sohar': 'OM', 'nizwa': 'OM', 'sur': 'OM',
        'ibri': 'OM', 'barka': 'OM', 'rustaq': 'OM', 'ibra': 'OM',
        'bahla': 'OM', 'buraimi': 'OM', 'duqm': 'OM', 'saham': 'OM',
        'shinas': 'OM', 'samail': 'OM', 'izki': 'OM', 'adam': 'OM',
        'quriyat': 'OM', 'khasab': 'OM', 'ruwi': 'OM', 'ghala': 'OM',
        'azaiba': 'OM', 'qurum': 'OM', 'mabela': 'OM', 'amerat': 'OM',
        'khuwair': 'OM', 'ghubra': 'OM', 'bousher': 'OM', 'wadi kabir': 'OM',
        'al khuwair': 'OM', 'al amerat': 'OM', 'sultanate': 'OM',
        # United Arab Emirates
        'dubai': 'AE', 'abu dhabi': 'AE', 'abudhabi': 'AE', 'sharjah': 'AE',
        'ajman': 'AE', 'fujairah': 'AE', 'ras al khaimah': 'AE',
        'umm al quwain': 'AE', 'al ain': 'AE', 'deira': 'AE', 'bur dubai': 'AE',
        # Qatar
        'doha': 'QA', 'al wakrah': 'QA', 'al khor': 'QA', 'lusail': 'QA',
        'rayyan': 'QA', 'umm salal': 'QA',
        # Kuwait
        'kuwait city': 'KW', 'hawalli': 'KW', 'salmiya': 'KW',
        'farwaniya': 'KW', 'jahra': 'KW', 'ahmadi': 'KW', 'fahaheel': 'KW',
        # Bahrain
        'manama': 'BH', 'muharraq': 'BH', 'riffa': 'BH', 'isa town': 'BH',
        'hamad town': 'BH', 'sitra': 'BH',
        # Saudi Arabia
        'riyadh': 'SA', 'jeddah': 'SA', 'jiddah': 'SA', 'mecca': 'SA',
        'makkah': 'SA', 'medina': 'SA', 'madinah': 'SA', 'dammam': 'SA',
        'khobar': 'SA', 'dhahran': 'SA', 'taif': 'SA', 'abha': 'SA',
        'tabuk': 'SA', 'jubail': 'SA', 'yanbu': 'SA', 'hail': 'SA',
        'buraidah': 'SA', 'khamis mushait': 'SA', 'najran': 'SA',
        # India - metros
        'mumbai': 'IN', 'bombay': 'IN', 'delhi': 'IN', 'new delhi': 'IN',
        'bangalore': 'IN', 'bengaluru': 'IN', 'chennai': 'IN',
        'kolkata': 'IN', 'calcutta': 'IN', 'hyderabad': 'IN', 'pune': 'IN',
        'ahmedabad': 'IN', 'surat': 'IN', 'jaipur': 'IN', 'lucknow': 'IN',
        'nagpur': 'IN', 'indore': 'IN', 'bhopal': 'IN', 'patna': 'IN',
        'noida': 'IN', 'gurgaon': 'IN', 'gurugram': 'IN', 'chandigarh': 'IN',
        'coimbatore': 'IN', 'madurai': 'IN', 'mysore': 'IN', 'mysuru': 'IN',
        'mangalore': 'IN', 'visakhapatnam': 'IN', 'vijayawada': 'IN',
        # India - Kerala, where most of this catalogue sells
        'kochi': 'IN', 'cochin': 'IN', 'ernakulam': 'IN', 'aluva': 'IN',
        'trivandrum': 'IN', 'thiruvananthapuram': 'IN', 'kollam': 'IN',
        'quilon': 'IN', 'kozhikode': 'IN', 'calicut': 'IN', 'thrissur': 'IN',
        'trichur': 'IN', 'kannur': 'IN', 'cannanore': 'IN', 'kasaragod': 'IN',
        'alappuzha': 'IN', 'alleppey': 'IN', 'kottayam': 'IN',
        'palakkad': 'IN', 'palghat': 'IN', 'malappuram': 'IN',
        'pathanamthitta': 'IN', 'idukki': 'IN', 'wayanad': 'IN',
        'kalamassery': 'IN', 'kakkanad': 'IN', 'perinthalmanna': 'IN',
        'manjeri': 'IN', 'tirur': 'IN', 'ponnani': 'IN', 'guruvayur': 'IN',
        'chalakudy': 'IN', 'angamaly': 'IN', 'muvattupuzha': 'IN',
        'thodupuzha': 'IN', 'changanassery': 'IN', 'thiruvalla': 'IN',
        'chengannur': 'IN', 'adoor': 'IN', 'punalur': 'IN', 'attingal': 'IN',
        'neyyattinkara': 'IN', 'nedumangad': 'IN', 'varkala': 'IN',
        'cherthala': 'IN', 'mavelikkara': 'IN', 'kayamkulam': 'IN',
        'vadakara': 'IN', 'koyilandy': 'IN', 'payyanur': 'IN', 'thalassery': 'IN',
    }

    @api.model
    def _sa_country_in_address(self, address):
        """The country an address names, or an empty recordset.

        Matched against `res.country` - the list Odoo already ships - rather
        than a table maintained here. Whole words only, so "Indiana" is not
        India, and the *last* match wins because an address ends with its
        country.

        Names shorter than four letters are skipped: two-letter codes collide
        with everything ("in", "no", "is") and a three-letter one would make
        "uae" out of any word containing it.
        """
        import re
        words = [w for w in re.split(r"[^0-9A-Za-z.]+", (address or '').lower())
                 if w]
        if not words:
            return self.env['res.country']
        Country = self.env['res.country'].sudo()

        seen = set(words)
        for word in reversed(words):
            code = self._SA_COUNTRY_ALIASES.get(word.strip('.'))
            if code:
                found = Country.search([('code', '=', code)], limit=1)
                if found:
                    return found

        # A city names its country as surely as the country does, and is
        # what people actually write. Checked before the state list because
        # the countries with no states in Odoo are exactly the ones this is
        # here for. Longest name first, so "abu dhabi" is not read as a
        # stray "dhabi" and "kuwait city" beats nothing at all.
        flat = ' %s ' % ' '.join(words)
        for city in sorted(self._SA_CITY_COUNTRY, key=len, reverse=True):
            if ' %s ' % city in flat:
                found = Country.search(
                    [('code', '=', self._SA_CITY_COUNTRY[city])], limit=1)
                if found:
                    return found

        # Odoo also ships states, emirates and provinces. "Dubai" and
        # "Kerala" are in there and name their country unambiguously - free
        # coverage for addresses that give a region but no country. Only
        # accepted when exactly one country claims that name, so a "Punjab"
        # in both India and Pakistan decides nothing.
        states = self.env['res.country.state'].sudo().search([])
        by_name = {}
        for state in states:
            key = (state.name or '').lower()
            # The same skip list the country loop uses. Without it the state
            # names reintroduced exactly what it was written to prevent:
            # "Georgia Apartments, Bangalore" resolved to the United States.
            if len(key) > 3 and key not in self._SA_COUNTRY_AMBIGUOUS:
                by_name.setdefault(key, set()).add(state.country_id.id)
        for word in reversed(words):
            owners = by_name.get(word.strip('.'))
            if owners and len(owners) == 1:
                return Country.browse(list(owners)[0])

        # One pass over the country list, matching whole names - so
        # "United Arab Emirates" is found as well as "Oman".
        best, best_at = self.env['res.country'], -1
        for country in Country.search([]):
            name = (country.name or '').lower()
            parts = [w for w in re.split(r"[^0-9a-z]+", name) if w]
            if not parts or len(name) < 4:
                continue
            if name in self._SA_COUNTRY_AMBIGUOUS:
                continue
            if not set(parts) <= seen:
                continue
            try:
                at = max(len(words) - 1 - words[::-1].index(w) for w in parts)
            except ValueError:
                continue
            if at > best_at:
                best, best_at = country, at
        return best

    def _sa_pincode_wanted(self, partner):
        """False where the country issues no postcodes at all."""
        self.ensure_one()
        country = self._sa_pin_country(partner)
        shape = self._SA_PIN_FORMATS.get(country.code or '')
        return not (shape is not None and not shape[0])

    def _sa_find_pincode(self, text, partner):
        """The postcode in `text`, or None when there is nothing believable.

        Digit count is the least of it: "789655" has six digits and is not an
        Indian pincode. Without a national postcode list the only exact check
        is the set of areas the business actually delivers to, which is why
        that is a setting. Everything rulable out for free is ruled out here -
        the wrong shape for the country, and the runs people type to get past
        the question.
        """
        import re
        self.ensure_one()
        if not self._sa_pincode_wanted(partner):
            return None
        country = self._sa_pin_country(partner)
        shape = self._SA_PIN_FORMATS.get(country.code or '')
        pattern = shape[0] if shape else self._SA_PIN_FALLBACK
        settings = self._settings()
        allowed = [p.strip() for p in (settings.pincode_prefixes or '').split(',')
                   if p.strip()]
        haystack = (text or '').upper()
        for match in re.finditer(
                r'(?<![A-Z0-9])(?:' + pattern + r')(?![A-Z0-9])', haystack):
            candidate = match.group(0).strip()
            digits = candidate.replace(' ', '').replace('-', '')
            if digits.isdigit():
                if not digits.strip('0'):
                    continue        # 0, 00, 000 - nowhere at all
                if len(digits) >= 4:
                    # The repeat rule only where a repeat is implausible: Oman
                    # really does use 111, and Cape Town really is 0002.
                    if len(set(digits)) == 1 or self._sa_is_run(digits):
                        continue
            if allowed and not any(candidate.startswith(p) for p in allowed):
                continue
            return candidate
        return None

    @api.model
    def _sa_is_run(self, digits):
        """123456 or 654321 - typed to get past the question, not an address."""
        steps = [int(b) - int(a) for a, b in zip(digits, digits[1:])]
        return bool(steps) and (all(s == 1 for s in steps)
                                or all(s == -1 for s in steps))

    def _sa_pincode_hint(self, partner):
        """What a good postcode looks like here, for the retry message."""
        self.ensure_one()
        settings = self._settings()
        allowed = [p.strip() for p in (settings.pincode_prefixes or '').split(',')
                   if p.strip()]
        if allowed:
            return _("a postcode for the areas we deliver to - %(areas)s",
                     areas=', '.join(allowed[:6]))
        country = self._sa_pin_country(partner)
        shape = self._SA_PIN_FORMATS.get(country.code or '')
        if shape and shape[1]:
            return _("a postcode for %(country)s, like *%(eg)s*",
                     country=country.name or '', eg=shape[1])
        return _("a valid postcode")

    def _sa_profile_question(self, order):
        """What to ask next. Returns the tracker's (reply, reply_type) pair.

        Everything is typed `await_address` on purpose: that is the one state
        the tracker already loops on, so each answer comes back through
        `_wa_apply_address` and the next question goes out from
        `_payment_or_finalize`. No new state machine, and nothing in the shared
        module has to change.
        """
        self.ensure_one()
        partner = order.partner_id
        step = self.profile_step
        if not step:
            step = 'confirm' if self._sa_profile_complete(partner) else 'name'
            self.profile_step = step
        # Every path below returns a question, so this is the moment the form
        # last spoke. `write_date` cannot serve: it is bumped by the form
        # answering a message, which let an abandoned form keep itself alive
        # for ever on the very messages it should not have been reading.
        self.profile_asked_on = fields.Datetime.now()

        # A rejected answer must not be met with the same words: an identical
        # message inside three minutes is swallowed as a duplicate, so the
        # customer would be left in silence for having typed the wrong thing.
        again = self.profile_retry
        # Quoting their own words back is not decoration. Two bad answers in a
        # row produced the same sentence twice, the second was dropped as a
        # duplicate, and the customer was met with silence for having typed
        # something wrong - which is exactly when they most need an answer.
        bad = (self.profile_last_bad or '').strip()[:40]
        if step == 'name':
            if again:
                return (_("Sorry, I can't use *%(bad)s* as a name - letters "
                          "only, please. What name should the quotation be "
                          "in?", bad=bad or '-'), 'await_address')
            if self.profile_restarted:
                # Kept because it reads better after a NO, not because it has
                # to differ from the first question any more.
                self.profile_restarted = False
                return (_("No problem, let's do those again \U0001F501"
                          "\n\n\U0001F464 What name should the quotation "
                          "be in?"), 'await_address')
            return (_("\U0001F464 Before I raise your quotation - what name "
                      "should it be in?"), 'await_address')
        if step == 'address':
            if again:
                return (_("I can't deliver to *%(bad)s*. Please send the "
                          "full address - door number, street, area and city.",
                          bad=bad or '-'), 'await_address')
            return (_("\U0001F3E0 Thanks %(name)s. What is your full address?",
                      name=partner.name or ''), 'await_address')
        if step == 'pin':
            if again:
                # Where the country was never stated - not on the contact, not
                # in the address - it was worked out from the dialling code of
                # the phone, and that is a guess worth admitting to. A tester
                # gave "Building #12, Street 45, Muscat" from an Indian number
                # and was told to send a postcode "for India, like 691001",
                # with no way to say otherwise.
                if not partner.country_id:
                    return (_("*%(bad)s* is not a postcode for "
                              "*%(country)s*.\n\nIf the address is somewhere "
                              "else, send me the country name - like "
                              "*Oman* - and I'll check it against that "
                              "instead.",
                              bad=bad or '-',
                              country=self._sa_pin_country(partner).name or ''),
                            'await_address')
                return (_("*%(bad)s* is not a postcode. I need %(hint)s.",
                          bad=bad or '-',
                          hint=self._sa_pincode_hint(partner)), 'await_address')
            return (_("\U0001F4EE And your pincode?"), 'await_address')
        summary = self._sa_profile_summary(partner)
        if again:
            summary = _("Sorry, I didn't understand *%(bad)s*.\n\n%(summary)s",
                        bad=bad or '-', summary=summary)
        return (summary, 'await_address')

    def _sa_profile_summary(self, partner):
        """Read the details back before anything is raised against them."""
        self.ensure_one()
        return _("\U0001F4CB *Please check your details*\n\n"
                 "\U0001F464 %(name)s\n"
                 "\U0001F3E0 %(street)s\n"
                 "\U0001F4EE %(zip)s\n"
                 "\U0001F4F1 %(phone)s\n\n"
                 "Reply *YES* to confirm, *NO* to change them, "
                 "or *CANCEL* to stop.",
                 name=partner.name or '-', street=partner.street or '-',
                 zip=partner.zip or '-', phone=partner.phone or '-')

    @api.model
    def _sa_rename_own_addresses(self, partner, old_name):
        """The customer's own delivery addresses carry their name - the
        address book copies it on when it makes one. When they change their
        name, those follow; an address for somebody else keeps its own.

        Before: NO > NAME > "Sri" renamed the contact only, so the order's
        address still said "RaviKavitha", the read-back showed
        "RaviKavitha (for Sri)" and the rider was given the old name (S00024).
        """
        old_name = (old_name or '').strip()
        partner = partner.sudo()
        if not old_name or old_name == (partner.name or '').strip():
            return
        own = partner.child_ids.filtered(
            lambda c: c.type in ('delivery', 'other')
            and (c.name or '').strip() == old_name)
        if own:
            own.write({'name': partner.name})

    def _sa_take_profile_answer(self, text, order):
        """Record one answer and move the ladder on."""
        self.ensure_one()
        import re
        partner = order.partner_id.sudo()
        answer = (text or '').strip()
        step = self.profile_step or 'name'

        # They are already chatting from it, so asking for the number would be
        # asking them to type something we can see.
        if not partner.phone and self.conversation_id.phone:
            partner.phone = self.conversation_id.phone

        def move_on(next_step):
            self.write({'profile_step': next_step, 'profile_retry': 0,
                        'profile_last_bad': False, 'profile_restarted': False})

        def reject():
            self.write({'profile_retry': self.profile_retry + 1,
                        'profile_last_bad': answer[:60]})

        # At every step, not only at the summary. "cancel" typed at the name
        # question satisfied "two characters and not a digit", so it was
        # written down as the customer's name and the quotation went ahead.
        if self._sa_is_cancel(answer):
            self.profile_step = 'done'
            self._sa_cancel_deal()
            return

        if step == 'name':
            if self._sa_looks_like_name(answer):
                old = partner.name
                partner.name = answer[:80]
                self._sa_rename_own_addresses(partner, old)
                move_on('address')
            else:
                reject()
            return

        if step == 'address':
            if not self._sa_looks_like_address(answer):
                reject()
                return
            partner.street = answer[:250]
            # Written down, not only used for the postcode check: a delivery
            # address with no country on the quotation is the same problem
            # one step later.
            if not partner.country_id:
                named = self._sa_country_in_address(answer)
                if named:
                    partner.country_id = named.id
                    _logger.info("Sales Automation: enquiry %s - read %s from "
                                 "the address given", self.id, named.name)
            found = self._sa_find_pincode(answer, partner)
            if found:
                # Typed together with the address, as most people do - no
                # sense asking for something they have already given.
                partner.zip = found
                move_on('confirm')
            elif not self._sa_pincode_wanted(partner):
                # The UAE, Qatar and Hong Kong issue none. Asking for one
                # there is a question with no right answer.
                move_on('confirm')
            else:
                move_on('pin')
            return

        if step == 'pin':
            # They answered the question above with a country rather than a
            # postcode. Record it and ask again, now against the right rules -
            # the alternative is refusing a correct answer to our own question.
            named = self._sa_country_in_address(answer)
            if named and named != partner.country_id:
                partner.country_id = named.id
                _logger.info("Sales Automation: enquiry %s - customer says the "
                             "address is in %s", self.id, named.name)
                if not self._sa_pincode_wanted(partner):
                    move_on('confirm')
                    return
                self.write({'profile_retry': 0, 'profile_last_bad': False})
                self._say(_("Thanks - *%(country)s* it is. I need %(hint)s.",
                            country=named.name,
                            hint=self._sa_pincode_hint(partner)),
                          addressed=False)
                return
            found = self._sa_find_pincode(answer, partner)
            if found:
                partner.zip = found
                move_on('confirm')
            elif not self._sa_pincode_wanted(partner):
                move_on('confirm')
            else:
                reject()
            return

        if step == 'confirm':
            # No numbered options here, so a bare digit is not an answer -
            # it is far more likely to be a quantity typed a beat too late.
            verdict = self._read_yes_no(answer, numbered=False)
            if verdict is True:
                if not partner.customer_rank:
                    partner.customer_rank = 1
                move_on('done')
                _logger.info("Sales Automation: enquiry %s - customer %s "
                             "confirmed their details", self.id, partner.name)
            elif verdict is False:
                move_on('name')
                self.profile_restarted = True
            else:
                reject()
            return

    def _settings(self):
        """The one row that holds margin, reply window and bargaining."""
        return self.env['sa.ai.settings'].sudo().get_settings()

    def _bargain_floor(self):
        """The lowest price this deal may close at.

        Built on what the goods actually cost us - the winning vendor quote
        where there was one - so a discount can never quietly eat the margin.
        With no vendor cost the catalog price is the floor: an in-stock item is
        not sold below its list price by a bot.
        """
        self.ensure_one()
        margin = 1.0 + (self._settings().min_margin_percent or 0.0) / 100.0
        if self.vendor_price:
            return self.vendor_price * margin
        # Owner's rule (29 Sep 2026): with no vendor quote the deal may go
        # down to the product's COST plus the minimum margin, never below.
        product = self.product_id
        cost = 0.0
        if product:
            priced = product.with_company(self.finder_company_id
                                          or self._company_for(self.group_id))
            cost = priced.standard_price or 0.0
        if cost > 0:
            floor = cost * margin
            top = self.quoted_price or product.list_price or floor
            return min(floor, top) if top else floor
        return self.product_id.list_price or self.quoted_price or 0.0

    @api.model
    def _parse_quantity(self, text):
        """A plain count, or None. Deliberately strict."""
        cleaned = (text or '').strip().lower()
        for word in ('pcs', 'pieces', 'nos', 'units', 'qty', 'x'):
            cleaned = cleaned.replace(word, ' ')
        parts = [p for p in cleaned.replace(',', ' ').split() if p]
        if len(parts) != 1:
            return None
        try:
            value = float(parts[0])
        except ValueError:
            return None
        return value if 0 < value < 1000000 else None

    def _handoff_to_dm(self):
        """Kept as a name, not as a behaviour.

        The whole conversation stays in the group now. This used to message
        the customer privately and arm the tracker; anything still calling it
        gets the in-group continuation instead, so no code path can quietly
        reopen a private chat.
        """
        self.ensure_one()
        return self._ask_quantity()

    def _handoff_to_dm_legacy(self):
        """Move the agreed deal into a one-to-one chat with the buyer.

        Quantity, name, address and payment have no business being posted to a
        group: everyone in it would see where this customer lives and what they
        pay. The price was public because the group asked for it; the order is
        not.

        The DM goes to `requester_phone` - the number behind the @lid of the
        person who actually bargained, not the group and not whoever spoke
        last - so the quotation and the private chat are the same customer.

        From here the tracker's own engine owns the conversation. Seeding a
        `quantity_ask` row at the agreed price is what hands it over: its next
        step reads that row, asks for quantity, raises the order, then collects
        the delivery address and payment. None of that is reimplemented.
        """
        self.ensure_one()
        # An unlisted enquiry has no product until now. It is created at the
        # moment of acceptance rather than when it was first asked about, so
        # the catalog only ever gains things a vendor priced and a customer
        # agreed to buy - abandoned enquiries leave nothing behind.
        if not self.product_id:
            self._create_product_from_enquiry()
        product = self.product_id
        price = self.agreed_price or self.quoted_price

        if self.requester_is_lid or not self.requester_phone:
            # No number behind the alias: we cannot open a private chat, and
            # asking for an address in the group is not an acceptable fallback.
            self._say(_("Great - *%(price).2f* it is. \U0001F91D\n\nPlease "
                        "message us directly and we'll take your details and "
                        "finish the order.", price=price))
            self.state = 'handed_off'
            return True

        employee_session = self.group_id.employee_session_id
        conversation = self.conversation_id or self._ensure_conversation()
        AutoReply = self.env['wa.auto.reply'].sudo()

        detail = _(
            "Hi! Following up on *%(group)s* \U0001F447\n\n"
            "\U0001F4E6 *%(product)s*\n%(availability)s\n"
            "\U0001F4B0 *Agreed price:* %(price).2f\n\n"
            "How many do you need? Reply with a number and I'll raise your "
            "order.",
            group=self.group_id.name,
            product=product.name if product else (self.ai_search_term or ''),
            availability=self._availability_line(),
            price=price)

        guard = self.env['sa.outbox.guard'].sudo()
        trigger = self.env.context.get('sa_trigger_msg') or self.id
        if not guard.claim('%s|dm|%s|%s' % (trigger, self.requester_phone,
                                            detail)):
            _logger.info("Sales Automation: already opened the private chat "
                         "with %s for this message", self.requester_phone)
            return True

        # Keyed on the enquiry, not the message, and this is the difference
        # that matters. `state = 'handed_off'` is the ordinary guard against
        # handing the same deal over twice, but it is written inside this
        # transaction - and on 1 Sep this one hit SERIALIZATION_FAILURE two
        # seconds after sending, so the state was rolled back while the
        # WhatsApp message stayed sent. The next tap read the enquiry as still
        # `quoted` and handed it over again: three private chats and three
        # "Perfect - I've messaged you privately" in the group, ten seconds
        # apart.
        #
        # The guard table is written on its own connection and committed
        # immediately, so it is the one record of "this already happened" that
        # a rollback cannot take back. Claimed here rather than at the top of
        # the method so that a failure before this point does not consume the
        # only attempt.
        if not guard.claim('handoff|%s' % self.id, 900):
            _logger.info("Sales Automation: enquiry %s has already been handed "
                         "over - not doing it again", self.id)
            self.state = 'handed_off'
            return True
        try:
            if product:
                AutoReply._send_product_with_image(
                    employee_session, self.requester_phone, product, detail)
            else:
                employee_session.session_id.send_message(
                    self.requester_phone, detail)
        except Exception as err:  # noqa: BLE001
            _logger.error("Sales Automation: could not open a private chat "
                          "with %s: %s", self.requester_phone, err)
            self._say(_("Great - *%(price).2f* it is. \U0001F91D\n\nPlease "
                        "message us directly to finish the order.", price=price))
            self.write({'state': 'handed_off', 'error': str(err)[:2000]})
            return True

        # The seed. `quantity_ask` carrying `offered_price` is the state the
        # tracker resumes from, so the customer's next private message is
        # understood as a quantity against this exact deal.
        AutoReply.create({
            'conversation_id': conversation.id if conversation else False,
            'employee_session_id': employee_session.id,
            'phone': self.requester_phone,
            'customer_message': self.raw_text,
            'reply_message': detail,
            'matched_products': product.name if product else '',
            'selected_product_id': product.id if product else False,
            'reply_type': 'quantity_ask',
            'offered_price': price,
            'status': 'sent',
        })
        self.state = 'handed_off'
        # Only in the group, and only when the customer is not already
        # in the private chat. Since a tapped link answers from their
        # own chat, this note was being sent there - telling someone
        # they had been messaged privately, privately.
        if not self.env.context.get('sa_reply_to'):
            self._say(_("Perfect \U0001F91D - I've messaged you privately to "
                        "take your details and finish the order."))
        _logger.info("Sales Automation: enquiry %s handed to %s privately at "
                     "%.2f", self.id, self.requester_phone, price)
        return True

    def _create_product_from_enquiry(self):
        """Raise a product for something the catalog did not have.

        Everything it needs is already known by this point: what the customer
        called it, what a vendor charges, what we quoted, and who supplied the
        price. The supplierinfo line is the part that compounds - the next
        person to ask finds a real product with a real vendor, and routing
        takes the ordinary category path instead of the unlisted fallback.
        """
        self.ensure_one()
        # Cleaned again here, not only where the term was classified. A
        # product record outlives the conversation that made it and is matched
        # against every enquiry afterwards, so junk that gets in stays in:
        # seven of these were created before the term was being cleaned -
        # "I Need Iphone 16 Pro Max Display", "Do You Have A Wireless Mouse?"
        # - and the first of them was then offered to a customer who had typed
        # "I need #4577". Whatever the classifier or the AI hands over, the
        # catalog gets a product name.
        Classifier = self.env['sa.ai.classifier'].sudo()
        name = (Classifier._sa_clean_term(self.ai_search_term or '')
                or Classifier._sa_clean_term(self.raw_text or '')).strip()
        if not name or not Classifier._sa_term_is_meaningful(name):
            _logger.info("Sales Automation: enquiry %s - %r is not a name to "
                         "put in the catalog", self.id,
                         (self.ai_search_term or self.raw_text or '')[:40])
            return self.env['product.template']

        # The same spacing-blind matcher that finds "Powerbank" for "Power
        # Bank" - so asking twice, worded differently, does not leave two
        # near-identical products behind.
        existing = self._search_products_loose(name)
        if existing:
            self.product_id = existing[0].id
            _logger.info("Sales Automation: enquiry %s reused existing product "
                         "%s rather than creating one", self.id, existing[0].name)
            return existing[0]

        settings = self.env['sa.ai.settings'].sudo().get_settings()
        quote = self.best_quote_id
        cost = self.vendor_price or (quote.price if quote else 0.0)

        values = {
            'name': name[:120].title(),
            'sale_ok': True,
            'purchase_ok': True,
            'is_storable': True,
            'list_price': self.agreed_price or self.quoted_price or 0.0,
            'standard_price': cost,
            'sa_created_from_enquiry': True,
            'sa_enquiry_id': self.id,
        }
        # Always a category: on a database where Odoo's default category was
        # removed the INSERT failed on categ_id NOT NULL (DUBAI_TEST, 30 Sep
        # 2026) and the enquiry looped on the counter screen.
        values['categ_id'] = self._sa_new_product_category(settings).id

        product = self.env['product.template'].sudo().create(values)
        self.product_id = product.id

        # Attach the vendor who actually quoted, at the price they quoted.
        partner = quote.partner_id if quote else False
        if partner:
            self.env['product.supplierinfo'].sudo().create({
                'partner_id': partner.id,
                'product_tmpl_id': product.id,
                'price': cost,
                'delay': quote.delay_days or 0,
            })

        _logger.info("Sales Automation: enquiry %s created product %s "
                     "(cost %.2f, sells %.2f%s)", self.id, product.name, cost,
                     values['list_price'],
                     ', vendor %s' % partner.name if partner else '')
        return product

    def _sa_new_product_category(self, settings=None):
        """The category a product made from an enquiry is filed under.

        The setting first; then Odoo's own default ("All"); then any live
        category; finally one created for the purpose, so a product can
        always be raised and the counter never loops on a failed insert.
        """
        settings = settings or self._settings()
        if settings.new_product_category_id and settings.new_product_category_id.exists():
            return settings.new_product_category_id
        Categ = self.env['product.category'].sudo()
        default = self.env.ref('product.product_category_all', raise_if_not_found=False)
        if default and default.exists():
            return default
        any_categ = Categ.search([], order='id', limit=1)
        if any_categ:
            return any_categ
        return Categ.create({'name': _('WhatsApp Enquiries')})

    def _availability_line(self):
        """Nothing. Kept so the private chat and the group stay in step.

        The delivery time a vendor gives is theirs, not ours, and repeating it
        to a customer turns it into our promise. It stays on the vendor quote,
        where the person fulfilling the order can see it.
        """
        self.ensure_one()
        if self.stock_status == 'in_stock':
            return _("📦 In stock")
        # No delivery date. The vendor's lead time is theirs,
        # and repeating it makes it our promise instead.
        return ''

    QTY_OTHER = '✏️ Other amount'

    def _sa_ask_qty_poll(self, body):
        """How many, as one tap: 1 to 6, or Other amount (then typed).
        Owner, 8 Oct 2026: "nothing should be typed". A tapped "3" arrives as
        the text "3", which `_parse_quantity` already reads."""
        self.ensure_one()
        opts = [{'id': 'sa_qty_%d' % n, 'title': str(n)} for n in range(1, 7)]
        opts.append({'id': 'sa_qty_other', 'title': self.QTY_OTHER})
        self.state = 'awaiting_qty'
        return self._ask(body, opts)

    def _sa_is_qty_other(self, text):
        import re
        return re.sub(r'[^a-z]', '', (text or '').lower()) in ('otheramount', 'other', 'custom')

    def _ask_quantity(self, repeat=False):
        self.ensure_one()
        price = self.agreed_price or self.quoted_price
        if self.qty and not repeat:
            return self._ask_order_confirm()
        # A poll now (1-6 + Other); `_ask` adds the deadline note itself.
        if repeat:
            self._sa_ask_qty_poll(_("\U0001F522 How many do you need at *%(price).2f*? "
                                    "Tap one \U0001F447", price=price))
        else:
            self._sa_ask_qty_poll(_("Great - *%(price).2f* it is. \U0001F91D\n\n"
                                    "\U0001F522 How many do you need? Tap one \U0001F447",
                                    price=price))
        self.state = 'awaiting_qty'
        return True

    def _ask_quantity_typed(self, repeat=False):
        """The old typed question, kept for reference and for overrides."""
        self.ensure_one()
        price = self.agreed_price or self.quoted_price
        if self.qty and not repeat:
            return self._ask_order_confirm()
        note = self._sa_deadline_note()
        # Asked as a plain number, here in the group. This used to offer a
        # wa.me link with `#HG QTY 1` prefilled, which moved the customer into
        # a private chat the moment they tapped it. A bare reply is enough:
        # `awaiting_qty` is in `_active_deal`, so the number is matched to the
        # sender's own deal, and `_parse_quantity` still accepts `#HG QTY 2`
        # from anyone who would rather name the enquiry.
        if repeat:
            # Worded differently from the first ask on purpose: the gateway
            # drops a message identical to one sent minutes earlier, and the
            # repeat used to be the same bytes - CHANGE QUANTITY answered
            # with silence (Ref 2J, 30 Sep 2026).
            self._say(_("\U0001F522 How many do you need at *%(price).2f*? "
                        "Reply with just the number - like *2*%(note)s",
                        price=price, note=('\n\n%s' % note) if note else ''))
        else:
            self._say(_("Great - *%(price).2f* it is. \U0001F91D\n\nHow many do "
                        "you need?\n\n\U0001F522 *Just reply with the number* "
                        "\u2014 like *2*%(note)s", price=price,
                        note=('\n\n%s' % note) if note else ''))
        self.state = 'awaiting_qty'
        return True

    def _ask_order_confirm(self):
        self.ensure_one()
        price = self.agreed_price or self.quoted_price
        qty = self.qty or 1
        name = self.product_id.name or self.ai_search_term or _("this item")
        self._ask(
            _("\U0001F4CB *Order summary*\n\n%(product)s\n%(qty)s x "
              "%(price).2f\n*Total: %(total).2f*",
              product=name, qty=int(qty) if float(qty).is_integer() else qty,
              price=price, total=price * qty),
            [{'id': 'sa_yes', 'title': _('CONFIRM')},
             {'id': 'sa_no', 'title': _('CHANGE')}])
        self.state = 'awaiting_order_confirm'
        return True

    @staticmethod
    def _sa_lines_in_stock(order):
        """Every storable line can be served from free stock right now. The
        enquiry's product is a template; `free_qty` lives on the variant, so
        the order's own lines are what is checked."""
        try:
            lines = order.order_line.filtered(lambda l: not l.display_type and l.product_id)
            storable = lines.filtered(lambda l: getattr(l.product_id, 'is_storable', False))
            if not storable:
                return True
            for l in storable:
                free = l.product_id.sudo().with_company(order.company_id).free_qty or 0.0
                if float(free) < float(l.product_uom_qty or 0.0):
                    return False
            return True
        except Exception:  # noqa: BLE001 - when in doubt, buy in first
            return False

    def _place_order(self):
        """Turn the agreed deal into a quotation, and post its number.

        The tracker's own `_create_sale_order` is reused rather than a second
        implementation: it already finds or creates the partner, picks the
        variant, sets the company and prices the line. Passing `unit_price`
        makes it honour what was actually negotiated instead of re-reading the
        catalog.
        """
        self.ensure_one()
        product = self.product_id
        if not product:
            self._say(_("I could not raise an order for this one - somebody "
                        "will follow up. \U0001F64F"))
            return self._drop('no_product')

        conversation = self.conversation_id or self._ensure_conversation()
        if not conversation:
            if self.requester_is_lid or not self.requester_phone:
                self._say(_("I need to message you directly to finish the "
                            "order, but WhatsApp is hiding your number here. "
                            "Please message us directly. \U0001F64F"))
                return self._drop('lid_no_dm')
            # The number is known; the shop side is what is missing.
            _logger.error("Sales Automation: enquiry %s cannot be ordered - "
                          "no employee session could be made for group %s",
                          self.id, self.group_id.name)
            self._say(_("Something went wrong raising the order - somebody "
                        "will follow up. \U0001F64F"))
            return self._drop('error')

        # Stock can go between the quote and CONFIRM: read it again, fresh,
        # and refuse only what may not be sold short.
        if not self._assess_availability(product, fresh=True):
            return self._sa_say_unavailable(product)

        price = self.agreed_price or self.quoted_price
        qty = self.qty or 1
        # The order is the group's business's, not whichever company the
        # shared employee session happens to name (S00003: a Test 2 order for
        # NEW COMPANY was raised in My Company, the session's).
        AutoReply = self.env['wa.auto.reply'].sudo()._sa_for_company(
            self._sa_order_company())
        order = AutoReply._create_sale_order(
            self.group_id.employee_session_id, conversation, product, qty,
            self._is_existing_contact(conversation), unit_price=price)
        if order:
            # Back in this request's own environment, so nothing made later
            # in this flow inherits the order company switch.
            order = self.env['sale.order'].sudo().browse(order.id)
        if not order:
            self._say(_("Something went wrong raising the order - somebody "
                        "will follow up. \U0001F64F"))
            return self._drop('error')
        # Another module recomputes the line price from the product on
        # create (S00013: agreed 370.50, line 510.00). The agreed price is the
        # deal, so it is written again once the line exists.
        try:
            for line in order.sudo().order_line.filtered(
                    lambda l: not l.display_type and l.product_id):
                if abs((line.price_unit or 0.0) - float(price)) > 0.005:
                    line.write({'price_unit': price})
                    _logger.info("Sales Automation: %s line price set to the "
                                 "agreed %.2f (was %.2f)", order.name, price,
                                 line.price_unit)
        except Exception as err:  # noqa: BLE001 - the order still stands
            _logger.warning("Sales Automation: could not pin the agreed price "
                            "on %s: %s", order.name, err)

        # Items the customer put in their cart before this one join the same
        # order (sales_automation_confirm/models/sa_cart.py) - before the stock
        # check, the "Done!" and the details, so all of them see every line.
        self._sa_order_extra_lines(order)

        # The group hears everything; the email bridge's private PDF copy of
        # the order is held back for orders born here.
        if 'auto_wa_sent_at_confirm' in order._fields:
            order.sudo().write({'auto_wa_sent_at_confirm': True})
        # In stock: the order stays a quotation until the payment lands (the
        # payment confirms it and raises the delivery). Not in stock: it is
        # confirmed now so its job can wait at the counter for the goods.
        in_stock = self._sa_lines_in_stock(order)
        if False:  # the signature confirms a not-in-stock order (sa_group_oos)
            try:
                order.sudo().action_confirm()
            except Exception as err:  # noqa: BLE001 - a draft is still a result
                _logger.warning("Sales Automation: could not confirm %s: %s",
                                order.name, err)

        self.write({'order_id': order.id, 'state': 'order_created'})
        product_lines = order.order_line.filtered(lambda l: not l.display_type and l.product_id)
        if len(product_lines) > 1:
            # A cart: every item, and the order's own total.
            done = _("\u2705 Done! Your order *%(ref)s* is placed.\n\n"
                     "%(lines)s\n*Total: %(total).2f*",
                     ref=order.name, lines=self._sa_order_lines_text(order),
                     # Before tax, like the summary just tapped and the
                     # one-item "Done!" - the pay link carries the taxed total.
                     total=order.amount_untaxed)
        else:
            done = _("\u2705 Done! Your order *%(ref)s* is placed.\n\n"
                     "%(qty)s x %(product)s\n*Total: %(total).2f*",
                     ref=order.name, qty=int(qty) if float(qty).is_integer() else qty,
                     product=self._sa_done_item_name(), total=price * qty)
        # In stock: the pay link follows at once, here in the group. Not in
        # stock: the goods are bought in first, and the customer is asked to
        # confirm again when they arrive (see sa_group_stock_confirm).
        # Both cases (29 Sep 2026): the customer's name, address and a
        # read-back with their phone come first, in the group; then the
        # signature; the pay link follows the signature (in stock) or the
        # goods (not in stock). See sa_group_details.py.
        self._say(done)
        self._sa_group_details_start(order)
        if in_stock:
            self.write({'sa_stock_confirmed': True})
        _logger.info("Sales Automation: enquiry %s became %s at %.2f x %s",
                     self.id, order.name, price, qty)
        return True

    def _sa_done_item_name(self):
        """What the one-item "Done!" calls the product. The confirmation
        module names the exact variant the customer picked."""
        self.ensure_one()
        return self.product_id.name

    def _sa_order_extra_lines(self, order):
        """More lines for the order `_place_order` just raised. Nothing here:
        the confirmation module's cart adds the items waiting in it."""
        return False

    # Words that mean stop, as opposed to "no" - which at the order summary
    # means "change something". Conflating the two is why CANCEL there moved
    # the deal to negotiating and asked for a price instead of ending it.
    _SA_CANCEL_WORDS = ('cancel', 'stop', 'quit', 'exit', 'nevermind',
                        'never mind', 'abort', 'forget it', "don't want",
                        'dont want', 'not needed', 'no need')

    @api.model
    def _sa_is_cancel(self, text):
        """True when the customer is asking to stop, however they phrase it.

        Scanned rather than matched on the first of three words: "please
        cancel my order" is four words and was reaching the bargaining
        fall-through, leaving the deal open.
        """
        stripped = (text or '').strip().lower().strip('.!*? ')
        if not stripped or len(stripped) > 60:
            return False
        if stripped == 'sa_no':
            return False        # the poll's own no - the caller decides
        return any(word in stripped for word in self._SA_CANCEL_WORDS)

    def _sa_cancel_deal(self):
        """Stop the deal, and stop everything it has already set in motion.

        `_drop_deal` only ever changed this record's state. An order created
        before the cancel survived it, and so did the tracker seed row, which
        is what turns the customer's next number in a private chat into a sale
        order - so cancelling in the group and then answering the quantity
        question still produced a quotation.
        """
        self.ensure_one()
        order = self.order_id
        if order and order.state not in ('cancel', 'done'):
            try:
                order.sudo().action_cancel()
                _logger.info("Sales Automation: enquiry %s cancelled order %s",
                             self.id, order.name)
            except Exception as err:  # noqa: BLE001 - never leave the customer
                _logger.warning(       # without an answer over a workflow error
                    "Sales Automation: could not cancel %s (%s)",
                    order.name, err)
        self._sa_clear_tracker_seed()
        self._say(_("No problem \U0001F642 - that's cancelled. Send the "
                    "product name again whenever you need it."))
        self._drop('declined')
        return True     # handled: never let a cancel start a new enquiry

    def _sa_clear_tracker_seed(self):
        """Drop the row that would otherwise finish the order without us."""
        self.ensure_one()
        if not self.conversation_id:
            return
        seeds = self.env['wa.auto.reply'].sudo().search([
            ('conversation_id', '=', self.conversation_id.id),
            ('reply_type', 'in', ('quantity_ask', 'price_negotiate',
                                  'await_address', 'await_delivery')),
        ], order='id desc', limit=5)
        if seeds:
            seeds.write({'reply_type': 'general'})

    def _drop_deal(self):
        self.ensure_one()
        self._say(_("No problem \U0001F642 - just send the product name again "
                    "whenever you need it."))
        self._drop('declined')
        return True

    @api.model
    def _read_yes_no(self, text, numbered=True):
        """True, False, or None when the message is neither.

        `numbered=False` where a bare digit cannot mean yes. The details
        summary offers YES, NO and CANCEL - no numbers - and a customer who
        typed "1" meaning one unit had it read as "yes, confirm" and a
        quotation raised on the spot.
        """
        stripped = (text or '').lower().strip(' .!?')
        # A tapped list row arrives as the rowId set when sending - the
        # gateway's _text_of returns selectedRowId, not the visible label.
        if stripped == 'sa_yes':
            return True
        if stripped == 'sa_no':
            return False
        # send_buttons falls back to a numbered list when Evolution refuses
        # tappable buttons, so the answer can arrive as "1" or "2".
        if numbered:
            if stripped == '1':
                return True
            if stripped == '2':
                return False
        words = stripped.split()
        if not words or len(words) > 3:
            return None
        if words[0] in ('accept', 'confirm', 'ok'):
            return True
        if words[0] in ('cancel', 'change', 'stop'):
            return False
        if words[0] in _YES:
            return True
        if words[0] in _NO:
            return False
        return None

    @api.model
    def _company_for(self, group):
        """Whose books this enquiry belongs to.

        The group first: one WhatsApp session serves every group, so taking it
        from the session gave every group the same company however many
        businesses were on the database. The session is kept as the fallback
        so a group with nothing set behaves exactly as it did before.
        """
        employee_session = group.employee_session_id
        return (group.company_id
                or employee_session.auto_reply_company_id
                or group.session_id.company_id
                or self.env.company)

    def _sa_order_company(self):
        """The company a sale order for this enquiry is raised in: the
        group's. The finder's stock company is only the shelf the goods come
        from - the shop moves the delivery there at Accept - so it does not
        decide whose books the sale is in."""
        self.ensure_one()
        return self._company_for(self.group_id)

    # ==========================================================
    # The flow
    # ==========================================================
    def _process(self):
        self.ensure_one()
        group = self.group_id

        # ---- 1. Is this even an enquiry? ----
        verdict = self.env['sa.ai.classifier'].sudo().classify(
            self.raw_text, use_ai=group.ai_enabled)
        self.write({
            'ai_is_product': verdict['is_product'],
            'ai_search_term': verdict['search_term'],
            'ai_confidence': verdict['confidence'],
            'ai_source': verdict['source'],
            'qty': verdict['quantity'] or 0.0,
        })
        # Our own shelf label is not small talk. "Computer / Computer Parts"
        # was read as chatter with 0.95 confidence and dropped in silence -
        # the customer named a category from this very catalogue and got no
        # answer at all. The model cannot know the shop's vocabulary; the
        # category tree is exactly that vocabulary, so it overrules the model
        # here. What follows sends it to the finder, which asks which one.
        if not verdict['is_product'] and self._sa_looks_like_category(self.raw_text):
            _logger.info("Sales Automation: enquiry %s - %r is one of our "
                         "categories, answering instead of ignoring it",
                         self.id, (self.raw_text or '')[:40])
            verdict = dict(verdict, is_product=True,
                           search_term=(verdict['search_term']
                                        or (self.raw_text or '').strip()),
                           confidence=max(verdict['confidence'],
                                          group.min_confidence or 0.0))
            self.write({'ai_is_product': True,
                        'ai_search_term': verdict['search_term']})

        if not verdict['is_product']:
            # Before writing it off: a misspelling reads as chatter to every
            # keyword matcher there is. "Samsng Galxy S23" was dropped in
            # silence, and the customer had no way of knowing anyone had seen
            # it. So the words are snapped to the catalog's spelling and the
            # ordinary path runs again - which means every rule about brands
            # and parts still applies, instead of a separate guess that had
            # none of them and offered a back case for a phone.
            #
            # Only when the AI could not be reached: with it up, the model
            # corrects the spelling itself and never gets here.
            fixed = self._sa_correct_spelling(self.raw_text)
            if not fixed:
                # Not a near-miss of anything we sell. Stay quiet: most
                # messages in a sales group really are ordinary conversation.
                return self._drop('not_product')

            _logger.info("Sales Automation: enquiry %s - read %r as %r",
                         self.id, (self.raw_text or '')[:40], fixed[:40])
            self.ai_search_term = fixed
            self._say(_("I couldn't find *%(typed)s* - I've read that as "
                        "*%(fixed)s*.",
                        typed=(self.raw_text or '').strip()[:40], fixed=fixed))
            verdict = dict(verdict, is_product=True, search_term=fixed,
                           confidence=max(verdict['confidence'],
                                          group.min_confidence or 0.0))
        if verdict['confidence'] < (group.min_confidence or 0.0):
            return self._drop('low_confidence')

        if not group.employee_session_id:
            # The constraint on sa.sales.group stops this being reachable
            # through the UI, but a group enabled by data import could get here.
            return self._drop('no_employee_session')

        # A generic word - "headphone" - is not something to guess at or to
        # put to a supplier. The finder walks the customer to one model in
        # their own chat; it declines (False) when there is nothing to offer.
        if self._finder_eligible() and self._finder_start():
            return True

        # The finder declined. Usually that means the model was rate limited
        # or nothing in the catalogue matched - neither of which makes a
        # category worth putting to a supplier. Asking the customer costs a
        # message; asking a vendor "best price for Computer Parts" costs the
        # relationship. The ref keeps the text varying, because the gateway
        # drops a message identical to one sent minutes ago.
        if not self._sa_specific_enough():
            term = (self.ai_search_term or self.raw_text or '').strip()
            _logger.info("Sales Automation: enquiry %s - %r is too broad and "
                         "the finder had nothing to offer; asking the "
                         "customer rather than a supplier", self.id, term[:40])
            self._say(_("Which *%(term)s* do you need? \U0001F914\n\n"
                        "Tell me the brand or the model and I'll get you a "
                        "price.\n\n_Ref %(ref)s_",
                        term=term, ref=self.ref_code or self.id))
            return self._drop('need_clarification')

        # ---- 2. What are they asking for? ----
        term = verdict['search_term'] or self.raw_text
        products = self.env['wa.auto.reply'].sudo()._search_products(
            term, group.max_products or 5)
        if not products:
            products = self._search_products_loose(term)
        # Another company's product would be quoted from a price list this
        # business does not own and reserved against stock it does not have.
        # A product with no company belongs to all of them, which is how most
        # catalogues are set up.
        company = self._company_for(group)
        products = products.filtered(
            lambda prod: not prod.company_id or prod.company_id == company)
        products = products.filtered(
            lambda prod: self._sa_match_is_plausible(prod, term))

        # Offering something the same person turned down minutes ago is worse
        # than offering nothing: it reads as not having listened. One tester
        # was asked "Did you mean SATEST Laptop Charger?" three times running
        # and answered NO to every one.
        refused = self._sa_recently_rejected()
        if refused:
            still_open = products.filtered(lambda prod: prod.id not in refused)
            if still_open != products:
                _logger.info("Sales Automation: enquiry %s - dropped %d "
                             "already-rejected suggestion(s)", self.id,
                             len(products) - len(still_open))
            products = still_open
        if products:
            self.product_id = products[0].id

        # ---- 3. Confirm before spending anyone's time ----
        # Keyword matching is loose - it matches on substrings, so "Single"
        # matches "in" - and asking vendors to price the wrong product wastes
        # their goodwill as well as ours.
        # Only a *matched* product is worth confirming. With nothing matched
        # there is no question to ask - repeating the customer's own words back
        # at them adds a round trip and advertises that the assistant did not
        # recognise the request. It just goes and gets a price.
        # More than one product fits, and the keyword matcher has no real way
        # to rank them - "battery 50000" scores the same against a product
        # called "battery" as against "Battery 5000mAh". Picking one and asking
        # "did you mean this?" hides that ambiguity behind a confident-looking
        # question. Show what was found and let the customer say which.
        if len(products) > 1 and group.require_confirmation:
            return self._ask_choice(products)
        if group.require_confirmation and self.product_id:
            return self._ask_confirmation()
        return self._on_confirmed()

    @api.model
    def _search_products_loose(self, text):
        """Catalog search that ignores spacing and punctuation.

        The tracker's search matches on words, so "Powerbank" never finds
        "Power Bank" - and when the AI is unavailable that search is the only
        one running, which is exactly when a near miss costs a sale. Comparing
        with the spaces taken out catches the whole family of these: powerbank,
        power-bank, USB C vs USB-C, 20000mah vs 20000 mAh.

        Run only after the ordinary search has failed, so the normal path keeps
        its ordering and this never slows it down.
        """
        squashed = ''.join(c for c in (text or '').lower() if c.isalnum())
        if len(squashed) < 4:
            return self.env['product.template']

        Product = self.env['product.template'].sudo()
        hits = Product
        for product in Product.search([('sale_ok', '=', True),
                                       ('active', '=', True)] + self._sa_unsellable_domain(), limit=2000):
            name = ''.join(c for c in (product.name or '').lower() if c.isalnum())
            if not name:
                continue
            if squashed in name or name in squashed:
                hits |= product
        if hits:
            _logger.info("Sales Automation: loose match found %s for %r",
                         hits[0].name, (text or '')[:40])
        return hits[:5]

    def _reject_match(self):
        """They said no to our guess. Source what they actually asked for.

        The product we offered was wrong, so it is cleared - and with nothing
        matched the enquiry follows the unlisted path, which asks vendors using
        the customer's own wording. That is very often exactly the item: a
        variant the catalog has never carried.
        """
        self.ensure_one()
        _logger.info("Sales Automation: enquiry %s - %r was rejected, sourcing "
                     "%r instead", self.id,
                     self.product_id.name, (self.ai_search_term or '')[:40])
        if self.product_id:
            self.rejected_product_ids = [(4, self.product_id.id)]
        self.product_id = False
        return self._on_confirmed()

    def _sa_correct_spelling(self, text):
        """The message with each word snapped to the nearest catalog word.

        Returns '' when nothing was worth correcting, so the caller can tell a
        typo from ordinary conversation.

        Word level, not product level. Guessing a whole product from two
        near-matching words is how "Samsng Galxy S23" pointed at "Samsung
        Galaxy Back Case" - a phone answered with a case. Correcting the words
        and re-running the ordinary matcher keeps every rule about brands and
        parts in force.

        Two corrections are required. One lucky near-miss is noise, and short
        tokens are left alone entirely: "S23" is two edits from "S24", which is
        a different phone, not a typo.
        """
        self.ensure_one()
        import difflib
        words = (text or '').split()
        if len(words) < 2:
            return ''
        vocabulary = self._sa_catalog_vocabulary()
        if not vocabulary:
            return ''

        rebuilt, corrections, known = [], 0, 0
        for word in words:
            bare = word.strip('.,!?:;()*_-/').lower()
            if len(bare) < 4:
                rebuilt.append(word)          # "Not", "Pr", "S23" - leave alone
                continue
            if bare in vocabulary:
                rebuilt.append(word)
                known += 1
                continue
            near = difflib.get_close_matches(bare, vocabulary, n=1, cutoff=0.8)
            if near:
                # Keep the shape the customer typed, so the message we read
                # back to them looks like a product name and not a slug.
                fixed = near[0].capitalize() if word[:1].isupper() else near[0]
                rebuilt.append(fixed)
                corrections += 1
            else:
                rebuilt.append(word)
        # One correction is enough when the rest of the line is already words
        # we sell: "Redmi Not 13 Pr Camra" only has one word long enough to
        # correct, because "Not" and "Pr" are too short to tell from real
        # words. What makes it a typo rather than chatter is that "Redmi" is
        # ours too. Two pieces of catalog evidence, at least one of them a
        # correction.
        return ' '.join(rebuilt) if corrections and (corrections + known) >= 2 else ''

    @api.model
    def _sa_catalog_vocabulary(self):
        """Every word of four letters or more that appears in a product name."""
        found = set()
        for name in self.env['product.template'].sudo().search_read(
                [('sale_ok', '=', True)], ['name'], limit=2000):
            for word in self._sa_words(name.get('name') or ''):
                if len(word) >= 4:
                    found.add(word)
        return found

    def _sa_match_is_plausible(self, product, term):
        """Do the request and the product actually describe the same thing?

        The keyword matcher scores on any shared token, so "i need Sony
        Bluetooth Speaker" came back as "Did you mean Sony 64Gb Usb Flash
        Drive?" on the strength of the word Sony alone. Asking that wastes the
        customer's turn and makes the assistant look like it is guessing.

        Two words have to line up before a product is worth putting to them -
        unless they only gave us one, in which case one is all there is.
        """
        self.ensure_one()
        wanted = self._sa_words(term)
        if not wanted:
            return True
        have = self._sa_words(product.name or '')
        needed = min(2, len(wanted))
        if len(wanted & have) < needed:
            return False

        Classifier = self.env['sa.ai.classifier'].sudo()

        # Different manufacturers are different products, whatever else the
        # words have in common. "Google Pixel 8 Pro Camera" was answered with
        # "Oppo Reno 11 Pro Camera" on the strength of "pro" and "camera".
        brands = Classifier._sa_brand_vocabulary()
        asked_brand, have_brand = wanted & brands, have & brands
        # Both sides had to name a brand before this could refuse anything, so
        # a product carrying no brand at all was never checked: "HP Pavilion
        # Laptop Charger" was answered with "SATEST Laptop Charger" three
        # times in four minutes, on "laptop" and "charger" alone. Naming a
        # brand is the customer being specific, and an unbranded product does
        # not answer it - a charger for an HP Pavilion is not any charger.
        if asked_brand and not (asked_brand & have_brand):
            return False

        # Parts have to agree in both directions. Checking only what the
        # customer said let "Samsung Galaxy S23" - a phone - be answered with
        # "Samsung Galaxy Back Case", because the request named no part at all
        # and so nothing was compared.
        parts = Classifier._sa_part_vocabulary()

        # Singular and plural are the same part. "JBL Tune 510BT headphone"
        # named the part the product calls "Headphones" and was refused.
        def stem(words):
            return {w[:-1] if w.endswith('s') and len(w) > 3 else w
                    for w in words}
        asked_part, have_part = stem(wanted & parts), stem(have & parts)
        if asked_part and have_part and not (asked_part & have_part):
            return False
        if asked_part and not have_part:
            return False
        if have_part and not asked_part:
            # The product names a part the customer left out. That is not a
            # different product when everything they *did* say is in its name:
            # "JBL Tune 510BT" is the customer typing the model and skipping
            # the noun, and it was answered with a vendor hunt for an item
            # sitting in stock. It still refuses "Samsung Galaxy S23" against
            # "Samsung Galaxy Back Case" - "s23" is not in that name.
            if not (wanted <= have):
                return False
        return True

    def _sa_recently_rejected(self):
        """Products this person has said no to while this enquiry is warm.

        Their own rejections and those on their recent enquiries, because a
        repeat of the same question arrives as a *new* enquiry - which is
        exactly the case that produced the same wrong suggestion three times.
        """
        self.ensure_one()
        domain = [('group_id', '=', self.group_id.id),
                  ('rejected_product_ids', '!=', False),
                  ('write_date', '>=', self._sa_still_warm())]
        if self.requester_phone:
            domain.append(('requester_phone', '=', self.requester_phone))
        elif self.requester_lid:
            domain.append(('requester_lid', '=', self.requester_lid))
        else:
            return set()
        past = self.sudo().search(domain, order='id desc', limit=5)
        return set(past.rejected_product_ids.ids)

    @api.model
    def _sa_words(self, text):
        """Meaningful lowercase words, punctuation and filler removed."""
        out = set()
        for word in (text or '').lower().split():
            word = word.strip('.,!?:;()*_-/')
            if len(word) > 1 and word not in self._SA_FILLER:
                out.add(word)
        return out

    def _ask_choice(self, products):
        """Offer the candidates and let the customer point at one.

        Capped at three: a poll with eight near-identical product names is
        harder to answer than the question it replaces. The last option is
        always a way out, because the right answer is often none of them.
        """
        self.ensure_one()
        shortlist = products[:3]
        self.candidate_product_ids = [(6, 0, shortlist.ids)]
        options = [{'id': 'sa_p%s' % p.id, 'title': p.name[:90]}
                   for p in shortlist]
        options.append({'id': 'sa_none', 'title': _('None of these')})
        self._ask(_("Which one do you need?"), options)
        self.state = 'awaiting_confirm'
        return True

    def _match_candidate(self, text):
        """Which offered product the customer picked.

        Returns the product, False for "none of these", or None when the reply
        was not about the choice at all.
        """
        self.ensure_one()
        stripped = (text or '').strip().lower()
        if not stripped or not self.candidate_product_ids:
            return None
        if stripped in ('sa_none', 'none of these', 'none', 'other'):
            return False
        for product in self.candidate_product_ids:
            if stripped == 'sa_p%s' % product.id:
                return product
            if stripped == (product.name or '').strip().lower():
                return product
        # A number, as the numbered fallback would send.
        if stripped.isdigit():
            index = int(stripped) - 1
            if 0 <= index < len(self.candidate_product_ids):
                return self.candidate_product_ids[index]
            if index == len(self.candidate_product_ids):
                return False
        return None

    def _on_candidate_chosen(self, product):
        """Take the customer's pick, or source what they actually asked for."""
        self.ensure_one()
        if not product and self.candidate_product_ids:
            # "None of these" turns down every one of them, not just the first.
            self.rejected_product_ids = [
                (4, pid) for pid in self.candidate_product_ids.ids]
        self.candidate_product_ids = [(5, 0, 0)]
        if not product:
            # "None of these" says the catalog is wrong, not that the customer
            # is. When they already named something specific - "65W charger",
            # "vivo V30 Back Panel" - the words are good enough to put in front
            # of a supplier, and asking them to type it again ends the enquiry
            # for no reason. Seven enquiries in one afternoon died exactly
            # there.
            #
            # Only a vague one-word request goes back for clarification: "None
            # of these" against "battery" leaves nothing to source that would
            # not produce the same wrong shortlist again.
            if self._sa_specific_enough():
                _logger.info("Sales Automation: enquiry %s - none of the "
                             "offered products fitted; sourcing %r as asked",
                             self.id, (self.ai_search_term or '')[:40])
                self.product_id = False
                return self._on_confirmed()
            _logger.info("Sales Automation: enquiry %s - none of the offered "
                         "products fitted and %r is too vague to source; asked "
                         "for the exact name", self.id,
                         (self.ai_search_term or '')[:40])
            self._say(_("No problem \U0001F642 - please send me the exact "
                        "product name or model, and I'll check it for you."))
            return self._drop('need_clarification')
        self.product_id = product.id
        _logger.info("Sales Automation: enquiry %s - customer chose %s",
                     self.id, product.name)
        return self._on_confirmed()

    # Filler that carries no product meaning. "i need a charger" names one
    # thing, not four, and counting the padding would send "battery" to a
    # supplier as though it were a model number.
    _SA_FILLER = frozenset("""
    i we you a an the is are do does have has need want any some please
    me my our your for of in on at to and or kindly send give tell price
    rate cost quote available stock pcs pc nos qty quantity urgent asap
    """.split())

    # Units and suffixes that pin an item down on their own: "65W", "10000mAh",
    # "128GB", "15.6 inch". A token carrying one of these is a specification,
    # not a category.
    _SA_SPEC_UNITS = ('w', 'kw', 'mah', 'ah', 'gb', 'tb', 'mb', 'mm', 'cm',
                      'inch', 'in', 'kg', 'ml', 'ltr', 'l', 'v', 'hz', 'mp')

    @staticmethod
    def _sa_categ_norm(text):
        """Lowercase, slashes to spaces, whitespace collapsed.

        So "Computer / Computer Parts", "computer/computer parts" and
        "Computer Parts" all reduce to something comparable. A customer who
        copies a category out of a catalogue keeps the separator; one who
        types it does not.
        """
        return ' '.join((text or '').lower().replace('/', ' ').split())

    def _sa_looks_like_category(self, text):
        """True when the customer typed one of our own category names.

        A customer who types "Computer Parts" has named a shelf, not a product,
        and no supplier can quote a shelf. This is the cheapest possible check
        and needs no AI: the category tree is already the shop's own vocabulary
        for "this is a group of things, not a thing".
        """
        self.ensure_one()
        probe = self._sa_categ_norm(text)
        if not probe:
            return False
        names = set()
        for categ in self.env['product.category'].sudo().search([]):
            # The whole path as well as each of its segments: "Computer /
            # Computer Parts" is as much a shelf as "Computer Parts".
            candidates = [categ.name or '', categ.complete_name or '']
            candidates += (categ.complete_name or '').split('/')
            for part in candidates:
                part = self._sa_categ_norm(part)
                if not part:
                    continue
                names.add(part)
                # "Chargers" typed as "charger".
                if len(part) > 4 and part.endswith('s') and not part.endswith('ss'):
                    names.add(part[:-1])
        return probe in names or self._finder_singular(probe) in names

    def _sa_has_spec_token(self, real):
        """A model number or a measured spec - "ATH-M70x", "65W", "128GB"."""
        for word in real:
            if any(ch.isdigit() for ch in word) and any(ch.isalpha() for ch in word):
                return True
            if word.isdigit():
                continue
            digits = word.rstrip(''.join(self._SA_SPEC_UNITS))
            if digits and digits.isdigit() and digits != word:
                return True
        return False

    def _sa_specific_enough(self):
        """Is the request worth putting in front of a supplier as written?

        The old bar was two real words, which let every two-word category
        through: "Computer Parts", "mobile phone" and "hp laptop" were all
        forwarded to suppliers as price checks. A supplier cannot price a
        category, so the answer came back wrong or not at all - and on this
        database "Hp Laptop" carries an iPhone parts supplier, so it came back
        wrong.

        Three layers, cheapest first. Only the last one costs an API call, and
        it is cached and fails open, so a quota outage restores the old
        behaviour rather than stalling every enquiry.
        """
        self.ensure_one()
        text = (self.ai_search_term or self.raw_text or '').lower()
        words = [w.strip('.,!?:;()*_-/') for w in text.split()]
        real = [w for w in words if w and w not in self._SA_FILLER]

        # One word was never enough, and still is not.
        if len(real) < 2:
            return False
        # Our own shelf labels: free, certain, no AI.
        if self._sa_looks_like_category(' '.join(real)):
            _logger.info("Sales Automation: enquiry %s - %r is a category, "
                         "narrowing instead of sourcing", self.id, text[:40])
            return False
        # A model number or a measured spec settles it the other way.
        if self._sa_has_spec_token(real):
            return True
        # Everything left is ambiguous prose - ask the model.
        verdict = self.env['sa.ai.classifier'].sudo().is_quotable(
            ' '.join(real))
        if verdict is None:
            return True            # unreachable model: behave as before
        if not verdict:
            _logger.info("Sales Automation: enquiry %s - %r not quotable as "
                         "written, narrowing instead of sourcing",
                         self.id, text[:40])
        return verdict

    def _ask_confirmation(self):
        self.ensure_one()
        # Only reached with a product: an unmatched enquiry skips
        # confirmation entirely, so no branch here names the catalog.
        question = _("Did you mean *%(product)s*?",
                     product=self.product_id.name)
        self._ask(question, [
            {'id': 'sa_yes', 'title': 'YES', 'subtitle': _("Get me a price")},
            {'id': 'sa_no', 'title': 'NO', 'subtitle': _("That's not it")},
        ])
        self.state = 'awaiting_confirm'
        return True

    def _sourcing_vendors(self):
        """The vendors to ask for a price on this enquiry.

        Two sources, both already filled in by somebody: the Vendors list on
        the product's category (walked up to the parents) and the vendors on
        the product's own Purchase tab. The union is asked, so a category-wide
        supplier and a product-specific one are both covered without anyone
        keeping two lists in step.

        Vendors with no phone number are skipped and logged rather than
        silently counted as asked.
        """
        self.ensure_one()
        product = self.product_id
        partners = self.env['res.partner']
        if product and product.categ_id:
            partners |= product.categ_id._sa_vendors_for_sourcing()
        if product:
            partners |= product.seller_ids.mapped('partner_id')
        if not product:
            partners |= self._unlisted_vendors()
        # The vendor's ticks (WhatsApp / WeChat) when the WeChat module is
        # installed; the phone alone otherwise.
        reachable = partners.filtered(
            lambda p: p._sa_sourcing_reachable() if hasattr(p, '_sa_sourcing_reachable')
            else (p.phone or '').strip())
        missing = partners - reachable
        if missing:
            _logger.info("Sales Automation: %d vendor(s) have no phone and "
                         "were not asked: %s", len(missing),
                         ', '.join(missing.mapped('name'))[:200])
        return reachable

    def _minutes_since_broadcast(self):
        """Minutes since the vendors were asked, or 0 if they were not.

        Called from `sa.vendor.quote` when a price arrives, to record how long
        that vendor took. It went missing once and the failure was quiet in the
        worst way: the webhook caught the AttributeError, the vendor's price
        fell through to the tracker, and the supplier was told "Sorry, I could
        not find matching products".
        """
        self.ensure_one()
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        window = settings.sourcing_window_minutes or 0
        if not self.sourcing_deadline or not window:
            return 0
        asked_at = fields.Datetime.subtract(
            self.sourcing_deadline, minutes=window)
        delta = fields.Datetime.now() - asked_at
        return max(0, int(delta.total_seconds() // 60))

    def _open_twin(self):
        """An enquiry from the same person for the same thing, still open."""
        self.ensure_one()
        domain = [
            ('id', '!=', self.id),
            ('group_id', '=', self.group_id.id),
            ('state', 'in', ('sourcing', 'awaiting_vendor_pick',
                             'quoted', 'negotiating',
                             'awaiting_qty', 'awaiting_order_confirm')),
        ]
        if self.requester_phone:
            domain.append(('requester_phone', '=', self.requester_phone))
        elif self.requester_lid:
            domain.append(('requester_lid', '=', self.requester_lid))
        else:
            return self.browse()
        if self.product_id:
            domain.append(('product_id', '=', self.product_id.id))
        else:
            term = (self.ai_search_term or self.raw_text or '').strip()
            if not term:
                return self.browse()
            domain += [('product_id', '=', False),
                       ('ai_search_term', '=ilike', term)]
        return self.sudo().search(domain, order='id desc', limit=1)

    # ----------------------------------------------------------
    # Held at the counter
    # ----------------------------------------------------------
    def _sa_vendor_candidates(self):
        """(vendors the shopkeeper may pick from, product-has-no-category).

        Vendors are routed by the product's category. Most of this catalog
        has none, and a shopkeeper shown an empty list cannot do anything -
        so fall back to the same list used for uncatalogued enquiries and
        flag it, rather than blocking the counter on a data problem.
        """
        self.ensure_one()
        product = self.product_id
        # No product at all - a model the catalogue does not carry, which is
        # what the finder produces for a market item - has no category either,
        # and the shopkeeper should be told so rather than shown a short list
        # with no explanation.
        no_categ = not (product and product.categ_id)
        vendors = self._sourcing_vendors()
        if no_categ:
            # Everyone reachable, not the configured shortlist. The automatic
            # path still uses _unlisted_vendors() and stays conservative; a
            # human being asked to choose needs the whole field in front of
            # them, including a supplier added to a category minutes ago.
            vendors |= self._unlisted_vendors()
            vendors |= self.env['product.category'].sudo().search(
                []).mapped('sa_vendor_ids')
            vendors = vendors.filtered(
                lambda partner: (partner.phone or '').strip())
        return vendors, no_categ

    def _shop_pick_message(self):
        """What the customer is told while a person decides.

        A template, because the wording is the shop's business. It must carry
        the product and the ref: the gateway drops a message identical to one
        it sent the same chat inside five minutes, so a generic "please wait"
        arrives as silence.
        """
        self.ensure_one()

        class _Missing(dict):
            def __missing__(self, key):
                return '{%s}' % key

        name = (self.product_id.name or self.ai_search_term
                or self.raw_text or _("that"))
        template = (self._settings().shop_pick_customer_text or '').strip()
        if not template:
            template = _(
                "Let me check that for you \u23F3\n\n*{product}*\n\n"
                "Our shopkeeper is checking this and will come back to you "
                "shortly.\n\n_Ref {ref}_")
        values = _Missing(
            product=name,
            ref=self.ref_code or self.id,
            customer=self.requester_name or '',
            shop=self.group_id.name or '',
        )
        try:
            return template.format_map(values)
        except Exception as err:  # noqa: BLE001 - a bad template must not
            _logger.warning(      # silence the customer
                "Sales Automation: shop-pick template is malformed (%s) - "
                "using the built-in wording", err)
            return _("Let me check that for you \u23F3\n\n*%(product)s*\n\n"
                     "Our shopkeeper is checking this and will come back to "
                     "you shortly.\n\n_Ref %(ref)s_",
                     product=name, ref=self.ref_code or self.id)

    def _park_for_shop(self, vendors):
        """Hold the enquiry at the counter. No vendor is messaged yet."""
        self.ensure_one()
        window = max(1, self._settings().shop_pick_window_minutes or 5)
        candidates, no_categ = self._sa_vendor_candidates()
        if not candidates:
            candidates = vendors
        self.write({
            'state': 'awaiting_vendor_pick',
            'shop_pick_deadline': fields.Datetime.add(
                fields.Datetime.now(), minutes=window),
            'shop_pick_vendor_ids': [(6, 0, candidates.ids)],
            'shop_pick_no_categ': no_categ,
            'shop_pick_auto': False,
        })
        self._say(self._shop_pick_message())
        self._sa_enquiry_notify()
        _logger.info("Sales Automation: enquiry %s parked for the shop - "
                     "%d candidate vendor(s), auto-sending in %d min",
                     self.id, len(candidates), window)
        return True

    def _sa_tag_last_outgoing(self, destination):
        """Attach the message we just sent to this enquiry.

        The gateway logs the row; we claim it. Same trick `_ask` already uses
        to remember which poll it asked.
        """
        self.ensure_one()
        try:
            target = str(destination or '')
            domain = [
                ('direction', '=', 'outgoing'),
                ('sa_request_id', '=', False),
                # Seconds old, not "the newest one lying around": a send that
                # produced no row must not make us adopt an older message.
                ('create_date', '>=', fields.Datetime.subtract(
                    fields.Datetime.now(), seconds=30)),
            ]
            if '@' in target:
                domain.append(('phone', '=', target))
            else:
                digits = ''.join(ch for ch in target if ch.isdigit())
                if not digits:
                    return True
                domain.append(('phone', 'like', digits[-9:]))
            sent = self.env['whatsapp.message'].sudo().search(
                domain, order='id desc', limit=1)
            if sent:
                sent.sa_request_id = self.id
        except Exception as err:  # noqa: BLE001 - tagging is for the history
            _logger.debug("Sales Automation: could not tag the message to "
                          "enquiry %s: %s", self.id, err)
        return True

    def _sa_tag_message(self, message):
        """Attach an incoming message to this enquiry."""
        self.ensure_one()
        try:
            if message and not message.sa_request_id:
                message.sa_request_id = self.id
        except Exception as err:  # noqa: BLE001
            _logger.debug("Sales Automation: could not tag incoming message "
                          "to enquiry %s: %s", self.id, err)
        return True

    def _sa_enquiry_notify(self):
        """Tell the counter screen to redraw.

        A no-op here: the bus and the screen belong to sales_automation_store,
        which overrides this. Sourcing must not depend on a screen being
        installed.
        """
        return True

    @api.model
    def _cron_auto_source(self):
        """Nobody chose in time, so ask everyone."""
        now = fields.Datetime.now()
        due = self.sudo().search([
            ('state', '=', 'awaiting_vendor_pick'),
            ('shop_pick_deadline', '<=', now),
        ])
        for request in due:
            try:
                vendors = request.shop_pick_vendor_ids.filtered(
                    lambda partner: (partner.phone or '').strip())
                if not vendors:
                    request._sa_nobody_to_ask()
                    continue
                request.write({'shop_pick_auto': True,
                               'shop_pick_done_on': now})
                request._start_sourcing(vendors)
                _logger.info("Sales Automation: enquiry %s not picked up at "
                             "the counter - asked %d vendor(s) automatically",
                             request.id, len(vendors))
            except Exception as err:  # noqa: BLE001 - one bad row must not
                _logger.exception(    # stall the sweep
                    "Sales Automation: auto-sourcing enquiry %s failed: %s",
                    request.id, err)
                request.write({'state': 'dropped', 'drop_reason': 'error',
                               'error': str(err)[:500]})
        return True

    def _unlisted_vendors(self):
        """Who to ask about something that is not in the catalog.

        There is no product and therefore no category, so the configured list
        is used. With none configured, everyone named on any product category
        is asked instead - people already trusted to quote - capped so that a
        missing setting can never become a message to all 206 contacts.
        """
        self.ensure_one()
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        if settings.unlisted_vendor_ids:
            return settings.unlisted_vendor_ids
        known = self.env['product.category'].sudo().search(
            [('sa_vendor_ids', '!=', False)]).mapped('sa_vendor_ids')
        if len(known) > 20:
            _logger.info("Sales Automation: no unlisted-vendor list set; "
                         "using 20 of %d category vendors.", len(known))
        return known[:20]

    def _on_confirmed(self):
        """The customer said yes. Price it from stock, or go ask vendors."""
        self.ensure_one()
        product = self.product_id

        if product:
            sellable = self._assess_availability(product)
            if self.stock_status == 'in_stock':
                return self._quote_from_stock(product)
            if not sellable:
                return self._sa_say_unavailable(product)
            # Out of stock: the vendors are asked for today's price even when
            # the catalogue carries one (owner, 29 Sep 2026: the shelf price
            # is not a price we can promise for goods we have to buy in).

        # Asking again while the first ask is still open helps nobody. The
        # vendor gets the same question twice and answers once, so their single
        # price lands on whichever request happens to be newest and the others
        # time out empty - which reads, to the customer, as the assistant
        # ignoring them. Reuse the open one instead.
        twin = self._open_twin()
        if twin:
            _logger.info("Sales Automation: enquiry %s is already being priced "
                         "by enquiry %s - not asking again", self.id, twin.id)
            self.state = 'dropped'
            self.drop_reason = 'duplicate'
            name = (twin.product_id.name or twin.ai_search_term
                    or self.ai_search_term or _("that"))
            if twin.state == 'quoted' and twin.quoted_price:
                # The price is already in. Answering "still checking" when
                # we have the number is the assistant losing its own work:
                # the customer asked twice and was told to wait twice, two
                # minutes after a supplier had answered.
                twin._announce_price(name, twin.quoted_price, '')
                return True
            # Named, not "that". A bare status line is identical every
            # time, and the gateway drops any message identical to one it
            # sent in the last five minutes - so the second ask arrived as
            # silence.
            self._say(_("Still checking on *%(product)s* for you \u23F3",
                        product=name))
            return True

        vendors = self._sourcing_vendors()
        if not vendors and not product.categ_id._sa_vendor_groups_for_sourcing():
            # Nobody with a WhatsApp/WeChat tick on the category and no
            # vendor group either. This used to drop the enquiry with "Let me
            # check on that" - the customer waited forever and nobody at the
            # shop was told. Held for a hand-typed price instead.
            return self._sa_nobody_to_ask()
        # Decided before _start_sourcing runs, never undone afterwards. The
        # store module learned that the hard way on the rider side: letting
        # the send happen and then reversing the state left the rider already
        # told to come and a spent outbox guard that swallowed the real
        # message later.
        if self._settings().shop_picks_vendors:
            return self._park_for_shop(vendors)
        return self._start_sourcing(vendors)

    # ----------------------------------------------------------
    # In stock: no vendor needed
    # ----------------------------------------------------------
    def _sa_has_sale_price(self, product):
        """True when the catalogue can price this product on its own."""
        self.ensure_one()
        priced = product.with_company(self.finder_company_id
                                      or self._company_for(self.group_id))
        return bool((priced.list_price or 0.0) > 0
                    or (getattr(priced, 'wa_retail_price', 0.0) or 0.0) > 0)

    def _quote_from_catalog(self, product):
        """The sale price, for a product not on the shelf right now."""
        self.ensure_one()
        conversation = self._ensure_conversation()
        priced = product.with_company(self.finder_company_id
                                      or self._company_for(self.group_id))
        price = self._catalog_price(priced, self._is_existing_contact(conversation))
        self.quoted_price = price
        self._announce_price(product.name, price, _("🛒 Available to order"))
        self.state = 'quoted'
        self._seed_tracker_handoff(product, conversation, price)
        _logger.info("Sales Automation: enquiry %s quoted %s from the "
                     "catalogue (out of stock, sale price set)", self.id, price)
        return True

    def _quote_from_stock(self, product):
        self.ensure_one()
        conversation = self._ensure_conversation()
        priced = product.with_company(self.finder_company_id
                                      or self._company_for(self.group_id))
        price = self._catalog_price(priced, self._is_existing_contact(conversation))
        self.quoted_price = price
        self._announce_price(product.name, price, "📦 In stock")
        self.state = 'quoted'
        self._seed_tracker_handoff(product, conversation, price)
        return True

    # ----------------------------------------------------------
    # Out of stock: ask the vendors
    # ----------------------------------------------------------
    def _sa_ask_via_wechat(self, vendor, ask, guard, trigger):
        """True when this vendor is asked on another channel instead of
        WhatsApp. Nothing here: the WeChat module overrides it."""
        return False

    @api.model
    def _sa_typed_answer_hook(self, group, message, text):
        """A module that asked this person to type something answers here
        (anything but None stops the router). Nothing here by itself."""
        return None

    def _sa_ask_vendor_confirm(self, session, vendor, name, qty, ask):
        """True when the vendor was sent the picture + confirmation page
        instead of the YES / NO poll. Nothing here: the confirmation module
        overrides it."""
        return False

    def _start_sourcing(self, vendors):
        """Ask each vendor privately for a price.

        One private message per vendor rather than a single post in a shared
        group. It costs more sends and buys what the group could not give: a
        reply that can only belong to the request it answers. No reply-quote to
        hope for, no "newest open request" guess, and no vendor reading a
        competitor's price.
        """
        self.ensure_one()
        group = self.group_id
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        window = max(1, settings.sourcing_window_minutes or 10)
        name = self.product_id.name or self.ai_search_term or self.raw_text
        qty = self.qty or 0

        # Ask for the amount and nothing else. The reply router already
        # matches a bare number to the only price check a supplier has open,
        # so making them type the code was ceremony - and a supplier copying
        # `#HG 450` by hand is a supplier who might not bother next time.
        #
        # The code still rides in the header: it is what a supplier quotes
        # when they answer days later with three of our questions in their
        # chat, and it is what `_sa_ask_which` asks for when a bare number
        # could belong to more than one. It is offered as the exception now,
        # in small print, instead of being the instruction.
        #
        # No wa.me link either. The supplier was messaged privately, so the
        # link opens the chat they are already reading.
        ask = _("\U0001F50E *Price check* \u2014 *#%(ref)s*"
                "\n\n*%(product)s*%(qty)s"
                "\n\nBest price *and delivery time* please."
                "\n\n\U0001F449 *Just reply with the amount* \u2014 like "
                "*450*"
                "\nWith the days if you can: *450 3 days*"
                "\n\n_Answering about something else? Put its code first: "
                "#%(ref)s 450_",
                ref=self.ref_code, product=name,
                qty=(_("\nQuantity: %s", int(qty)) if qty else ''))

        session = group.employee_session_id.session_id or group.session_id
        asked = self.env['res.partner']
        guard = self.env['sa.outbox.guard'].sudo()
        trigger = self.env.context.get('sa_trigger_msg') or self.id

        # Groups first, so `sourcing_group_id` and the posted message id are
        # already on the record if a supplier answers before the private
        # messages have finished going out.
        posted = self._sa_ask_vendor_groups(session, ask, guard, trigger)
        for vendor in vendors:
            try:
                # Another channel first (WeChat): asked there, or already
                # asked there, and the WhatsApp poll is skipped.
                if self._sa_ask_via_wechat(vendor, ask, guard, trigger):
                    asked |= vendor
                    continue
                # Guarded for the same reason as the group post: a replayed
                # request asked every supplier again, so they were being sent
                # the same price check three times over.
                if not guard.claim('%s|ask|%s|%s' % (trigger, vendor.phone,
                                                     ask)):
                    asked |= vendor
                    continue
                # The picture + page link when the confirmation module is
                # installed; the YES / NO poll otherwise.
                if not self._sa_ask_vendor_confirm(session, vendor, name, qty, ask):
                    self._sa_ask_vendor_has_it(session, vendor.phone,
                                               name, qty, ask)
                self._sa_tag_last_outgoing(vendor.phone)
                asked |= vendor
            except WhatsAppQueued:
                asked |= vendor        # queued, and it will go out
            except Exception as err:   # noqa: BLE001 - one bad number must not
                _logger.warning(       # stop the rest being asked
                    "Sales Automation: could not ask %s (%s): %s",
                    vendor.name, vendor.phone, err)

        if not asked and not posted:
            return self._sa_nobody_to_ask()

        self.write({
            'sourcing_vendor_ids': [(6, 0, asked.ids)],
            'sourcing_deadline': fields.Datetime.add(
                fields.Datetime.now(), minutes=window),
            'state': 'sourcing',
        })
        # The product is named for the customer's sake - with several
        # enquiries running they cannot otherwise tell which one this
        # answers - and because the gateway refuses a message identical to
        # one it sent in the last five minutes. Two enquiries from the same
        # person produced the very same sentence, and the second was
        # blocked before it ever left.
        self._say(_("Let me check that for you ⏳\n\n*%(product)s*\n\nI'll come back with the price within %(mins)s minutes.\n\n_Ref %(ref)s_",
                    product=name, mins=window, ref=self.ref_code or self.id))
        _logger.info("Sales Automation: enquiry %s asked %d vendor(s), closing "
                     "in %d min", self.id, len(asked), window)
        return True

    def _last_outgoing_id(self, vendor_group):
        """The WhatsApp id of the message we just sent to the vendor group.

        `send_message` returns True, not the record it logged, so the row is
        read back. Our own send created it moments ago in this transaction, so
        the newest outgoing row for that JID is it.
        """
        self.ensure_one()
        logged = self.env['whatsapp.message'].sudo().search([
            ('session_id', '=', vendor_group.session_id.id),
            ('phone', '=', vendor_group.group_jid),
            ('direction', '=', 'outgoing'),
        ], order='id desc', limit=1)
        return logged.wa_message_id or ''

    @api.model
    def _match_vendor_reply(self, message, group):
        """(request, matched_by) for a price posted in a vendor group.

        A vendor who used WhatsApp's reply button is matched exactly. Otherwise
        the newest still-open request in that group is assumed - a guess, so it
        is labelled as one, because with two requests in flight it can be
        wrong and the customer would be quoted a price for the other product.
        """
        quoted = (message.quoted_wa_message_id or '').strip()
        if quoted:
            exact = self.sudo().search([
                ('broadcast_wa_message_id', '=', quoted),
            ], order='id desc', limit=1)
            if exact:
                return exact, 'reply_quote'

        open_request = self.sudo().search([
            ('sourcing_group_id', '=', group.id),
            ('state', '=', 'sourcing'),
            ('sourcing_deadline', '>', fields.Datetime.now()),
        ], order='id desc', limit=1)
        return open_request, 'newest_open'

    # ----------------------------------------------------------
    # Closing the window
    # ----------------------------------------------------------
    @api.model
    def _cron_close_sourcing(self):
        """Quote the customer once the vendor reply window has passed."""
        due = self.sudo().search([
            ('state', '=', 'sourcing'),
            ('sourcing_deadline', '<=', fields.Datetime.now()),
        ])
        for request in due:
            try:
                request._close_sourcing()
            except Exception as err:  # noqa: BLE001 - one bad enquiry must not
                _logger.exception(                    # stall every other one
                    "Sales Automation: closing enquiry %s failed", request.id)
                request.write({'state': 'dropped', 'drop_reason': 'error',
                               'error': str(err)[:2000]})

    def _close_sourcing(self):
        self.ensure_one()
        best = self.quote_ids.sorted('price')[:1]
        if best:
            return self._apply_winning_quote(best)

        # Nobody priced it. The price list is NOT quoted any more: on 8 Sep
        # it sent a customer 540 from a supplier who had never been asked
        # (the product had no category, so its Purchase tab named the wrong
        # one), while the supplier who HAD been asked had just said "yes, I
        # have it" and was typing the number. A guess is not a price. The
        # list survives as a hint to the shopkeeper - see _sa_price_hint -
        # and the enquiry is held open for a person: a supplier's late reply
        # or the shopkeeper's typed number, whichever comes first.
        return self._sa_stall_for_price()

    # ----------------------------------------------------------
    # Nobody answered
    # ----------------------------------------------------------
    def _sa_nobody_to_ask(self):
        """No reachable vendor at all: hold the enquiry for the shop's price.

        Same outcome as every vendor staying silent - the enquiry stays in
        `sourcing`, the desk shows "Needs a price" with its alarm, the
        escalation phone gets the link - so the shop can type a price or
        add a vendor. Before 173.4.4 this dropped the enquiry.
        """
        self.ensure_one()
        self.write({'state': 'sourcing',
                    'sourcing_vendor_ids': [(5, 0, 0)],
                    'shop_pick_vendor_ids': [(5, 0, 0)]})
        _logger.info("Sales Automation: enquiry %s has no reachable vendor "
                     "on category %s - held for a hand-entered price",
                     self.id, self.product_id.categ_id.display_name)
        return self._sa_stall_for_price()

    def _sa_stall_for_price(self):
        """Hold the enquiry open and ask the shop for a price."""
        self.ensure_one()
        import secrets
        name = (self.product_id.name or self.ai_search_term
                or self.raw_text or _("this item"))
        vals = {
            'sa_price_stalled': True,
            'sa_price_asked_on': fields.Datetime.now(),
            # Cleared so `_cron_close_sourcing` stops matching this row: its
            # domain is `sourcing_deadline <= now`, and NULL never matches.
            'sourcing_deadline': False,
        }
        if not self.sa_price_token:
            vals['sa_price_token'] = secrets.token_urlsafe(24)
        self.write(vals)

        # No time promised - a person has to make a phone call. The ref stays
        # because the gateway drops a message byte-identical to one sent to
        # the same chat minutes ago, and two people asking about the same
        # thing would otherwise produce the same bytes.
        self._say(_("Still checking on *%(product)s* for you \u23F3\n\n"
                    "We'll come back to you shortly.\n\n_Ref %(ref)s_",
                    product=name, ref=self.ref_code or self.id))
        self._sa_enquiry_notify()
        self._sa_tell_shop_no_price(name)
        _logger.info("Sales Automation: enquiry %s had no vendor reply - "
                     "held open for a hand-entered price", self.id)
        return True

    def _sa_price_entry_url(self):
        """The link the shop taps to type a price in."""
        self.ensure_one()
        if not self.sa_price_token:
            return ''
        return self.env['wa.auto.reply'].sudo()._sa_public_link(
            '/wa/quote/%s?token=%s' % (self.id, self.sa_price_token))

    def _sa_price_hint(self):
        """(price-list line, converted price) - or (empty, 0.0).

        The same lookup `_close_sourcing` used to QUOTE from. Now it is only
        ever shown to a person, labelled as a guess, so the shopkeeper on the
        phone has a number to sanity-check against.
        """
        self.ensure_one()
        product = self.product_id
        seller = self._best_vendor(product) if product else False
        if not seller:
            return self.env['product.supplierinfo'], 0.0
        return seller, self._converted(seller.price, seller.currency_id)

    def _sa_vendor_lists(self):
        """(said yes, said no, silent) as name lists, for every screen."""
        self.ensure_one()
        priced = set(self.quote_ids.mapped('partner_id').ids)
        yes = self.sa_vendor_yes_ids.filtered(lambda p: p.id not in priced)
        no = self.sa_vendor_no_ids
        silent = self.sourcing_vendor_ids.filtered(
            lambda p: p.id not in priced and p not in yes and p not in no)
        return (yes.mapped('name'), no.mapped('name'), silent.mapped('name'))

    def _sa_tell_shop_no_price(self, name):
        """Message the escalation number, once, with what they need to act."""
        self.ensure_one()
        phone = (self._settings().price_escalation_phone or '').strip()
        if not phone:
            _logger.info("Sales Automation: no escalation number set - "
                         "enquiry %s waits on the Enquiries screen only",
                         self.id)
            return False
        # Once per enquiry. A retry after a serialisation failure must not
        # message the counter twice about the same thing.
        if not self.env['sa.outbox.guard'].sudo().claim(
                'noprice|%s' % self.id, 86400):
            return False

        yes, no, silent = self._sa_vendor_lists()
        seller, hint = self._sa_price_hint()
        lines = []
        if yes:
            lines.append(_("\u2705 Said YES, no price yet: %s", ', '.join(yes)))
        if no:
            lines.append(_("\u274C Said NO: %s", ', '.join(no)))
        if silent:
            lines.append(_("\U0001F507 Silent: %s", ', '.join(silent)))
        if not lines:
            lines.append(_(
                "\u26A0 No vendor with a WhatsApp or WeChat tick on category "
                "*%(categ)s* - add one there (Contacts \u25B8 Sales & Purchase "
                "\u25B8 tick WhatsApp + phone), or just type the price.",
                categ=self.product_id.categ_id.display_name or '-'))
        if seller:
            # A hint, labelled as one. This number used to go straight to the
            # customer; it is here so the person on the phone can tell a
            # sensible quote from a silly one, not so it can be sent on.
            lines.append(_("\U0001F4A1 Price list says %(price).2f "
                           "(%(vendor)s) \u2014 check before using",
                           price=hint, vendor=seller.partner_id.name))
        body = _(
            "\u26A0 *No price yet* \u2014 *#%(ref)s*\n\n"
            "\U0001F4E6 *%(product)s*%(qty)s\n"
            "\U0001F464 %(customer)s\n\n"
            "%(lines)s\n\n"
            "Please call them, then type the price here:\n%(link)s",
            ref=self.ref_code or self.id,
            product=name,
            qty=(_("\nQuantity: %s", int(self.qty)) if self.qty else ''),
            customer=(self.requester_name or self.requester_phone or ''),
            lines='\n'.join(lines),
            link=self._sa_price_entry_url() or _("(no public link configured)"),
        )
        session = (self.group_id.employee_session_id.session_id
                   or self.group_id.session_id)
        try:
            session.send_message(phone, body)
            _logger.info("Sales Automation: told %s that enquiry %s got no "
                         "vendor reply", phone, self.id)
        except Exception as err:  # noqa: BLE001 - the desk still has it
            _logger.warning("Sales Automation: could not tell %s about "
                            "enquiry %s: %s", phone, self.id, err)
            return False
        return True

    def _sa_apply_manual_price(self, cost, vendor_id=None, days=0, source=''):
        """Quote the customer from a price somebody typed in.

        One method for both the public link and the counter screen, so there
        is a single place where a typed number is validated.

        The price is appended as a `sa.vendor.quote` rather than written onto
        the enquiry: an appended row is auditable and can be re-picked with
        "Use This Price", and both security incidents this codebase has
        recorded were public routes that wrote directly.
        """
        self.ensure_one()
        try:
            amount = float(str(cost).strip().replace(',', ''))
        except (TypeError, ValueError):
            raise UserError(_("Type the price as a number, like 500."))
        if amount <= 0:
            raise UserError(_("The price has to be more than zero."))
        try:
            delay = int(days or 0)
        except (TypeError, ValueError):
            delay = 0

        vendor = self.env['res.partner'].sudo().browse(int(vendor_id)) \
            if vendor_id else self.env['res.partner']
        if vendor and not vendor.exists():
            vendor = self.env['res.partner']

        quote = self.env['sa.vendor.quote'].sudo().create({
            'request_id': self.id,
            'partner_id': vendor.id or False,
            'vendor_name': vendor.name or _("Entered at the shop"),
            'vendor_phone': (vendor.phone or '').strip(),
            'price': amount,
            'delay_days': max(0, delay),
            'matched_by': 'manual',
            'raw_text': _("Typed in at the shop%s", source and ' (%s)' % source),
            'currency_id': (self.currency_id.id
                            or self.env.company.currency_id.id),
        })
        self.write({
            'sa_price_stalled': False,
            'sa_price_by_id': self.env.uid,
            # The customer was told we were still checking, so the quote that
            # follows leads with "good news" rather than arriving cold.
            'answered_late': True,
        })
        _logger.info("Sales Automation: enquiry %s priced by hand at %s by %s",
                     self.id, amount, self.env.user.name)
        self._apply_winning_quote(quote)
        self._sa_enquiry_notify()
        return quote

    def _sa_ask_vendor_has_it(self, session, phone, name, qty, fallback):
        """Step one: do they even stock it? Tappable YES / NO.

        A poll, not buttons: `sendButtons` arrives as "This message couldn't
        load" on this transport, and a poll is the one tappable thing that
        renders everywhere. If the poll is refused the price check goes out as
        it always did, so a supplier is never left with nothing.
        """
        self.ensure_one()
        question = _("\U0001F50E *#%(ref)s* - do you have this?"
                     "\n\n*%(product)s*%(qty)s",
                     ref=self.ref_code, product=name,
                     qty=(_("\nQuantity: %s", int(qty)) if qty else ''))
        try:
            session.sa_send_poll(phone, question, [_('YES'), _('NO')])
            self._sa_remember_vendor_poll(phone)
            return 'poll'
        except WhatsAppQueued:
            self._sa_remember_vendor_poll(phone)
            return 'poll'
        except Exception as err:  # noqa: BLE001
            _logger.info("Sales Automation: YES/NO poll to %s refused (%s) - "
                         "asking for the price directly", phone, err)
        session.send_message(phone, fallback)
        return 'text'

    def _sa_ask_vendor_price(self, session, phone):
        """Step two: they have it, so what do they want for it?

        The code is spelled out in the example here, unlike the one-step ask:
        this arrives as a reply to a question they answered a moment ago, and
        a bare number in a chat with three of our questions in it is exactly
        what `_sa_ask_which` has to go back and disambiguate.
        """
        self.ensure_one()
        name = (self.product_id.name or self.ai_search_term
                or self.raw_text or _("this item"))
        body = _("\U0001F44D Good - what is your best price for "
                 "*%(product)s*?"
                 "\n\n\U0001F449 Reply *#%(ref)s 500* - change the number"
                 "\nWith the days if you can: *#%(ref)s 500 3 days*",
                 product=name, ref=self.ref_code)
        if not self.env['sa.outbox.guard'].sudo().claim(
                'askprice|%s|%s' % (self.id, phone), 3600):
            return False
        # They have just committed to pricing it. Closing the window on them
        # thirty seconds later - which a one-minute window did - is how the
        # customer came to be quoted from a price list instead. Restart it,
        # but only while the enquiry is still genuinely waiting; a stalled
        # one is the shopkeeper's now, and a late price is handled on
        # arrival.
        if self.state == 'sourcing' and not self.sa_price_stalled:
            window = max(1, self._settings().sourcing_window_minutes or 10)
            fresh = fields.Datetime.add(fields.Datetime.now(), minutes=window)
            if not self.sourcing_deadline or self.sourcing_deadline < fresh:
                self.write({'sourcing_deadline': fresh})
        try:
            session.send_message(phone, body)
        except WhatsAppQueued:
            pass
        except Exception as err:  # noqa: BLE001
            _logger.warning("Sales Automation: could not ask %s for a price "
                            "on %s: %s", phone, self.id, err)
            return False
        _logger.info("Sales Automation: %s has %s - asked for their price",
                     phone, self.id)
        return True

    def _sa_vendor_by_phone(self, phone):
        """The asked vendor behind a number, matched on the last nine digits
        the way `_capture_direct` does, so a space in the stored number
        does not lose them."""
        self.ensure_one()
        tail = ''.join(ch for ch in (phone or '') if ch.isdigit())[-9:]
        if not tail:
            return self.env['res.partner']
        return self.sourcing_vendor_ids.filtered(
            lambda v: ''.join(ch for ch in (v.phone or '') if ch.isdigit()).endswith(tail))[:1]

    def _sa_vendor_confirmed(self, phone):
        """True once this vendor said they have it - YES to the poll here,
        ACCEPT on the page in sales_automation_confirm."""
        self.ensure_one()
        vendor = self._sa_vendor_by_phone(phone)
        return bool(vendor and vendor in self.sa_vendor_yes_ids)

    def _sa_vendor_confirm_first(self, session, phone):
        """A price (or anything else) from a vendor who has not said they have
        it yet: ask for that first. Once per five minutes, so a vendor
        typing several lines gets one reminder, not one each."""
        self.ensure_one()
        if not self.env['sa.outbox.guard'].sudo().claim(
                'confirmfirst|%s|%s' % (self.id, phone), 300):
            return False
        body = self._sa_vendor_confirm_first_text(phone)
        try:
            session.send_message(phone, body)
        except WhatsAppQueued:
            pass
        except Exception as err:  # noqa: BLE001
            _logger.warning("Sales Automation: could not remind %s to confirm "
                            "%s first: %s", phone, self.id, err)
            return False
        _logger.info("Sales Automation: %s sent %s a reply before confirming - "
                     "asked to confirm first, no price taken", phone, self.id)
        return True

    def _sa_vendor_confirm_first_text(self, phone):
        """The reminder. The poll flow asks for a YES; sales_automation_confirm
        replaces it with the page link."""
        self.ensure_one()
        name = (self.product_id.name or self.ai_search_term
                or self.raw_text or _("this item"))
        return _("⚠️ Please tell us first if you have this exact "
                 "product: *%(product)s*\n\nReply *YES* or *NO*. Then send "
                 "your price, for example *#%(ref)s 450*.",
                 product=name, ref=self.ref_code)

    def _sa_vendor_has_none(self, session, phone, partner):
        """They answered NO. Record it and let them go."""
        self.ensure_one()
        if partner:
            self.sudo().write({'sa_vendor_no_ids': [(4, partner.id)]})
        _logger.info("Sales Automation: %s does not have %s",
                     partner.name or phone, self.id)
        if not self.env['sa.outbox.guard'].sudo().claim(
                'noack|%s|%s' % (self.id, phone), 3600):
            return True
        try:
            session.send_message(phone, _(
                "No problem - thanks for letting me know \U0001F44D"))
        except Exception:  # noqa: BLE001 - the answer is already recorded
            pass
        return True

    def _sa_ask_vendor_groups(self, session, ask, guard, trigger):
        """Post the price check in the vendor groups covering this category.

        One post reaches everyone in it, which is the whole point: a group of
        eight suppliers used to mean eight private messages, or - if none of
        them were registered as partners - nobody being asked at all.

        `sourcing_group_id` and `broadcast_wa_message_id` are stamped because
        `_match_vendor_reply` needs them: the first matches any price posted
        in that group while the window is open, the second matches a supplier
        who used WhatsApp's reply button, which is exact even with two
        enquiries in flight.
        """
        self.ensure_one()
        product = self.product_id
        if not product or not product.categ_id:
            return self.env['sa.sales.group']
        groups = product.categ_id._sa_vendor_groups_for_sourcing()
        if not groups:
            return groups

        posted = self.env['sa.sales.group']
        for vendor_group in groups:
            if not guard.claim('%s|askgrp|%s|%s' % (
                    trigger, vendor_group.group_jid, ask)):
                posted |= vendor_group
                continue
            try:
                session.send_message(vendor_group.group_jid, ask)
            except WhatsAppQueued:
                # Queued, not lost - the gateway will deliver it. The group
                # still has to be recorded below, or the price that comes back
                # matches nothing and is dropped without a word.
                _logger.info("Sales Automation: price check for enquiry %s "
                             "queued for %s", self.id, vendor_group.name)
            except Exception as err:  # noqa: BLE001 - the private asks stand
                _logger.warning("Sales Automation: could not post the price "
                                "check in %s: %s", vendor_group.name, err)
                continue
            posted |= vendor_group
            self._sa_tag_last_outgoing(vendor_group.group_jid)
            if not self.sourcing_group_id:
                # Many2one: the first group is the one a loose reply is
                # matched against. A supplier in any of the others has to use
                # WhatsApp's reply button, which matches exactly.
                #
                # The id is looked up rather than taken from
                # `_sa_tag_last_outgoing`, which returns True - the same
                # 30-second, destination-scoped window `_ask` uses, so a send
                # that logged no row cannot adopt an older message.
                sent = self.env['whatsapp.message'].sudo().search(
                    [('phone', '=', vendor_group.group_jid),
                     ('direction', '=', 'outgoing'),
                     ('create_date', '>=', fields.Datetime.subtract(
                         fields.Datetime.now(), seconds=30))],
                    order='id desc', limit=1)
                self.write({
                    'sourcing_group_id': vendor_group.id,
                    'broadcast_wa_message_id': sent.wa_message_id or False,
                })
        if posted:
            _logger.info("Sales Automation: enquiry %s asked %d vendor "
                         "group(s): %s", self.id, len(posted),
                         ', '.join(posted.mapped('name')))
        return posted

    def _sa_price_choice_needed(self, quote):
        """(page price, vendor-based price) when the shop must choose, else None.

        Only for a product that already carries a sale price, only for a
        real vendor quote (not one typed at the counter), and only when the
        two prices differ by more than the tolerance. Owner's rule, 29 Sep
        2026: the customer is not quoted until a person at the counter says
        which price stands - the page's or the vendor's.
        """
        self.ensure_one()
        settings = self._settings()
        if not getattr(settings, 'price_approval_enabled', True):
            return None
        if self.env.context.get('sa_price_approved'):
            return None
        if getattr(quote, 'matched_by', '') == 'manual':
            return None
        product = self.product_id
        if not product or not self._sa_has_sale_price(product):
            return None
        priced = product.with_company(self.finder_company_id
                                      or self._company_for(self.group_id))
        page = self._catalog_price(priced, self._is_existing_contact(
            self.conversation_id))
        margin = settings.margin_percent or 0.0
        vendor_sell = (quote.price or 0.0) * (1.0 + margin / 100.0)
        if page <= 0:
            return None
        tolerance = (getattr(settings, 'price_approval_tolerance_percent', 0.0) or 0.0)
        if abs(page - vendor_sell) <= page * tolerance / 100.0 + 0.005:
            return None
        return page, vendor_sell

    def _sa_hold_for_price_choice(self, quote, page, vendor_sell):
        """Park the enquiry for the counter: the desk alarm rings, the
        customer is told we are still checking. Nothing goes to the
        escalation phone (owner: counter screen only)."""
        self.ensure_one()
        self.quote_ids.filtered('is_best').is_best = False
        quote.is_best = True
        self.write({
            'best_quote_id': quote.id,
            'sa_price_choice_quote_id': quote.id,
            'vendor_price': quote.price,
            'vendor_delay': quote.delay_days,
            'stock_status': 'on_order',
            'sa_price_stalled': False,
            'sa_price_choice_pending': True,
            'sa_price_page': page,
            'sa_price_vendor': vendor_sell,
            'sa_price_asked_on': fields.Datetime.now(),
            'sourcing_deadline': False,
            'state': 'sourcing',
        })
        name = (self.product_id.name or self.ai_search_term
                or self.raw_text or _("this item"))
        self._say(_("Still checking on *%(product)s* for you \u23F3\n\n"
                    "We'll come back to you shortly.\n\n_Ref %(ref)s_",
                    product=name, ref=self.ref_code or self.id))
        self._sa_enquiry_notify()
        _logger.info("Sales Automation: enquiry %s waits for the counter to "
                     "choose a price - page %.2f vs vendor %.2f (cost %.2f)",
                     self.id, page, vendor_sell, quote.price)
        return True

    def _sa_apply_price_choice(self, choice, sell=None, source=''):
        """The counter chose. Quote the customer at that selling price."""
        self.ensure_one()
        if not self.sa_price_choice_pending:
            raise UserError(_("This enquiry is not waiting for a price choice."))
        quote = self.sa_price_choice_quote_id or self.best_quote_id
        if not quote:
            raise UserError(_("The vendor quote behind this enquiry is gone."))
        if choice == 'page':
            price = self.sa_price_page
        elif choice == 'vendor':
            price = self.sa_price_vendor
        elif choice == 'typed':
            try:
                price = float(str(sell or '').strip().replace(',', ''))
            except (TypeError, ValueError):
                raise UserError(_("Type the price as a number, like 500."))
        else:
            raise UserError(_("Unknown choice %s.", choice))
        if not price or price <= 0:
            raise UserError(_("The price has to be more than zero."))
        self.write({'sa_price_choice_pending': False,
                    'sa_price_choice': choice,
                    'sa_price_choice_by': (source or '')[:80] + (
                        ' (%s)' % self.env.user.name if self.env.user else ''),
                    'sa_price_by_id': self.env.user.id,
                    'answered_late': True})
        _logger.info("Sales Automation: enquiry %s price approved at %.2f "
                     "(%s) by %s", self.id, price, choice, source)
        res = self.with_context(sa_price_approved=True,
                                sa_sell_price=price)._apply_winning_quote(quote)
        self._sa_enquiry_notify()
        return res

    def _apply_winning_quote(self, quote):
        """Make `quote` the winner and quote the customer from it."""
        self.ensure_one()
        needed = self._sa_price_choice_needed(quote)
        if needed:
            return self._sa_hold_for_price_choice(quote, *needed)
        self.quote_ids.filtered('is_best').is_best = False
        quote.is_best = True
        self.write({
            'best_quote_id': quote.id,
            'vendor_price': quote.price,
            'vendor_delay': quote.delay_days,
            'stock_status': 'on_order',
            # A real price ends the wait for a typed one, whoever won.
            'sa_price_stalled': False,
        })
        _logger.info("Sales Automation: enquiry %s won by %s at %.2f of %d "
                     "quote(s)", self.id, quote.vendor_name or quote.vendor_phone,
                     quote.price, len(self.quote_ids))
        return self._quote_customer(quote.price, quote.delay_days,
                                    sell=self.env.context.get('sa_sell_price'))

    def _quote_customer(self, cost, delay, sell=None):
        """Cost + margin - or the selling price the counter approved -
        posted where the group was configured to see it."""
        self.ensure_one()
        margin = self.env['sa.ai.settings'].sudo().get_settings().margin_percent or 0.0
        price = float(sell) if sell else cost * (1.0 + margin / 100.0)
        self.quoted_price = price

        # A vendor who said nothing about timing leaves `delay` at 0, and so
        # does one who said "ready stock" - but only the second may be
        # promised to a customer, which is why the winning quote is checked
        # rather than the number alone.
        # No delivery line. What a vendor promises us is not a promise we
        # can make on their behalf, and a date the customer then holds us
        # to is worse than no date at all. The lead time is still recorded
        # on the quote for whoever fulfils the order.
        availability = ''
        name = self.product_id.name or self.ai_search_term or _("your item")
        self._announce_price(name, price, availability)
        self.state = 'quoted'

        conversation = self._ensure_conversation()
        self._seed_tracker_handoff(self.product_id, conversation, price)

        # They already told us what they want to pay, so quoting the list price
        # and stopping would be ignoring them. Answer it now, in the same turn.
        if (self.target_price and self._settings().bargain_enabled
                and self.target_price < price):
            self._counter_offer('%.2f' % self.target_price)
        return True

    def _announce_price(self, name, price, availability):
        """Post the price with the confirm choice attached.

        The choice belongs on the quote itself, not one message later. Telling
        a customer a price and then telling them to go and message us is a step
        most of them will not take - and the ones who do arrive in a private
        chat with no context. Tapping ACCEPT here is the whole handoff: it
        opens the private chat for them, already carrying the product and the
        agreed price.

        The price is public because the group asked for it. Everything after
        the tap - quantity, name, address, payment - happens privately.
        """
        self.ensure_one()
        body = _(
            "✅ *%(product)s*\n%(availability)s\n💰 *%(price).2f*",
            product=name, availability=availability, price=price)
        if self.answered_late:
            # Two minutes earlier this customer was told we could not get
            # a price. Leading with the good news makes that a sequence
            # rather than a contradiction.
            body = "%s\n\n%s" % (
                _("👍 Good news - a price came through after all."),
                body)
            self.answered_late = False
        if self.group_id.handoff_dm:
            # The reference is not decoration: without it this sentence is
            # identical every time, and the gateway drops a message identical
            # to one sent to the same chat in the last five minutes - so a
            # customer asking twice was answered once.
            # Said in the group only: once the finder has moved the enquiry
            # to the private chat, telling the customer there that they have
            # been messaged privately would be nonsense.
            if self._sa_reply_to() == self.group_id.group_jid:
                self._say(_("✅ *%(product)s*\n%(availability)s\n\nI've sent "
                            "you the price privately. 💬\n\n_Ref %(ref)s_",
                            product=name, availability=availability,
                            ref=self.ref_code or self.id))
            return True
        # A product with quantity ranges needs the number before the deal
        # can be offered: the number decides whether bargaining exists.
        if self._sa_qty_first(body):
            return True
        rendered = self._ask(body, self._sa_deal_options())
        # The poll can be tapped in a group, but it cannot carry a number, so
        # the wa.me links remain the way an arbitrary price is sent with one
        # tap. They are the FALLBACK now: where the poll rendered, BETTER
        # PRICE already asks for that number, and posting the same choices
        # again as links is what made this thread noisy.
        if rendered != 'poll':
            self._say(self._sa_price_taps(price))
        return True

    # ----------------------------------------------------------
    # Talking
    # ----------------------------------------------------------
    def _ask(self, body, buttons):
        """Post a question, as a poll or as tappable buttons.

        The default is a poll, because `sendButtons` in a group was seen to
        arrive as "This message couldn't load. Open the message on your phone
        to view it." Evolution *accepts* that call and returns success, so
        `send_buttons`'s own numbered fallback never fires - it only triggers
        when Evolution rejects the call - and an accepted-but-unrenderable
        message is worse than a refused one.

        `group_use_buttons` on the group switches to buttons anyway. It is a
        setting rather than a replacement because the failure above is a
        property of the transport, not of the code, and it may differ by client
        and by Evolution version. `include_numbers=True` keeps the numbered
        text in the same message, so where buttons do render the customer can
        still answer by typing.

        Either way the ids in `buttons` are what come back: a tapped button
        returns `sa_yes` or `sa_no` through the gateway's `_text_of`, and a
        poll returns the visible label. Both are already understood.
        """
        self.ensure_one()
        self._sa_stamp_asked()
        destination = self._sa_reply_to()
        try:
            # The countdown goes inside the question, which for a poll is the
            # only text the customer sees on that bubble.
            note = self._sa_deadline_note()
            if note:
                body = '%s\n\n%s' % (body, note)
            question = (self._sa_addressed(body)
                        if destination == self.group_id.group_jid else body)
            if not self.env['sa.outbox.guard'].sudo().claim(
                    '%s|poll|%s|%s' % (
                        self.env.context.get('sa_trigger_msg') or 0,
                        destination, question)):
                _logger.info("Sales Automation: already asked this of %s "
                             "moments ago - not repeating it", destination)
                return True
            # `group_use_buttons` used to move a question into the
            # customer's own chat so it could be sent as tappable buttons.
            # The conversation stays in the group now, and a poll is the only
            # tappable prompt that renders there at all, so the branch is
            # disabled rather than removed - the setting still exists on
            # groups that have it ticked.
            if False and self.group_id.group_use_buttons:
                in_group = destination == self.group_id.group_jid
                # Buttons render one-to-one and not in a group, so a group
                # question is moved to the requester's own chat rather than
                # sent somewhere it will arrive unreadable.
                target = self._sa_dm_target() if in_group else destination
                if target:
                    self.group_id.session_id.send_buttons(
                        target, body, buttons, include_numbers=True)
                    if in_group:
                        self._sa_note_moved_to_dm()
                    # No poll id to keep: a tapped button arrives as an
                    # ordinary message from the person who tapped, so it is
                    # already attributable without one.
                    return True
                # Nobody to write to privately - fall through to the poll.
            self.group_id.session_id.sa_send_poll(
                destination, question, [b['title'] for b in buttons])
            # The gateway records the WhatsApp id on the row it just logged.
            # Keeping it is what lets a vote be matched to the enquiry that
            # asked, rather than to whatever the voter has open.
            # Scoped to this destination and to the last half minute.
            # "Newest outgoing row on the session" also matched a message to
            # another chat, or another enquiry answered in the same second -
            # and then one enquiry owned the other's poll and every later vote
            # went to the wrong person, invisibly.
            sent = self.env['whatsapp.message'].sudo().search(
                [('session_id', '=', self.group_id.session_id.id),
                 ('direction', '=', 'outgoing'),
                 ('phone', '=', destination),
                 ('create_date', '>=', fields.Datetime.subtract(
                     fields.Datetime.now(), seconds=30))],
                order='id desc', limit=1)
            if sent.wa_message_id:
                self._sa_remember_poll(sent.wa_message_id)
            # 'poll' vs 'text' so the caller knows whether the customer got
            # tappable options. It used to return True either way, and the
            # tap-links were then posted every time - on top of a poll that
            # already offered the same choices.
            return 'poll'
        except Exception as err:  # noqa: BLE001
            _logger.warning("Sales Automation: tappable prompt failed in %s "
                            "(%s) - asking as plain text.",
                            self.group_id.name, err)
            choices = ' or '.join('*%s*' % b['title'] for b in buttons)
            # Still False when even the plain text could not be delivered.
            # `_finder_start` reads a falsy answer as "the question never
            # reached them" and keeps the enquiry in the finder rather than
            # sending a generic word to a supplier - returning 'text'
            # unconditionally would have made a failed send look delivered.
            if self._say('%s\n\n%s' % (body, _("Reply %s.", choices))):
                return 'text'
            return False

    def _sa_reply_link(self, text):
        """A tap-link that opens our chat with `text` already written.

        There is no button on this transport that can carry a typed amount.
        `sendButtons` arrives as "This message couldn't load", `sendList` can be
        accepted and then never displayed, and a poll - the one tappable thing
        that does render in a group - has no field for a number. A wa.me link
        is a plain URL in a plain message, so it renders everywhere, and
        tapping it opens the chat with the message already filled in. The
        panel's own signature works this way, so the mechanism is proven here.

        Returns '' when the session has no usable number, so the caller falls
        back to asking for a typed reply rather than offering a link to nobody.
        """
        self.ensure_one()
        # Never in the group. A wa.me link to our own number opens a
        # ONE-TO-ONE chat, so a customer tapping it in the group is moved
        # into a private thread - the very thing this flow had removed
        # everywhere else. The caller's typed fallback keeps the answer where
        # everyone else's is.
        if self._sa_reply_to() == self.group_id.group_jid:
            return ''
        from urllib.parse import quote
        digits = ''.join(
            c for c in (self.group_id.session_id.phone_number or '')
            if c.isdigit())
        if len(digits) < 10:
            return ''
        return 'https://wa.me/%s?text=%s' % (digits, quote(text or ''))

    def _sa_tap(self, label, prefill):
        """One "label: link" line, or the typed instruction when we have no
        number to link to."""
        self.ensure_one()
        link = self._sa_reply_link(prefill)
        if not link:
            return _("%(label)s - reply *%(prefill)s*",
                     label=label, prefill=prefill)
        return '%s\n%s' % (label, link)

    def _sa_deal_options(self, allow_bargain=True):
        """The tappable answers to a price.

        One definition, because these options are offered from four places
        (first quote, stepped counter-offer, final price, and the re-quote
        that answers anything we could not place) and they drifted: two of
        them never offered bargaining at all, so whether a customer could ask
        for a better price with a tap depended on which message they happened
        to be looking at.

        BETTER PRICE is dropped when bargaining is switched off or there is
        no room left - offering a button that can only answer "no" is worse
        than not offering it.
        """
        self.ensure_one()
        options = [{'id': 'sa_yes', 'title': _('ACCEPT')}]
        # A product with its own quantity ranges shows BETTER PRICE only
        # inside a range, and only once (sa_qty_bargain.py).
        if (allow_bargain and self._settings().bargain_enabled
                and self._sa_qty_bargain_allowed()):
            options.append({'id': 'sa_bargain', 'title': _('BETTER PRICE')})
        options.append({'id': 'sa_no', 'title': _('CANCEL')})
        return options

    def _sa_wants_better_price(self, text):
        """True when the customer tapped (or typed) the bargain option.

        A poll answers with the visible label, a button with its id, so both
        have to be recognised. Checked before `_read_yes_no` and before the
        offer parser: "BETTER PRICE" is not a yes, not a no, and the word
        "price" in a message has been read as a product name before.
        """
        stripped = (text or '').strip().lower().strip('.!*? ')
        if stripped == 'sa_bargain':
            return True
        # The label travels with its emoji on some clients.
        cleaned = ''.join(ch for ch in stripped
                          if ch.isalnum() or ch.isspace()).strip()
        return cleaned in ('better price', 'best price', 'bargain',
                           'lower price', 'cheaper')

    def _ask_their_price(self):
        """They tapped BETTER PRICE: give one, or say the price is final.

        This used to answer with "what price would you like? - like 594":
        a question in reply to a request for a lower price, with an invented
        example that read as an offer. The tap is the bargaining move, so it
        steps the price down exactly as a typed "can you reduce" does -
        same step, same floor, same "that is our final price" when the
        steps are spent. A customer who wants to name a number still can;
        typed numbers keep their own path.
        """
        self.ensure_one()
        return self._counter_offer('', tapped=True)

    def _sa_price_taps(self, price, accept_only=False):
        """What a customer can do about a price, as tap-links.

        Each carries the enquiry code, so the reply says which deal it belongs
        to without the customer typing anything. That is the whole point: in a
        group where three people asked eighty-odd questions in two days, a bare
        "30" could belong to any of them - and did get attached to the wrong
        one more than once.
        """
        self.ensure_one()
        accept = self._sa_tap(_("\u2705 Accept this price"),
                              '#%s ACCEPT' % self.ref_code)
        if accept_only:
            return accept
        offer = self._sa_tap(
            _("\U0001F4AC Offer your own price"),
            '#%s %.2f' % (self.ref_code, price))
        return accept + '\n\n' + offer

    def _sa_dm_target(self):
        """The requester's own chat, when there is one to write to.

        A LID-hidden requester has no reachable number - WhatsApp gives us an
        opaque id instead - so there is nothing to open a private chat with,
        and the caller has to stay in the group.
        """
        self.ensure_one()
        if self.requester_is_lid or not self.requester_phone:
            return ''
        return self.requester_phone

    def _sa_reply_to(self):
        """Where an answer belongs: the chat the question came from.

        A customer who taps a link is answering in their own chat, and replying
        to the group there would put their price in front of everyone else and
        leave them with silence.
        """
        self.ensure_one()
        return self.env.context.get('sa_reply_to') or self.group_id.group_jid

    def _sa_note_moved_to_dm(self):
        """Tell the group once that the thread moved, so it is not silent.

        Once per enquiry, not once per question: the customer is asked five or
        six things before an order exists, and a line in the group for each of
        them would be worse than saying nothing at all.
        """
        self.ensure_one()
        # Nothing moves to a private chat any more, so there is nothing to
        # announce. Kept as a no-op rather than deleted: several callers say
        # it, and a missing method is a harder failure than a quiet one.
        return False

    def _sa_tell_bystander(self, message):
        """Say whose question that was, instead of ignoring the tap.

        Refusing a bystander's vote is right - it is how one person stopped
        cancelling another person's deal - but doing it in silence looks
        identical to being broken. A tester tapped the ACCEPT in front of her,
        which belonged to somebody else's quote, and was left with a
        confirmation for a different product entirely and no explanation.

        Posted once per person per minute: everyone in a group can see and tap
        every poll, so a lively group could otherwise produce a burst of these.
        """
        self.ensure_one()
        who = (message.participant_phone or message.participant_lid or '')
        if not who:
            return False
        if not self.env['sa.outbox.guard'].sudo().claim(
                'bystander|%s|%s' % (self.group_id.id, who), 60):
            return False
        name = (message.push_name or '').strip()
        if not name or name.isdigit():
            name = '+...%s' % who[-4:] if who else ''
        owner = (self.requester_name or '').strip() or _("someone else")
        body = _("\U0001F44B That price was for *%(owner)s*. Send me the "
                 "product you need and I'll get you your own price.",
                 owner=owner)
        if name:
            body = '*%s* \U0001F447\n\n%s' % (name, body)
        try:
            self.group_id.session_id.send_message(
                self.group_id.group_jid, body)
        except Exception as err:  # noqa: BLE001 - never break the routing
            _logger.warning("Sales Automation: could not answer a bystander "
                            "vote in %s: %s", self.group_id.name, err)
        return True

    _SA_POLL_HISTORY = 8

    def _sa_poll_answered(self, poll_ref, text=''):
        """True when this poll was already acted on. A vote changed later
        on WhatsApp arrives as a new vote; it is not a new decision."""
        self.ensure_one()
        poll_ref = (poll_ref or '').strip()
        return bool(poll_ref) and poll_ref in [
            p for p in (self.answered_poll_wa_ids or '').split(',') if p]

    def _sa_mark_poll_answered(self, poll_ref):
        self.ensure_one()
        poll_ref = (poll_ref or '').strip()
        if not poll_ref:
            return False
        known = [p for p in (self.answered_poll_wa_ids or '').split(',') if p]
        if poll_ref not in known:
            known.insert(0, poll_ref)
            self.sudo().write({'answered_poll_wa_ids': ','.join(known[:20])})
        return True

    def _sa_tell_poll_spent(self, text):
        """Once, per poll: the first answer stands."""
        self.ensure_one()
        try:
            self._say(_("\u2139\ufe0f That question was already answered - "
                        "the first choice stands. To change anything, just "
                        "type it (for example *cancel*)."))
        except Exception as err:  # noqa: BLE001 - a note, never a failure
            _logger.info("Sales Automation: poll-spent note failed: %s", err)
        return False

    def _sa_remember_poll(self, wa_id):
        """Keep this poll id, and the last few before it."""
        self.ensure_one()
        wa_id = (wa_id or '').strip()
        if not wa_id:
            return False
        known = [p for p in (self.poll_wa_ids or '').split(',') if p]
        if wa_id in known:
            known.remove(wa_id)
        known.insert(0, wa_id)
        self.sudo().write({
            'poll_wa_id': wa_id,
            'poll_wa_ids': ','.join(known[:self._SA_POLL_HISTORY]),
        })
        return True

    def _sa_remember_vendor_poll(self, phone):
        """Keep the id of the YES/NO poll just sent to `phone`.

        A vote names the poll it answers, and that is the only thing that
        tells a supplier's YES from a customer's when one phone is both -
        which is exactly what put a payment poll in a supplier's chat.
        """
        self.ensure_one()
        digits = ''.join(ch for ch in str(phone or '') if ch.isdigit())
        domain = [('direction', '=', 'outgoing'),
                  ('create_date', '>=', fields.Datetime.subtract(
                      fields.Datetime.now(), seconds=30))]
        if digits:
            domain.append(('phone', 'like', digits[-9:]))
        sent = self.env['whatsapp.message'].sudo().search(
            domain, order='id desc', limit=1)
        wa_id = (sent.wa_message_id or '').strip()
        if not wa_id:
            return False
        known = [p for p in (self.vendor_poll_wa_ids or '').split(',') if p]
        if wa_id in known:
            known.remove(wa_id)
        known.insert(0, wa_id)
        self.sudo().write({'vendor_poll_wa_ids': ','.join(known[:16])})
        return True

    @api.model
    def _sa_by_vendor_poll(self, poll_ref, digits):
        """The enquiry whose supplier poll this vote answers, or empty.

        Scoped to the voter too: the poll id says which question, the phone
        says it was one of the suppliers we put it to.
        """
        poll_ref = (poll_ref or '').strip()
        tail = (digits or '')[-9:]
        if not poll_ref or len(tail) < 8:
            return self.browse()
        # Both spellings: `phone` as typed ('+91 93612 19598' has a space
        # inside its last nine digits and never matched) and the sanitized
        # E.164 form, which is what `_find_partner` matches on.
        return self.sudo().search(
            [('vendor_poll_wa_ids', 'like', poll_ref),
             '|', ('sourcing_vendor_ids.phone', 'like', tail),
             ('sourcing_vendor_ids.phone_sanitized', 'like', tail)],
            order='id desc', limit=1)

    @api.model
    def _sa_by_poll(self, poll_ref):
        """The enquiry that asked this poll, however long ago."""
        poll_ref = (poll_ref or '').strip()
        if not poll_ref:
            return self.browse()
        found = self.sudo().search([('poll_wa_id', '=', poll_ref)], limit=1)
        if found:
            return found
        # An earlier question of an enquiry that has since asked another.
        return self.sudo().search(
            [('poll_wa_ids', 'like', poll_ref)], order='id desc', limit=1)

    def _sa_known_name(self):
        """The sender's real name, or ''. Filled in by sa_customer_name."""
        return ''

    def _sa_mention_target(self):
        """The digits to @mention, or '' when the member is hidden.

        A member WhatsApp addresses only by @lid has no phone JID at all, so
        they can never be mentioned - the name prefix is all they get.
        """
        self.ensure_one()
        if self.requester_is_lid:
            return ''
        return ''.join(ch for ch in (self.requester_phone or '')
                       if ch.isdigit())

    def _sa_addressed(self, body):
        """Address a message posted to a shared group to one person.

        A group is not a private chat. When two people are enquiring at once
        both see "Which one do you need?" with nothing to say whose it is, so
        one of them answers the other's question - and because every lookup is
        scoped to the sender, that answer matches nothing and is dropped in
        silence.

        A real @mention is used where the member has a visible number: it
        highlights and it notifies, which a bold name does not. The ref rides
        along on every message so the customer can always answer `#G6 yes`
        instead of hunting for the right poll.
        """
        self.ensure_one()
        ref = self.ref_code or self.id
        mention = self._sa_mention_target()
        # The customer's real name where we know it (website account, the
        # order's contact) - a number alone is not a person (owner, 8 Oct).
        known = self._sa_known_name()
        if mention:
            # The token is what WhatsApp highlights; the `mentioned` array
            # sent alongside is what makes it a mention. Both are required,
            # so the name goes after the token, never instead of it.
            if known:
                return '@%s - %s \u00b7 Ref %s \U0001F447\n\n%s' % (mention, known, ref, body)
            return '@%s \u00b7 Ref %s \U0001F447\n\n%s' % (mention, ref, body)
        name = known or (self.requester_name or '').strip()
        if not name or name.isdigit():
            # A group that addresses members by @lid gives us a numeric
            # push name, which is no more use to a reader than no name.
            tail = (self.requester_phone or '')[-4:]
            name = ('+...%s' % tail) if tail else ''
        if not name:
            # Last resort, and it matters more than it reads: the gateway
            # drops a message identical to one sent to the same chat in the
            # last five minutes, and in a group the chat is the group. Two
            # hidden members asking for the same product would otherwise
            # produce the same bytes, and the second would never be posted.
            lid = (self.requester_lid or '')[-4:]
            name = ('#%s' % lid) if lid else ''
        if not name:
            # Nothing to address it with, but the ref still has to be
            # there: two hidden members asking for the same product
            # would otherwise produce identical bytes and the gateway
            # would drop the second.
            return 'Ref %s \U0001F447\n\n%s' % (ref, body)
        return '*%s* \u00b7 Ref %s \U0001F447\n\n%s' % (name, ref, body)

    # ----------------------------------------------------------
    # The customer's own clock
    # ----------------------------------------------------------
    def _sa_reply_minutes(self):
        """How long the customer gets, or 0 when the timeout is off."""
        self.ensure_one()
        try:
            return max(0, int(self._settings().customer_reply_minutes or 0))
        except Exception:  # noqa: BLE001 - a missing setting must not mute us
            return 0

    def _sa_stamp_asked(self):
        """Restart the customer's clock.

        Called from `_say` and `_ask`, which between them are every message
        this module sends a customer - so there is no question anywhere that
        can start a silent deadline. Stamped whether or not the send
        succeeded: what it records is that we asked, and a send that failed
        is not a customer who ignored us.
        """
        self.ensure_one()
        minutes = self._sa_reply_minutes()
        now = fields.Datetime.now()
        self.sudo().write({
            'customer_asked_on': now,
            'customer_deadline': (fields.Datetime.add(now, minutes=minutes)
                                  if minutes else False),
        })

    def _sa_deadline_note(self):
        """The remaining time, to print in the question we are about to ask.

        WhatsApp has no live timer - a message is fixed once it is sent, so
        nothing on that side can tick. What it can do is say how long is left
        at the moment of asking, and because every message restarts the clock
        this line is always true when it arrives. The counter screen is where
        a genuinely running clock lives.
        """
        self.ensure_one()
        minutes = self._sa_reply_minutes()
        if not minutes:
            return ''
        return _("\u23F3 _Please reply within %s min_", minutes)

    def _cron_expire_customer(self):
        """Close enquiries the customer stopped answering.

        Only states where the ball is genuinely in the customer's court.
        `sourcing` and `awaiting_vendor_pick` are excluded on purpose: those
        are waiting on a supplier or on the shop, and they have deadlines of
        their own.
        """
        # Read the setting, not just the stamped deadlines: switching the
        # timeout off has to stop closures immediately. A deadline already on
        # a row is only cleared the next time we message that customer, and an
        # enquiry sitting in `quoted` with nobody typing never gets that
        # chance - so without this, "off" still closed deals for a while.
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        if not (settings.customer_reply_minutes or 0):
            return True
        now = fields.Datetime.now()
        waiting = self.search([
            ('state', 'in', ('awaiting_confirm', 'finding', 'quoted',
                             'negotiating', 'awaiting_qty',
                             'awaiting_order_confirm')),
            ('customer_deadline', '!=', False),
            ('customer_deadline', '<=', now),
        ])
        for request in waiting:
            name = (request.product_id.name or request.ai_search_term
                    or request.raw_text or _("that item"))
            # Said before the drop: `_say` is addressed and `_drop` may close
            # the conversation the mention is built from.
            request._say(_(
                "\u23F0 I'm closing this one for now - *%(product)s* "
                "(_Ref %(ref)s_).\n\n"
                "Just message me again when you're ready and I'll pick it "
                "straight back up. \U0001F44D",
                product=name, ref=request.ref_code or request.id))
            request._drop('customer_timeout')
        if waiting:
            _logger.info("Sales Automation: closed %d enquiry(ies) the "
                         "customer stopped answering.", len(waiting))
        return True

    def _say(self, body, addressed=True):
        """Post in the customer group. A failed post must not lose the state."""
        self.ensure_one()
        self._sa_stamp_asked()
        destination = self._sa_reply_to()
        # In a one-to-one chat there is nobody to tell apart, so the name
        # prefix is noise.
        if addressed and destination == self.group_id.group_jid:
            body = self._sa_addressed(body)
        if not self.env['sa.outbox.guard'].sudo().claim(
                '%s|%s|%s' % (self.env.context.get('sa_trigger_msg') or 0,
                              destination, body)):
            _logger.info("Sales Automation: already posted this to %s moments "
                         "ago - not repeating it", destination)
            return True
        try:
            mention = (self._sa_mention_target()
                       if destination == self.group_id.group_jid else '')
            sent = self._sa_send_once_more(destination, body, mention)
            self._sa_tag_last_outgoing(destination)
            return bool(sent) or True
        except Exception as err:  # noqa: BLE001
            _logger.warning("Sales Automation: could not post in group %s: %s",
                            self.group_id.name, err)
            return False

    def _sa_send_once_more(self, destination, body, mention):
        """Send; if the gateway refused it as a duplicate, send it again
        with a zero-width space on the end.

        The gateway drops a message identical to one sent to the same chat
        in the last few minutes and returns False. A re-asked question
        ("How many?", "What is your address?") is often identical to the
        first ask, and the customer was left in silence (Ref 2J, 30 Sep
        2026). The extra character is invisible to the reader and different
        bytes to the gateway. Never raises for the retry.
        """
        session = self.group_id.session_id

        def _send(text):
            if mention:
                return session.sa_send_text_mentioning(destination, text, mention)
            return session.send_message(destination, text)

        sent = _send(body)
        if sent:
            return sent
        _logger.info("Sales Automation: gateway refused the message to %s "
                     "(duplicate?) - sending it once more with a variation",
                     destination)
        try:
            return _send(body + '\u200b')
        except Exception as err:  # noqa: BLE001 - the first refusal stands
            _logger.warning("Sales Automation: retry to %s failed: %s",
                            destination, err)
            return False

    def _seed_tracker_handoff(self, product, conversation, price):
        """Hand the thread to the tracker's engine at the price we quoted.

        The tracker decides where it is in a conversation by reading the most
        recent sent reply. A row typed `price_negotiate` carrying our number in
        `offered_price` drops it straight into bargaining at the right price,
        so the customer's next direct message - "yes", or "can you do less" -
        is understood without a word of new state-machine code.
        """
        self.ensure_one()
        if self.requester_is_lid or not self.requester_phone:
            return False
        # No longer gated on `handoff_dm`: a vendor-priced item that the
        # catalogue does not carry still needs a product for the order to
        # hang off, and the conversation no longer moves anywhere.
        if not product:
            # An unlisted item, priced by a vendor. The group has just been
            # told "I've sent you the price privately", so a product has to
            # exist for the private thread to hang off - otherwise that line
            # is a lie and the customer hears nothing more. Creating it now
            # rather than at acceptance is the trade: the catalogue gains a
            # vendor-priced item even if this customer walks away.
            try:
                # A savepoint: a failed INSERT otherwise leaves the whole
                # transaction aborted, and the request dies later with
                # "current transaction is aborted" after the customer has
                # already been sent the price.
                with self.env.cr.savepoint():
                    self._create_product_from_enquiry()
                product = self.product_id
            except Exception as err:  # noqa: BLE001
                _logger.error("Sales Automation: could not create a product "
                              "for enquiry %s: %s", self.id, err)
        if not product:
            return False

        # Nothing is handed over. The row this used to create typed the
        # thread `price_negotiate`, which made the customer's next direct
        # message to the business number get read as a bargaining move on
        # this deal - a private path that ran even with `handoff_dm` off.
        # The product above is still worth creating; the seed is not.
        return True

        employee_session = self.group_id.employee_session_id  # noqa: F841
        AutoReply = self.env['wa.auto.reply'].sudo()

        if self.group_id.handoff_dm:
            detail = _(
                "Hi! You asked about this in *%(group)s* 👇\n\n📦 *%(product)s*\n"
                "💰 *Price:* %(price).2f\n\nReply *yes* to order, or tell me "
                "your price and I'll see what I can do. 🙂\n\n"
                "_Ref %(ref)s_",
                group=self.group_id.name, product=product.name, price=price,
                ref=self.ref_code or self.id)
            if not self.env['sa.outbox.guard'].sudo().claim(
                    '%s|dm|%s|%s' % (
                        self.env.context.get('sa_trigger_msg') or self.id,
                        self.requester_phone, detail)):
                self.state = 'handed_off'
                return True
            try:
                AutoReply._send_product_with_image(
                    employee_session, self.requester_phone, product, detail)
                self.state = 'handed_off'
                self._sa_dm_yes_no(employee_session, product, price)
            except Exception as err:  # noqa: BLE001
                _logger.error("Sales Automation: private handoff to %s failed: "
                              "%s", self.requester_phone, err)
                self.write({'error': str(err)[:2000]})
        else:
            detail = _("Quoted in *%(group)s* at %(price).2f",
                       group=self.group_id.name, price=price)

        AutoReply.create({
            'conversation_id': conversation.id if conversation else False,
            'employee_session_id': employee_session.id,
            'phone': self.requester_phone,
            'customer_message': self.raw_text,
            'reply_message': detail,
            'matched_products': product.name,
            'selected_product_id': product.id,
            'reply_type': 'price_negotiate',
            'offered_price': price,
            'status': 'sent',
        })
        return True

    def _sa_dm_yes_no(self, employee_session, product, price):
        """Tappable Yes / No under the private quote.

        Sent as its own message after the text, not instead of it: an
        interactive message never renders on WhatsApp Web, so the text is
        what a desktop customer reads and types against, and the buttons are
        what a phone customer taps. The ids are the words the tracker already
        understands - a tap arrives as "yes" or "no", exactly as if typed.
        """
        self.ensure_one()
        # A poll, not buttons: quick-reply buttons arrive on WhatsApp Web as
        # "This message couldn't load", and a poll is the one tappable thing
        # this transport renders everywhere. The vote comes back as the
        # label, which the webhook turns into ordinary text.
        try:
            employee_session.session_id.sa_send_poll(
                self.requester_phone,
                _("Order *%(product)s* at %(price).2f?  (Ref %(ref)s)",
                  product=product.name, price=price,
                  ref=self.ref_code or self.id),
                [_('Yes'), _('No')])
        except Exception as err:  # noqa: BLE001 - the text already went
            _logger.warning("Sales Automation: Yes/No poll to %s not sent: "
                            "%s", self.requester_phone, err)
        return True

    def _drop(self, reason):
        self.ensure_one()
        # A closed enquiry must not keep ringing on the counter screen: the
        # "needs a price" flags go with the state (DUBAI_TEST #22, 30 Sep).
        self.write({'sa_price_stalled': False, 'sa_price_choice_pending': False,
                    'state': 'dropped', 'drop_reason': reason})
        _logger.info("Sales Automation: enquiry %s dropped (%s) - %r",
                     self.id, reason, (self.raw_text or '')[:60])
        if reason in ('not_product', 'low_confidence'):
            self._sa_acknowledge_chatter()
        return False

    def _sa_acknowledge_chatter(self):
        """Answer small talk, if this database has asked for that.

        Off by default. A sales group is mostly members talking to each other,
        and a bot that replies to all of it is worse than one that says
        nothing - but in a quiet group silence reads as broken, which is how
        this was reported: a customer said \"Have a nice day\" after a failed
        price check and got no response at all.

        Rate limited to one per person per minute, so a burst of chat cannot
        become a burst of replies, and alternated so two in a row are never
        word-for-word identical - the gateway drops any message matching one
        it sent to the same place in the last five minutes.
        """
        self.ensure_one()
        settings = self._settings()
        if settings.chatter_action != 'reply':
            return False
        body = (settings.chatter_reply_text or '').strip()
        if not body:
            return False
        who = self.requester_phone or self.requester_lid or 'anon'
        guard = self.env['sa.outbox.guard'].sudo()
        if not guard.claim('chatter|%s|%s' % (self.group_id.id, who), 60):
            _logger.info("Sales Automation: already acknowledged chat from %s "
                         "in the last minute", who)
            return False
        if not guard.claim('chatter-alt|%s|%s' % (self.group_id.id, who), 600):
            body = '%s %s' % (body, _("Just say the word if you need "
                                      "anything."))
        self._say(body)
        return True

    # ----------------------------------------------------------
    # Contact resolution
    # ----------------------------------------------------------
    def _ensure_conversation(self):
        """The tracker's own thread for this requester, or an empty recordset."""
        self.ensure_one()
        if self.requester_is_lid or not self.requester_phone:
            return self.env['wa.conversation']
        employee_session = self.group_id.employee_session_id
        if not employee_session:
            # A fresh database with no WA Tracker employee session yet: make
            # one rather than fail - the tracker cannot open a thread without
            # it, and every later step (quote, order) needs the thread.
            try:
                employee_session = self.group_id._sa_ensure_employee_session()
            except Exception as err:  # noqa: BLE001 - pricing still works
                _logger.warning("Sales Automation: could not create an "
                                "employee session for group %s: %s",
                                self.group_id.name, err)
                employee_session = self.env['wa.employee.session']
        if not employee_session:
            return self.env['wa.conversation']
        conversation = self.env['wa.conversation'].sudo()._get_or_create(
            employee_session, self.requester_phone)
        if conversation:
            self.write({
                'conversation_id': conversation.id,
                'requester_partner_id': conversation.partner_id.id or False,
            })
        return conversation or self.env['wa.conversation']

    def _is_existing_contact(self, conversation):
        """Wholesale or retail, decided exactly as the tracker decides it."""
        if not conversation:
            return False
        return self.env['wa.auto.reply'].sudo()._resolve_is_existing_contact(
            conversation)

    # ----------------------------------------------------------
    # Availability and price
    # ----------------------------------------------------------
    def _sa_stock_rule(self, product, fresh=False):
        """(available, in_stock, sellable) for this enquiry's product.

        The product's own settings decide, the same way the website does:
          * not tracked in stock (is_storable off): never short - the old code
            read qty_available, which is always 0 for those, so every such
            order went to vendors although the shop had it on the shelf;
          * tracked: free stock (on hand minus already reserved), summed over
            the variants - or the exact variant the customer picked - read in
            the company the order will belong to;
          * tracked and short: sellable only when the product allows selling
            out of stock (website_sale_stock's switch; without that module the
            answer is yes, which is what happened before).
        `fresh` drops the cached quantities first: they are cached for the
        whole transaction, and the re-check before an order must see a unit
        sold since the quote.
        """
        self.ensure_one()
        group = self.group_id
        company = self.finder_company_id or self._company_for(group)
        wanted = self.qty or 1.0
        picked = getattr(self, 'sa_variant_id', None)
        variants = picked if picked else product.product_variant_ids
        if not variants:
            return 0.0, False, True
        if not getattr(product, 'is_storable', False):
            return wanted, True, True
        field = 'virtual_available' if group.use_virtual_stock else (
            'free_qty' if 'free_qty' in variants._fields else 'qty_available')
        vs = variants.sudo().with_company(company)
        if fresh:
            vs.invalidate_recordset([field])
        available = sum((v[field] or 0.0) for v in vs)
        in_stock = available >= wanted and available > 0
        allowed = True
        if 'allow_out_of_stock_order' in product._fields:
            allowed = bool(product.allow_out_of_stock_order)
        return available, in_stock, (in_stock or allowed)

    def _assess_availability(self, product, fresh=False):
        """Set stock_status and available_qty; returns whether it may be sold."""
        self.ensure_one()
        available, in_stock, sellable = self._sa_stock_rule(product, fresh=fresh)
        self.available_qty = available
        self.stock_status = 'in_stock' if in_stock else 'on_order'
        return sellable

    def _sa_say_unavailable(self, product):
        """Short, and the product may not be sold short."""
        self.ensure_one()
        name = product.display_name or self.ai_search_term or _("that")
        left = int(self.available_qty or 0)
        if left > 0:
            self._say(_("Sorry, only *%(n)d* of *%(product)s* left right now, not the %(qty)d you asked for. \U0001F64F",
                        n=left, product=name, qty=int(self.qty or 1)))
        else:
            self._say(_("Sorry, *%(product)s* is out of stock right now. \U0001F64F", product=name))
        return self._drop('unavailable')

    @api.model
    def _sa_unsellable_domain(self):
        """Domain on product.template that leaves out products which may not
        be sold short and have no free stock. Empty when the website's
        out-of-stock switch is not installed, so nothing changes elsewhere."""
        Tmpl = self.env['product.template']
        if 'allow_out_of_stock_order' not in Tmpl._fields or 'free_qty' not in self.env['product.product']._fields:
            return []
        in_stock = self.env['product.product'].sudo().search([('free_qty', '>', 0)]).mapped('product_tmpl_id').ids
        return ['|', '|', ('is_storable', '=', False), ('allow_out_of_stock_order', '=', True), ('id', 'in', in_stock)]

    @api.model
    def _catalog_price(self, product, is_existing_contact):
        """The tracker's retail/wholesale rule, minus its zero-price hole.

        The tracker quotes `wa_retail_price` to anyone it does not recognise,
        and that field ships with no default - so an unconfigured product is
        offered at 0.00 and invoiced at 0.00. Falling back to the sale price
        keeps the same intent (retail sees the higher number where one is set)
        without ever quoting nothing.
        """
        if is_existing_contact:
            return product.list_price
        return product.wa_retail_price or product.list_price

    def _best_vendor(self, product):
        """Cheapest currently-valid vendor line for this product."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        company = self._company_for(self.group_id)
        return self.env['product.supplierinfo'].sudo().search([
            ('product_tmpl_id', '=', product.id),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
            '|', ('date_start', '=', False), ('date_start', '<=', today),
            '|', ('date_end', '=', False), ('date_end', '>=', today),
        ], order='sequence, price', limit=1)

    def _converted(self, amount, from_currency):
        self.ensure_one()
        target = self.currency_id or self.env.company.currency_id
        if not from_currency or from_currency == target:
            return amount
        return from_currency._convert(
            amount, target, self._company_for(self.group_id),
            fields.Date.context_today(self))

    # ----------------------------------------------------------
    # Housekeeping
    # ----------------------------------------------------------
    @api.model
    def _cron_expire_stale(self):
        """Close enquiries nobody came back to.

        The tracker only restores conversation context for 15 minutes, so a
        requester who replies a day later starts a fresh search anyway. Leaving
        these open would make the list read as a pipeline that it is not.
        """
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), hours=24)
        stale = self.search([
            ('state', 'in', ('awaiting_confirm', 'finding', 'quoted',
                             'answered', 'handed_off')),
            ('create_date', '<', cutoff),
        ])
        if stale:
            stale.write({'state': 'dropped', 'drop_reason': 'stale'})
            _logger.info("Sales Automation: closed %d abandoned enquiry(ies).",
                         len(stale))

    def action_view_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.order_id.id,
            'view_mode': 'form',
        }

    def action_view_conversation(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wa.communication.log',
            'name': _('Chat - %s', self.requester_phone or ''),
            'view_mode': 'list,form',
            'domain': [('conversation_id', '=', self.conversation_id.id)],
        }

    def action_close_sourcing_now(self):
        """Stop waiting and quote from whatever has arrived."""
        self.ensure_one()
        return self._close_sourcing()
