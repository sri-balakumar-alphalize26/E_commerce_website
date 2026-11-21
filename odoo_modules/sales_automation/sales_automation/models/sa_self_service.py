# -*- coding: utf-8 -*-
"""The customer's self-service menu in the WhatsApp group (7 Oct 2026).

"hi" opens:  📦 MY ORDERS · 🚚 TRACK MY ORDER · 🆕 NEW ORDER · 💰 WALLET & POINTS · ➕ MORE
  MY ORDERS -> one button per order -> the order card, with only the buttons
  that apply: TRACK · DOOR CODE · INVOICE · PAY · SIGN · CANCEL · RETURN.
  MORE      -> MY DETAILS · CHANGE ADDRESS · HELP · TALK TO A PERSON ·
               STOP / START UPDATES (+ whatever other modules add).
Every screen has BACK and MAIN MENU and at most ten options. Typed questions
("where is my order", "send invoice", "door code", "talk to a person") get the
same answers without the menu.

Built as *slots*: each `_sa_...` method below works on its own for WhatsApp
orders and is meant to be overridden. The 369 Mart bridge (another team's
module) fills them with its website orders, wallet, points and rider data.
Slots and what they return:

  _sa_customer_orders()        list of rows {key, ref, title, status, total_text,
                               paid, in_flight, delivered, needs_sign, can_pay, can_cancel,
                               can_return, has_invoice, can_code}, newest first
  _sa_order_card(key)          text
  _sa_track_text(key)          text
  _sa_resend_door_code(key)    text (the code itself goes privately)
  _sa_send_invoice(key)        text
  _sa_cancel_order(key)        text or None (None = the flow already spoke)
  _sa_start_return(key)        text
  _sa_wallet_text()            text, '' hides WALLET & POINTS
  _sa_help_text()              text for HELP
  _sa_help_answer(text)        text for a typed question, None = not a question
  _sa_hand_to_person(reason)   text
  _sa_updates_on()             bool;  _sa_set_updates(on) -> text
`key` is an opaque string; ours is "req:<enquiry id>".
"""
import json
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

STATUS_WORDS = {
    'awaiting_shop': 'Being prepared at the shop',
    'preparing': 'Being packed',
    'ready': 'Packed, waiting for the rider',
    'to_assign': 'Finding a rider',
    'offered': 'Finding a rider',
    'accepted': 'Rider is going to the shop',
    'picked': 'Picked up by the rider',
    'dispatched': 'On the way to you',
    'out_for_delivery': 'Rider is near you',
    'delivered': 'Delivered',
    'returning': 'Coming back to the shop',
    'returned': 'Returned to the shop',
    'failed': 'Could not be delivered',
}
IN_FLIGHT = ('awaiting_shop', 'preparing', 'ready', 'to_assign', 'offered',
             'accepted', 'picked', 'dispatched', 'out_for_delivery')
ON_THE_ROAD = ('dispatched', 'out_for_delivery')
RETURN_DAYS = 7
PERSON_HOURS = 2


class ResPartnerUpdates(models.Model):
    _inherit = 'res.partner'

    sa_wa_updates_off = fields.Boolean(
        'WhatsApp Updates Off',
        help="The customer tapped STOP UPDATES: delivery status messages "
             "(packed, on the way, ...) are not sent. The delivery code, "
             "invoices and answers to their own questions still are.")


