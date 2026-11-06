# -*- coding: utf-8 -*-
"""Our side of the shared cards (Overlap Board, 7 Oct 2026) - hooks with defaults.

Each `_sa_...` hook below answers the way the flow behaves today, so nothing
changes until another module (the 369 Mart bridge) plugs in its own answer.
Nothing here imports or depends on that module.

  sale.order._sa_paid_elsewhere()   money taken outside Odoo payments (wallet, COD app) -> 0.0
  sale.order._sa_wallet_apply()     take what you can from the customer's wallet, return it -> 0.0
  sale.order._sa_points_offer()     {'points': n, 'value': x} the customer may spend -> None
  sale.order._sa_points_apply()     apply the points, return the discount given -> 0.0
  sale.order._sa_review_link()      a page to rate the products after delivery -> ''
  sale.order._sa_coupon_allowed()   False once the price was bargained in the chat
  sa.group.request._sa_live_deal_price()  a live deal / offer price -> None (bargaining never goes below it)

Also here, no hook needed:
  * the landmark / gate question before the details check writes a note for
    THIS order (`sale.order.sa_delivery_note`), not the address's landmark;
  * STOP / START UPDATES respects the gateway's opt-out list (a number on it
    counts as "off"; START takes it off the list, STOP never adds to it - that
    list means "no messages at all", and the door code must still arrive).
"""
import logging
import re
from urllib.parse import urlsplit

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

SKIP = ('skip', 'no', 'none', 'nil', 'na', 'n/a', '-', 'nothing', 'no landmark',
        'illa', 'illai', 'vendam', '1')


class SaleOrderCommonHooks(models.Model):
    _inherit = 'sale.order'

    sa_delivery_note = fields.Char(
        'Note for This Delivery', copy=False,
        help="What the customer answered to \"any landmark, flat number or gate note?\" "
             "for this order only. The address keeps its own landmark.")
    sa_bargained = fields.Boolean(
        'Price Bargained on WhatsApp', copy=False, readonly=True,
        help="The agreed price is below the quoted one. No coupon on top of it.")

    def _sa_paid_elsewhere(self):
        """Money already taken outside Odoo's payments (a wallet, an app's
        cash-on-delivery record). Subtracted from what the rider collects."""
        return 0.0

    def _sa_wallet_apply(self):
        """Take as much of the total as the customer's wallet holds and
        return the amount taken. Must be safe to call more than once."""
        return 0.0

    def _sa_points_offer(self):
        """Points the customer may spend on this order, as
        {'points': n, 'value': money}, or None."""
        return None

    def _sa_points_apply(self):
        """Apply the offered points; return the discount given (money)."""
        return 0.0

    def _sa_review_link(self):
        """A page where the customer rates the products, or ''."""
        return ''

    def _sa_coupon_allowed(self):
        """A coupon is never stacked on a price bargained in the chat."""
        self.ensure_one()
        return not self.sa_bargained


