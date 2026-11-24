# -*- coding: utf-8 -*-
"""Goods not in stock: sign first, pay when they arrive, all in the group.

  1. Order placed without stock -> a "sign your order" link (no payment).
     The signature confirms the order; its job then waits at the counter.
  2. Goods at the branch, the shop presses Accept -> the pay link, with the
     order number, the lines and the amount. Packing is blocked until paid.
  3. Paid -> the paid invoice and the delivery date, then the usual flow.
     Not paid -> reminders, the last one saying a sales agent will assist.
  4. A returning customer saying hello is shown their orders: track the
     paid one, pay the waiting one, or start something new.
"""
import json
import logging
import re
from datetime import timedelta
from urllib.parse import urlsplit

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

IN_FLIGHT = ('awaiting_shop', 'preparing', 'ready', 'to_assign', 'offered',
             'accepted', 'picked', 'dispatched', 'out_for_delivery')


class SaGroupRequestOos(models.Model):
    _inherit = 'sa.group.request'

    sa_sign_link_sent_on = fields.Datetime('Sign Link Sent On', copy=False)
    sa_address_pending = fields.Selection([('typing', 'Waiting for the new address'),
                                           ('confirm', 'Waiting for the confirmation')],
                                          'Address change', copy=False)
    sa_address_draft = fields.Text('New address (unconfirmed)', copy=False)
    sa_change_pending = fields.Boolean('CHANGE menu shown', copy=False)
    sa_menu_json = fields.Text('Returning-customer menu', copy=False,
                               help="The options of the last welcome-back poll, by label.")

    # ------------------------------------------------------------------
    # Links
    # ------------------------------------------------------------------
    def _sa_portal_link(self, order):
        return self.env['wa.auto.reply'].sudo()._sa_public_link(
            '/my/orders/%s?access_token=%s' % (order.id, order.sudo()._portal_ensure_token()))

    def _sa_pay_link_any_state(self, order):
        """A link that takes money for the order whatever its state. The
        portal order page only pays a quotation; a confirmed order pays
        through Odoo's payment link, re-based onto the public address."""
        order = order.sudo()
        if order.state in ('draft', 'sent'):
            return self.env['wa.auto.reply'].sudo()._online_pay_msg(order, 'card')
        try:
            w = self.env['payment.link.wizard'].sudo().with_context(
                active_model='sale.order', active_id=order.id).create({
                    'res_model': 'sale.order', 'res_id': order.id,
                    'amount': order.amount_total, 'currency_id': order.currency_id.id,
                    'partner_id': order.partner_id.id})
            parts = urlsplit(w.link or '')
            path = parts.path + ('?' + parts.query if parts.query else '')
            url = self.env['wa.auto.reply'].sudo()._sa_public_link(path)
        except Exception as err:  # noqa: BLE001 - fall back to the order page
            _logger.warning("Pay link for %s: wizard failed (%s), using the order page", order.name, err)
            url = self._sa_portal_link(order)
        return _("\U0001F4B3 Pay here:\n%(url)s", url=url)

    def _sa_order_lines_text(self, order):
        out = []
        for l in order.order_line.filtered(lambda l: not l.display_type and l.product_id):
            q = l.product_uom_qty
            out.append('%s x %s' % (('%g' % q), l.product_id.display_name))
        return '\n'.join(out)

    # ------------------------------------------------------------------
    # 1. Not in stock: sign first
    # ------------------------------------------------------------------
    def _sa_send_group_sign_link(self, order):
        self.ensure_one()
        order = order.sudo()
        vals = {}
        if 'require_signature' in order._fields and not order.require_signature:
            vals['require_signature'] = True
        if 'require_payment' in order._fields and order.require_payment:
            vals['require_payment'] = False
        if vals:
            order.write(vals)
        link = self._sa_portal_link(order)
        self._say(_("The goods are being arranged for you.\n\n"
                    "✍️ Please sign your order here to confirm it:\n%(link)s\n\n"
                    "Once signed, delivery is quick the moment the goods are in - "
                    "we will post the payment link here then.", link=link))
        self.write({'sa_sign_link_sent_on': fields.Datetime.now()})
        return True

    # ------------------------------------------------------------------
    # 2. Goods at the branch: the shop accepted -> pay
    # ------------------------------------------------------------------
    def _sa_accept_pay_link(self, job):
        """The pay link for a signed order whose goods are now at the shop."""
        self.ensure_one()
        order = job.sale_id.sudo()
        if not order or self._sa_order_is_paid(order):
            return False
        body = _("✅ Good news - your order *#%(ref)s* is at %(shop)s and ready to pack.\n\n"
                 "%(order)s\n%(lines)s\n*Total: %(cur)s %(total).2f*\n\n%(pay)s\n\n"
                 "Pay once and it goes out quickly. \U0001F69A",
                 ref=self.ref_code or order.name, shop=job.sa_shop_id.name or _("our shop"),
                 order=order.name, lines=self._sa_order_lines_text(order),
                 cur=order.currency_id.symbol or '', total=order.amount_total,
                 pay=self._sa_pay_link_any_state(order))
        if self.with_context(sa_private_window=60)._say(body) is False:
            _logger.warning("Sales Automation: pay link of %s was not sent", order.name)
            job.sudo().write({'sa_last_error': _("The payment link was not sent. Press Send payment link.")})
            return False
        self.write({'sa_pay_link_sent_on': fields.Datetime.now(), 'sa_stock_confirmed': True,
                    'sa_pay_remind_count': 0, 'sa_pay_reminded_on': False})
        return True

    def _sa_job_waits_for_payment(self, job):
        """True when packing must wait: a group order, a pay link out, no money."""
        order = job.sale_id
        if not order:
            return False
        return bool(self.sa_pay_link_sent_on) and not self._sa_order_is_paid(order)

    # ------------------------------------------------------------------
    # 4. Returning customer
    # ------------------------------------------------------------------
    @api.model
    def _sa_pay_url(self, order):
        """Just the URL of the pay link, whatever the state of the order."""
        text = self._sa_pay_link_any_state(order)
        m = re.search(r'https?://\S+', text or '')
        return m.group(0) if m else text

    # Every poll the returning customer sees is one level of this menu.
    # The options of the poll last shown are kept in `sa_menu_json` on the
    # enquiry that asked; each entry says what it does and which level it
    # was shown on, so BACK always knows where to go.
    MENU_BACK = '\u2B05\uFE0F BACK'
    MENU_MAIN = '\U0001F3E0 MAIN MENU'
    MENU_DONE = "\U0001F64F THAT'S ALL, THANK YOU"
    MENU_PARENT = {'orders': 'main', 'pending': 'orders', 'delivery': 'orders', 'more': 'main'}

    def _sa_menu_items(self):
        """This customer's orders, as (kind, enquiry) pairs: 'track' (paid, on
        its way), 'sign' (waiting for the signature), 'pay' (waiting for the
        money). Newest first."""
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
            return []
        items = []
        for r in self.sudo().search(dom, order='id desc', limit=20):
            o = r.order_id.sudo()
            if o.state == 'cancel':
                continue
            job = o.picking_ids.filtered(lambda p: p.state != 'cancel' and
                                         getattr(p, 'sa_delivery_state', 'none') in IN_FLIGHT).sorted('id')[:1]
            paid = r._sa_order_is_paid(o)
            if paid and job:
                items.append(('track', r))
            elif o.state in ('draft', 'sent') and o._has_to_be_signed() and r.sa_sign_link_sent_on:
                items.append(('sign', r))
            elif r.sa_details_pending and o.state in ('draft', 'sent'):
                continue          # name / address first, then sign, then pay
            elif not paid and (r.sa_pay_link_sent_on or o.state in ('draft', 'sent')):
                items.append(('pay', r))
        return items

    @api.model
    def _sa_returning_menu(self, message, group):
        """A hello from somebody we have orders for: the main menu."""
        digits = ''.join(c for c in (message.participant_phone or '') if c.isdigit())
        tail = digits[-9:] if len(digits) >= 9 else ''
        lid = message.participant_lid or ''
        dom = [('group_id', '=', group.id), ('order_id', '!=', False)]
        if tail and lid:
            dom += ['|', ('requester_phone', 'like', tail), ('requester_lid', '=', lid)]
        elif tail:
            dom += [('requester_phone', 'like', tail)]
        elif lid:
            dom += [('requester_lid', '=', lid)]
        else:
            return False
        latest = self.sudo().search(dom, order='id desc', limit=1)
        if not latest:
            # A first hello: nobody has an order yet, but the menu is still
            # the right answer (NEW ORDER, MORE). The row that carries the
            # poll is a closed enquiry, so nothing else reads it as a request.
            latest = self.sudo().create({
                'group_id': group.id,
                'message_id': message.id,
                'requester_phone': message.participant_phone or '',
                'requester_lid': message.participant_lid or '',
                'requester_name': message.push_name or '',
                'requester_is_lid': message.participant_is_lid,
                'raw_text': (message.message or '').strip(),
                'currency_id': self._company_for(group).currency_id.id,
                'state': 'dropped', 'drop_reason': 'not_product', 'ai_source': 'prefilter',
            })
            try:
                latest._sa_tag_message(message)
            except Exception:  # noqa: BLE001 - tagging is cosmetic
                pass
        return latest._sa_menu_show('main')

    def _sa_menu_show(self, level):
        """Post one level of the menu as a poll."""
        self.ensure_one()
        items = self._sa_menu_items()
        pending = [(k, r) for k, r in items if k in ('pay', 'sign')]
        delivery = [(k, r) for k, r in items if k == 'track']
        opts = []
        if level == 'main':
            body = (_("Hi \U0001F44B welcome back! What would you like to do? Tap one:") if (items or self.order_id)
                    else _("Hi \U0001F44B welcome! What would you like to do? Tap one:"))
            if items:
                opts.append((_("\U0001F4E6 MY ORDERS"), {'kind': 'menu', 'level': 'orders'}))
            opts.append((_("\U0001F195 NEW ORDER"), {'kind': 'new'}))
            opts.append((_("\u2795 MORE"), {'kind': 'menu', 'level': 'more'}))
        elif level == 'orders':
            body = _("\U0001F4E6 *Your orders* - tap one:")
            opts.append((_("\u23F3 PENDING ORDERS (%d)") % len(pending), {'kind': 'menu', 'level': 'pending'}))
            opts.append((_("\U0001F69A DELIVERY ORDERS (%d)") % len(delivery), {'kind': 'menu', 'level': 'delivery'}))
        elif level == 'pending':
            body = (_("\u23F3 *Orders waiting for payment or signature* - tap one:") if pending
                    else _("\u23F3 You have no pending orders. \U0001F44D"))
            for kind, r in pending[:4]:
                o = r.order_id.sudo()
                ref = r.ref_code or o.name
                if kind == 'sign':
                    opts.append((_("\u270D\uFE0F SIGN #%s") % ref, {'kind': 'sign', 'target': r.id}))
                else:
                    opts.append((_("\U0001F4B3 PAY #%(ref)s (%(cur)s %(total).2f)",
                                   ref=ref, cur=o.currency_id.symbol or '', total=o.amount_total),
                                 {'kind': 'pay', 'target': r.id}))
            for kind, r in pending[:3]:
                opts.append((_("\u274C CANCEL #%s") % (r.ref_code or r.order_id.name), {'kind': 'cancel', 'target': r.id}))
        elif level == 'delivery':
            body = (_("\U0001F69A *Orders on their way* - tap one to track:") if delivery
                    else _("\U0001F69A No order is out for delivery right now."))
            for kind, r in delivery[:5]:
                opts.append((_("\U0001F4E6 TRACK #%s") % (r.ref_code or r.order_id.name), {'kind': 'track', 'target': r.id}))
        elif level == 'more':
            body = _("More options - tap one:")
            for label, extra in self._sa_more_extra_options():
                opts.append((label, extra))
            opts.append((_("\U0001F464 MY DETAILS"), {'kind': 'details'}))
            opts.append((_("\U0001F4CD CHANGE ADDRESS"), {'kind': 'address'}))
        else:
            return self._sa_menu_show('main')
        if level != 'main':
            opts.append((self.MENU_BACK, {'kind': 'menu', 'level': self.MENU_PARENT.get(level, 'main')}))
            opts.append((self.MENU_MAIN, {'kind': 'menu', 'level': 'main'}))
        menu = {}
        for label, item in opts:
            item = dict(item); item.setdefault('req', self.id); item['parent'] = level
            menu[label] = item
        self.sa_menu_json = json.dumps(menu)
        self._ask(body, [{'id': 'sa_menu_%d' % i, 'title': label} for i, label in enumerate(menu)])
        return True

    def _sa_say_link_or_nav(self, body, level):
        """A SIGN / PAY / TRACK answer. With a link in it the link is the next
        step: nothing to tap follows (owner, 22 Nov 2026: link only, no extra
        poll). Without one ("it has not left the shop yet") BACK / MAIN MENU
        stays, or the customer would be left with nothing to tap."""
        self.ensure_one()
        if not re.search(r'https?://', body or ''):
            self._say(body)
            return self._sa_nav(level)
        self._say(body + _("\n\n_Say *hi* in the group for the menu._"))
        return True

    def _sa_nav(self, level):
        """After a reply: BACK to the level it came from, or the main menu."""
        self.ensure_one()
        menu = {self.MENU_BACK: {'kind': 'menu', 'level': level or 'main', 'req': self.id, 'parent': level},
                self.MENU_MAIN: {'kind': 'menu', 'level': 'main', 'req': self.id, 'parent': level},
                self.MENU_DONE: {'kind': 'done', 'req': self.id, 'parent': level}}
        self.sa_menu_json = json.dumps(menu)
        self._ask(_("What next?"), [{'id': 'sa_nav_%d' % i, 'title': label} for i, label in enumerate(menu)])
        return True

    @staticmethod
    def _sa_menu_key(label):
        return re.sub(r'[^a-z0-9#]', '', (label or '').lower())

    def _sa_menu_label(self, text):
        """The welcome-back option this text is, or None."""
        self.ensure_one()
        if not self.sa_menu_json:
            return None
        try:
            menu = json.loads(self.sa_menu_json)
        except ValueError:
            return None
        key = self._sa_menu_key(text)
        for label in menu:
            if key and key == self._sa_menu_key(label):
                return label
        return None

    # The welcome-back poll follows the same rule as every other poll: one
    # tap. The owner saw TRACK and then PAY both answered on one poll and
    # asked why - a second wish is a new "hi".

    def _sa_answer_poll(self, text):
        """A tap on the welcome-back poll sends that one link."""
        self.ensure_one()
        if self.sa_address_pending == 'confirm' and self._sa_address_answer(text):
            return True
        if self.sa_change_pending and self._sa_change_answer(text):
            return True
        if self.sa_menu_json:
            try:
                menu = json.loads(self.sa_menu_json)
            except ValueError:
                menu = {}
            key = self._sa_menu_key(text)
            for label, item in menu.items():
                if key and key == self._sa_menu_key(label):
                    return self._sa_menu_tapped(item)
        return super()._sa_answer_poll(text)

    def _sa_menu_tapped(self, item):
        self.ensure_one()
        kind = item.get('kind')
        parent = item.get('parent') or 'main'
        if kind == 'menu':
            return self._sa_menu_show(item.get('level') or 'main')
        if kind == 'done':
            # The customer is finished: a thank-you, and no further poll.
            self._say(_("\U0001F64F Thank you! Message us here anytime - just say *hi* for the menu."))
            return True
        if kind == 'new':
            # A fresh start: whatever deal this person still had open would
            # otherwise swallow their next words as its own answer (a typed
            # product name was read as a quantity of an older enquiry).
            self._sa_close_open_deals()
            self._say(_("\U0001F195 Sure! Just tell me what you need - the product and how many."))
            return True
        if kind == 'details':
            self._sa_say_my_details()
            return self._sa_nav(parent)
        if kind == 'points':
            self._sa_say_loyalty_points()
            return self._sa_nav(parent)
        if kind == 'address':
            return self._sa_ask_new_address()
        target = self.sudo().browse(item.get('target') or 0).exists()
        o = target.order_id.sudo() if target else self.env['sale.order']
        ref = (target.ref_code or o.name) if target else ''
        if not target or not o:
            self._say(_("That order is no longer available."))
            return self._sa_nav(parent)
        if kind in ('sign', 'pay') and target.sa_details_pending and target.state == 'order_created' \
                and o.state in ('draft', 'sent'):
            return target._sa_details_ask(o)      # an old poll: the details come first
        if kind == 'pay' and o.state in ('draft', 'sent') and o._has_to_be_signed() \
                and target.sa_sign_link_sent_on:
            kind = 'sign'                         # sign first, then pay
        if kind == 'track':
            job = o.picking_ids.filtered(lambda p: p.state != 'cancel' and
                                         getattr(p, 'sa_delivery_state', 'none') in IN_FLIGHT).sorted('id')[:1]
            return self._sa_say_link_or_nav(_("\U0001F4E6 *Order #%(ref)s* (%(lines)s)\n\nTrack it here \U0001F447\n%(url)s",
                        ref=ref, lines=self._sa_order_lines_text(o).replace('\n', ', '),
                        url=(job.sa_track_url or target._sa_portal_link(o))), parent)
        if kind == 'sign':
            return self._sa_say_link_or_nav(_("\u270D\uFE0F *Order #%(ref)s* - sign here to continue \U0001F447\n%(url)s",
                        ref=ref, url=target._sa_portal_link(o)), parent)
        if kind == 'pay':
            return self._sa_say_link_or_nav(_("\U0001F4B3 *Order #%(ref)s* - %(cur)s %(total).2f\n%(lines)s\n\nPay here \U0001F447\n%(url)s\n\n"
                        "Once paid, your invoice and delivery date come here automatically. \u2705",
                        ref=ref, cur=o.currency_id.symbol or '', total=o.amount_total,
                        lines=self._sa_order_lines_text(o), url=target._sa_pay_url(o)), parent)
        if kind == 'cancel':
            if o.state in ('cancel', 'done') or target._sa_order_is_paid(o):
                self._say(_("Order #%s can no longer be cancelled here - our sales agent will help you.") % ref)
            else:
                target._sa_cancel_deal()
            return self._sa_nav(parent)
        return None

    # ------------------------------------------------------------------
    # Paid: invoice, delivery date, then buttons to track it
    # ------------------------------------------------------------------
    def _sa_group_confirmed(self, order):
        told_before = bool(self.sa_paid_told_on)
        res = super()._sa_group_confirmed(order)
        # (a task that is tried again goes on here after the words went out)
        if self.sa_paid_told_on and (not told_before or self.env.context.get('sa_after_task')):
            return self._sa_after_part('menu', lambda: self._sa_paid_after(order)) or res or True
        return res

    def _sa_paid_after(self, order):
        """The points line and the buttons after the paid message."""
        self.ensure_one()
        try:
            self._sa_paid_extras(order)      # other modules: the points line
        except Exception as err:  # noqa: BLE001
            _logger.warning("Sales Automation: paid extras for %s failed: %s", order.name, err)
        try:
            self._sa_paid_menu(order)
        except Exception as err:  # noqa: BLE001
            _logger.warning("Sales Automation: paid menu for %s failed: %s", order.name, err)
        return True

    def _sa_paid_extras(self, order):
        """Hook: anything else to say once the paid invoice is out."""
        return None

    def _sa_paid_menu(self, order):
        """After the paid invoice and the delivery date: one tap to track
        this order, or back to the customer's orders / the main menu."""
        self.ensure_one()
        menu = {}
        has_job = any(getattr(p, 'sa_delivery_state', 'none') not in ('none', False, 'cancelled')
                      for p in order.sudo().picking_ids)
        if has_job:                                   # nothing to track without a job
            menu[_("\U0001F4E6 TRACK THIS ORDER")] = {'kind': 'track', 'target': self.id, 'req': self.id, 'parent': 'orders'}
        menu.update({
            _("\U0001F4E6 MY ORDERS"): {'kind': 'menu', 'level': 'orders', 'req': self.id, 'parent': 'main'},
            self.MENU_MAIN: {'kind': 'menu', 'level': 'main', 'req': self.id, 'parent': 'main'},
            self.MENU_DONE: {'kind': 'done', 'req': self.id, 'parent': 'main'},
        })
        self.sa_menu_json = json.dumps(menu)
        self._ask(_("What next?"), [{'id': 'sa_paid_%d' % i, 'title': label} for i, label in enumerate(menu)])
        return True

    # ------------------------------------------------------------------
    # CHANGE on the order summary: buttons, not free typing
    # ------------------------------------------------------------------
    CHANGE_QTY = '\U0001F522 CHANGE QUANTITY'
    CHANGE_PRICE = '\U0001F4B0 BETTER PRICE'
    CHANGE_KEEP = '\u21A9\uFE0F KEEP AS IT IS'
    CHANGE_CANCEL = '\u274C CANCEL ORDER'

    def _sa_change_menu(self):
        """What to change, as a poll. Free typing here produced prices in
        every format and words that were read as new enquiries."""
        self.ensure_one()
        settings = self._settings()
        options = [self.CHANGE_QTY]
        can_bargain = bool(settings.bargain_enabled)
        if can_bargain and hasattr(self, '_sa_qty_bargain_allowed'):
            can_bargain = self._sa_qty_bargain_allowed()
        if can_bargain and not (hasattr(self, '_sa_qty_tiered') and self._sa_qty_tiered()):
            can_bargain = self.bargain_count < (settings.bargain_max_steps or 0)
        if can_bargain:
            options.append(self.CHANGE_PRICE)
        options += [self.CHANGE_KEEP, self.CHANGE_CANCEL]
        self.write({'state': 'negotiating', 'sa_change_pending': True})
        self._ask(_("What would you like to change?"),
                  [{'id': 'sa_chg_%d' % i, 'title': o} for i, o in enumerate(options)])
        return True

    def _sa_change_answer(self, text):
        """True when `text` is one of the change-menu buttons."""
        self.ensure_one()
        key = self._sa_menu_key(text)
        keys = {self._sa_menu_key(self.CHANGE_QTY): 'qty', self._sa_menu_key(self.CHANGE_PRICE): 'price',
                self._sa_menu_key(self.CHANGE_KEEP): 'keep', self._sa_menu_key(self.CHANGE_CANCEL): 'cancel'}
        choice = keys.get(key)
        if not choice:
            return False
        self.sa_change_pending = False
        if choice == 'qty':
            self.qty = 0
            self._sa_ask_qty_poll(_("\U0001F522 No problem - how many do you need instead? "
                                    "Tap one \U0001F447"))
            self.state = 'awaiting_qty'
            return True
        if choice == 'price':
            return self._ask_their_price()
        if choice == 'keep':
            return self._ask_order_confirm()
        return self._sa_cancel_deal()

    # ------------------------------------------------------------------
    # Change of address: type it, confirm it, saved on the customer
    # ------------------------------------------------------------------
    def _sa_address_partner(self):
        self.ensure_one()
        if self.order_id and self.order_id.partner_id:
            return self.order_id.partner_id.sudo()
        if not (self.requester_phone or '').strip():
            return self.env['res.partner']
        # the one shared lookup (whatsapp_employee_tracker)
        return self.env['res.partner'].sudo()._sa_phone_owner(self.requester_phone)

    def _sa_ask_new_address(self):
        self.ensure_one()
        partner = self._sa_address_partner()
        current = ''
        if partner:
            parts = [partner.street, partner.street2, partner.city, partner.zip]
            current = ', '.join(x for x in parts if x)
        self.write({'sa_address_pending': 'typing', 'sa_address_draft': False})
        body = _("\U0001F4CD *Change of address*\n\nCurrent: %(cur)s\n\nPlease type your *full delivery "
                 "address* in one message - house / building, street, area, city and postcode.",
                 cur=current or _("not on file yet"))
        self._say(body)
        return True

    @api.model
    def _sa_address_waiting(self, group, message):
        """The enquiry of this sender that is waiting for a typed address."""
        digits = ''.join(c for c in (message.participant_phone or '') if c.isdigit())
        tail = digits[-9:] if len(digits) >= 9 else ''
        lid = message.participant_lid or ''
        dom = [('group_id', '=', group.id), ('sa_address_pending', '=', 'typing')]
        if tail and lid:
            dom += ['|', ('requester_phone', 'like', tail), ('requester_lid', '=', lid)]
        elif tail:
            dom += [('requester_phone', 'like', tail)]
        elif lid:
            dom += [('requester_lid', '=', lid)]
        else:
            return self.browse()
        return self.sudo().search(dom, order='write_date desc, id desc', limit=1)

    def _sa_take_address(self, text):
        """The typed address: checked the way the order flow checks one, then
        read back for a yes / no."""
        self.ensure_one()
        text = (text or '').strip()
        partner = self._sa_address_partner()
        if not self._sa_looks_like_address(text):
            self._say(_("That does not look like a full address yet. Please send the house / building, "
                        "street, area, city and postcode in one message."))
            return True
        if partner and self._sa_pincode_wanted(partner) and not self._sa_find_pincode(text, partner):
            self._say(_("Please include the postcode too. %(hint)s", hint=self._sa_pincode_hint(partner)))
            return True
        self.write({'sa_address_pending': 'confirm', 'sa_address_draft': text[:500]})
        self._ask(_("\U0001F4CD Is this your correct delivery address?\n\n%(addr)s", addr=text[:500]),
                  [{'id': 'sa_addr_yes', 'title': _("\u2705 YES, SAVE IT")},
                   {'id': 'sa_addr_no', 'title': _("\u270F\uFE0F NO, TYPE AGAIN")}])
        return True

    def _sa_address_answer(self, text):
        """True when `text` answered the address confirmation."""
        self.ensure_one()
        if self.sa_address_pending != 'confirm':
            return False
        key = self._sa_menu_key(text)
        yes = key in ('yessaveit', 'yes', 'y', 'save', 'correct', 'ok')
        no = key in ('notypeagain', 'no', 'n', 'again', 'retype', 'change')
        if not yes and not no:
            return False
        if no:
            self.write({'sa_address_pending': 'typing', 'sa_address_draft': False})
            self._say(_("No problem - please type the full address again."))
            return True
        partner = self._sa_address_partner()
        draft = self.sa_address_draft or ''
        if not partner:
            self.write({'sa_address_pending': False})
            self._say(_("Sorry, we could not find your customer record - our sales agent will update it."))
            return True
        vals = {'street': draft[:250]}
        pin = self._sa_find_pincode(draft, partner) if self._sa_pincode_wanted(partner) else None
        if pin:
            vals['zip'] = pin
        partner.write(vals)
        # Open orders point at this same customer record, so they take the new address with it.
        self.write({'sa_address_pending': False, 'sa_address_draft': False})
        self._say(_("\u2705 Address saved:\n%(addr)s\n\nYour next deliveries go there.", addr=draft))
        return self._sa_nav('more')

    @api.model
    def _on_group_message(self, message):
        """A typed address for a pending change is taken before anything
        else reads it as an enquiry."""
        group = self.env['sa.sales.group'].sudo().search([
            ('session_id', '=', message.session_id.id), ('group_jid', '=', message.group_jid),
            ('enabled', '=', True)], limit=1)
        text = (message.message or '').strip()
        if group and text and not self.env.context.get('sa_poll_ref') and group.group_type != 'vendor':
            waiting = self._sa_address_waiting(group, message)
            if waiting and not self._sa_is_greeting(text):
                return waiting.with_context(sa_trigger_msg=message.wa_message_id or ('row%s' % message.id))._sa_take_address(text)
        return super()._on_group_message(message)

    def _sa_close_open_deals(self):
        """Drop this person's open pre-order enquiries in this group."""
        self.ensure_one()
        digits = ''.join(c for c in (self.requester_phone or '') if c.isdigit())
        tail = digits[-9:] if len(digits) >= 9 else ''
        dom = [('group_id', '=', self.group_id.id),
               ('state', 'in', ('sourcing', 'awaiting_vendor_pick', 'quoted', 'negotiating',
                                'awaiting_qty', 'awaiting_order_confirm', 'awaiting_confirm', 'finding'))]
        if tail and self.requester_lid:
            dom += ['|', ('requester_phone', 'like', tail), ('requester_lid', '=', self.requester_lid)]
        elif tail:
            dom += [('requester_phone', 'like', tail)]
        elif self.requester_lid:
            dom += [('requester_lid', '=', self.requester_lid)]
        else:
            return 0
        stale = self.sudo().search(dom)
        for r in stale:
            try:
                r._sa_clear_tracker_seed()
            except Exception as err:  # noqa: BLE001
                _logger.info("Sales Automation: seed clear on %s failed: %s", r.id, err)
            r.write({'state': 'dropped', 'drop_reason': 'stale'})
        if stale:
            _logger.info("Sales Automation: NEW ORDER closed %d open enquiries of %s", len(stale), self.requester_phone)
        return len(stale)

    # ------------------------------------------------------------------
    # MORE: replies
    # ------------------------------------------------------------------
    def _sa_more_extra_options(self):
        """Extra entries for the MORE level, (label, item) pairs. Other
        modules add theirs here (the loyalty card adds its points)."""
        self.ensure_one()
        return []

    def _sa_say_my_details(self):
        self.ensure_one()
        partner = self.order_id.partner_id if self.order_id else self.env['res.partner']
        digits = self.requester_phone or ''
        orders = self.sudo().search([('group_id', '=', self.group_id.id), ('order_id', '!=', False),
                                     ('requester_phone', 'like', digits[-9:] if len(digits) >= 9 else digits)])
        open_orders = orders.filtered(lambda r: r.order_id.state not in ('cancel',) and not r._sa_order_is_paid(r.order_id))
        paid_orders = orders.filtered(lambda r: r.order_id.state != 'cancel' and r._sa_order_is_paid(r.order_id))
        address = ''
        if partner:
            parts = [partner.street, partner.street2, partner.city, partner.zip,
                     partner.state_id.name if partner.state_id else '', partner.country_id.name if partner.country_id else '']
            address = ', '.join(p for p in parts if p)
        self._say(_("\U0001F464 *Your details*\n\nName: %(name)s\nPhone: %(phone)s\nAddress: %(addr)s\n\n"
                    "Paid orders: %(paid)d\nOrders waiting for payment: %(open)d\n\n"
                    "To change anything, just tell us here.",
                    name=(partner.name if partner else self.requester_name) or '-',
                    phone=('+' + digits) if digits else '-', addr=address or _("not on file yet"),
                    paid=len(paid_orders), open=len(open_orders)))
        return True

    def _sa_say_loyalty_points(self):
        """Replaced by the loyalty module when it is installed."""
        self.ensure_one()
        self._say(_("Loyalty points are not available on this shop yet."))
        return True

    # ------------------------------------------------------------------
    # Reminders: sign or pay, and the last one hands over to a person
    # ------------------------------------------------------------------
    def _sa_customer_domain(self):
        """This customer's enquiries, as a domain - or None when WhatsApp hides
        who they are."""
        self.ensure_one()
        digits = ''.join(c for c in (self.requester_phone or '') if c.isdigit())
        tail = digits[-9:] if len(digits) >= 9 else ''
        lid = self.requester_lid or ''
        dom = [('group_id', '=', self.group_id.id)]
        if tail and lid:
            return dom + ['|', ('requester_phone', 'like', tail), ('requester_lid', '=', lid)]
        if tail:
            return dom + [('requester_phone', 'like', tail)]
        if lid:
            return dom + [('requester_lid', '=', lid)]
        return None

    def _sa_customer_quiet(self, minutes):
        """True when this customer has been silent that long: no message and no
        tap in the group, nothing in their private chat, no product accepted
        on its page. A reminder in the middle of another conversation reads
        like that conversation's next step (Ref T's sign link right after Ref
        U's ACCEPT link, 23 Nov 2026)."""
        self.ensure_one()
        since = fields.Datetime.now() - timedelta(minutes=minutes)
        digits = ''.join(c for c in (self.requester_phone or '') if c.isdigit())
        tail = digits[-9:] if len(digits) >= 9 else ''
        lid = self.requester_lid or ''
        Message = self.env['whatsapp.message'].sudo()
        dom = [('direction', '=', 'incoming'), ('create_date', '>=', since)]
        for who in ((('participant_phone', 'like', tail) if tail else None),
                    (('participant_lid', '=', lid) if lid else None)):
            if who and Message.search_count(
                    dom + [('group_jid', '=', self.group_id.group_jid), who], limit=1):
                return False
        if tail and Message.search_count(
                dom + [('group_jid', '=', False), ('phone', 'like', tail)], limit=1):
            return False
        mine = self._sa_customer_domain()
        if mine and 'sa_confirm_accepted_on' in self._fields and self.sudo().search_count(
                mine + [('sa_confirm_accepted_on', '>=', since)], limit=1):
            return False
        return True

    def _sa_remind_body(self, order, n, cap):
        """The reminder for the step this order is really at, or ''. The
        signature comes before the money, whatever links went out."""
        self.ensure_one()
        tail = _("\n\nIf you need any help, our sales agent will assist you shortly. "
                 "Thank you. \U0001F64F") if n >= cap else ''
        if order.state in ('draft', 'sent') and order._has_to_be_signed():
            if not self.sa_sign_link_sent_on:
                return ''
            return _("⏰ Reminder %(n)s of %(cap)s: your order *#%(ref)s* is waiting for your signature.\n\n"
                     "✍️ Sign here:\n%(link)s%(tail)s",
                     n=n, cap=cap, ref=self.ref_code or order.name, link=self._sa_portal_link(order), tail=tail)
        if self.sa_pay_link_sent_on and not self._sa_order_is_paid(order):
            return _("⏰ Reminder %(n)s of %(cap)s: your order *#%(ref)s* (%(cur)s %(total).2f) "
                     "is still waiting for payment.\n\n%(pay)s\n\nPay once and delivery goes out quickly. \U0001F69A%(tail)s",
                     n=n, cap=cap, ref=self.ref_code or order.name, cur=order.currency_id.symbol or '',
                     total=order.amount_total, pay=self._sa_pay_link_any_state(order), tail=tail)
        return ''

    @api.model
    def _cron_pay_remind(self):
        """Sign / pay reminders (owner, 23 Nov 2026): only after a long silence,
        one at a time per customer, and never put in the outbox - two queued
        reminders came out together 18 hours later, in another order's flow."""
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        minutes = int(settings.pay_remind_minutes or 0)
        cap = int(settings.pay_remind_max or 0)
        if minutes <= 0 or cap <= 0:
            return True
        now = fields.Datetime.now()
        due = now - timedelta(minutes=minutes)
        rows = self.sudo().search([
            ('order_id', '!=', False), ('order_id.state', '!=', 'cancel'),
            ('sa_details_pending', '=', False),
            ('sa_paid_told_on', '=', False), ('sa_pay_remind_count', '<', cap),
            '|', ('sa_pay_link_sent_on', '<=', due), ('sa_sign_link_sent_on', '<=', due),
            '|', ('sa_pay_reminded_on', '=', False), ('sa_pay_reminded_on', '<=', due)], order='id')
        online = {}
        for req in rows:
            order = req.order_id.sudo()
            session = req.group_id.session_id
            if not session or not req.group_id.group_jid:
                continue
            try:
                # alone: no other order of this customer was reminded just now
                mine = req._sa_customer_domain()
                if mine and self.sudo().search_count(
                        mine + [('id', '!=', req.id), ('sa_pay_reminded_on', '>', due)], limit=1):
                    continue
                if not req._sa_customer_quiet(minutes):
                    continue
                if session.id not in online:
                    session._refresh_state()
                    online[session.id] = session.status == 'connected'
                if not online[session.id]:
                    continue
                n = req.sa_pay_remind_count + 1
                body = req._sa_remind_body(order, n, cap)
                if not body:
                    continue
                with self.env.cr.savepoint():
                    req._sa_remind_send(body)
                    req.write({'sa_pay_reminded_on': now, 'sa_pay_remind_count': n})
            except Exception as err:  # noqa: BLE001 - next run
                _logger.warning("Reminder for %s failed: %s", order.name, err)
        return True

    def _sa_remind_send(self, body):
        """Send now or not at all: what could not go out is not left waiting
        in the outbox (raises, the caller's savepoint drops the row)."""
        self.ensure_one()
        Message = self.env['whatsapp.message'].sudo()
        last = Message.search([], order='id desc', limit=1).id or 0
        if not self._say(body):
            raise UserError(_("WhatsApp did not take the reminder."))
        # the private copy failed and the group got it: no second copy later
        Message.search([('id', '>', last), ('direction', '=', 'outgoing'), ('status', '=', 'pending'),
                        ('session_id', '=', self.group_id.session_id.id),
                        ('message', 'like', body[:40])]).write({'status': 'failed'})
        return True


class PaymentTransactionInvoiceGroup(models.Model):
    _inherit = 'payment.transaction'

    def _post_process(self):
        """A payment made against the invoice (the pay link of a confirmed
        order) also tells the group."""
        res = super()._post_process()
        for tx in self.filtered(lambda t: t.state == 'done'):
            orders = tx.sale_order_ids
            if not orders and tx.invoice_ids:
                orders = tx.invoice_ids.mapped('invoice_line_ids.sale_line_ids.order_id')
            for so in orders:
                req = so._sa_group_enquiry()
                if req and req.group_id and not req.sa_paid_told_on and so.state == 'sale':
                    try:
                        req.sudo()._sa_group_paid(so)
                    except Exception as err:  # noqa: BLE001
                        _logger.error("Group paid message failed for %s: %s", so.name, err)
        return res
