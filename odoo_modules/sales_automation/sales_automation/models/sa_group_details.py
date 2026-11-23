# -*- coding: utf-8 -*-
"""Every group order: name -> address -> details check (with the phone) ->
signature -> payment. All of it in the group, before any money is asked for.

Before (29 Sep 2026) an in-stock order jumped straight to the pay link and an
out-of-stock one straight to the sign link, so the quotation was raised in
the name the tracker invented from the phone number - "+917907543611" - and
nobody ever asked where to deliver. The private-chat flow already had a
details ladder (`_sa_profile_question` / `_sa_take_profile_answer`); this
file runs the same ladder in the group and then hands over to the existing
sign-then-pay steps.
"""
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SaGroupRequestDetails(models.Model):
    _inherit = 'sa.group.request'

    sa_details_pending = fields.Boolean(
        'Asking for the customer details', copy=False,
        help="The name / address / confirmation questions are open in the "
             "group; the next message from this customer answers them.")
    sa_details_fix = fields.Selection([
        ('menu', 'Asked what to change'),
        ('name', 'Changing the name only'),
        ('address', 'Changing the address only'),
    ], 'Details change', copy=False,
        help="After NO on the read-back: which field is being redone. Only "
             "that field is asked again, then the read-back comes back.")
    sa_note_step = fields.Selection([
        ('ask', 'Asked'), ('done', 'Answered or skipped'),
    ], 'Landmark question', copy=False,
        help="The optional landmark / flat / gate question, asked once "
             "between the address and the read-back.")

    # ------------------------------------------------------------------
    # 1. After the order: ask
    # ------------------------------------------------------------------
    def _sa_group_details_start(self, order):
        """Open the ladder and put the first question in the group."""
        self.ensure_one()
        # the sign-link token now, so a retried save later builds the same
        # "Details saved - sign here" text and the outbox guard drops the
        # repeat (S00013 got two links, one dead, 22 Nov 2026)
        if order:
            order.sudo()._portal_ensure_token()
        self.write({'sa_details_pending': True, 'profile_step': False, 'sa_note_step': False,
                    'profile_retry': 0, 'profile_last_bad': False,
                    'profile_restarted': False})
        if self._sa_details_known(order):
            return self.with_context(sa_details_known=True)._sa_details_done(order)
        return self._sa_details_ask(order)

    def _sa_details_known(self, order):
        """True when nothing has to be asked: the order carries the customer's
        address already. Filled in by the address book."""
        return False

    DETAILS_YES = '✅ YES, CORRECT'
    DETAILS_NO = '✏️ NO, CHANGE'
    DETAILS_CANCEL = '❌ CANCEL'

    FIX_NAME = '👤 NAME'
    FIX_ADDRESS = '🏠 ADDRESS'
    FIX_BACK = '⬅️ BACK'

    def _sa_details_ask(self, order):
        """The next question. The read-back is a poll - one tap instead of
        typing YES (owner, 29 Sep: "not typeable, button based need").

        While one field is being redone the question is worded differently
        from the first time: the gateway drops a message byte-identical to
        one sent to the same chat in the last five minutes, and "Thanks Sri
        Bala. What is your full address?" asked twice arrived once (Ref 15).
        """
        self.ensure_one()
        fix = self.sa_details_fix
        if fix == 'menu':
            self._ask(_("✏️ What would you like to change?"),
                      [{'id': 'sa_fix_name', 'title': self.FIX_NAME},
                       {'id': 'sa_fix_address', 'title': self.FIX_ADDRESS},
                       {'id': 'sa_fix_back', 'title': self.FIX_BACK}])
            return True
        reply, _kind = self._sa_profile_question(order)
        step = self.profile_step
        if step == 'confirm' and not fix and not self.sa_note_step:
            # One optional question before the read-back (rider-app report,
            # 3 Oct 2026). The order ref keeps the text unique in the group.
            self.write({'sa_note_step': 'ask'})
            self._say(_("\U0001F4CD Order *#%(ref)s*: any landmark, flat number or gate note "
                        "for the delivery person?\n\nReply *SKIP* if none.",
                        ref=self.ref_code or order.name))
            return True
        if step == 'confirm':
            body = reply.replace(
                _("Reply *YES* to confirm, *NO* to change them, or *CANCEL* to stop."),
                _("Tap one:")).rstrip()
            ship = order.partner_shipping_id or order.partner_id
            note = (ship.sa_delivery_note
                    if 'sa_delivery_note' in ship._fields else '') or ''
            if note:
                body = body.replace(_("Tap one:"),
                                    _("\U0001F4CD Note for the rider: %s\n\nTap one:") % note)
            self._ask(body, [{'id': 'sa_det_yes', 'title': self.DETAILS_YES},
                             {'id': 'sa_det_no', 'title': self.DETAILS_NO},
                             {'id': 'sa_det_cancel', 'title': self.DETAILS_CANCEL}])
            return True
        if fix == 'name' and step == 'name' and not self.profile_retry:
            reply = _("\U0001F464 New name - what name should the quotation be in?")
        elif fix == 'address' and step == 'address' and not self.profile_retry:
            reply = _("\U0001F3E0 New address for %(name)s - please send the full "
                      "address: door number, street, area and city.",
                      name=order.partner_id.name or '')
        if step == 'name':
            # One tap for the name we can already see (owner, 8 Oct: nothing
            # typed). Typing a different one still works.
            sugg = self._sa_name_suggestion(order)
            if sugg:
                self._ask(reply + _("\n\nTap your name, or type a different one \U0001F447"),
                          [{'id': 'sa_name_sugg', 'title': '✅ %s' % sugg[:60]},
                           {'id': 'sa_name_typing', 'title': self.NAME_OTHER}])
                return True
        self._say(reply)
        return True

    NAME_OTHER = '✏️ Type my name'

    def _sa_name_suggestion(self, order):
        """A name worth offering as one tap, or ''. Not the one being changed."""
        self.ensure_one()
        current = order.partner_id._sa_real_name() if order.partner_id else ''
        for name in (self._sa_known_name(), ' '.join((self.requester_name or '').split())):
            if name and self._sa_looks_like_name(name) and name != (current if self.sa_details_fix == 'name' else None):
                return name
        return ''

    def _sa_details_change(self, choice):
        """NAME / ADDRESS / BACK from the change menu."""
        self.ensure_one()
        order = self.order_id.sudo()
        if choice == 'name':
            self.write({'sa_details_fix': 'name', 'profile_step': 'name',
                        'profile_retry': 0, 'profile_last_bad': False,
                        'profile_restarted': False})
        elif choice == 'address':
            self.write({'sa_details_fix': 'address', 'profile_step': 'address',
                        'profile_retry': 0, 'profile_last_bad': False,
                        'profile_restarted': False})
        else:
            self.write({'sa_details_fix': False, 'profile_step': 'confirm',
                        'profile_retry': 0, 'profile_last_bad': False})
        return self._sa_details_ask(order)

    def _sa_answer_poll(self, text):
        """A tap on the details read-back poll or the change menu."""
        self.ensure_one()
        if self.sa_details_pending and self.state == 'order_created':
            key = self._sa_menu_key(text)
            if self.profile_step == 'name':
                if key == self._sa_menu_key(self.NAME_OTHER):
                    self._say(_("\u270F\uFE0F Type the name for the order \U0001F447"))
                    return True
                if (text or '').strip().startswith('✅'):
                    return self._sa_take_details((text or '').strip()[1:].strip())
            if self.sa_details_fix == 'menu':
                if key in (self._sa_menu_key(self.FIX_NAME), 'name'):
                    return self._sa_details_change('name')
                if key in (self._sa_menu_key(self.FIX_ADDRESS), 'address'):
                    return self._sa_details_change('address')
                if key in (self._sa_menu_key(self.FIX_BACK), 'back'):
                    return self._sa_details_change('back')
            if self.profile_step == 'confirm':
                word = None
                if key in (self._sa_menu_key(self.DETAILS_YES), 'yes', 'y', 'correct', 'ok'):
                    word = 'yes'
                elif key in (self._sa_menu_key(self.DETAILS_NO), 'no', 'n', 'change'):
                    word = 'no'
                elif key in (self._sa_menu_key(self.DETAILS_CANCEL), 'cancel'):
                    word = 'cancel'
                if word:
                    return self._sa_take_details(word)
        return super()._sa_answer_poll(text)

    _SA_PIN_RE = re.compile(r'^\U0001F4CD\s*(-?\d{1,2}\.\d+),\s*(-?\d{1,3}\.\d+)\s*$')

    @api.model
    def _sa_take_location(self, group, message, lat, lng):
        """A WhatsApp location pin from a customer: saved on the contact of
        their latest order in this group (and on its open delivery job)."""
        digits = ''.join(c for c in (message.participant_phone or '') if c.isdigit())
        tail = digits[-9:] if len(digits) >= 9 else ''
        lid = message.participant_lid or ''
        dom = [('group_id', '=', group.id), ('order_id', '!=', False),
               ('order_id.state', '!=', 'cancel')]
        if tail and lid:
            dom += ['|', ('requester_phone', 'like', tail), ('requester_lid', '=', lid)]
        elif tail:
            dom += [('requester_phone', 'like', tail)]
        elif lid:
            dom += [('requester_lid', '=', lid)]
        else:
            return False
        req = self.sudo().search(dom, order='id desc', limit=1)
        if not req:
            return False
        order = req.order_id.sudo()
        # the pin belongs to the address THIS order goes to, not to every
        # address of the customer
        # ... unless the rider has asked for a location for this delivery
        # (wrong address / the customer is elsewhere today): then it is the
        # drop point of that job only and the saved address is not touched.
        one_off = order.picking_ids.filtered(lambda p: getattr(p, 'sa_drop_pending', False))
        if not one_off:
            (order.partner_shipping_id or order.partner_id).write(
                {'partner_latitude': lat, 'partner_longitude': lng})
        jobs = order.picking_ids.filtered(
            lambda p: getattr(p, 'sa_delivery_state', 'none') not in (
                'none', False, 'delivered', 'cancelled', 'returned', 'failed'))
        if jobs and hasattr(jobs, 'sa_set_customer_pin'):
            jobs.sa_set_customer_pin(lat, lng, source='whatsapp')
        req._say(_("\U0001F4CD Location saved for order *#%(ref)s* - the rider will be "
                   "guided to this pin. Thank you!", ref=req.ref_code or order.name))
        return True

    @api.model
    def _sa_details_waiting(self, group, message):
        """This sender's enquiry whose details questions are open."""
        digits = ''.join(c for c in (message.participant_phone or '') if c.isdigit())
        tail = digits[-9:] if len(digits) >= 9 else ''
        lid = message.participant_lid or ''
        # A question nobody answered for half an hour stops catching typed
        # messages (owner, 22 Nov 2026). The order is kept and its poll still
        # works (`_sa_answer_poll` is not filtered by this).
        since = fields.Datetime.now() - timedelta(minutes=self.DETAILS_TYPED_MINUTES)
        dom = [('group_id', '=', group.id), ('sa_details_pending', '=', True),
               ('state', '=', 'order_created'), ('order_id', '!=', False),
               ('profile_asked_on', '>=', since)]
        if tail and lid:
            dom += ['|', ('requester_phone', 'like', tail), ('requester_lid', '=', lid)]
        elif tail:
            dom += [('requester_phone', 'like', tail)]
        elif lid:
            dom += [('requester_lid', '=', lid)]
        else:
            return self.browse()
        return self.sudo().search(dom, order='id desc', limit=1)

    def _sa_take_details(self, text):
        """One answer in; the next question out, or the sign link when done."""
        self.ensure_one()
        order = self.order_id.sudo()
        answer = (text or '').strip()
        fix = self.sa_details_fix
        if self.sa_note_step == 'ask' and self.profile_step == 'confirm':
            # the answer to the landmark question
            self.write({'sa_note_step': 'done'})
            if not self._sa_is_cancel(answer):
                low = answer.lower().strip(' .!')
                note = '' if low in ('skip', 'no', 'none', 'nil', 'na', 'n/a', '-', 'nothing',
                                     'no landmark', 'illa', 'illai', 'vendam') else answer[:120]
                (order.partner_shipping_id or order.partner_id).sudo().write(
                    {'sa_delivery_note': note or False})
                return self._sa_details_ask(order)
        if fix == 'menu':
            # A typed choice instead of a tap.
            low = answer.lower()
            if self._sa_is_cancel(answer):
                pass                        # falls through to the ladder's cancel
            elif 'name' in low:
                return self._sa_details_change('name')
            elif 'addr' in low:
                return self._sa_details_change('address')
            elif low in ('back', 'ok', 'fine', 'correct', 'yes'):
                return self._sa_details_change('back')
            else:
                return self._sa_details_ask(order)       # the menu again
        if self.profile_step == 'confirm' and not self._sa_is_cancel(answer) \
                and self._read_yes_no(answer, numbered=False) is False:
            # NO on the read-back: ask WHICH field, instead of starting the
            # whole ladder again from the name (owner, 29 Sep).
            self.write({'sa_details_fix': 'menu'})
            return self._sa_details_ask(order)
        self._sa_take_profile_answer(text, order)
        if self.state != 'order_created':
            # CANCEL inside the ladder ends the deal (`_sa_cancel_deal`).
            self.write({'sa_details_pending': False, 'sa_details_fix': False})
            return True
        if fix == 'name' and self.profile_step == 'address':
            # Only the name was being redone: straight back to the read-back.
            self.write({'sa_details_fix': False, 'profile_step': 'confirm',
                        'profile_retry': 0, 'profile_last_bad': False})
        elif fix == 'address' and self.profile_step == 'confirm':
            self.write({'sa_details_fix': False})
        if self.profile_step == 'done':
            self.write({'sa_details_pending': False, 'sa_details_fix': False})
            return self._sa_details_done(order)
        return self._sa_details_ask(order)

    # ------------------------------------------------------------------
    # 2. Details confirmed: sign
    # ------------------------------------------------------------------
    def _sa_order_brief(self, order):
        """Order number, items and total, as the sign page shows them."""
        self.ensure_one()
        order = order.sudo()
        return _("\U0001F9FE Order *%(order)s*\n%(lines)s\n*Total: %(cur)s %(total).2f*",
                 order=order.name, lines=self._sa_order_lines_text(order),
                 cur=order.currency_id.symbol or '', total=order.amount_total)

    def _sa_details_done(self, order):
        """The customer said YES to their details: now the signature."""
        self.ensure_one()
        order = order.sudo()
        vals = {}
        if 'require_signature' in order._fields and not order.require_signature:
            vals['require_signature'] = True
        if 'require_payment' in order._fields and order.require_payment:
            vals['require_payment'] = False       # the portal page must sign, not pay
        if vals:
            order.write(vals)
        link = self._sa_portal_link(order)
        if self._sa_lines_in_stock(order):
            tail = _("The payment link is posted here the moment it is signed.")
        else:
            tail = _("The goods are being arranged for you; the payment link "
                     "is posted here once they are in.")
        # the location is added on the page itself (owner, 23 Nov 2026); one
        # sent in the group is still read
        # the label only: this may be posted in the group
        ship = order.partner_shipping_id or order.partner_id
        if ship and (ship.street or '').strip():
            tail = _("\U0001F3E0 Deliver to: *%s* (you can change it on the page before you sign)",
                     ship._sa_label()) + '\n\n' + tail
        head = '' if self.env.context.get('sa_details_known') else _(
            "✅ Details saved, thank you %(name)s.\n\n", name=order.partner_id.name or '')
        self._say(head + _("%(order)s\n\n✍️ Please sign your order *#%(ref)s* here to "
                           "confirm it:\n%(link)s\n\n%(tail)s",
                           order=self._sa_order_brief(order), ref=self.ref_code or order.name,
                           link=link, tail=tail))
        self.write({'sa_sign_link_sent_on': fields.Datetime.now()})
        return True

    # ------------------------------------------------------------------
    # 3. Signed: pay (in stock) or wait for the goods
    # ------------------------------------------------------------------
    def _sa_flow_end(self):
        """Where the WhatsApp order flow stops by itself: 'order' (signed
        order), 'invoice', 'paid' or 'delivery' - Delivery > Configuration >
        Delivery Settings. Without the delivery module: up to the payment."""
        if 'sa.delivery.settings' not in self.env:
            return 'paid'
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        return getattr(settings, 'flow_end', None) or 'delivery'

    def _sa_signed_stop(self, order, end):
        """The flow ends at the signed order or at the invoice: the order
        (and the invoice) go to the group, no pay link, no delivery job."""
        self.ensure_one()
        order = order.sudo()
        inv_line = ''
        if end == 'invoice':
            try:
                inv = order.invoice_ids.filtered(
                    lambda m: m.move_type == 'out_invoice' and m.state != 'cancel')
                if not inv:
                    inv = order._create_invoices()
                if 'auto_wa_sent_at_post' in inv._fields:
                    inv.write({'auto_wa_sent_at_post': True})
                inv.filtered(lambda m: m.state == 'draft').with_context(
                    wa_skip_autosend=True).action_post()
                first = inv.sorted('id')[:1]
                pdf, _x = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                    'account.account_invoices', first.ids)
                fname = ((first.name or 'Invoice').replace('/', '_')) + '.pdf'
                caption = _("\U0001F9FE Invoice %(name)s for order *#%(ref)s* - "
                            "amount due %(cur)s %(due).2f.",
                            name=first.name or '', ref=self.ref_code or order.name,
                            cur=order.currency_id.symbol or '', due=first.amount_residual)
                session = self.group_id.session_id
                # privately when allowed (sa_private_links.py); the line below says where
                where = self._sa_send_doc(
                    lambda to: session.send_document(to, pdf, fname, caption=caption))
                inv_line = (_("\nYour invoice %s is in your private chat \U0001F512", first.name or '')
                            if where == 'private' else
                            _("\nYour invoice %s is above.", first.name or ''))
            except Exception as err:  # noqa: BLE001 - the words still go out
                _logger.warning("Flow end: invoice for %s failed: %s", order.name, err)
        self._say(_("\u270d\ufe0f Signed - thank you! Your order *#%(ref)s* is confirmed.%(inv)s\n\n"
                    "%(order)s\n%(lines)s\n*Total: %(cur)s %(total).2f*\n\n"
                    "We will contact you about the next step.",
                    ref=self.ref_code or order.name, inv=inv_line, order=order.name,
                    lines=self._sa_order_lines_text(order),
                    cur=order.currency_id.symbol or '', total=order.amount_total))
        self.write({'sa_paid_told_on': fields.Datetime.now(), 'sa_stock_confirmed': True})
        try:
            self._sa_paid_menu(order)
        except Exception as err:  # noqa: BLE001
            _logger.warning("Flow end: menu for %s failed: %s", order.name, err)
        return True

    def _sa_group_signed(self, order):
        """Called when the order is confirmed - the portal signature does that.

        Only for an order whose sign link went out and that has not been
        paid or sent its pay link: a payment-confirmed order, or a manual
        confirmation before the ladder ran, changes nothing here.
        """
        self.ensure_one()
        order = order.sudo()
        if not self.sa_sign_link_sent_on or self.sa_pay_link_sent_on:
            return False
        if self._sa_order_is_paid(order):
            return False
        if not self.group_id or not self.group_id.group_jid:
            return False
        Task = self.env['sa.after.task'].sudo()
        if Task.search_count([('request_id', '=', self.id), ('step', '=', 'signed')], limit=1):
            return False
        # The PDF first, then the words (owner, 29 Sep) - both after the
        # customer's page has moved on to the payment (sa_after_order.py).
        end = self._sa_flow_end()
        if end in ('order', 'invoice'):
            mode = 'stop'
        elif self._sa_pay_link_when(order) == 'sign':
            # the admin's rule for goods in stock / not in stock (sa_pay_link_rule.py)
            mode = 'pay' if self._sa_lines_in_stock(order) else 'pay_goods'
            self.write({'sa_pay_link_sent_on': fields.Datetime.now(),
                        'sa_stock_confirmed': True,
                        'sa_pay_remind_count': 0, 'sa_pay_reminded_on': False})
        else:
            mode = 'wait' if self._sa_lines_in_stock(order) else 'wait_goods'
        Task._queue(self, order, 'signed', mode)
        return True

    def _sa_signed_words(self, order, mode):
        """"Signed - thank you!" with the pay link, or that the goods are being
        arranged."""
        self.ensure_one()
        if mode == 'wait':
            return _("✍️ Signed - thank you! Order *#%(ref)s* is with the shop; "
                     "we will write here about the payment.", ref=self.ref_code or order.name)
        if mode == 'wait_goods' and self._settings().pay_link_no_stock == 'never':
            return _("✍️ Signed - thank you! We are arranging the goods for order *#%(ref)s* "
                     "and will write here when they are in.", ref=self.ref_code or order.name)
        if mode not in ('pay', 'pay_goods'):
            return _("✍️ Signed - thank you! We are arranging the "
                     "goods for order *#%(ref)s*; the payment link will be "
                     "posted here as soon as they are in.",
                     ref=self.ref_code or order.name)
        after = (_("Once the payment is done, your invoice and the delivery "
                   "date will be posted here.") if self._sa_flow_end() == 'delivery'
                 else _("Once the payment is done, your invoice will be posted here."))
        return _("✍️ Signed - thank you!\n\n"
                 "%(order)s\n%(lines)s\n*Total: %(cur)s %(total).2f*\n\n%(pay)s\n\n%(after)s",
                 order=order.name, lines=self._sa_order_lines_text(order),
                 cur=order.currency_id.symbol or '', total=order.amount_total,
                 pay=((_("We are arranging the goods. You can pay now to have them reserved for you.\n\n")
                       if mode == 'pay_goods' else '') + self._sa_pay_link_any_state(order)), after=after)

    def _sa_send_order_pdf(self, order):
        """The signed, confirmed order as a PDF in the group. Never raises."""
        self.ensure_one()
        session = self.group_id.session_id
        dest = self.group_id.group_jid
        try:
            pdf, _kind = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                'sale.action_report_saleorder', order.ids)
            fname = ((order.name or 'Order').replace('/', '_')) + '.pdf'
            caption = _("\U0001F4C4 Order %(name)s - confirmed. Thank you!", name=order.name or '')
            # privately when allowed (sa_private_links.py), the group otherwise
            self._sa_send_doc(
                lambda to: session.send_document(to, pdf, fname, caption=caption),
                note=_("\U0001F4C4 Your order %s (PDF) is in your *private chat* \U0001F512")
                % (order.name or ''))
            return True
        except Exception as err:  # noqa: BLE001 - the words still go out
            _logger.warning("Sales Automation: order PDF for %s not sent to %s: "
                            "%s", order.name, dest, err)
            return False

    # ------------------------------------------------------------------
    # Routing: the customer's next group message answers the open question
    # ------------------------------------------------------------------
    @api.model
    def _on_group_message(self, message):
        group = self.env['sa.sales.group'].sudo().search([
            ('session_id', '=', message.session_id.id), ('group_jid', '=', message.group_jid),
            ('enabled', '=', True)], limit=1)
        text = (message.message or '').strip()
        pin = self._SA_PIN_RE.match(text) if text else None
        if group and pin and group.group_type != 'vendor':
            try:
                with self.env.cr.savepoint():
                    if self._sa_take_location(group, message, float(pin.group(1)), float(pin.group(2))):
                        return True
            except Exception as err:  # noqa: BLE001 - a pin must never break the chat
                _logger.warning("Location pin from %s not saved: %s", message.participant_phone, err)
            return True          # a bare pin is never an enquiry
        if group and text and not self.env.context.get('sa_poll_ref') and group.group_type != 'vendor':
            waiting = self._sa_details_waiting(group, message)
            if waiting and not self._sa_is_greeting(text):
                waiting = waiting.with_context(
                    sa_trigger_msg=message.wa_message_id or ('row%s' % message.id))
                # NEW ORDER / the menu opened after the details question:
                # what they type now is a search, not an answer (S00012, Ref R:
                # "tablet" after NEW ORDER got "Sorry, I didn't understand").
                if self._sa_details_menu_newer(waiting, message):
                    return super()._on_group_message(message)
                # On the read-back, only an answer to it is taken as one; a
                # product is shown, anything else gets "couldn't find".
                if waiting._sa_details_readback_open() and not waiting._sa_details_answer_like(text):
                    out = waiting._sa_details_off_topic(text)
                    if out is not None:
                        return out
                    # in the catalogue but not on the menu: the ordinary
                    # enquiry (the vendors); this order keeps waiting
                    return super()._on_group_message(message)
                return waiting._sa_take_details(text)
        return super()._on_group_message(message)

    # ------------------------------------------------------------------
    # Typed words that are not an answer to the details question
    # ------------------------------------------------------------------
    DETAILS_TYPED_MINUTES = 30

    @api.model
    def _sa_details_menu_newer(self, waiting, message):
        """True when this sender opened the menu / NEW ORDER after the details
        question went out. Nothing here: the NEW ORDER module overrides it."""
        return False

    def _sa_details_readback_open(self):
        """The "Please check your details" poll is the open question (not the
        landmark, the change menu, a field being redone or the address book)."""
        self.ensure_one()
        return (self.profile_step == 'confirm' and not self.sa_details_fix
                and self.sa_note_step != 'ask'
                and not getattr(self, 'sa_book_step', False))

    def _sa_details_answer_like(self, text):
        """YES / NO / CANCEL (typed or a poll title), 1-3, name, address, back."""
        self.ensure_one()
        answer = (text or '').strip()
        low = answer.lower().strip(' .!*?')
        if not low:
            return True
        if low.isdigit() and len(low) <= 2:
            return True
        if low in ('yes', 'y', 'no', 'n', 'ok', 'okay', 'correct', 'change', 'cancel',
                   'stop', 'name', 'back') or low.startswith('addr'):
            return True
        if self._sa_is_cancel(answer):
            return True
        key = self._sa_menu_key(re.sub(r'^\s*\d{1,2}\s+', '', answer))
        titles = (self.DETAILS_YES, self.DETAILS_NO, self.DETAILS_CANCEL,
                  self.FIX_NAME, self.FIX_ADDRESS, self.FIX_BACK)
        if key and key in [self._sa_menu_key(t) for t in titles]:
            return True
        return self._read_yes_no(answer, numbered=False) is not None

    def _sa_details_catalog_show(self, term):
        """Show what `term` finds in the catalogue; None when nothing. Nothing
        here: the NEW ORDER module overrides it."""
        return None

    def _sa_details_off_topic(self, text):
        """A product word on the read-back is shown from the catalogue (the
        order keeps waiting); anything else: "couldn't find - type the right
        word, or hi"."""
        self.ensure_one()
        term = ' '.join((text or '').split())[:80]
        shown = self._sa_details_catalog_show(term)
        if shown is not None:
            _logger.info("Sales Automation: enquiry %s waits for details - %r shown from the catalogue",
                         self.id, term)
            return shown
        if self._sa_listed_unshown(term):
            return None
        return self._sa_say_not_found(term)

    def _sa_listed_unshown(self, term):
        """True for a product the shop has but the menu cannot show. Nothing
        here: the NEW ORDER module answers it."""
        return False

    def _sa_say_not_found(self, term):
        """"Sorry, we couldn't find anything for X - type the correct product
        name, or hi" (owner, 22 Nov 2026). Always True: the text is answered."""
        self.ensure_one()
        term = ' '.join((term or '').split())[:60]
        who = self.requester_phone or self.requester_lid or 'anon'
        key = 'notfound|%s|%s|%s' % (self.group_id.id, who, term.lower())
        if not self.env['sa.outbox.guard'].sudo().claim(key, 120):
            return True         # said a moment ago: once is enough
        body = _("\U0001F50D Sorry, we couldn't find anything for *%(term)s*.\n\n"
                 "Please type the correct product name, or type *hi* to continue.",
                 term=term or '-')
        contact = self._sa_contact_number()
        if contact:
            body += _("\n\nFor anything else, please contact us on *%(phone)s*.", phone=contact)
        self._say(body)
        _logger.info("Sales Automation: enquiry %s - nothing found for %r", self.id, term)
        return True


class SaleOrderGroupSigned(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            try:
                req = order._sa_group_enquiry()
                if req:
                    req.sudo()._sa_group_signed(order)
            except Exception as err:  # noqa: BLE001 - the confirmation stands
                _logger.warning("Sales Automation: after-signature step for %s "
                                "failed: %s", order.name, err)
        return res


class ResPartnerDeliveryNote(models.Model):
    _inherit = 'res.partner'

    sa_delivery_note = fields.Char(
        'Delivery note / landmark',
        help="Flat, gate or landmark the customer gave on WhatsApp. Kept for "
             "their next order and copied onto each delivery job.")