class SaGroupRequestCommonHooks(models.Model):
    _inherit = 'sa.group.request'

    def _sa_live_deal_price(self):
        """A live deal / offer price for the product, or None."""
        return None

    # ---------------------------------------------------------- bargaining
    def _bargain_floor(self):
        floor = super()._bargain_floor()
        try:
            deal = self._sa_live_deal_price()
        except Exception as err:  # noqa: BLE001 - a hook must never break a quote
            _logger.info("Sales Automation: live deal price failed: %s", err)
            deal = None
        if deal:
            floor = max(floor or 0.0, float(deal))
        return floor

    def _place_order(self):
        res = super()._place_order()
        try:
            order = self.order_id
            if order and self.quoted_price and self.agreed_price \
                    and self.agreed_price < self.quoted_price - 0.004:
                order.sudo().write({'sa_bargained': True})
        except Exception as err:  # noqa: BLE001
            _logger.info("Sales Automation: bargained flag not set: %s", err)
        return res

    # ------------------------------------------------- note for this order
    def _sa_take_details(self, text):
        """The landmark / gate answer belongs to this order, not to the
        address (the address has its own landmark in the address book)."""
        self.ensure_one()
        order = self.order_id.sudo() if self.order_id else None
        if order and self.sa_note_step == 'ask' and self.profile_step == 'confirm' \
                and not self.sa_book_step:
            answer = (text or '').strip()
            low = answer.lower().strip(' .!*')
            back = hasattr(self, 'NOTE_BACK') and re.sub(r'[^a-z0-9]', '', answer.lower()) \
                == re.sub(r'[^a-z0-9]', '', self.NOTE_BACK.lower())
            if not back and low not in ('2', 'back') and not self._sa_is_cancel(answer):
                skip = low in SKIP or (hasattr(self, 'NOTE_SKIP') and re.sub(
                    r'[^a-z0-9]', '', answer.lower()) == re.sub(r'[^a-z0-9]', '', self.NOTE_SKIP.lower()))
                order.write({'sa_delivery_note': False if skip else answer[:120]})
                self.write({'sa_note_step': 'done'})
                return self._sa_details_ask(order)
        return super()._sa_take_details(text)

    def _sa_profile_summary(self, partner):
        text = super()._sa_profile_summary(partner)
        order = self.order_id.sudo() if self.order_id else None
        note = order.sa_delivery_note if order else ''
        if note:
            line = _("\U0001F4DD Note for this delivery: %s") % note
            marker = _("Reply *YES* to confirm")
            text = text.replace('\n\n' + marker, '\n' + line + '\n\n' + marker, 1) \
                if ('\n\n' + marker) in text else text + '\n' + line
        return text

    # ------------------------------------------------ wallet + points + pay
    def _sa_pay_link_any_state(self, order):
        """The pay link, less what the wallet took; plus the points offer."""
        order = order.sudo()
        text = super()._sa_pay_link_any_state(order)
        try:
            taken = float(order._sa_wallet_apply() or 0.0)
        except Exception as err:  # noqa: BLE001 - never block a payment
            _logger.info("Sales Automation: wallet hook failed: %s", err)
            taken = 0.0
        # A reminder must not ask again for what the wallet already paid:
        # the wallet hook takes money only once, so read what it took.
        try:
            already = float(order._sa_paid_elsewhere() or 0.0)
        except Exception as err:  # noqa: BLE001
            _logger.info("Sales Automation: paid-elsewhere hook failed: %s", err)
            already = 0.0
        part = max(taken, already)
        if part > 0.004:
            rest = max(0.0, order.amount_total - part)
            cur = order.currency_id.symbol or ''
            if rest <= 0.004:
                text = _("💰 Your wallet covers this order (%(cur)s %(taken).2f) - "
                         "nothing more to pay.", cur=cur, taken=part)
                self._sa_wallet_covered(order)
            else:
                url = self._sa_pay_url_for_amount(order, rest)
                if taken > 0.004:
                    text = _("💰 %(cur)s %(taken).2f taken from your wallet. "
                             "Pay the rest, %(cur)s %(rest).2f, here:\n%(url)s",
                             cur=cur, taken=part, rest=rest, url=url)
                else:
                    text = _("💰 %(cur)s %(taken).2f was already paid from your wallet. "
                             "Pay the rest, %(cur)s %(rest).2f, here:\n%(url)s",
                             cur=cur, taken=part, rest=rest, url=url)
        try:
            offer = order._sa_points_offer()
        except Exception as err:  # noqa: BLE001
            _logger.info("Sales Automation: points hook failed: %s", err)
            offer = None
        if offer and offer.get('points'):
            text += _("\n\n\U0001F48E You have %(n)s points worth %(cur)s %(v).2f. "
                      "Tap *💎 USE POINTS* below to take them off before paying.",
                      n=offer['points'], cur=order.currency_id.symbol or '', v=offer.get('value') or 0.0)
        return text

    def _sa_wallet_covered(self, order):
        """The wallet paid the whole order, so no online payment will ever
        arrive to move it on: run the paid step now (it runs once)."""
        self.ensure_one()
        if self.sa_paid_told_on or order.state == 'cancel' or not self.group_id:
            return False
        try:
            return self._sa_group_paid(order)
        except Exception as err:  # noqa: BLE001 - the shop sees the order either way
            _logger.warning("Sales Automation: paid step after the wallet for %s failed: %s",
                            order.name, err)
            return False

    def _sa_pay_url_for_amount(self, order, amount):
        """Odoo's payment link for a part of the total, on the public address."""
        try:
            w = self.env['payment.link.wizard'].sudo().with_context(
                active_model='sale.order', active_id=order.id).create({
                    'res_model': 'sale.order', 'res_id': order.id,
                    'amount': amount, 'currency_id': order.currency_id.id,
                    'partner_id': order.partner_id.id})
            parts = urlsplit(w.link or '')
            path = parts.path + ('?' + parts.query if parts.query else '')
            return self.env['wa.auto.reply'].sudo()._sa_public_link(path)
        except Exception as err:  # noqa: BLE001 - fall back to the full link
            _logger.warning("Pay link for %s (%s): %s", order.name, amount, err)
            return self._sa_pay_url(order)

    _USE_POINTS = re.compile(r"^\s*(use|apply|redeem)\s+(my\s+)?points?\s*[.!]?\s*$", re.I)

    @api.model
    def _sa_typed_answer_hook(self, group, message, text):
        res = super()._sa_typed_answer_hook(group, message, text)
        if res is not None or not self._USE_POINTS.match(text or ''):
            return res
        rows = self._sa_ss_sender_rows(group, message, [('order_id', '!=', False)]) \
            if hasattr(self, '_sa_ss_sender_rows') else self.browse()
        req = rows[:1]
        if not req:
            return None
        return req._sa_use_points()

    def _sa_use_points(self):
        """Take the customer's points off this order (typed or tapped)."""
        self.ensure_one()
        req = self
        order = req.order_id.sudo()
        if not order:
            return True
        try:
            given = float(order._sa_points_apply() or 0.0)
        except Exception as err:  # noqa: BLE001
            _logger.info("Sales Automation: points apply failed: %s", err)
            given = 0.0
        if given <= 0.004:
            req._say(_("You have no points to use on order *#%s* right now.") % (req.ref_code or order.name))
            return True
        req._say(_("\U0001F48E %(cur)s %(v).2f taken off with your points.\n\n%(pay)s",
                   cur=order.currency_id.symbol or '', v=given, pay=req._sa_pay_link_any_state(order)))
        return True

    # ----------------------------------------------------- consent in step
    def _sa_optout_phone(self):
        customer = self._sa_ss_customer() if hasattr(self, '_sa_ss_customer') else None
        return (customer.phone if customer and customer.phone else self.requester_phone) or ''

    def _sa_updates_on(self):
        on = super()._sa_updates_on()
        if on and 'whatsapp.optout' in self.env:
            phone = self._sa_optout_phone()
            if phone and self.env['whatsapp.optout'].sudo().is_opted_out(phone):
                return False
        return on

    def _sa_set_updates(self, on):
        res = super()._sa_set_updates(on)
        if on and 'whatsapp.optout' in self.env:
            Opt = self.env['whatsapp.optout'].sudo()
            phone = self._sa_optout_phone()
            cleaned = Opt._clean(phone)
            if cleaned:
                rows = Opt.with_context(active_test=False).search([('phone', '=', cleaned), ('active', '=', True)])
                if rows:
                    rows.write({'active': False})
                    _logger.info("Sales Automation: %s asked for updates again - taken off the opt-out list", cleaned)
        return res
