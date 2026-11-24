# -*- coding: utf-8 -*-
"""Rider app "next round" (6 Oct 2026): a proper resend of the customer's
code, a thank-you message with the order, time and rider, the role checked
before a sign-in code goes out, and Packed allowed before the payment (the
rider is called by itself when the payment lands)."""
import logging
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SaDeliverySettingsRound2(models.Model):
    _inherit = 'sa.delivery.settings'

    packed_wait_payment_seconds = fields.Integer(
        'Packed before payment: show "waiting" for (seconds)', default=60,
        help="The counter may press Packed on an unpaid order. The card says "
             "'Waiting for payment' for this long, then a calm note. The rider "
             "is called by itself the moment the payment arrives, whenever "
             "that is.")
    code_resend_limit = fields.Integer(
        "Customer code: resends allowed per delivery", default=5)
    code_resend_cooldown = fields.Integer(
        "Customer code: seconds between resends", default=60)


class StockPickingRound2(models.Model):
    _inherit = 'stock.picking'

    sa_code_sent_on = fields.Datetime("Customer Code Sent On", copy=False, readonly=True)
    sa_code_resends = fields.Integer("Customer Code Resends", copy=False, readonly=True)
    sa_packed_unpaid_on = fields.Datetime(
        'Packed Before Payment On', copy=False, readonly=True,
        help="The counter pressed Packed while the customer had not paid. The "
             "rider is called by itself when the payment arrives.")

    # ------------------------------------------------------------------
    # The customer's code: resend
    # ------------------------------------------------------------------
    def sa_issue_delivery_otp(self, send=True):
        ok, msg, code = super().sa_issue_delivery_otp(send=send)
        if send:
            self.sudo().write({'sa_code_sent_on': fields.Datetime.now()})
        return ok, msg, code

    @staticmethod
    def _sa_mask_phone(phone):
        digits = ''.join(c for c in (phone or '') if c.isdigit())
        return ('•••' + digits[-4:]) if len(digits) >= 4 else ''

    def sa_resend_customer_code(self, rider=None):
        """The rider at the door asks for the customer's code again. Returns
        {sent, sent_to, retry_after, reason, message, code}."""
        self.ensure_one()
        job = self.sudo()
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        limit = max(1, settings.code_resend_limit or 5)
        cooldown = max(10, settings.code_resend_cooldown or 60)
        who = rider.name if rider else self.env.user.name
        if job.sa_delivery_state != 'out_for_delivery' or not job.sa_arrived_customer_on:
            return {'sent': False, 'reason': 'wrong_state', 'retry_after': 0,
                    'message': _("Press Reached first - the code is sent when you are at the door.")}
        if job.sa_code_resends >= limit:
            return {'sent': False, 'reason': 'limit', 'retry_after': 0,
                    'message': _("%(n)s resends already - that is the most. Ask the counter to read the "
                                 "code to you from the job.", n=limit)}
        if job.sa_code_sent_on:
            waited = (fields.Datetime.now() - job.sa_code_sent_on).total_seconds()
            if waited < cooldown:
                left = int(cooldown - waited)
                return {'sent': False, 'reason': 'too_soon', 'retry_after': left,
                        'message': _("A code went out %(s)s seconds ago. Wait %(left)s s and try again.",
                                     s=int(waited), left=left)}
        ok, msg, code = job.sa_issue_delivery_otp()
        job.write({'sa_code_resends': job.sa_code_resends + 1})
        job.message_post(body=_("Customer code resent by %(who)s (%(n)s of %(max)s) - %(how)s.",
                                who=who, n=job.sa_code_resends, max=limit,
                                how=_("sent on WhatsApp") if ok else _("NOT sent: %s", msg)))
        phone = (job.partner_id.phone or '').strip()
        if not phone and job.sale_id and getattr(job.sale_id, 'wa_conversation_id', False):
            phone = job.sale_id.wa_conversation_id.phone or ''
        return {'sent': bool(ok), 'sent_to': self._sa_mask_phone(phone) if ok else '',
                'retry_after': cooldown if ok else 0,
                'reason': '' if ok else 'whatsapp_failed',
                'message': (_("A new code has been sent to the customer on WhatsApp. The old one no longer works.")
                            if ok else _("WhatsApp did not send the code. Ask the counter to read it to you from the job.")),
                'code': code, 'resends': job.sa_code_resends, 'limit': limit}

    # ------------------------------------------------------------------
    # Thank you after Delivered
    # ------------------------------------------------------------------
    def _sa_notify_customer(self, state):
        # every customer message is logged with its result, so a missing
        # "rider is near" can be told apart from the near rule not firing
        if state != 'delivered' or self.env.context.get('sa_quiet'):
            res = super()._sa_notify_customer(state)
            if not self.env.context.get('sa_quiet'):
                _logger.info("Delivery: customer message for %s at %s -> %s",
                             self.sa_ref_code or self.name, state, 'sent' if res else 'NOT sent')
            return res
        self.ensure_one()
        # the customer's clock: the company's zone, else the rider's (they
        # are in the same town), else the user's, else UTC
        tz = self.env['sa.delivery.partner']._sa_company_tz(self.company_id or self.env.company)
        when = fields.Datetime.context_timestamp(self.with_context(tz=tz),
                                                 self.sa_delivered_on or fields.Datetime.now())
        body = _(
            "✅ Your order *#%(order)s* was delivered at %(time)s by *%(rider)s*.\n\n"
            "Thank you for shopping with us! \U0001F64F",
            order=self.sale_id.name or self.sa_ref_code or self.name,
            time=when.strftime('%H:%M'),
            rider=self._sa_carrier_name())
        # "⭐ Rate your products" (once per order, when the shop asks for
        # reviews). This message replaced the base one and had left it out,
        # so the review link never went (21 Nov 2026).
        review = self._sa_review_line()
        order = self.sale_id
        group_order = bool(order and hasattr(order, '_sa_group_enquiry') and order._sa_group_enquiry())
        if review and group_order:
            # its own message: the Delivered words stay in the group, the
            # personal link goes to the private chat (sa_private_links.py)
            sent = self._sa_tell_customer(body)
            if not self._sa_tell_customer(review.strip()):
                self.env['sa.outbox.guard'].sudo().release(self._sa_review_guard_key())
            return sent
        sent = self._sa_tell_customer(body + review)
        if review and not sent:
            self.env['sa.outbox.guard'].sudo().release(self._sa_review_guard_key())
        return sent

    # ------------------------------------------------------------------
    # Packed before the payment
    # ------------------------------------------------------------------
    def sa_set_state(self, state):
        if state == 'dispatched':
            self.sudo().write({'sa_code_resends': 0, 'sa_code_sent_on': False})
        return super().sa_set_state(state)

    def sa_packed_wait_left(self):
        """Seconds the card still says 'Waiting for payment', else 0."""
        self.ensure_one()
        if not self.sa_packed_unpaid_on:
            return 0
        total = max(0, self.env['sa.delivery.settings'].sudo().get_settings().packed_wait_payment_seconds or 0)
        gone = (fields.Datetime.now() - self.sa_packed_unpaid_on).total_seconds()
        return max(0, int(total - gone))

    def _sa_carrier_name(self):
        """Who delivered, for the customer's message."""
        self.ensure_one()
        return self.sa_delivery_partner_id.name or _("our rider")

    def _compute_sa_stage_text(self):
        super()._compute_sa_stage_text()
        for p in self:
            if p.sa_packed_unpaid_on and p.sa_delivery_state in ('ready', 'to_assign') \
                    and not p.sa_delivery_partner_id:
                p.sa_stage_text = _("Packed - not paid yet. The rider is called by itself when the customer pays.")


