"""The senior's sockets, plugged in: our wallet, points, deals, reviews and
website orders inside his WhatsApp flow.

His "Bridge hooks for 369 Mart" page (sales_automation 173.8.0, delivery
29.0.0) put a method with a do-nothing default at each place where the
WhatsApp flow needs something only this shop knows. They are answered here
and nowhere else; his flow around them is never overridden.

  sale.order._sa_wallet_apply()      the 369 Wallet pays first on the pay link
  sale.order._sa_paid_elsewhere()    ...so the rider collects only the rest
  sale.order._sa_points_offer()      "You have 120 points worth 12.00"
  sale.order._sa_points_apply()      USE POINTS: a discount line on the order
  sale.order._sa_review_link()       after Delivered: rate it on our order page
  sa.group.request._sa_live_deal_price()   bargaining never goes below a deal
  sa.group.request slots             MY ORDERS / TRACK / DOOR CODE / INVOICE /
                                     CANCEL / RETURN / HELP / TALK TO A PERSON /
                                     WALLET & POINTS know the website's orders

Every answer starts by asking whether the order or the customer is ours; for
anything else the stack's own default answers (`super()`), so his WhatsApp
orders behave exactly as he wrote them. A local copy of his modules older than
those hooks has no parent method, hence `getattr(super(), name, None)`. And a
hook never raises: the pay link, the bargain and the menu must not break over
a wallet.
"""

import logging
import math
import re
from datetime import timedelta

from odoo import _, api, fields, models

from odoo.addons.mart369_support.models.bot import STATUS_WORDS, LIVE_STATES
from odoo.addons.mart369_support.models.whatsapp import DEFAULT_LINK, LINK_PARAM

_logger = logging.getLogger(__name__)

RETURN_DAYS = 7
WEB_KEY = re.compile(r'web:(\d+)')
# A typed line that is asking something, not naming a product to order.
QUESTION = re.compile(
    r"\?|^(what|when|where|why|how|who|which|can|could|do|does|is|are|will|"
    r"refund|return|replace|cancel|payment|paid|wallet|coupon|delivery charge)\b", re.I)


def _floor2(value):
    return math.floor((value or 0.0) * 100 + 1e-6) / 100