class SaGroupRequestSelfService(models.Model):
    _inherit = 'sa.group.request'

    sa_person_until = fields.Datetime(
        'Waiting for a Person Until', copy=False, readonly=True,
        help="The customer asked to talk to a person: the assistant stays "
             "quiet for them until then (or until they type hi).")

    SS_ORDERS = '\U0001F4E6 MY ORDERS'
    SS_TRACK = '\U0001F69A TRACK MY ORDER'
    SS_NEW = '\U0001F195 NEW ORDER'
    SS_WALLET = '\U0001F4B0 WALLET & POINTS'
    SS_MORE = '➕ MORE'
    SS_SHOP = '🛒 SHOP ONLINE'

    # ------------------------------------------------------------------
    # The shop's website (system parameter `sa.shop_url`, empty = no link).
    # A plain URL in a plain text is the only tappable link that renders on
    # this transport everywhere (group, one-to-one, WhatsApp Web); URL
    # buttons arrive as "This message couldn't load" and lists never show.
    # ------------------------------------------------------------------
    def _sa_shop_url(self):
        return (self.env['ir.config_parameter'].sudo().get_param('sa.shop_url', '') or '').strip()

    def _sa_shop_line(self):
        url = self._sa_shop_url()
        return _("🛒 Shop online: %s") % url if url else ''

    def _sa_say_shop_link(self):
        """The link line with WhatsApp's preview card under it."""
        line = self._sa_shop_line()
        if not line:
            return False
        return self.with_context(sa_link_preview=True)._say(line, addressed=False)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _sa_ss_requests(self):
        """This customer's enquiries with an order in this group, newest first."""
        self.ensure_one()
        digits = ''.join(c for c in (self.requester_phone or '') if c.isdigit())
        tail = digits[-9:] if len(digits) >= 9 else ''
        lid = self.requester_lid or ''
        dom = [('group_id', '=', self.group_id.id), ('order_id', '!=', False)]
        if tail and lid:
            dom += ['|', ('requester_phone', 'like', tail), ('requester_lid', '=', lid)]
        elif tail:
            dom += [('requester_phone', 'like', tail)]
        elif lid:
            dom += [('requester_lid', '=', lid)]
        else:
            return self.browse()
        return self.sudo().search(dom, order='id desc', limit=20)

    def _sa_ss_job(self, order, live_only=False):
        jobs = order.sudo().picking_ids.filtered(
            lambda p: p.state != 'cancel' and getattr(p, 'sa_delivery_state', 'none') not in ('none', False))
        if live_only:
            jobs = jobs.filtered(lambda p: p.sa_delivery_state in IN_FLIGHT)
        return jobs.sorted('id', reverse=True)[:1]

    def _sa_ss_invoices(self, order):
        return order.sudo().invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted')

    def _sa_customer_orders(self):
        rows, seen = [], set()
        for r in self._sa_ss_requests():
            o = r.order_id.sudo()
            if o.state == 'cancel' or o.id in seen:
                continue
            seen.add(o.id)
            job = self._sa_ss_job(o)
            dstate = job.sa_delivery_state if job else False
            paid = r._sa_order_is_paid(o)
            needs_sign = bool(o.state in ('draft', 'sent') and o._has_to_be_signed()
                              and r.sa_sign_link_sent_on)
            delivered = dstate == 'delivered'
            in_flight = dstate in IN_FLIGHT
            if dstate and dstate in STATUS_WORDS:
                status = _(STATUS_WORDS[dstate])
            elif needs_sign:
                status = _("Waiting for your signature")
            elif not paid and (r.sa_pay_link_sent_on or o.state in ('draft', 'sent')):
                status = _("Waiting for payment")
            elif o.state in ('draft', 'sent'):
                status = _("Not confirmed yet")
            else:
                status = _("Confirmed")
            done_on = getattr(job, 'sa_delivered_on', False) if delivered else False
            rows.append({
                'key': 'req:%d' % r.id,
                'ref': r.ref_code or o.name,
                'title': o.name,
                'status': status,
                'total_text': '%s %.2f' % (o.currency_id.symbol or '', o.amount_total),
                'paid': paid,
                'in_flight': in_flight,
                'delivered': delivered,
                'needs_sign': needs_sign,
                'can_pay': bool(not paid and not needs_sign and not delivered
                                and (r.sa_pay_link_sent_on or o.state in ('draft', 'sent'))),
                'can_cancel': bool(not paid and not delivered and dstate not in ('picked',) + ON_THE_ROAD),
                'can_return': bool(delivered and done_on
                                   and fields.Datetime.now() - done_on <= timedelta(days=RETURN_DAYS)),
                'has_invoice': bool(self._sa_ss_invoices(o)),
                'can_code': dstate in ON_THE_ROAD and hasattr(job, 'sa_issue_delivery_otp'),
            })
        return rows

    def _sa_ss_row(self, key):
        for row in self._sa_customer_orders():
            if row['key'] == key:
                return row
        return None

    def _sa_ss_req_of(self, key):
        """Our own key -> the enquiry, only if it is this customer's."""
        m = re.fullmatch(r'req:(\d+)', key or '')
        if not m:
            return self.browse()
        req = self.sudo().browse(int(m.group(1))).exists()
        return req if req and req in self._sa_ss_requests() else self.browse()

    # ------------------------------------------------------------------
    # Continue an unfinished order (owner, 8 Oct 2026): a customer who left
    # half-way and comes back with "hi" gets one extra option on top of the
    # main menu - "▶️ #7M LAPTOP BATTERY (How many?)" - and a tap asks that
    # step's question again. Confirmed but unpaid orders count too.
    # ------------------------------------------------------------------
    RESUME_DAYS = 14
    _SA_RESUME_SKIP = ('dropped', 'new', 'sourcing', 'awaiting_vendor_pick', 'answered', 'handed_off')

    def _sa_ss_my_enquiries(self):
        """This customer's enquiries in this group from the last RESUME_DAYS,
        any state but closed or waiting on the shop, newest first."""
        self.ensure_one()
        digits = ''.join(c for c in (self.requester_phone or '') if c.isdigit())
        tail = digits[-9:] if len(digits) >= 9 else ''
        lid = self.requester_lid or ''
        since = fields.Datetime.now() - timedelta(days=self.RESUME_DAYS)
        dom = [('group_id', '=', self.group_id.id), ('state', 'not in', self._SA_RESUME_SKIP),
               ('create_date', '>=', since)]
        if tail and lid:
            dom += ['|', ('requester_phone', 'like', tail), ('requester_lid', '=', lid)]
        elif tail:
            dom += [('requester_phone', 'like', tail)]
        elif lid:
            dom += [('requester_lid', '=', lid)]
        else:
            return self.browse()
        return self.sudo().search(dom, order='id desc', limit=10)

    def _sa_resume_step(self):
        """(step key, words for the brackets) when this enquiry waits on the
        CUSTOMER, else (False, ''). Steps: confirm, finder, offer, qty,
        summary, details, sign, pay."""
        self.ensure_one()
        r = self.sudo()
        cur = r.currency_id.symbol or r.currency_id.name or ''
        st = r.state
        if st == 'awaiting_confirm':
            link = getattr(r, 'sa_confirm_link_id', False)
            if link and link.decided:
                return False, ''
            return 'confirm', _("Waiting for your confirmation")
        if st == 'finding':
            if getattr(r, 'finder_locked', False):
                return False, ''
            return 'finder', _("Choosing the exact model")
        if st in ('quoted', 'negotiating'):
            price = r.agreed_price or r.quoted_price
            return 'offer', (_("Price offered · %s %.2f") % (cur, price)) if price else _("Price offered")
        if st == 'awaiting_qty':
            return 'qty', _("How many?")
        if st == 'awaiting_order_confirm':
            return 'summary', _("Confirm your order")
        o = r.order_id
        if st != 'order_created' or not o or o.state == 'cancel':
            return False, ''
        if r.sa_details_pending:
            step = r.sa_details_fix if r.sa_details_fix in ('name', 'address') else r.profile_step
            if step == 'name':
                return 'details', _("Name needed")
            if step in ('address', 'pin'):
                return 'details', _("Address needed")
            if step == 'confirm':
                return 'details', _("Check your details")
            return 'details', _("Details needed")
        if o.state in ('draft', 'sent') and o._has_to_be_signed() and r.sa_sign_link_sent_on:
            return 'sign', _("Signature needed")
        if r._sa_order_is_paid(o):
            return False, ''
        job = self._sa_ss_job(o)
        if job and job.sa_delivery_state in ('delivered', 'returning', 'returned'):
            return False, ''
        due = (o.amount_total or 0.0) - (o._sa_paid_elsewhere() or 0.0)
        if due <= 0.005:
            return False, ''
        return 'pay', _("Payment pending · %s %.2f") % (o.currency_id.symbol or cur, due)

    def _sa_resume_candidate(self):
        """Slot: (enquiry, step, bracket words) for the main menu's extra
        option - the newest enquiry of this customer that waits on them -
        or (None, False, '')."""
        self.ensure_one()
        for r in self._sa_ss_my_enquiries():
            step, words = r._sa_resume_step()
            if step:
                return r, step, words
        return None, False, ''

    def _sa_resume_label(self, req, step, words):
        o = req.order_id
        name = ''
        if getattr(req, 'sa_variant_id', False) and hasattr(req, '_sa_variant_name'):
            name = req._sa_variant_name()
        name = (name or req.product_id.name or (o.order_line[:1].product_id.name if o else '')
                or req.ai_search_term or req.raw_text or '').strip().replace('\n', ' ')
        if len(name) > 28:
            name = name[:27].rstrip() + '…'
        icon = '\U0001F4B3' if step == 'pay' else '▶️'
        return ('%s #%s %s (%s)' % (icon, req.ref_code or (o.name if o else req.id), name, words))[:99]

    def _sa_resume_continue(self, step):
        """Ask the question of `step` again, from this enquiry."""
        self.ensure_one()
        if step == 'confirm':
            # The confirmation page (sales_automation_confirm): the link again,
            # as text - it makes the link when the enquiry has none yet.
            if hasattr(self, '_sa_confirm_customer_send') and self._sa_confirm_settings().confirm_enabled \
                    and (self.product_id or self._sa_confirm_name()):
                return self._sa_confirm_customer_send(text_only=True)
            return self._ask_confirmation()
        if step == 'finder':
            return self._finder_ask(self.finder_step or 'type')
        if step == 'offer':
            return self._say_current_offer('')
        if step == 'qty':
            return self._ask_quantity(repeat=True)
        if step == 'summary':
            if getattr(self, 'sa_stock_confirm_on', False) and not getattr(self, 'sa_stock_confirmed', False):
                return self._sa_ask_stock_confirm(repeat=True)
            return self._ask_order_confirm()
        if step == 'details':
            return self._sa_details_ask(self.order_id)
        if step in ('sign', 'pay'):
            return self._sa_menu_tapped({'kind': step, 'target': self.id, 'parent': 'main'})
        return False

    def _sa_resume_tap(self, item):
        """The extra option was tapped: carry on from where the order is NOW."""
        self.ensure_one()
        target = self.sudo().browse(item.get('target') or 0).exists()
        if not target or target not in self._sa_ss_my_enquiries():
            self._say(_("That order is no longer available."))
            return self._sa_menu_show('main')
        step, _words = target._sa_resume_step()
        if not step:
            self._say(_("✅ Order #%s needs nothing more from you.") % (target.ref_code or target.id))
            return self._sa_menu_show('main')
        return target._sa_resume_continue(step)

    def _sa_ss_when(self, dt, company):
        if not dt:
            return ''
        tz = 'UTC'
        if 'sa.delivery.partner' in self.env:
            try:
                tz = self.env['sa.delivery.partner']._sa_company_tz(company) or tz
            except Exception:  # noqa: BLE001
                pass
        local = fields.Datetime.context_timestamp(self.with_context(tz=tz), dt)
        today = fields.Datetime.context_timestamp(self.with_context(tz=tz), fields.Datetime.now()).date()
        day = '' if local.date() == today else local.strftime('%d %b ')
        return day + local.strftime('%I:%M %p').lstrip('0')

    def _sa_order_card(self, key):
        req = self._sa_ss_req_of(key)
        row = self._sa_ss_row(key)
        if not req or not row:
            return _("That order is no longer available.")
        o = req.order_id.sudo()
        job = self._sa_ss_job(o)
        money = (_("✅ Paid") if row['paid'] else
                 _("✍️ Waiting for your signature") if row['needs_sign'] else
                 _("\U0001F4B5 To pay"))
        lines = [_("*Order #%(ref)s* (%(name)s)", ref=row['ref'], name=o.name),
                 self._sa_order_lines_text(o),
                 _("*Total: %s*") % row['total_text'], money,
                 '\U0001F69A %s' % row['status']]
        promised = getattr(job, 'sa_promised_on', False) if job else False
        if promised and row['in_flight']:
            lines[-1] += _(", arriving by %s") % self._sa_ss_when(promised, o.company_id)
        return '\n'.join(x for x in lines if x)

    def _sa_track_text(self, key):
        req = self._sa_ss_req_of(key)
        row = self._sa_ss_row(key)
        if not req or not row:
            return _("That order is no longer available.")
        o = req.order_id.sudo()
        job = self._sa_ss_job(o)
        if not job:
            return _("\U0001F4E6 *Order #%(ref)s*: %(status)s.\nIt has not left the shop yet - "
                     "you will get a message here when it does.", ref=row['ref'], status=row['status'])
        out = [_("\U0001F69A *Order #%(ref)s*: %(status)s", ref=row['ref'], status=row['status'])]
        rider = job.sa_delivery_partner_id if 'sa_delivery_partner_id' in job._fields else False
        if rider and job.sa_delivery_state in ('accepted', 'picked') + ON_THE_ROAD:
            out.append(_("%s is bringing it.") % rider.name)
            if job.sa_delivery_state in ON_THE_ROAD and rider.phone:
                out.append(_("Call the rider: %s") % rider.phone)
        promised = getattr(job, 'sa_promised_on', False)
        if promised and row['in_flight']:
            out.append(_("Arriving by %s") % self._sa_ss_when(promised, o.company_id))
        url = getattr(job, 'sa_track_url', '') if row['in_flight'] else ''
        if url:
            out.append(_("Follow it live: %s") % url)
        return '\n'.join(out)

    def _sa_resend_door_code(self, key):
        req = self._sa_ss_req_of(key)
        row = self._sa_ss_row(key)
        if not req or not row or not row['can_code']:
            return _("The door code is sent when the rider is on the way to you.")
        job = self._sa_ss_job(req.order_id, live_only=True)
        try:
            ok, _msg, _code = job.sa_issue_delivery_otp()     # private message, never the group
        except Exception as err:  # noqa: BLE001
            _logger.warning("Self-service door code for %s failed: %s", row['ref'], err)
            ok = False
        if not ok:
            return _("Sorry, the code could not be sent just now - the rider can ask for it at the door.")
        digits = ''.join(c for c in (job.partner_id.phone or '') if c.isdigit())
        return _("\U0001F511 The door code for order *#%(ref)s* was sent to your own WhatsApp "
                 "number%(end)s. Give it to the rider only after you have the parcel.",
                 ref=row['ref'], end=(' (•••%s)' % digits[-4:]) if len(digits) >= 4 else '')

    def _sa_send_invoice(self, key):
        req = self._sa_ss_req_of(key)
        if not req:
            return _("That order is no longer available.")
        inv = self._sa_ss_invoices(req.order_id)[:1]
        if not inv:
            return _("There is no invoice for this order yet - it comes here as soon as it is made.")
        session = self.group_id.session_id
        caption = _("\U0001F9FE Invoice %(name)s for order #%(ref)s",
                    name=inv.name or '', ref=req.ref_code or req.order_id.name)
        try:
            # privately when allowed (sa_private_links.py), the group otherwise
            where = req._sa_send_doc(
                lambda to: session.send_odoo_report(to, 'account.account_invoices', inv, caption=caption))
        except Exception as err:  # noqa: BLE001
            _logger.warning("Self-service invoice for %s failed: %s", inv.name, err)
            return _("Sorry, the invoice could not be sent just now. Please try again in a minute.")
        if where == 'private':
            return _("\U0001F9FE Invoice %s sent to your *private chat* \U0001F512") % (inv.name or '')
        return _("\U0001F9FE Invoice %s is above.") % (inv.name or '')

    def _sa_cancel_order(self, key):
        req = self._sa_ss_req_of(key)
        row = self._sa_ss_row(key)
        if not req or not row:
            return _("That order is no longer available.")
        if not row['can_cancel']:
            return _("Order #%s can no longer be cancelled here - tap TALK TO A PERSON and "
                     "our team will help.") % row['ref']
        req._sa_cancel_deal()
        return None

    def _sa_start_return(self, key):
        row = self._sa_ss_row(key)
        ref = row['ref'] if row else ''
        return self._sa_hand_to_person(_("return of order #%s") % ref)

    def _sa_wallet_text(self):
        return ''

    def _sa_help_text(self):
        return _("❓ *How to use this chat*\n\n"
                 "• Everything is a tap: say *hi* any time and pick from the menu\n"
                 "• To order: tap *NEW ORDER*, or just send the product name, like "
                 "*Redmi Note 13 back cover*\n"
                 "• Your orders, tracking, invoice and door code are under *MY ORDERS*\n"
                 "• Tap *TALK TO A PERSON* if you need our team")

    _SA_HELP_PATTERNS = [
        ('track', r"\b(where('?s| is)? (is )?my (order|parcel|delivery)|track(ing)? (my )?(order|parcel)|"
                  r"order status|status of (my )?order|when will (my )?(order|parcel) (come|arrive)|"
                  r"(who|which) is my rider|rider (name|number|phone|details)|delivery boy)\b"),
        ('invoice', r"\b((send|need|want|get|share)( me)? (the |my )?(invoice|bill)|^invoice$|^bill$)"),
        ('code', r"\b(door code|delivery code|otp|delivery otp)\b"),
        ('person', r"\b(talk|speak|chat) (to|with) (a |an )?(person|human|agent|staff|someone|team)|"
                   r"customer (care|support)|call me\b"),
        ('help', r"^(help|menu help|how to order)$"),
    ]

    def _sa_help_answer(self, text):
        """A typed question answered without the menu, or None."""
        low = (text or '').strip().lower()
        if not low or len(low) > 80:
            return None
        kind = next((k for k, p in self._SA_HELP_PATTERNS if re.search(p, low)), None)
        if not kind:
            return None
        if kind == 'help':
            return self._sa_help_text()
        if kind == 'person':
            return self._sa_hand_to_person(_("asked in the chat: %s") % text[:60])
        rows = self._sa_customer_orders()
        if not rows:
            return _("You have no orders with us yet. Type the product you need to start one \U0001F642")
        if kind == 'track':
            live = [r for r in rows if r['in_flight']] or rows[:1]
            return '\n\n'.join(self._sa_track_text(r['key']) for r in live[:3])
        if kind == 'invoice':
            row = next((r for r in rows if r['has_invoice']), None)
            return self._sa_send_invoice(row['key']) if row else _(
                "None of your orders has an invoice yet - it comes here as soon as it is made.")
        if kind == 'code':
            row = next((r for r in rows if r['can_code']), None)
            return self._sa_resend_door_code(row['key']) if row else _(
                "The door code is sent when the rider is on the way to you.")
        return None

    def _sa_hand_to_person(self, reason=''):
        """The assistant steps aside for this customer and the team is told."""
        self.ensure_one()
        until = fields.Datetime.now() + timedelta(hours=PERSON_HOURS)
        self.sudo().write({'sa_person_until': until})
        try:
            order = self._sa_ss_requests()[:1].order_id.sudo()
            target = order or self._sa_book_customer() if hasattr(self, '_sa_book_customer') else order
            if target:
                user = (order.user_id if order else False) or self.env.ref('base.user_admin')
                target.activity_schedule(
                    'mail.mail_activity_data_todo', user_id=user.id,
                    summary=_("WhatsApp: customer wants to talk to a person"),
                    note=_("%(who)s (%(phone)s) in group %(group)s - %(why)s",
                           who=self.requester_name or '', phone=self.requester_phone or '',
                           group=self.group_id.name or '', why=reason or ''))
        except Exception as err:  # noqa: BLE001 - the customer still gets the answer
            _logger.warning("Talk-to-a-person to-do for %s failed: %s", self.requester_phone, err)
        return _("\U0001F64B A team member will reply to you here shortly. The assistant stays "
                 "quiet for you meanwhile - type *hi* any time to get the menu back.")

    def _sa_ss_customer(self):
        if hasattr(self, '_sa_book_customer'):
            return self._sa_book_customer()
        return self.order_id.partner_id.sudo() if self.order_id else self._sa_address_partner()

    # The shop app has its own "WhatsApp updates" switch on the same customer
    # (mart369_notify_whatsapp, True = wants them). The two are kept in step:
    # off in either means off, and STOP / START here moves both.
    _SA_SHOP_SWITCH = 'mart369_notify_whatsapp'

    def _sa_updates_on(self):
        customer = self._sa_ss_customer()
        if not customer:
            return True
        if customer.sa_wa_updates_off:
            return False
        if self._SA_SHOP_SWITCH in customer._fields and not customer[self._SA_SHOP_SWITCH]:
            return False
        return True

    def _sa_set_updates(self, on):
        customer = self._sa_ss_customer()
        if not customer:
            return _("Sorry, we could not find your customer record.")
        vals = {'sa_wa_updates_off': not on}
        if self._SA_SHOP_SWITCH in customer._fields:
            vals[self._SA_SHOP_SWITCH] = bool(on)
        customer.sudo().write(vals)
        if on:
            return _("\U0001F514 Delivery updates are back on - you will hear from us at every step.")
        return _("\U0001F515 Delivery updates are off. You will still get your door code, invoices "
                 "and answers to your questions. Tap START UPDATES under MORE to turn them back on.")

    # ------------------------------------------------------------------
    # Screens
    # ------------------------------------------------------------------
    def _sa_ss_post(self, level, body, opts):
        """Keep the options (by label) and post the poll; BACK and MAIN on
        every screen but the main one; never more than ten options."""
        if level != 'main':
            parent = 'orders' if level.startswith('order:') else self.MENU_PARENT.get(level, 'main')
            opts = opts[:8] + [(self.MENU_BACK, {'kind': 'menu', 'level': parent}),
                               (self.MENU_MAIN, {'kind': 'menu', 'level': 'main'})]
        menu = {}
        for label, item in opts[:10]:
            item = dict(item)
            item.setdefault('req', self.id)
            item['parent'] = level
            menu[label] = item
        self.sa_menu_json = json.dumps(menu)
        self._ask(body, [{'id': 'sa_menu_%d' % i, 'title': label} for i, label in enumerate(menu)])
        return True

    def _sa_menu_show(self, level):
        self.ensure_one()
        if level == 'main':
            rows = self._sa_customer_orders()
            name = self._sa_known_name()
            if not name:
                push = (self.requester_name or '').strip()
                name = push if push and self._sa_looks_like_name(push) else ''
            name = name.split(' ')[0]
            body = _("Hi %s \U0001F44B What would you like to do? Tap one, "
                     "or just type the product you need:") % name if name \
                else _("Hi \U0001F44B What would you like to do? Tap one, "
                       "or just type the product you need:")
            opts = []
            req, step, words = self._sa_resume_candidate()
            if req:
                opts.append((self._sa_resume_label(req, step, words),
                             {'kind': 'ss_resume', 'target': req.id, 'step': step}))
            if rows:
                opts.append((self.SS_ORDERS, {'kind': 'menu', 'level': 'orders'}))
            if any(r['in_flight'] for r in rows):
                opts.append((self.SS_TRACK, {'kind': 'ss_track_any'}))
            opts.append((self.SS_NEW, {'kind': 'new'}))
            if self._sa_shop_url():
                self._sa_say_shop_link()
                opts.append((self.SS_SHOP, {'kind': 'ss_shop'}))
            if self._sa_wallet_text():
                opts.append((self.SS_WALLET, {'kind': 'ss_wallet'}))
            opts.append((self.SS_MORE, {'kind': 'menu', 'level': 'more'}))
            return self._sa_ss_post('main', body, opts)
        if level in ('orders', 'orders_live'):
            rows = self._sa_customer_orders()
            if level == 'orders_live':
                rows = [r for r in rows if r['in_flight']]
            body = _("\U0001F4E6 *Your orders* - tap one:") if rows else _("You have no orders yet.")
            opts = [('#%s · %s · %s' % (r['ref'], r['status'], r['total_text']),
                     {'kind': 'menu', 'level': 'order:%s' % r['key']}) for r in rows[:8]]
            return self._sa_ss_post('orders', body, opts)
        if level.startswith('order:'):
            key = level[len('order:'):]
            row = self._sa_ss_row(key)
            if not row:
                return self._sa_menu_show('orders')
            self._say(self._sa_order_card(key))
            req = self._sa_ss_req_of(key)
            opts = []
            if row['in_flight'] or row['delivered']:
                opts.append((_("\U0001F69A TRACK"), {'kind': 'ss_track', 'key': key}))
            if row['can_code']:
                opts.append((_("\U0001F511 DOOR CODE"), {'kind': 'ss_code', 'key': key}))
            if row['has_invoice']:
                opts.append((_("\U0001F9FE INVOICE"), {'kind': 'ss_invoice', 'key': key}))
            if row['needs_sign']:
                opts.append((_("✍️ SIGN"), {'kind': 'sign', 'target': req.id}))
            if row['can_pay']:
                opts.append((_("\U0001F4B3 PAY"), {'kind': 'pay', 'target': req.id}))
            if row['can_cancel']:
                opts.append((_("❌ CANCEL ORDER"), {'kind': 'ss_cancel', 'key': key}))
            if row['can_return']:
                opts.append((_("↩️ RETURN"), {'kind': 'ss_return', 'key': key}))
            return self._sa_ss_post(level, _("What would you like to do with order #%s?") % row['ref'], opts)
        if level == 'more':
            opts = list(self._sa_more_extra_options())
            opts += [(_("\U0001F464 MY DETAILS"), {'kind': 'details'}),
                     (_("\U0001F4CD CHANGE ADDRESS"), {'kind': 'address'}),
                     (_("❓ HELP"), {'kind': 'ss_help'}),
                     (_("\U0001F64B TALK TO A PERSON"), {'kind': 'ss_person'})]
            if self._sa_updates_on():
                opts.append((_("\U0001F515 STOP UPDATES"), {'kind': 'ss_updates', 'on': False}))
            else:
                opts.append((_("\U0001F514 START UPDATES"), {'kind': 'ss_updates', 'on': True}))
            return self._sa_ss_post('more', _("More options - tap one:"), opts)
        return super()._sa_menu_show(level)

    def _sa_menu_tapped(self, item):
        self.ensure_one()
        kind = item.get('kind')
        parent = item.get('parent') or 'main'
        key = item.get('key')
        if kind == 'ss_track_any':
            live = [r for r in self._sa_customer_orders() if r['in_flight']]
            if len(live) == 1:
                self._say(self._sa_track_text(live[0]['key']))
                return self._sa_nav('main')
            return self._sa_menu_show('orders_live' if live else 'orders')
        if kind == 'ss_resume':
            return self._sa_resume_tap(item)
        say = None
        if kind == 'ss_track':
            say = self._sa_track_text(key)
        elif kind == 'ss_code':
            say = self._sa_resend_door_code(key)
        elif kind == 'ss_invoice':
            say = self._sa_send_invoice(key)
        elif kind == 'ss_cancel':
            say = self._sa_cancel_order(key)
            if say is None:
                return True                 # the cancel step already spoke
        elif kind == 'ss_return':
            say = self._sa_start_return(key)
        elif kind == 'ss_wallet':
            say = self._sa_wallet_text() or _("Wallet and points are not available on this shop yet.")
        elif kind == 'ss_shop':
            self._sa_say_shop_link() or self._say(_("The online shop is not set up yet."))
            return self._sa_nav(parent)
        elif kind == 'ss_help':
            say = self._sa_help_text()
        elif kind == 'ss_person':
            self._say(self._sa_hand_to_person(_("tapped TALK TO A PERSON")))
            return True                     # no further menu: a person takes over
        elif kind == 'ss_updates':
            say = self._sa_set_updates(bool(item.get('on')))
        else:
            return super()._sa_menu_tapped(item)
        self._say(say)
        if kind == 'ss_return':
            return True
        return self._sa_nav(parent)

    # ------------------------------------------------------------------
    # Routing: typed questions, and quiet while a person takes over
    # ------------------------------------------------------------------
    @api.model
    def _sa_ss_sender_rows(self, group, message, extra=None):
        digits = ''.join(c for c in (message.participant_phone or '') if c.isdigit())
        tail = digits[-9:] if len(digits) >= 9 else ''
        lid = message.participant_lid or ''
        dom = [('group_id', '=', group.id)] + (extra or [])
        if tail and lid:
            dom += ['|', ('requester_phone', 'like', tail), ('requester_lid', '=', lid)]
        elif tail:
            dom += [('requester_phone', 'like', tail)]
        elif lid:
            dom += [('requester_lid', '=', lid)]
        else:
            return self.browse()
        return self.sudo().search(dom, order='id desc', limit=5)

    @api.model
    def _sa_typed_answer_hook(self, group, message, text):
        res = super()._sa_typed_answer_hook(group, message, text)
        if res is not None:
            return res
        rows = self._sa_ss_sender_rows(group, message)
        owner = rows[:1]
        if not owner:
            return None
        try:
            answer = owner._sa_help_answer(text)
        except Exception as err:  # noqa: BLE001 - never lose the message over a help answer
            _logger.warning("Self-service typed answer failed: %s", err)
            return None
        if not answer:
            return None
        owner._say(answer)
        if owner.sa_person_until and owner.sa_person_until > fields.Datetime.now():
            return True                     # handed to a person: no menu after it
        owner._sa_nav('main')
        return True

    @api.model
    def _on_group_message(self, message):
        """While a person is taking over for this customer, the assistant
        reads nothing they type - unless they say hi to get the menu back."""
        group = self.env['sa.sales.group'].sudo().search([
            ('session_id', '=', message.session_id.id), ('group_jid', '=', message.group_jid),
            ('enabled', '=', True)], limit=1)
        text = (message.message or '').strip()
        if group and text and group.group_type != 'vendor' and not self.env.context.get('sa_poll_ref'):
            held = self._sa_ss_sender_rows(group, message,
                                           [('sa_person_until', '>', fields.Datetime.now())])
            if held:
                if self._sa_is_greeting(text) or text.lower().strip(' .!') in ('menu', 'bot'):
                    held.write({'sa_person_until': False})
                else:
                    _logger.info("Sales Automation: %s is with a person - assistant quiet",
                                 message.participant_phone or message.participant_lid)
                    return True
        return super()._on_group_message(message)