# A company with no zone on its contact: the zone of its country. One zone
# for the whole database, never a rider's own preference, never UTC by accident.
_COUNTRY_TZ = {'AE': 'Asia/Dubai', 'OM': 'Asia/Muscat', 'IN': 'Asia/Kolkata', 'SA': 'Asia/Riyadh',
               'QA': 'Asia/Qatar', 'KW': 'Asia/Kuwait', 'BH': 'Asia/Bahrain', 'LK': 'Asia/Colombo',
               'PK': 'Asia/Karachi', 'BD': 'Asia/Dhaka', 'GB': 'Europe/London', 'SG': 'Asia/Singapore',
               'MY': 'Asia/Kuala_Lumpur'}


class SaDeliveryPartnerRound2(models.Model):
    _inherit = 'sa.delivery.partner'

    @api.model
    def _sa_company_tz(self, company=None):
        """The database's one time zone: the company contact's zone, else
        the zone of the company's country, else UTC (and a warning)."""
        company = company or self.env.company
        partner = company.sudo().partner_id
        tz = partner.tz or _COUNTRY_TZ.get(partner.country_id.code or '') or ''
        if not tz:
            _logger.warning("Delivery: company %s has no time zone and no known country - "
                            "set it on the company's contact (Contacts > Time zone)", company.name)
            return 'UTC'
        return tz

    @api.model
    def _sa_kind_label(self, kind):
        return _("Delivery Partner") if kind == 'third_party' else _("Office rider")

    def sa_kind_mismatch(self, wanted):
        """None, or the refusal for a sign-in that chose the wrong role."""
        self.ensure_one()
        wanted = (wanted or '').strip().lower()
        if wanted in ('partner', 'delivery_partner'):
            wanted = 'third_party'
        if wanted in ('office', 'staff'):
            wanted = 'own'
        if wanted not in ('own', 'third_party') or wanted == (self.kind or 'own'):
            return None
        label = self._sa_kind_label(self.kind or 'own')
        return {'code': 'wrong_kind', 'registered_kind': self.kind or 'own',
                'message': _("This number is registered as %(a)s. Choose %(b)s and sign in again.",
                             a=('a ' + label) if self.kind == 'third_party' else ('an ' + label), b=label)}