class SaleOrderSaHooks(models.Model):
    _inherit = 'sale.order'

    def _mart369_stack(self, name):
        """The senior's method above ours, or None on an older copy of his stack."""
        return getattr(super(SaleOrderSaHooks, self), name, None)

    # ------------------------------------------------------------- what is ours

    def _mart369_wa_ours(self):
        """A WhatsApp order this shop pays and rewards: the wallet and the
        points are the website account's, and the customer is the same one."""
        self.ensure_one()
        return self.mart369_channel == 'whatsapp' and not self.mart369_ref \
            and self.state != 'cancel'

    def _mart369_wa_due(self):
        """What is still to pay on a WhatsApp order, wallet included."""
        self.ensure_one()
        order = self.sudo()
        return order.currency_id.round(
            order.amount_total - order._mart369_wa_paid())

    @api.model
    def _mart369_public_link(self, ref):
        """The order's page on the storefront: track, rate, return."""
        link = (self.env['ir.config_parameter'].sudo().get_param(LINK_PARAM)
                or DEFAULT_LINK)
        return link % ref if '%s' in link else link

    def _mart369_wallet_card(self):
        """The customer's 369 Wallet, without making one."""
        self.ensure_one()
        Card = self.env['loyalty.card'].sudo() if 'loyalty.card' in self.env else None
        if Card is None or not hasattr(Card, '_mart369_program'):
            return None
        try:
            program = Card._mart369_program()
        except Exception:  # noqa: BLE001 - no wallet programme, no wallet
            return None
        return Card.search([('program_id', '=', program.id),
                            ('partner_id', '=', self.partner_id.commercial_partner_id.id)],
                           limit=1) or None

    # --------------------------------------------------------- wallet pays first

    def _sa_wallet_apply(self):
        """Take what the 369 Wallet holds, up to what is due, once."""
        self.ensure_one()
        if not self._mart369_wa_ours():
            stack = self._mart369_stack('_sa_wallet_apply')
            return stack() if stack else 0.0
        order = self.sudo()
        if order.mart369_wallet_used:
            return 0.0          # taken already: his flow may ask on every reminder
        try:
            due = order._mart369_wa_due()
            card = order._mart369_wallet_card()
            if due <= 0 or not card:
                return 0.0
            take = order.currency_id.round(min(card._mart369_balance(), due))
            if take <= 0:
                return 0.0
            with self.env.cr.savepoint():
                card._mart369_move(take, 'spend', _('Order'),
                                   sub=_('Order %s', order.name), order=order)
                order.mart369_wallet_used = take
            return take
        except Exception:  # noqa: BLE001 - never block a payment
            _logger.exception('bridge: wallet for %s failed', order.name)
            return 0.0

    def _sa_paid_elsewhere(self):
        """The wallet's part, which no Odoo payment shows: off the rider's cash."""
        self.ensure_one()
        if self.mart369_channel == 'whatsapp' and not self.mart369_ref:
            return self.sudo().mart369_wallet_used or 0.0
        stack = self._mart369_stack('_sa_paid_elsewhere')
        return stack() if stack else 0.0

    # ------------------------------------------------------------------ points

    def _mart369_wa_points(self):
        """(card, points, value) this WhatsApp order could take off, or None.

        The checkout's rules (mart369_loyalty cart.py `_mart369_points_block`):
        redeeming switched on, an active card, once a day, the minimum, and
        never more than the rule's share of what is still due.
        """
        self.ensure_one()
        order = self.sudo()
        # mart369_loyalty is not a dependency: points only where it is installed.
        if 'mart369_points_spent' not in order._fields or not order._mart369_wa_ours() \
                or order.mart369_points_spent:
            return None
        if order.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted'):
            return None         # a discount line would not reach the bill
        Card = self.env['pos.loyalty.card'].sudo()
        if not hasattr(Card, '_mart369_enabled') or not Card._mart369_enabled():
            return None
        if not self.env['mart369.config'].sudo()._get().loyalty_redeem:
            return None
        rule = Card._mart369_rule()
        card = Card._mart369_card_for(order.partner_id)
        if not rule or not card or card.state != 'active' or card._mart369_redeemed_today():
            return None
        due = order._mart369_wa_due()
        if due <= 0:
            return None
        per_rupee = rule._mart369_per_rupee()
        minimum = rule.min_redeem_points or 0.0
        max_percent = rule.max_redeem_percent or 100.0
        total = order.amount_total
        cap_value = _floor2(min(due, total * max_percent / 100.0))
        usable = _floor2(min(card.total_points, cap_value * per_rupee))
        if usable <= 0 or usable < minimum:
            return None
        return card, usable, min(rule._mart369_value(usable), due)

    def _sa_points_offer(self):
        self.ensure_one()
        if not self._mart369_wa_ours():
            stack = self._mart369_stack('_sa_points_offer')
            return stack() if stack else None
        try:
            found = self._mart369_wa_points()
        except Exception:  # noqa: BLE001
            _logger.exception('bridge: points offer for %s failed', self.name)
            return None
        if not found:
            return None
        __, points, value = found
        return {'points': int(points) if float(points).is_integer() else points,
                'value': value}

    def _sa_points_apply(self):
        """USE POINTS: the points come off as a discount line, once."""
        self.ensure_one()
        if not self._mart369_wa_ours():
            stack = self._mart369_stack('_sa_points_apply')
            return stack() if stack else 0.0
        order = self.sudo()
        try:
            with self.env.cr.savepoint():
                found = order._mart369_wa_points()
                if not found:
                    return 0.0
                card, points, value = found
                card._mart369_lock()
                if card.total_points + 1e-6 < points:
                    return 0.0
                try:
                    tax = order._mart369_tax()
                except Exception:  # noqa: BLE001 - an untaxed line is still a discount
                    tax = self.env['account.tax']
                self.env['sale.order.line'].sudo().create(order._mart369_charge_line(
                    _('Loyalty points (%s)', '%g' % points), -value, 'points', tax))
                order.write({'mart369_points_spent': points, 'mart369_points_off': value,
                             'mart369_loyalty_card_id': card.id})
                card._mart369_write(points, 'redeemed', _('Points used'),
                                    sub=_('Order #%s', order.name), order=order, amount=value)
            return value
        except Exception:  # noqa: BLE001 - the pay link goes out either way
            _logger.exception('bridge: points for %s failed', order.name)
            return 0.0

    # ------------------------------------------------------------------ review

    def _mart369_delivered(self):
        self.ensure_one()
        if self.mart369_state == 'delivered':
            return True
        job = self.sudo()._mart369_bridge_job()
        return bool(job and job.sa_delivery_state == 'delivered')

    def _sa_review_link(self):
        """Our order page, which has the stars and the per-item rating; a
        WhatsApp-only customer signs in there with their number."""
        self.ensure_one()
        if self.mart369_ref or self.mart369_channel == 'whatsapp':
            if self._mart369_delivered():
                return self._mart369_public_link(self.mart369_ref or self.name)
            return ''
        stack = self._mart369_stack('_sa_review_link')
        return stack() if stack else ''


