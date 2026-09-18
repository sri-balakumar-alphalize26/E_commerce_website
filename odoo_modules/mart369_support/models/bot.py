"""The bot.

One rule: **the reply object is exactly `{text, actions?, chips?, agent?}`.**
`SupportBot.jsx:169` rebuilds the message field by field from those four, so
anything else added here is silently dropped on the floor. `agentReply` is
different again - it must return a bare string, because `SupportBot.jsx:167`
does not unwrap it.

Two things this deliberately does that the browser version could not:

* **the numbers are looked up, not retyped.** The bot used to recite "₹30
  delivery, free above ₹499, minimum ₹99" from a string in its own file, and it
  had already drifted from what the cart charges - it quoted Express delivery in
  "2-5 days" where the rule says 2-3, and implied a minimum that does not exist.
  Here those come from `mart369.delivery.rule` and `mart369.coupon`, which are
  the records the cart itself uses, so the two cannot disagree again.

* **it never says the delivery code.** The order-track bot printed it into the
  chat (`OrderTrack.jsx:418`). It was computable from the order id back then, so
  saying it out loud cost nothing; now it is issued once by the server and kept
  hashed, and a support answer is not a reason to undo that.
"""

import logging
import re

from odoo import api, models

_logger = logging.getLogger(__name__)

# The app's own wording for where an order is (STATUS_WORDS, botReplies.js:16).
STATUS_WORDS = {
    'placed': 'confirmed and being packed',
    'packed': 'packed and waiting for a rider',
    'shipped': 'shipped and on its way to your city',
    'out': 'out for delivery',
    'delivered': 'delivered',
    'cancelled': 'cancelled',
}

LIVE_STATES = ('placed', 'packed', 'shipped', 'out')

# What the panel opens with (START_CHIPS, botReplies.js:13).
START_CHIPS = [
    'Track my order', 'Refund status', 'Cancel an order',
    'Payment issue', 'Delivery charges', 'Talk to an agent',
]

BOT_NAME = 'Mitra'
AGENT_NAME = 'Anjali'

ORDER_ID = re.compile(r'369[me]-?\d{3,}', re.I)


