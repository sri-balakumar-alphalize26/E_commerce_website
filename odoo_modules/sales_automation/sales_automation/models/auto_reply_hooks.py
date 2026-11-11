"""Three small hooks into the tracker's selling engine.

The engine itself is reused whole - this module never reimplements bargaining,
quantity parsing, order creation, delivery, payment or invoicing. These hooks
only correct what the engine cannot know about a group-sourced enquiry.

1. `_handle_bargain` - the tracker floors every negotiation at the product's
   sale price. For something quoted from a vendor because it is out of stock,
   the sale price is not the floor; the vendor's cost plus a margin is.
2. `create` - the tracker drops a negotiated price when the customer accepts
   with a plain "yes" instead of bargaining, and then invoices at catalog
   price. Carrying it forward keeps the deal that was actually struck.
3. `_create_sale_order` - links the resulting order back to the enquiry, so a
   group message and the order it produced can be read as one story.
"""

import logging
import re

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class WaAutoReply(models.Model):
    _inherit = 'wa.auto.reply'

    # ----------------------------------------------------------
    # 1. Cost-based floor for out-of-stock quotes
    # ----------------------------------------------------------
    def _handle_bargain(self, session, prev_reply, stripped, is_existing_contact):
        request = self._sa_request_for(prev_reply)
        if not request or not request.vendor_price:
            return super()._handle_bargain(
                session, prev_reply, stripped, is_existing_contact)

        product = prev_reply.selected_product_id
        floor = request.vendor_price * (
            1.0 + (request._settings().min_margin_percent or 0.0) / 100.0)
        # Once a price has been settled in the group, that is the floor. Left
        # at cost-plus-margin the engine kept haggling after the deal was
        # done: agreed 550.00, and the very next message offered 525.00 -
        # a discount the customer never asked for, off our own margin.
        if request.agreed_price:
            floor = max(floor, request.agreed_price)
        opening = max(request.quoted_price or floor, floor)

        accept = stripped in (
            'yes', 'y', 'ok', 'okay', 'confirm', 'accept', 'accept_price',
            'sure', 'deal', 'done', 'buy', 'order', 'proceed',
        )
        cancel = stripped in ('no', 'cancel', 'stop', 'nevermind', 'never mind')

        if accept:
            deal = prev_reply.offered_price or opening
            return (
                "Perfect! \U0001F91D Deal at *%.2f* for *%s*.\n\n"
                "How many units would you like? Reply with the *quantity* "
                "(e.g. 1, 2, 5)." % (deal, product.name),
                'quantity_ask', deal,
            )
        if cancel:
            return ("No problem! \U0001F60A Type another product name to "
                    "search anytime.", 'general', 0.0)

        current = prev_reply.offered_price or opening
        target = self._parse_price(stripped)
        if target is None:
            offer = max(floor, round((current + floor) / 2.0, 2))
        elif target >= current:
            offer = current
        else:
            offer = max(floor, target)

        if offer <= floor:
            reply = (
                "\U0001F4E6 *%s*\n\U0001F4B0 Best I can do: *%.2f* \U0001F64F\n\n"
                "This item comes in on order, so that is our final price. "
                "Reply *yes* to confirm." % (product.name, offer)
            )
        else:
            reply = (
                "\U0001F4E6 *%s*\n\U0001F4B0 Special price for you: *%.2f* "
                "\U0001F389\n\nReply *yes* to accept, or send your price to "
                "negotiate further." % (product.name, offer)
            )
        return reply, 'price_negotiate', offer

    # ----------------------------------------------------------
    # 2. Do not lose the agreed price on a plain "yes"
    # ----------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Carry a negotiated price into the quantity step.

        The tracker sets `offered_price` when the bargain branch produces a
        `quantity_ask`, but not when a plain "yes" on a product detail produces
        one. `_create_sale_order` then reads `offered_price` off that row, finds
        nothing, and falls back to the catalog price - so a customer who simply
        agreed to the offered number is invoiced at a different one.
        """
        for vals in vals_list:
            if vals.get('reply_type') != 'quantity_ask' or vals.get('offered_price'):
                continue
            conversation_id = vals.get('conversation_id')
            product_id = vals.get('selected_product_id')
            if not conversation_id or not product_id:
                continue
            previous = self.search([
                ('conversation_id', '=', conversation_id),
                ('selected_product_id', '=', product_id),
                ('offered_price', '>', 0),
            ], order='create_date desc, id desc', limit=1)
            if previous:
                vals['offered_price'] = previous.offered_price
        return super().create(vals_list)

    # ----------------------------------------------------------
    # 3. Link the order back to the enquiry that started it
    # ----------------------------------------------------------
    @api.model
    def _sa_for_company(self, company):
        """This model, set to raise its next sale order in `company`.

        The tracker writes the employee session's Order Company onto every
        order it makes. One session serves every group, so a group selling
        for another company had its orders booked in the session's instead.
        The tracker is shared by every database on the server and is left
        alone; `sale.order.create` here reads the context key instead.
        """
        if not company:
            return self
        return self.with_company(company).with_context(sa_order_company_id=company.id)

    def _create_sale_order(self, session, conv, product_template, qty,
                           is_existing_contact, unit_price=None):
        request = self.env['sa.group.request']
        if conv:
            request = request.sudo().search([
                ('conversation_id', '=', conv.id),
                ('product_id', '=', product_template.id),
                ('state', 'in', ('answered', 'handed_off')),
            ], order='id desc', limit=1)
        engine = self
        if request and not self.env.context.get('sa_order_company_id'):
            # The quantity was answered in the private chat after a group
            # quote: the order is still the group's.
            engine = self._sa_for_company(request._sa_order_company())
        order = super(WaAutoReply, engine)._create_sale_order(
            session, conv, product_template, qty, is_existing_contact,
            unit_price=unit_price)
        if not order or not conv:
            return order
        order = order.with_env(self.env)
        if request:
            request.write({'order_id': order.id, 'state': 'order_created'})
            order.sudo().sa_group_request_id = request.id
            _logger.info("Sales Automation: enquiry %s became order %s",
                         request.id, order.name)
        return order

    # ----------------------------------------------------------
    # A typo with a digit in it is not a quantity
    # ----------------------------------------------------------
    # Entries in the tracker's autocorrect table that are ordinary English
    # words. That table is for *voice transcripts* - "fai" heard as five - and
    # applying it to typed text made "tree" a quantity of 3. The customer had
    # typed a word; the reply that followed talked about matching products,
    # because this parser had already said the quantity was fine and stepped
    # aside.
    #
    # Refusing them costs one more round trip. Accepting them puts a number
    # the customer never wrote onto a quotation, so the asymmetry decides it.
    _SA_WORD_LOOKALIKES = frozenset((
        'tree', 'too', 'fore', 'fur', 'fir', 'sec', 'thee', 'tue', 'si',
        'tow', 'on', 'ine', 'fie',
    ))

    def _parse_quantity(self, text):
        """Reject junk that merely happens to contain a digit.

        The tracker pulls the first run of digits out of anything it is given,
        so "A4" was read as 4 and "Aaa5" as 5 - both accepted in silence and
        put on a quotation. A real quantity stands on its own ("5", "i want 5",
        "5 pcs") or is spelled out ("five units"); digits welded to letters are
        a mistyped message, and the customer should be asked again.

        Overridden here rather than in the tracker, which every database on
        this server shares.
        """
        qty = super()._parse_quantity(text)
        if not qty or qty <= 0:
            return None
        # The tracker reads digits and ignores the point, so "1.5" came back
        # as 1: the customer asked for one and a half and was given one, with
        # nothing said about it. These are chargers and phone parts - they do
        # not come in halves.
        # Any number of dots, and spaces around them: "4..6" and
        # "4. 6" are the same mistake as "4.6", and one dot was
        # all this matched.
        if re.search(r'(?<![a-z0-9])\d+(?:\s*\.\s*)+\d+', text or ''):
            _logger.info("Sales Automation: %r is not a whole quantity",
                         (text or '')[:24])
            return None
        ceiling = self.env['sa.ai.settings'].sudo().get_settings(
            ).max_order_quantity or 0
        if ceiling and qty > ceiling:
            # Nobody buys a hundred thousand charging flexes over WhatsApp.
            # Without a ceiling that went straight onto a quotation for
            # 2,808,000 with nothing said about it.
            _logger.info("Sales Automation: refused a quantity of %s (limit "
                         "%s)", qty, ceiling)
            return None
        cleaned = (text or '').strip().lower()
        # A digit run that nothing alphanumeric runs into: "5", "5pcs" and
        # "want 5" qualify; the 4 in "a4" and the 5 in "aaa5" do not.
        # No symbols anywhere. Anchoring on "not preceded by a letter or
        # digit" let "@3" through because @ is neither, and requiring the
        # digit to start a word would still have taken "6@" and "@ 6".
        # A quantity is digits, or a word, with nothing else attached.
        if re.search(r'[^0-9A-Za-z\s.,]', cleaned):
            _logger.info("Sales Automation: %r is not a quantity - symbols",
                         (text or '')[:24])
            return None
        # A number spelled out *and* written in digits, in one message.
        # "Five 4" is either five or four and there is no way to tell;
        # the tracker took the digit, so it was quietly read as 4 and
        # carried straight through to the order summary. "Five 5"
        # agrees with itself but is no clearer about intent, so both are
        # sent back. Alphabetic tokens only, so the digit inside "1st"
        # is not counted as arguing with itself.
        if re.search(r'\d', cleaned) and any(
                word in self._WORD_TO_NUM
                for word in re.findall(r'[a-z]+', cleaned)):
            _logger.info("Sales Automation: %r gives a quantity twice "
                         "over - asking again", (text or '')[:24])
            return None
        if re.search(r'(?:^|\s)\d', cleaned):
            return qty
        if not re.search(r'\d', cleaned):
            # The number was spelled out. "seven" and "five units" are real and
            # must not be thrown away.
            spelled = cleaned.rstrip('.,!?')
            if any(word in self._WORD_TO_NUM
                   for word in re.findall(r'[a-z]+', spelled)):
                return qty
            # What is left came from the autocorrect table, which exists for
            # voice transcripts - "fai" for five. It also holds two-letter
            # entries, and "Tw" was quietly priced as a quantity of 2 with no
            # warning at all. Take those only when the whole message is the
            # token and it is long enough to be a real attempt at a word.
            if (spelled in self._FUZZY_NUM and len(spelled) >= 3
                    and spelled not in self._SA_WORD_LOOKALIKES):
                return qty
            _logger.info("Sales Automation: %r is not a quantity - asking "
                         "again", (text or '')[:24])
            return None

        # Digits are present but every one of them is welded to a letter -
        # "A4", "Aaa5". That is a mistyped message, not a count.
        _logger.info("Sales Automation: %r is not a quantity - asking again",
                     (text or '')[:24])
        return None

    # ----------------------------------------------------------
    # The customer is not whoever else shares that phone number
    # ----------------------------------------------------------
    def _get_or_create_partner(self, conv):
        """Resolve the chat to a customer, never to a supplier.

        The tracker matches on the phone number and takes the first hit. Our
        four supplier contacts share one test number, so a customer buying from
        that number had their quotation raised against "Charger & Battery
        Supplier" - who is not the buyer, and whose address is not the delivery
        address.

        A supplier is only rejected when nothing better matches. One number
        genuinely can be both, and a contact already marked as a customer is
        the right answer either way.
        """
        digits = ''.join(c for c in (conv.phone or '') if c.isdigit())
        if len(digits) >= 8:
            Partner = self.env['res.partner'].sudo()
            # the one shared lookup (whatsapp_employee_tracker), which other
            # modules may narrow - 369 Mart's bridge keeps unproven accounts out
            buyer = Partner._sa_phone_owner(conv.phone)
            if buyer:
                return buyer
            if Partner._sa_phone_matches(conv.phone):
                _logger.info("Sales Automation: %s is only known as a supplier "
                             "- opening a separate customer contact", conv.phone)
                return Partner.create({
                    'name': conv.contact_name or _('WhatsApp Customer (%s)',
                                                   conv.phone),
                    'phone': Partner._sa_phone_e164(conv.phone),
                    'customer_rank': 1,
                    'comment': _('Auto-created from WhatsApp. The same number '
                                 'is also on a supplier contact.'),
                })
        return super()._get_or_create_partner(conv)

    # ----------------------------------------------------------
    # Ask who they are before raising anything in their name
    # ----------------------------------------------------------
    def _route_after_order(self, session, conv, order, product, qty, price):
        """Start the details ladder for anything that came out of a group.

        The link from order back to enquiry is written here rather than waiting
        for `_create_sale_order` to return, because the steps below are reached
        from inside this call and have only the order to go on.
        """
        request = self._sa_request_for_conversation(conv)
        if request and order and not order.sa_group_request_id:
            order.sudo().sa_group_request_id = request.id
        return super()._route_after_order(
            session, conv, order, product, qty, price)

    def _delivery_step(self, order):
        """Ask for the name first, not the delivery address.

        The tracker offers "Tap Same as my address" - which, on a contact that
        has no address, stored the words "Same as my address" as the street.
        """
        request = order.sudo().sa_group_request_id
        if request:
            return request._sa_profile_question(order)
        return super()._delivery_step(order)

    def _wa_apply_address(self, order, text):
        request = order.sudo().sa_group_request_id
        if request:
            return request._sa_take_profile_answer(text, order)
        return super()._wa_apply_address(order, text)

    @api.model
    def _sa_public_base(self):
        """The address to put in a link somebody outside will tap.

        Not `web.base.url`: that one identifies this server to the WhatsApp
        panel, which issued its API key against a single address and refuses
        every send if it changes. So it stays on localhost while this carries
        whatever the outside world reaches - a tunnel today, a domain later.
        """
        params = self.env['ir.config_parameter'].sudo()
        return (params.get_param('sa_delivery.public_base_url')
                or params.get_param('web.base.url') or '')

    @api.model
    def _sa_public_link(self, path):
        """A link a customer can open, wrapped so it finds the database.

        `/wa/pay`, `/wa/track` and `/wa/delivery` are public routes, and a
        public route on a server with no `dbfilter` cannot tell which of the
        two dozen databases a cold request belongs to - werkzeug answers 404
        before any of our code runs. The doorway in `wa_link_entry` binds the
        database first and then redirects, so the link works from a phone that
        has never seen this server.
        """
        from urllib.parse import quote
        base = (self._sa_public_base() or '').rstrip('/')
        if not base:
            return path
        return '%s/scoped_app/wa-link?db=%s&to=%s' % (
            base, quote(self.env.cr.dbname), quote(path, safe=''))

    def _online_pay_msg(self, order, method):
        """The pay-by-link message, on the public address.

        The tracker builds this from `web.base.url` and a customer was sent
        http://localhost:8069/wa/pay/402 - a link that can only work on the
        server itself. Everything else about the message is the tracker's, so
        only the base is changed here.
        """
        base = self._sa_public_base()
        if not base:
            return super()._online_pay_msg(order, method)
        try:
            token = order.sudo()._portal_ensure_token()
        except Exception:  # noqa: BLE001 - an older order may have no token
            token = order.sudo().access_token or ''
        kind = 'card' if method == 'card' else 'upi'
        url = self._sa_public_link('/wa/pay/%s?method=%s&token=%s'
                                   % (order.id, kind, token))
        return _("\U0001F4B3 Pay by %(label)s here:\n%(url)s\n\nComplete the "
                 "quick payment and your invoice will be sent here "
                 "automatically. \u2705",
                 label='Card' if kind == 'card' else 'UPI', url=url)

    def _payment_or_finalize(self, session, conv, order):
        """Keep asking until the details are confirmed."""
        request = (order.sudo().sa_group_request_id if order
                   else self.env['sa.group.request'])
        if request and request.profile_step != 'done':
            return request._sa_profile_question(order)
        return super()._payment_or_finalize(session, conv, order)

    # ----------------------------------------------------------
    # 4. Never auto-reply to a vendor
    # ----------------------------------------------------------
    def _check_conversation_for_message(self, conv, session, cutoff, trigger_log=None):
        """Skip the sales reply entirely when the sender is a supplier.

        Recording a vendor's price means writing a `whatsapp.message` row, and
        the tracker hooks that create to schedule an auto-reply. So capturing
        the quote is itself what wakes the salesbot, which then reads "950" as a
        product search, finds nothing, and tells the supplier "Sorry, I could
        not find matching products. An agent will assist you shortly."

        The quote is captured correctly either way - this only stops the reply
        that follows it.
        """
        if conv and self._sa_is_vendor_conversation(conv):
            _logger.info("Sales Automation: %s is a supplier we asked for a "
                         "price - no auto-reply.", conv.phone)
            return
        if self._sa_was_coded_reply(trigger_log):
            _logger.info("Sales Automation: %r was a coded reply, already "
                         "answered - no second reply.",
                         (getattr(trigger_log, 'message_text', '') or '')[:24])
            return
        if self._sa_was_finder_vote(trigger_log):
            return
        if self._sa_finder_in_progress(conv, session, trigger_log):
            return
        if self._sa_greeting_mid_form(conv, session, trigger_log):
            return
        if self._sa_form_in_progress(conv, session, trigger_log):
            return
        if self._sa_quantity_refused(conv, session, trigger_log):
            return
        return super()._check_conversation_for_message(
            conv, session, cutoff, trigger_log)

    @api.model
    def _sa_was_coded_reply(self, trigger_log):
        """True when the sales flow already answered this exact message.

        A coded reply opens with `#` and a short reference - `#DK ACCEPT`,
        `#DK 240`. `_sa_customer_code_reply` has handled it by the time this
        runs, so reading it again as an answer to whatever question is open
        can only produce a second, wrong reply.

        Matched on the shape rather than a flag on the row: the row is written
        by the gateway before the sales flow sees it, and adding a column to a
        shared model for this would be a heavier change than the problem.
        """
        text = (getattr(trigger_log, 'message_text', '') or '').strip()
        if not text.startswith('#'):
            return False
        ref = re.match(r'^#\s*([0-9A-Za-z]{1,6})\b', text)
        if not ref:
            return False
        return bool(self.env['sa.group.request'].sudo().search(
            [('ref_code', '=ilike', ref.group(1))], limit=1))

    @api.model
    def _sa_keep_deal(self, previous, request):
        """The product and price a re-ask has to carry forward.

        The tracker resumes the quantity step from the newest reply row, and
        its test is `reply_type == 'quantity_ask' and prev_reply
        .selected_product_id` (auto_reply.py:1181). Our re-asks were typed
        `quantity_ask` but carried no product, so the first refusal erased the
        deal: a customer who typed 10000000000, then 1999, then a perfectly
        good 5 was answered "Sorry, I could not find matching products" -
        the product had been dropped two messages earlier, by us.
        """
        product = (previous.selected_product_id
                   or (request.product_id if request else None))
        return {
            'selected_product_id': product.id if product else False,
            'matched_products': (previous.matched_products
                                 or (product.name if product else '')),
            'offered_price': (previous.offered_price
                              or (request.agreed_price or request.quoted_price
                                  if request else 0.0) or 0.0),
        }

    def _sa_quantity_refused(self, conv, session, trigger_log):
        """Answer a quantity we cannot accept, and say why.

        Two problems at once. The tracker's re-ask is generic - "Please reply
        with the quantity" - so a customer who typed 100000 is told nothing
        about what was wrong. And it is word-for-word the same every time, so
        the gateway refuses it as a duplicate: the first 100000 got an answer,
        the second got silence.

        The wording here names the number and the limit, and varies when the
        same refusal has just gone out, so repeating a bad quantity always
        gets a reply.
        """
        if not conv or not trigger_log:
            return False
        text = (trigger_log.message_text or '').strip()
        if not text:
            return False
        previous = self.search([('conversation_id', '=', conv.id)],
                               order='id desc', limit=1)
        if not previous or previous.reply_type != 'quantity_ask':
            return False
        request = self._sa_request_for_conversation(conv)
        if not request:
            return False

        # Whole units only, and say so - otherwise the tracker's generic
        # re-ask leaves the customer guessing what was wrong with "1.5".
        fraction = re.search(
            r'(?<![a-z0-9])(\d+(?:\s*\.\s*)+\d+)', text)
        if fraction:
            reply = self._sa_unused_phrasing(conv.phone, [
                _("I can only order whole units - *%(qty)s* is not one. How "
                  "many do you need? Send a number like *2*.",
                  qty=fraction.group(1)),
                _("Still *%(qty)s*? Please send a whole number, such as *2*.",
                  qty=fraction.group(1)),
            ])
            self._dispatch_auto_reply(session, conv, reply, 'quantity_ask',
                                      request.product_id or None, '')
            self.create(dict(
                self._sa_keep_deal(previous, request),
                conversation_id=conv.id,
                employee_session_id=session.id,
                trigger_message_id=trigger_log.id,
                phone=conv.phone,
                customer_message=text,
                reply_message=reply,
                reply_type='quantity_ask',
                status='sent',
            ))
            _logger.info("Sales Automation: refused the fractional quantity "
                         "%r for %s", fraction.group(1), conv.phone)
            return True

        # What the tracker would have read, before our own ceiling applied.
        raw = super()._parse_quantity(text)
        ceiling = self.env['sa.ai.settings'].sudo().get_settings(
            ).max_order_quantity or 0

        # An acceptable quantity is not ours to answer.
        if self._parse_quantity(text):
            return False

        # A number that is simply too large has its own message below.
        # Everything else here has nothing usable in it at all - "@", "S".
        # The tracker's re-ask is word-for-word the same every time, so the
        # second one is dropped as a duplicate and the customer gets silence.
        if not (raw and ceiling and raw > ceiling):
            if self.env['sa.ai.classifier'].sudo(
                    )._looks_like_product_request(text):
                return False    # they have moved on to something else
            reply = self._sa_unused_phrasing(conv.phone, [
                _("I couldn't read *%(said)s* as a quantity. How many do you "
                  "need? Send a number like *2*.", said=text[:24]),
                _("Still not a number - *%(said)s*. Please reply with a "
                  "quantity, such as *2*.", said=text[:24]),
            ])
            self._dispatch_auto_reply(session, conv, reply, 'quantity_ask',
                                      request.product_id or None, '')
            self.create(dict(
                self._sa_keep_deal(previous, request),
                conversation_id=conv.id,
                employee_session_id=session.id,
                trigger_message_id=trigger_log.id,
                phone=conv.phone,
                customer_message=text,
                reply_message=reply,
                reply_type='quantity_ask',
                status='sent',
            ))
            _logger.info("Sales Automation: %r is not a quantity - asked again",
                         text[:24])
            return True

        # Only the too-large case is left.

        product = request.product_id
        name = product.name or request.ai_search_term or _('this item')
        stock = 0
        if product and product.is_storable:
            # The order's company, not the group's - `sa.sales.group` has no
            # company_id, and reading it raised AttributeError right here.
            # The exception escaped the whole handler, so a customer who typed
            # a huge quantity got no reply at all: the crash looked exactly
            # like the bot ignoring them.
            company = request.order_id.company_id or self.env.company
            stock = int(product.with_company(company).qty_available)

        if 0 < stock < raw:
            options = [
                _("I only have *%(stock)s* of *%(product)s* right now, and I "
                  "can take up to *%(max)s* in one order. How many do you "
                  "need?", stock=stock, product=name, max=ceiling),
                _("*%(qty)s* is more than I have - there are *%(stock)s* in "
                  "stock. Please send a smaller number.",
                  qty=int(raw), stock=stock),
            ]
        else:
            options = [
                _("*%(qty)s* is more than I can take - the most I can order "
                  "in one go is *%(max)s*. How many do you need?",
                  qty=int(raw), max=ceiling),
                _("Still *%(qty)s*? The largest I can accept is *%(max)s* - "
                  "please send a smaller number.", qty=int(raw), max=ceiling),
            ]
        reply = self._sa_unused_phrasing(conv.phone, options)

        self._dispatch_auto_reply(session, conv, reply, 'quantity_ask',
                                  product or None, '')
        self.create(dict(
            self._sa_keep_deal(previous, request),
            conversation_id=conv.id,
            employee_session_id=session.id,
            trigger_message_id=trigger_log.id,
            phone=conv.phone,
            customer_message=text,
            reply_message=reply,
            reply_type='quantity_ask',
            status='sent',
        ))
        _logger.info("Sales Automation: refused a quantity of %s (limit %s) "
                     "for %s", raw, ceiling, conv.phone)
        return True

    @api.model
    def _sa_unused_phrasing(self, phone, options):
        """The first wording that has not just been sent to this number.

        The gateway drops a message identical to one it sent in the last five
        minutes, so repeating a refusal verbatim arrives as silence.
        """
        digits = ''.join(c for c in (phone or '') if c.isdigit())
        if not digits:
            return options[0]
        since = fields.Datetime.subtract(fields.Datetime.now(), minutes=6)
        recent = self.env['whatsapp.message'].sudo().search([
            ('direction', '=', 'outgoing'),
            ('phone', 'like', digits[-9:]),
            ('create_date', '>=', since),
        ]).mapped('message')
        for option in options:
            if not any(option in (sent or '') for sent in recent):
                return option
        return options[-1]

    @api.model
    def _sa_was_finder_vote(self, trigger_log):
        """True when the webhook already answered this tap in the finder.

        The stamp is the WhatsApp message id, claimed by the webhook before
        it logged the row. Claiming it here and succeeding means nobody had -
        an ordinary message - and costs one harmless guard row.
        """
        if not trigger_log:
            return False
        # `message_id` on the log is the whatsapp.message row itself.
        row = getattr(trigger_log, 'message_id', None)
        wa_id = (getattr(row, 'wa_message_id', '') or '') if row else ''
        if not wa_id:
            return False
        if self.env['sa.outbox.guard'].sudo().claim(
                'finder_vote|%s' % wa_id, 900):
            return False
        _logger.info("Sales Automation: %s was a finder tap, already "
                     "answered - no auto-reply", wa_id)
        return True

    def _sa_finder_in_progress(self, conv, session, trigger_log):
        """A typed answer to an open guided finder, in the private chat.

        Poll taps arrive through the webhook and never reach here; this is
        for the customer who types the option, a number, or the model name
        the finder asked for. A genuinely new product request falls through
        and closes the finder - a new question outranks an old poll.
        """
        if not conv or not trigger_log:
            return False
        text = (trigger_log.message_text or '').strip()
        if not text:
            return False
        Request = self.env['sa.group.request'].sudo()
        warm = Request._sa_still_warm()
        finder = Request.search([
            ('conversation_id', '=', conv.id),
            ('state', '=', 'finding'),
            ('finder_asked_on', '>=', warm),
        ], order='id desc', limit=1)
        if not finder and conv.phone:
            finder = Request.search([
                ('requester_phone', 'like', conv.phone[-9:]),
                ('state', '=', 'finding'),
                ('finder_asked_on', '>=', warm),
            ], order='id desc', limit=1)
        if not finder:
            return False
        handled = finder.with_context(
            sa_reply_to=conv.phone,
            sa_trigger_msg=(trigger_log.message_id.wa_message_id if trigger_log.message_id else '') or trigger_log.id,
        )._finder_answer(text)
        if handled:
            _logger.info("Sales Automation: %r answered the finder on enquiry "
                         "%s", text[:24], finder.id)
            return True
        finder._drop('not_confirmed')
        return False

    def _sa_form_in_progress(self, conv, session, trigger_log):
        """Route a private message into the details form when one is open.

        The tracker decides what a message means by reading the most recent
        reply it sent. That breaks the moment anything else writes a reply
        row: on 1 Sep a customer was halfway through the address form when
        they asked for a second product **in the group**, which seeded a
        `price_negotiate` row in the same private chat. Their next message -
        "No", meaning "change my details" - was read against that instead, and
        answered "Type another product name to search anytime". The form was
        left open with nothing to move it on.

        An open form is unambiguous, so it wins. A genuinely new product
        request still falls through, because that is a new enquiry rather than
        an answer.
        """
        if not conv or not trigger_log:
            return False
        text = (trigger_log.message_text or '').strip()
        if not text:
            return False
        request = self._sa_open_form(conv)
        if not request:
            return False
        if self.env['sa.ai.classifier'].sudo()._looks_like_product_request(text):
            return False        # a new request, not an answer to this one

        order = request.order_id
        request._sa_take_profile_answer(text, order)
        reply, reply_type = self._payment_or_finalize(session, conv, order)
        if not reply:
            return True
        self._dispatch_auto_reply(session, conv, reply, reply_type, None, '')
        self.create({
            'conversation_id': conv.id,
            'employee_session_id': session.id,
            'trigger_message_id': trigger_log.id,
            'phone': conv.phone,
            'customer_message': text,
            'reply_message': reply,
            'order_id': order.id,
            'reply_type': reply_type,
            'status': 'sent',
        })
        _logger.info("Sales Automation: %r answered the open details form on "
                     "enquiry %s", text[:24], request.id)
        return True

    def _sa_open_form(self, conv):
        """The details form entitled to this conversation's next reply.

        Being open is not enough, and that is what two testers found. Nine
        forms in two conversations had been abandoned mid-way - one since the
        day before - and the newest of them silently claimed every private
        message that arrived afterwards. So a customer who was asked *"How
        many do you need?"* and answered was told their answer "is not a
        postcode", and the next one that "I can't use that as a name": a
        question from yesterday was answering today's message.

        Two gates, then:

        * the form must have asked something recently. `write_date` cannot
          measure that, because reading a message bumps it - an abandoned form
          kept itself warm on exactly the messages it should not have had.
          `profile_asked_on` is stamped only when a question goes out.
        * nothing newer may have asked its own question. A handoff seeds a
          `quantity_ask` row the moment it asks for a quantity, so a seed
          created after the form last spoke means the form is no longer the
          live question.

        Whoever asked last owns the answer.
        """
        Request = self.env['sa.group.request'].sudo()
        if not conv:
            return Request.browse()
        form = Request.search([
            ('conversation_id', '=', conv.id),
            ('profile_step', 'not in', (False, 'done')),
            ('order_id', '!=', False),
            ('profile_asked_on', '!=', False),
            ('profile_asked_on', '>=', Request._sa_still_warm()),
        ], order='id desc', limit=1)
        if not form:
            return Request.browse()
        newer = self.sudo().search_count([
            ('conversation_id', '=', conv.id),
            ('reply_type', 'in', ('quantity_ask', 'price_negotiate')),
            ('create_date', '>', form.profile_asked_on),
        ])
        if newer:
            _logger.info("Sales Automation: form on enquiry %s is not the "
                         "live question - %d newer ask(s) in conversation %s",
                         form.id, newer, conv.id)
            return Request.browse()
        return form

    def _sa_greeting_mid_form(self, conv, session, trigger_log):
        """Answer a bare "hello" that lands in the middle of the details form.

        The tracker tests for a greeting at auto_reply.py:948 and answers with
        the welcome message. Its check for "we are half way through collecting
        an address" is ninety lines further down, at :1041, so the greeting
        always wins: a customer asked for their name typed "hello", got "How
        can I help you today? Please tell me what product you're looking for",
        and the form was left standing with nothing to move it on.

        Handled here rather than reordering the tracker, which every database
        on this server shares. Only a bare greeting is taken - anything else is
        a real answer and belongs to the tracker's own loop.
        """
        if not conv or not trigger_log:
            return False
        text = (trigger_log.message_text or '').strip()
        if not text or text.lower().strip('.!? ') not in (
                'hi', 'hello', 'hey', 'hii', 'hiii', 'helo', 'hai', 'yo',
                'sup', 'howdy', 'greetings', 'good morning', 'good evening',
                'good afternoon', 'good night'):
            return False

        request_ = self._sa_open_form(conv)
        if not request_:
            return False

        # Not an answer to anything - so ask again, quoting what they sent so
        # the repeat is not word for word and never reads as silence.
        request_.write({'profile_retry': request_.profile_retry + 1,
                        'profile_last_bad': text[:60]})
        reply, reply_type = request_._sa_profile_question(request_.order_id)
        self._dispatch_auto_reply(session, conv, reply, reply_type, None, '')
        self.create({
            'conversation_id': conv.id,
            'employee_session_id': session.id,
            'trigger_message_id': trigger_log.id,
            'phone': conv.phone,
            'customer_message': text,
            'reply_message': reply,
            'order_id': request_.order_id.id,
            'reply_type': reply_type,
            'status': 'sent',
        })
        _logger.info("Sales Automation: %r arrived mid-form on enquiry %s - "
                     "asked again instead of greeting.", text[:20], request_.id)
        return True

    @api.model
    def _sa_is_vendor_conversation(self, conv):
        """True when this number is a supplier we have asked to quote.

        Deliberately not limited to still-open price checks: a vendor answering
        late, or following up the next morning, is still a vendor and still
        should not be sold to.
        """
        digits = ''.join(c for c in (conv.phone or '') if c.isdigit())
        if len(digits) < 8:
            return False
        Request = self.env['sa.group.request'].sudo()
        if not Request.search_count(
                [('sourcing_vendor_ids.phone', 'like', digits[-9:])]):
            return False
        # A supplier who is also buying from us today is a customer today.
        # Without this, being asked for a price once silences the sales flow
        # for that number for ever - a tester was quoted privately, replied
        # "yes", and was answered with nothing at all.
        if Request._sa_customer_outranks_vendor(digits):
            _logger.info("Sales Automation: %s is a supplier, but their own "
                         "enquiry is newer than anything we asked them - "
                         "answering as a customer.", conv.phone)
            return False
        return True

    # ----------------------------------------------------------
    # 5. Plain text in the private chat, so it renders anywhere
    # ----------------------------------------------------------
    def _dispatch_auto_reply(self, session, conv, reply, reply_type,
                             selected_product=None, matched=''):
        """Send the follow-up as text rather than buttons.

        The tracker sends these as tappable buttons. Those render in the
        WhatsApp phone app and arrive on WhatsApp Web and Desktop as "This
        message couldn't load. Open the message on your phone to view it." - so
        a customer sitting at a computer is asked for a quantity, or an
        address, and has nothing to answer.

        Nothing is lost by sending text: the tracker composes `reply` with the
        numbered choices already in it (which is why it passes
        include_numbers=False), so the same options arrive readable everywhere.

        Only deals that came out of a group are affected; the tracker's own
        one-to-one conversations keep their buttons.
        """
        # The guard in `_check_conversation_for_message` covers the entry it
        # sits on, and the tracker has two: the timer that fires when a message
        # lands and the auto-reply cron. On 29 Aug a supplier answered "300"
        # and was told "Hi! Thank you for reaching out. We couldn't find..."
        # while the log shows the guard refusing the very same message
        # seconds later - one path stopped, the other did not. Checking again
        # here catches whichever path reaches the wire.
        request = self._sa_request_for_conversation(conv)
        if not request and conv and self._sa_is_vendor_conversation(conv):
            _logger.info("Sales Automation: not selling to supplier %s",
                         conv.phone)
            return

        if not request or request.group_id.dm_use_buttons:
            return super()._dispatch_auto_reply(
                session, conv, reply, reply_type,
                selected_product=selected_product, matched=matched)

        phone = conv.phone or ''
        if reply_type == 'product_detail' and selected_product:
            try:
                self._send_product_with_image(
                    session, phone, selected_product, reply)
                return
            except Exception:  # noqa: BLE001 - the text still has to go out
                pass
        self._send_message_smart(session, phone, reply)
        self._sa_tap_poll(session, phone, reply, reply_type, request)

    # The private chat is tap-only. A poll is the one tappable thing this
    # transport renders on WhatsApp Web as well as on the phone, and its vote
    # arrives as the chosen label, which the webhook hands on as text.
    _SA_TAP_POLLS = (
        # (reply_type, phrase that must be in the text, question, options)
        # Ranges first; the webhook answers the range tapped with a second
        # poll of its exact numbers, so the tracker only ever sees a number.
        ('quantity_ask', 'how many',
         "How many? (Ref %s)", ['1-5', '6-10', '11-15', '16-20', 'Above 20']),
        (None, 'check your details',
         "Are these details right? (Ref %s)", ['YES', 'NO', 'CANCEL']),
        ('await_payment', 'payment method',
         "How would you like to pay? (Ref %s)",
         ['UPI', 'Card', 'Cash on Delivery']),
        ('price_negotiate', 'reply *yes*',
         "Order at this price? (Ref %s)", ['Yes', 'No']),
    )

    @api.model
    def _sa_tap_poll(self, session, phone, reply, reply_type, request):
        """The tappable half of a question the tracker just asked."""
        text = (reply or '').lower()
        for kind, phrase, question, options in self._SA_TAP_POLLS:
            if kind and kind != reply_type:
                continue
            if phrase not in text:
                continue
            if kind == 'await_payment' and 'cash on delivery' not in text:
                options = [o for o in options if o != 'Cash on Delivery']
            ref = (request and request.ref_code) or ''
            try:
                session.session_id.sa_send_poll(
                    phone, question % ref if ref else question.replace(
                        ' (Ref %s)', ''), options)
            except Exception as err:  # noqa: BLE001 - the text already went
                _logger.warning("Sales Automation: poll for %s to %s not "
                                "sent: %s", reply_type, phone, err)
            return True
        return False

    # `_sa_already_said` lived here. It dropped any reply identical to one
    # sent to the same number in the previous three minutes, to hide the fact
    # that the tracker answered every message twice - once from the timer that
    # fires on arrival, once from the `WA Tracker: Auto Reply Check` cron.
    #
    # It cost more than it saved. It could not tell a duplicate from a customer
    # who genuinely sent the same thing again, so it swallowed three real
    # replies: the retry after an invalid pincode, the answer to "0" at the
    # details summary, and the restart after "NO". Each arrived as silence and
    # each was reported as a bug.
    #
    # The cron is now off, so nothing duplicates and nothing needs suppressing.
    # `sa.outbox.guard` still covers the other cause of repeats - Odoo replaying
    # a whole request after a serialization failure - and is keyed on the
    # inbound message id, so it never blocks a genuine second message.

    @api.model
    def _sa_request_for_conversation(self, conv):
        """The group enquiry behind this private chat, if there is one."""
        if not conv:
            return self.env['sa.group.request']
        return self.env['sa.group.request'].sudo().search([
            ('conversation_id', '=', conv.id),
            ('state', 'in', ('handed_off', 'order_created')),
        ], order='id desc', limit=1)

    # ----------------------------------------------------------
    # 5. Hand back to a person once the quotation exists
    # ----------------------------------------------------------
    def _payment_step(self, session, order):
        """Stop at the quotation for anything that came out of a group.

        The tracker's own flow goes straight on to collect payment over
        WhatsApp. For a deal that started as a group enquiry that is a step too
        far: the price was negotiated by a bot against a vendor quote, and
        somebody should look at it before money moves. So the customer is told
        the quotation is raised and that the team will follow up, and the rest
        - confirming the order, sending the invoice, recording the payment -
        happens in Sales where it can be seen.

        Turning on 'Confirm and Take Payment Automatically' on the customer
        group restores the tracker's original behaviour.
        """
        request = self.env['sa.group.request'].sudo().search(
            [('order_id', '=', order.id)], limit=1)
        if not request or request.group_id.auto_confirm_order:
            return super()._payment_step(session, order)

        _logger.info("Sales Automation: %s left as a quotation for review "
                     "(enquiry %s)", order.name, request.id)
        return (_(
            "\U0001F9FE *Quotation %(ref)s* - Total: *%(total).2f*\n\n"
            "Our team will confirm it and send you the invoice shortly. "
            "\U0001F64F", ref=order.name, total=order.amount_total),
            'order_created')

    # ----------------------------------------------------------
    @api.model
    def _sa_request_for(self, prev_reply):
        """The out-of-stock group enquiry behind this thread, if any."""
        if not prev_reply or not prev_reply.conversation_id \
                or not prev_reply.selected_product_id:
            return self.env['sa.group.request']
        return self.env['sa.group.request'].sudo().search([
            ('conversation_id', '=', prev_reply.conversation_id.id),
            ('product_id', '=', prev_reply.selected_product_id.id),
            ('stock_status', '=', 'on_order'),
        ], order='id desc', limit=1)