class SaGroupRequestSaHooks(models.Model):
    _inherit = 'sa.group.request'

    def _mart369_stack(self, name):
        """The senior's method above ours, or None on an older copy of his stack."""
        return getattr(super(SaGroupRequestSaHooks, self), name, None)

    # ------------------------------------------------------------ deal floor

    def _sa_live_deal_price(self):
        """The cheapest live website deal on this product, when it is below
        the list price - the WhatsApp bargain never closes under it."""
        stack = self._mart369_stack('_sa_live_deal_price')
        theirs = stack() if stack else None
        product = getattr(self, 'product_id', False)
        if not product or 'mart369.deal' not in self.env:
            return theirs
        try:
            # His enquiry names a template; a variant is read the same way.
            product = product.sudo()
            if product._name == 'product.product':
                template, base = product.product_tmpl_id, product.lst_price
            else:
                template, base = product, product.list_price
            prices = [deal._mart369_apply(base)
                      for deal in self.env['mart369.deal']._mart369_live_deals()
                      if template in deal.product_ids]
            ours = min(prices) if prices else None
            if ours is None or ours >= base:
                return theirs
            return max(ours, theirs) if theirs else ours
        except Exception:  # noqa: BLE001 - a deal never breaks a quote
            _logger.exception('bridge: deal price for %s failed', product.display_name)
            return theirs

    # ------------------------------------------------------------ whose orders

    def _mart369_ss_partner(self):
        """The customer behind this chat, as the senior's menu sees them."""
        self.ensure_one()
        partner = None
        if hasattr(self, '_sa_ss_customer'):
            try:
                partner = self._sa_ss_customer()
            except Exception:  # noqa: BLE001
                partner = None
        if not partner:
            partner = self._sa_address_partner()
        return partner.commercial_partner_id.sudo() if partner else self.env['res.partner']

    def _mart369_ss_orders(self):
        """This customer's website orders, newest first."""
        partner = self._mart369_ss_partner()
        if not partner:
            return self.env['sale.order']
        return self.env['sale.order'].sudo().search([
            ('partner_id', 'child_of', partner.id),
            ('mart369_ref', '!=', False),
            ('mart369_state', 'not in', (False, 'draft', 'cancelled')),
        ], order='mart369_placed_at desc, id desc', limit=10)

    def _mart369_ss_order(self, key):
        found = WEB_KEY.fullmatch(key or '')
        if not found:
            return None
        order = self.env['sale.order'].sudo().browse(int(found.group(1))).exists()
        return order if order and order in self._mart369_ss_orders() else \
            self.env['sale.order']

    @staticmethod
    def _mart369_ss_money(order):
        return '%s %.2f' % (order.currency_id.symbol or '', order.amount_total)

    def _mart369_ss_delivered_at(self, order):
        stamp = order.mart369_stamp_ids.filtered(lambda s: s.state == 'delivered')[:1]
        return stamp.at if stamp else (order.write_date if order.mart369_state == 'delivered' else False)

    def _mart369_ss_row(self, order):
        state = order.mart369_state
        cod_due = any(tx.provider_id.mart369_is_cod and tx.state in ('draft', 'pending')
                      for tx in order._mart369_transactions())
        done_on = self._mart369_ss_delivered_at(order)
        return {
            'key': 'web:%d' % order.id,
            'ref': order.mart369_ref,
            'title': order.mart369_ref,
            'status': (STATUS_WORDS.get(state) or state or '').capitalize(),
            'total_text': self._mart369_ss_money(order),
            'paid': not cod_due,
            'in_flight': state in LIVE_STATES,
            'delivered': state == 'delivered',
            'needs_sign': False,
            'can_pay': False,
            'can_cancel': state == 'placed',
            'can_return': bool(state == 'delivered' and done_on
                               and fields.Datetime.now() - done_on <= timedelta(days=RETURN_DAYS)),
            'has_invoice': bool(order.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted')),
            'can_code': bool(state == 'out' and order.mart369_otp_code),
        }

    # ----------------------------------------------------------------- slots

    def _sa_customer_orders(self):
        """His WhatsApp orders and our website orders, newest first."""
        stack = self._mart369_stack('_sa_customer_orders')
        theirs = stack() if stack else []
        try:
            ours = [(o.mart369_placed_at or o.create_date, self._mart369_ss_row(o))
                    for o in self._mart369_ss_orders()]
        except Exception:  # noqa: BLE001 - the menu still lists his orders
            _logger.exception('bridge: website orders for the WhatsApp menu failed')
            return theirs
        if not ours:
            return theirs
        dated = []
        for row in theirs:
            req = re.fullmatch(r'req:(\d+)', row.get('key') or '')
            when = False
            if req:
                order = self.sudo().browse(int(req.group(1))).order_id
                when = order.date_order if order else False
            dated.append((when, row))
        merged = sorted(dated + ours, key=lambda pair: pair[0] or fields.Datetime.from_string('1970-01-01'),
                        reverse=True)
        return [row for __, row in merged][:20]

    def _mart369_ss_lines(self, order):
        out = []
        for line in order.order_line:
            if line.display_type or line.is_delivery or line.mart369_kind:
                continue
            out.append('• %s × %g' % (line.name.split('\n')[0], line.product_uom_qty))
        return '\n'.join(out[:8])

    def _sa_order_card(self, key):
        order = self._mart369_ss_order(key)
        if order is None:
            stack = self._mart369_stack('_sa_order_card')
            return stack(key) if stack else ''
        if not order:
            return _("That order is no longer available.")
        row = self._mart369_ss_row(order)
        lines = [_("*Order #%s* (website)") % order.mart369_ref,
                 self._mart369_ss_lines(order),
                 _("*Total: %s*") % row['total_text'],
                 _("✅ Paid") if row['paid'] else _("\U0001F4B5 To pay at the door"),
                 '\U0001F69A %s' % row['status']]
        if row['in_flight'] and order.mart369_eta:
            lines[-1] += ' · %s' % order.mart369_eta
        return '\n'.join(x for x in lines if x)

    def _sa_track_text(self, key):
        order = self._mart369_ss_order(key)
        if order is None:
            stack = self._mart369_stack('_sa_track_text')
            return stack(key) if stack else ''
        if not order:
            return _("That order is no longer available.")
        row = self._mart369_ss_row(order)
        out = [_("\U0001F69A *Order #%(ref)s*: %(status)s", ref=order.mart369_ref, status=row['status'])]
        rider = order._mart369_rider_name() if hasattr(order, '_mart369_rider_name') else \
            (order.mart369_rider_id.name or '')
        if rider and order.mart369_state in ('shipped', 'out'):
            out.append(_("%s is bringing it.") % rider)
        if row['in_flight'] and order.mart369_eta:
            out.append(order.mart369_eta)
        out.append(_("Follow it here: %s") % order._mart369_public_link(order.mart369_ref))
        return '\n'.join(out)

    def _sa_resend_door_code(self, key):
        order = self._mart369_ss_order(key)
        if order is None:
            stack = self._mart369_stack('_sa_resend_door_code')
            return stack(key) if stack else ''
        if not order or not self._mart369_ss_row(order)['can_code']:
            return _("The door code is sent when the rider is on the way to you.")
        job = order._mart369_bridge_job()
        ok = False
        if job:
            try:
                # Our job hook sends the website's code privately: the
                # customer's own number, and the address phone when different.
                ok = job.sa_issue_delivery_otp()[0]
            except Exception:  # noqa: BLE001
                _logger.exception('bridge: door code for %s failed', order.mart369_ref)
        if not ok:
            return _("Sorry, the code could not be sent just now - it is also on your "
                     "order page: %s") % order._mart369_public_link(order.mart369_ref)
        return _("\U0001F511 The door code for order *#%s* was sent to your own WhatsApp "
                 "number. Give it to the rider only after you have the parcel.") % order.mart369_ref

    def _sa_send_invoice(self, key):
        order = self._mart369_ss_order(key)
        if order is None:
            stack = self._mart369_stack('_sa_send_invoice')
            return stack(key) if stack else ''
        if not order:
            return _("That order is no longer available.")
        if not self._mart369_ss_row(order)['has_invoice']:
            return _("There is no invoice for this order yet - it comes as soon as it is made.")
        sent = self.env['mart369.whatsapp'].sudo()._mart369_send_invoice(order)
        if not sent:
            return _("Sorry, the invoice could not be sent just now. It is also on your "
                     "order page: %s") % order._mart369_public_link(order.mart369_ref)
        return _("\U0001F9FE The invoice for order #%s was sent to your own WhatsApp number.") \
            % order.mart369_ref

    def _sa_cancel_order(self, key):
        order = self._mart369_ss_order(key)
        if order is None:
            stack = self._mart369_stack('_sa_cancel_order')
            return stack(key) if stack else None
        if not order:
            return _("That order is no longer available.")
        if order.mart369_state != 'placed':
            return _("Order #%s can no longer be cancelled here - tap TALK TO A PERSON and "
                     "our team will help.") % order.mart369_ref
        try:
            order._mart369_cancel(reason=_('Cancelled on WhatsApp'))
        except Exception as err:  # noqa: BLE001 - say why, in words
            _logger.info('bridge: WhatsApp cancel of %s refused: %s', order.mart369_ref, err)
            return _("Order #%s could not be cancelled just now - tap TALK TO A PERSON.") \
                % order.mart369_ref
        refund = order.mart369_cancel_refund or 0.0
        tail = (_(" %(cur)s %(amount).2f is back in your 369 Wallet.",
                  cur=order.currency_id.symbol or '', amount=refund) if refund > 0 else '')
        return _("❌ Order #%s is cancelled.") % order.mart369_ref + tail

    def _sa_start_return(self, key):
        order = self._mart369_ss_order(key)
        if order is None:
            stack = self._mart369_stack('_sa_start_return')
            return stack(key) if stack else ''
        if not order:
            return _("That order is no longer available.")
        if not self._mart369_ss_row(order)['can_return']:
            return _("Order #%s is past the return window - tap TALK TO A PERSON and our "
                     "team will help.") % order.mart369_ref
        return _("↩️ Pick the items and add a photo here - a refund or a replacement, "
                 "your choice:\n%s") % order._mart369_public_link(order.mart369_ref)

    # ------------------------------------------------------- help and people

    def _sa_hand_to_person(self, reason=''):
        """His hand-over, and the shop's support desk hears it too."""
        stack = self._mart369_stack('_sa_hand_to_person')
        text = stack(reason) if stack else _(
            "\U0001F64B A team member will reply to you here shortly.")
        partner = self._mart369_ss_partner()
        if not partner or 'mart369.ticket' not in self.env:
            return text
        try:
            ticket = self.env['mart369.ticket'].sudo()._mart369_open(
                partner, _('WhatsApp: %s') % (reason or _('talk to a person')))
            ticket._mart369_say(_('From WhatsApp (%(phone)s): %(why)s',
                                  phone=self.requester_phone or '', why=reason or '-'))
            return text + _("\nYour ticket number is *%s*.") % ticket.name
        except Exception:  # noqa: BLE001 - the customer still gets the answer
            _logger.exception('bridge: support ticket from WhatsApp failed')
            return text

    def _sa_help_answer(self, text):
        """His patterns first; then the shop's answers - but only for a line
        that is asking something, never for a product someone is ordering."""
        stack = self._mart369_stack('_sa_help_answer')
        answer = stack(text) if stack else None
        if answer is not None:
            return answer
        typed = (text or '').strip()
        if not typed or len(typed) > 120 or not QUESTION.search(typed):
            return None
        partner = self._mart369_ss_partner()
        if not partner or 'mart369.bot' not in self.env:
            return None
        try:
            Bot = self.env['mart369.bot'].sudo()
            reply = Bot._mart369_reply(partner, typed)
            if not reply or reply.get('text') == Bot._mart369_fallback().get('text'):
                return None
            return reply.get('text') or None
        except Exception:  # noqa: BLE001
            _logger.exception('bridge: shop answer on WhatsApp failed')
            return None

    def _sa_wallet_text(self):
        """💰 WALLET & POINTS: the website's wallet and the shop's points."""
        stack = self._mart369_stack('_sa_wallet_text')
        theirs = stack() if stack else ''
        partner = self._mart369_ss_partner()
        if not partner:
            return theirs
        lines = []
        try:
            order = self.env['sale.order'].sudo().new({'partner_id': partner.id})
            card = order._mart369_wallet_card()
            if card:
                cur = card.currency_id or self.env.company.currency_id
                lines.append(_("\U0001F4B0 369 Wallet: %(cur)s %(amount).2f",
                               cur=cur.symbol or '', amount=card._mart369_balance()))
            Points = self.env['pos.loyalty.card'].sudo() if 'pos.loyalty.card' in self.env else None
            if Points is not None and hasattr(Points, '_mart369_card_for'):
                points = Points._mart369_card_for(partner)
                rule = Points._mart369_rule() if hasattr(Points, '_mart369_rule') else None
                if points and points.state == 'active':
                    value = rule._mart369_value(points.total_points) if rule else 0.0
                    lines.append(_("\U0001F48E Points: %(n)g (worth %(cur)s %(v).2f)",
                                   n=points.total_points,
                                   cur=self.env.company.currency_id.symbol or '', v=value))
        except Exception:  # noqa: BLE001
            _logger.exception('bridge: wallet text for WhatsApp failed')
            return theirs
        if not lines:
            return theirs
        return '\n'.join(([theirs] if theirs else []) + lines)