class Mart369Bot(models.AbstractModel):
    _name = 'mart369.bot'
    _description = '369 Mart Support Bot'

    # ------------------------------------------------------------- answering

    @api.model
    def _mart369_greeting(self, partner):
        return {
            'text': 'Hello! How can I help you today?',
            'chips': list(START_CHIPS),
        }

    @api.model
    def _mart369_reply(self, partner, text):
        """The answer to one thing a customer typed."""
        typed = (text or '').strip().lower()
        if not typed:
            return self._mart369_greeting(partner)

        ctx = self._mart369_context(partner, typed)
        for rule in self.env['mart369.bot.rule']._mart369_rules():
            if not self._mart369_matches(rule, typed):
                continue
            try:
                return self._mart369_answer(rule, ctx)
            except Exception:  # noqa: BLE001
                # A broken rule must not leave the customer with a dead panel.
                _logger.exception('mart369: support rule %s failed', rule.id)
                break
        return self._mart369_fallback()

    @api.model
    def _mart369_matches(self, rule, typed):
        try:
            return bool(re.search(rule.pattern, typed, re.I))
        except re.error:
            _logger.warning('mart369: rule %s has a bad pattern: %s',
                            rule.id, rule.pattern)
            return False

    @api.model
    def _mart369_fallback(self):
        return {
            'text': "I'm not sure I got that. Pick a topic below, or I can "
                    'connect you to an agent.',
            'chips': list(START_CHIPS),
        }

    @api.model
    def _mart369_answer(self, rule, ctx):
        handler = getattr(self, '_mart369_answer_%s' % rule.kind, None)
        reply = handler(rule, ctx) if handler else {'text': rule.reply or ''}

        # chips and the button come off the record unless the handler set them.
        if 'chips' not in reply and rule._mart369_chips():
            reply['chips'] = rule._mart369_chips()
        if 'actions' not in reply:
            action = rule._mart369_action()
            if action:
                reply['actions'] = [action]
        return {key: value for key, value in reply.items() if value not in (None, [], '')}

    # -------------------------------------------------------------- context

    @api.model
    def _mart369_context(self, partner, typed):
        """This customer's orders and wallet, which is all the bot ever reads."""
        orders = self.env['sale.order'].sudo().search([
            ('partner_id', '=', partner.id),
            ('mart369_ref', '!=', False),
            ('mart369_state', 'not in', (False, 'draft')),
        ], order='mart369_placed_at desc', limit=20)

        named = self.env['sale.order'].browse()
        found = ORDER_ID.search(typed)
        if found:
            wanted = found.group(0).replace('-', '').upper()
            named = orders.filtered(
                lambda o: (o.mart369_ref or '').replace('-', '').upper() == wanted)[:1]

        card = self.env['loyalty.card'].sudo()._mart369_wallet(partner)
        return {
            'partner': partner,
            'orders': orders,
            'named': named,
            'live': orders.filtered(lambda o: o.mart369_state in LIVE_STATES),
            'delivered': orders.filtered(lambda o: o.mart369_state == 'delivered')[:1],
            'cancelled': orders.filtered(lambda o: o.mart369_state == 'cancelled'),
            'wallet': card._mart369_balance() if card else 0.0,
            'currency': self.env.company.currency_id,
        }

    @api.model
    def _mart369_money(self, ctx, amount):
        return ctx['currency'].format(amount or 0.0)

    @api.model
    def _mart369_track(self, order, label=None):
        return {'label': label or ('Track #%s' % (order.mart369_ref or '')[-4:]),
                'go': ['track', order.mart369_ref]}

    # ------------------------------------------------------------- handlers

    def _mart369_answer_order(self, rule, ctx):
        """They named an order number."""
        order = ctx['named']
        if not order:
            return {'text': rule.reply_alt or "I couldn't find that order number "
                                              'on your account.'}
        words = STATUS_WORDS.get(order.mart369_state, order.mart369_state or '')
        text = 'Order #%s is %s' % (order.mart369_ref, words)
        if order.mart369_state in LIVE_STATES and order.mart369_eta:
            text += ', %s' % order.mart369_eta
        text += '. Total %s, paid via %s.' % (
            self._mart369_money(ctx, order.amount_total),
            order.mart369_pay_note or order.mart369_method or 'your chosen method')
        label = 'Track order' if order.mart369_state in LIVE_STATES else 'Order details'
        return {'text': text, 'actions': [self._mart369_track(order, label)]}

    def _mart369_answer_track(self, rule, ctx):
        live = ctx['live']
        if not live:
            return {'text': rule.reply_alt or 'You have no orders on the way right now.',
                    'actions': [{'label': 'See all orders', 'go': ['account', 'orders']}]}
        first = live[0]
        text = 'Order #%s is %s' % (
            first.mart369_ref, STATUS_WORDS.get(first.mart369_state, ''))
        if first.mart369_eta:
            text += ', %s' % first.mart369_eta
        text += '.'
        if len(live) > 1:
            text += ' You have %s orders on the way.' % len(live)
        return {'text': text,
                'actions': [self._mart369_track(order) for order in live[:2]]}

    def _mart369_answer_refund(self, rule, ctx):
        cancelled = ctx['cancelled']
        if not cancelled:
            return {'text': rule.reply_alt or (
                'No refunds are pending on your account. Your 369 Wallet balance '
                'is %s.' % self._mart369_money(ctx, ctx['wallet']))}
        order = cancelled[0]
        return {
            'text': 'Order #%s was cancelled. Money paid from the 369 Wallet is '
                    'returned instantly; anything charged to a card or UPI reaches '
                    'the bank in 3-5 working days. Your wallet balance is %s.' % (
                        order.mart369_ref, self._mart369_money(ctx, ctx['wallet'])),
        }

    def _mart369_answer_cancel(self, rule, ctx):
        live = ctx['live']
        if not live:
            return {'text': rule.reply_alt or 'You have no orders that could be cancelled.'}
        order = live[0]
        if order.mart369_state == 'placed':
            return {'text': 'Order #%s can still be cancelled from its tracking page. '
                            'A refund goes back to your 369 Wallet instantly, or to '
                            'the original payment in 3-5 working days.' % order.mart369_ref,
                    'actions': [self._mart369_track(order, 'Cancel order')]}
        return {'text': 'Order #%s is already %s, so it can no longer be cancelled. '
                        'You can ask for a return or a replacement once it arrives.' % (
                            order.mart369_ref, STATUS_WORDS.get(order.mart369_state, '')),
                'actions': [self._mart369_track(order)]}

    def _mart369_answer_return(self, rule, ctx):
        delivered = ctx['delivered']
        days = self.env['mart369.bot']._mart369_return_days()
        text = 'Returns are open for %s days after delivery.' % days
        if not delivered:
            return {'text': text + ' None of your orders have been delivered yet.'}
        order = delivered[0]
        return {'text': text + ' Open order #%s and choose Return or replace.' % order.mart369_ref,
                'actions': [self._mart369_track(order, 'Return or replace')]}

    def _mart369_answer_payment(self, rule, ctx):
        return {'text': rule.reply or (
            'If money left your account but the order did not go through, the bank '
            'releases it automatically within 48 hours. Nothing is charged twice.')}

    def _mart369_answer_delivery(self, rule, ctx):
        """Read off the real delivery rules rather than retyped into a string.

        The hardcoded version had already drifted: it quoted Express as 2-5 days
        where the rule says 2-3, and implied a minimum Express order that does
        not exist.
        """
        rules = self.env['mart369.delivery.rule']._mart369_rules()
        parts = []
        for mode in ('quick', 'all'):
            rule_record = rules.get(mode)
            if not rule_record:
                continue
            bits = ['%s: %s' % (rule_record.label or mode, rule_record.eta or '')]
            if rule_record.fee:
                bits.append('%s delivery' % self._mart369_money(ctx, rule_record.fee))
            else:
                bits.append('free delivery')
            if rule_record.free_above:
                bits.append('free above %s' % self._mart369_money(ctx, rule_record.free_above))
            if rule_record.min_order:
                bits.append('minimum order %s' % self._mart369_money(ctx, rule_record.min_order))
            parts.append(', '.join(bits) + '.')
        if not parts:
            return {'text': rule.reply_alt or 'Delivery charges are not set up yet.'}
        return {'text': ' '.join(parts)}

    def _mart369_answer_coupons(self, rule, ctx):
        """The codes that really work today, with their real minimums."""
        live = [coupon for coupon in self.env['mart369.coupon'].sudo().search([])
                if coupon._mart369_live()]
        if not live:
            return {'text': rule.reply_alt or 'There are no coupon codes running right now.'}
        parts = []
        for coupon in live[:4]:
            bit = coupon.code
            if coupon.title:
                bit += ' (%s' % coupon.title
                if coupon.min_spend:
                    bit += ', above %s' % self._mart369_money(ctx, coupon.min_spend)
                bit += ')'
            parts.append(bit)
        return {'text': 'Current codes: %s.' % ', '.join(parts)}

    def _mart369_answer_wallet(self, rule, ctx):
        return {'text': 'Your 369 Wallet balance is %s. It never expires and is used '
                        'before any other payment method.' % self._mart369_money(
                            ctx, ctx['wallet'])}

    def _mart369_answer_agent(self, rule, ctx):
        return {'text': rule.reply or 'Connecting you to a support agent…',
                'agent': True}

    @api.model
    def _mart369_return_days(self):
        """How long a return stays open. One number, not one per screen."""
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'mart369_support.return_days')
        try:
            return int(raw) if raw else 7
        except (TypeError, ValueError):
            return 7

    # ------------------------------------------------------------- the agent

    @api.model
    def _mart369_agent_reply(self, partner, ticket, text):
        """What a person would say, as a bare string.

        `SupportBot.jsx:167` pushes this straight into the transcript without
        unwrapping it, so returning a dict here puts "[object Object]" on the
        customer's screen.
        """
        typed = (text or '').strip().lower()
        if re.match(r'^(hi|hello|hey|hai|namaste)\b', typed):
            return 'Hi, how can I help?'
        if ticket and ticket.order_id:
            return ("Thanks for the details. I've noted this against order #%s "
                    'and someone will reply here shortly.' % (
                        ticket.order_id.mart369_ref or ''))
        return 'Thanks for the details. I have noted this and someone will reply here shortly.'
