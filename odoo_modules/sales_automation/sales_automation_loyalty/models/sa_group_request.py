# -*- coding: utf-8 -*-
"""Loyalty points in the WhatsApp group flow.

Before the pay link goes out, a customer whose card can redeem is asked
once - a poll, USE POINTS or PAY FULL. USE applies the redemption line and
the link is then built for the reduced amount; PAY FULL, or silence for
the configured minutes, sends the link unchanged. After payment the group
gets one line with the points earned and the balance.
"""
import json
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SaGroupRequestLoyalty(models.Model):
    _inherit = 'sa.group.request'

    sa_loyalty_offer_json = fields.Text('Loyalty offer options', copy=False)
    sa_loyalty_offer_on = fields.Datetime('Loyalty offer asked on', copy=False)
    sa_loyalty_pending = fields.Selection([('stock', 'In-stock pay link'), ('accept', 'Shop accept pay link')],
                                          'Pay link held for the offer', copy=False)
    sa_loyalty_pending_job_id = fields.Many2one('stock.picking', 'Job held for the offer', copy=False)
    sa_loyalty_choice = fields.Selection([('use', 'Use points'), ('full', 'Pay full')],
                                         'Loyalty choice', copy=False)
    sa_loyalty_told_on = fields.Datetime('Points-earned line sent on', copy=False)

    # ------------------------------------------------------------------
    # The offer
    # ------------------------------------------------------------------
    def _sa_loyalty_card_for(self, order):
        self.ensure_one()
        try:
            return order.sudo()._find_loyalty_card(create=False, extra_phones=[self.requester_phone or ''])
        except Exception as err:  # noqa: BLE001
            _logger.info("Loyalty offer: card lookup failed for %s: %s", order.name, err)
            return self.env['pos.loyalty.card']

    def _sa_loyalty_maybe_offer(self, order, pending, job=None):
        """True when the offer was posted and the pay link must wait."""
        self.ensure_one()
        settings = self._settings()
        if not settings.loyalty_offer_enabled or self.sa_loyalty_choice or self.sa_loyalty_offer_on:
            return False
        order = order.sudo()
        SO = self.env['sale.order']
        if not SO._loyalty_enabled() or self._sa_order_is_paid(order):
            return False
        rule = SO._loyalty_rule()
        card = self._sa_loyalty_card_for(order)
        if not rule or not card or card.state != 'active':
            return False
        if card.total_points < (rule.min_redeem_points or 0):
            return False
        if not card._check_redemption_cooldown().get('allowed'):
            return False
        points = order._loyalty_max_points(card)
        if points <= 0:
            return False
        value = round(points / (rule.points_per_currency or 1.0), 2)
        cur = order.currency_id.symbol or ''
        body = (settings.loyalty_offer_text or '').format(
            points='%g' % points, value='%.2f' % value, cur=cur, ref=self.ref_code or order.name)
        use_label = _("\U0001F381 USE POINTS (-%(cur)s %(value).2f)", cur=cur, value=value)
        full_label = _("PAY FULL")
        self.write({'sa_loyalty_offer_json': json.dumps({use_label: 'use', full_label: 'full'}),
                    'sa_loyalty_offer_on': fields.Datetime.now(),
                    'sa_loyalty_pending': pending,
                    'sa_loyalty_pending_job_id': job.id if job else False,
                    'sa_loyalty_choice': False})
        if pending == 'stock':
            # The deal is done; only the payment is open. Said now so a stray
            # text is not read as a fresh CONFIRM / CANCEL.
            self.write({'state': 'order_created', 'sa_stock_confirmed': True})
        self._ask(body, [{'id': 'sa_loy_use', 'title': use_label},
                         {'id': 'sa_loy_full', 'title': full_label}])
        return True

    def _sa_send_group_pay_link(self):
        if not self.env.context.get('sa_loyalty_offered') and self.order_id \
                and self._sa_loyalty_maybe_offer(self.order_id, 'stock'):
            return True
        return super()._sa_send_group_pay_link()

    def _sa_accept_pay_link(self, job):
        if not self.env.context.get('sa_loyalty_offered') and job.sale_id \
                and self._sa_loyalty_maybe_offer(job.sale_id, 'accept', job):
            return True
        return super()._sa_accept_pay_link(job)

    # ------------------------------------------------------------------
    # The answer
    # ------------------------------------------------------------------
    @staticmethod
    def _sa_loyalty_key(label):
        return re.sub(r'[^a-z0-9]', '', (label or '').lower())

    def _sa_loyalty_choice_of(self, text):
        self.ensure_one()
        if not self.sa_loyalty_offer_json or self.sa_loyalty_choice:
            return None
        try:
            menu = json.loads(self.sa_loyalty_offer_json)
        except ValueError:
            return None
        key = self._sa_loyalty_key(text)
        for label, choice in menu.items():
            if key and key == self._sa_loyalty_key(label):
                return choice
        low = (text or '').strip().lower()
        if low in ('use points', 'use', 'yes', 'y'):
            return 'use'
        if low in ('pay full', 'full', 'no', 'n'):
            return 'full'
        return None

    def _sa_answer_poll(self, text):
        self.ensure_one()
        choice = self._sa_loyalty_choice_of(text)
        if choice:
            return self._sa_loyalty_resolve(choice)
        return super()._sa_answer_poll(text)

    def _sa_loyalty_resolve(self, choice):
        """Apply the choice and send the pay link that was held."""
        self.ensure_one()
        order = self.order_id.sudo()
        self.write({'sa_loyalty_choice': choice})
        if choice == 'use' and order and order.state in ('draft', 'sent'):
            try:
                card = self._sa_loyalty_card_for(order)
                points = order._loyalty_max_points(card) if card else 0
                discount = order._loyalty_apply_redemption(card, points) if points else 0
                self._say(_("\U0001F381 *%(pts)g points applied* - %(cur)s %(disc).2f off. "
                            "New total: *%(cur)s %(total).2f*",
                            pts=points, cur=order.currency_id.symbol or '', disc=discount,
                            total=order.amount_total))
            except Exception as err:  # noqa: BLE001 - the link still goes out
                _logger.warning("Loyalty offer: applying points on %s failed: %s", order.name, err)
                self._say(_("Sorry, the points could not be applied this time - the full amount follows."))
        elif choice == 'use' and order:
            # Confirmed already (shop-accept path): apply on the confirmed order
            # is not allowed; say so and send the full link.
            self._say(_("The points could not be applied to this confirmed order - the full amount follows."))
        pending, job = self.sa_loyalty_pending, self.sa_loyalty_pending_job_id
        self.write({'sa_loyalty_pending': False, 'sa_loyalty_pending_job_id': False})
        me = self.with_context(sa_loyalty_offered=True)
        if pending == 'accept' and job:
            return me._sa_accept_pay_link(job)
        return me._sa_send_group_pay_link()

    @api.model
    def _cron_pay_remind(self):
        """Offers nobody answered: the full link goes out after the wait."""
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        wait = int(settings.loyalty_offer_wait_minutes or 10)
        due = fields.Datetime.now() - timedelta(minutes=wait)
        for req in self.sudo().search([('sa_loyalty_offer_on', '<=', due), ('sa_loyalty_choice', '=', False),
                                       ('sa_loyalty_pending', '!=', False)]):
            try:
                req._sa_loyalty_resolve('full')
            except Exception as err:  # noqa: BLE001
                _logger.warning("Loyalty offer: resolving %s failed: %s", req.id, err)
        return super()._cron_pay_remind()

    # ------------------------------------------------------------------
    # After payment
    # ------------------------------------------------------------------
    def _sa_loyalty_tell_earned(self, order):
        self.ensure_one()
        order = order.sudo()
        if self.sa_loyalty_told_on or not order.loyalty_earned_on or not order.loyalty_card_id:
            return False
        settings = self._settings()
        body = (settings.loyalty_paid_text or '').format(
            earned='%g' % order.loyalty_points_earned, balance='%g' % order.loyalty_card_id.total_points,
            ref=self.ref_code or order.name)
        if body.strip():
            self._say(body)
        self.write({'sa_loyalty_told_on': fields.Datetime.now()})
        return True

    # ------------------------------------------------------------------
    # MORE poll: the customer's points
    # ------------------------------------------------------------------
    def _sa_more_extra_options(self):
        res = super()._sa_more_extra_options()
        if self.env['sale.order']._loyalty_enabled():
            res.append((_("\U0001F381 MY LOYALTY POINTS"), {'kind': 'points', 'req': self.id}))
        return res

    @staticmethod
    def _sa_mask_card_number(number):
        """LC92000004 -> LC•••••004: the letters kept, the last three digits shown."""
        number = number or ''
        letters = ''.join(c for c in number[:3] if c.isalpha())
        body = number[len(letters):]
        if len(body) <= 3:
            return number
        # Bullets, not asterisks: WhatsApp reads * as a bold marker and eats them.
        return letters + '•' * (len(body) - 3) + body[-3:]

    def _sa_say_loyalty_points(self):
        self.ensure_one()
        SO = self.env['sale.order']
        if not SO._loyalty_enabled():
            return super()._sa_say_loyalty_points()
        card = self.env['pos.loyalty.card']
        if self.order_id:
            card = self._sa_loyalty_card_for(self.order_id)
        if not card and self.requester_phone:
            Card = card.sudo()
            _dial, n = Card._get_loyalty_mobile_cfg()
            digits = ''.join(c for c in self.requester_phone if c.isdigit())
            tail = digits[-n:] if len(digits) >= n else digits
            card = Card.search([('phone', 'like', tail), ('is_deleted', '=', False)], limit=1) if tail else card
        rule = SO._loyalty_rule()
        if not card:
            self._say(_("\U0001F381 You have no loyalty card yet. It is created automatically with your "
                        "first paid order, and you earn %(pts)g points for every %(spend)g spent.",
                        pts=rule.points_earned if rule else 0, spend=rule.spend_amount if rule else 0))
            return True
        value = round(card.total_points / (rule.points_per_currency or 1.0), 2) if rule else 0.0
        cur = (self.order_id.currency_id.symbol if self.order_id else '') or self.env.company.currency_id.symbol or ''
        since = card.registration_date.strftime('%d %b %Y') if card.registration_date else '-'
        # A group is not the place for the full number: everyone there can read it.
        num = self._sa_mask_card_number(card.card_number)
        self._say(_("\U0001F381 *Your loyalty card*\n\nCard: *%(num)s*\nStatus: %(state)s\nMember since: %(since)s\n\n"
                    "Points: *%(pts)g* (worth %(cur)s %(value).2f)\nMinimum to redeem: %(minpts)g points\n\n"
                    "You earn %(earn)g points for every %(spend)g spent. When you can redeem, we ask before "
                    "each pay link.",
                    num=num, state=dict(card._fields['state'].selection).get(card.state, card.state),
                    since=since, pts=card.total_points, cur=cur, value=value,
                    minpts=rule.min_redeem_points if rule else 0, earn=rule.points_earned if rule else 0,
                    spend=rule.spend_amount if rule else 0))
        return True

    def _sa_paid_extras(self, order):
        """The points line goes right after the invoice and the delivery
        date, before the track buttons."""
        res = super()._sa_paid_extras(order)
        try:
            self._sa_loyalty_tell_earned(order)
        except Exception as err:  # noqa: BLE001
            _logger.warning("Loyalty: points line for %s failed: %s", order.name, err)
        return res


class SaleOrderLoyaltyWhatsApp(models.Model):
    _inherit = 'sale.order'

    def _loyalty_after_earn(self, card, points):
        """Group orders are told by `_sa_group_confirmed`; a private-chat
        order is told here, in its own chat."""
        res = super()._loyalty_after_earn(card, points)
        req = self._sa_group_enquiry() if hasattr(self, '_sa_group_enquiry') else None
        if req:
            if req.sa_paid_told_on:
                # `_sa_group_confirmed` already ran (payment reconciled later):
                # say it now, once.
                req.sudo()._sa_loyalty_tell_earned(self)
            return res
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        if not settings.loyalty_notify_dm:
            return res
        phone = card.phone or self.partner_id.phone
        if not phone:
            return res
        try:
            session = self.env['whatsapp.session'].sudo().get_connected_session()
            if session:
                body = (settings.loyalty_paid_text or '').format(
                    earned='%g' % points, balance='%g' % card.total_points, ref=self.name)
                session.send_message(phone, body)
        except Exception as err:  # noqa: BLE001
            _logger.info("Loyalty: private points line for %s not sent: %s", self.name, err)
        return res
