"""The loyalty card, its history and its rule, as a sale order sees them.

`pos_loyalty_card` holds the card, the rule and the history; since it stopped
needing Point of Sale it does no earning or spending of its own. Three things
this adds:

* **A link to a `sale.order`** on each history row, `sale_order_id`.
* **Finding the right card for a customer.** By partner first, then by mobile
  number - so a card someone already has is the card their orders use - and
  never somebody else's.
* **A lock.** Every spend takes the card's row before checking the balance, so
  two spends of the same points cannot both pass.
"""

import logging
import re
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# The signs the counter's history uses (loyalty_card.py `_compute_total_points`).
CREDIT_TYPES = ('earned', 'redeem_returned')


class PosLoyaltyRule(models.Model):
    _inherit = 'pos.loyalty.rule'

    def _mart369_points_for(self, amount):
        """Points for spending `amount`. The counter's own formula
        (pos_order.py `_earn_points_for_sale`), in one place."""
        self.ensure_one()
        if not self.spend_amount or amount <= 0:
            return 0.0
        return round((amount / self.spend_amount) * (self.points_earned or 0.0), 2)

    def _mart369_per_rupee(self):
        self.ensure_one()
        return self.points_per_currency or 10.0

    def _mart369_value(self, points):
        """What `points` take off a bill, in rupees."""
        self.ensure_one()
        return round((points or 0.0) / self._mart369_per_rupee(), 2)

    def _mart369_serialize(self):
        self.ensure_one()
        return {
            'spend': self.spend_amount or 0.0,
            'earn': self.points_earned or 0.0,
            'minRedeem': self.min_redeem_points or 0.0,
            'perRupee': self._mart369_per_rupee(),
            'maxPercent': self.max_redeem_percent or 0.0,
        }


class PosLoyaltyHistory(models.Model):
    _inherit = 'pos.loyalty.history'

    sale_order_id = fields.Many2one(
        'sale.order', string='Order', index=True, ondelete='set null',
        help="The order this movement belongs to - from the app or from Odoo's Sales.")
    mart369_title = fields.Char(string='Shown as')
    mart369_sub = fields.Char(string='Shown under')

    def _mart369_serialize(self):
        """One row of the customer's points history."""
        self.ensure_one()
        order = self.sale_order_id
        title = self.mart369_title or self.description or {
            'earned': _('Points earned'),
            'redeemed': _('Points used'),
            'returned': _('Points taken back'),
            'redeem_returned': _('Points given back'),
        }.get(self.type, '')
        return {
            'id': self.id,
            'kind': self.type,
            'points': self.points,
            'credit': self.type in CREDIT_TYPES,
            'title': title,
            'sub': self.mart369_sub or '',
            'at': int(self.create_date.timestamp() * 1000) if self.create_date else None,
            # Only app orders open in the app; a Sales order is named in `sub`.
            'orderRef': order.mart369_ref or '' if order else '',
        }


class PosLoyaltyCard(models.Model):
    _inherit = 'pos.loyalty.card'

    # ----------------------------------------------------------- the switch

    @api.model
    def _mart369_enabled(self):
        """Loyalty on for the shop, and on for 369 Mart."""
        settings = self.env['pos.loyalty.card.settings'].sudo().get_settings()
        config = self.env['mart369.config'].sudo()._get()
        return bool(settings.enable_loyalty and config.loyalty_enabled)

    @api.model
    def _mart369_rule(self):
        return self.env['pos.loyalty.rule'].sudo().get_active_rule()

    # ------------------------------------------------------------- the card

    @api.model
    def _mart369_phone(self, partner):
        """The partner's mobile, written the way the counter stores it."""
        phone = (partner.phone or '').strip()
        if not re.sub(r'\D', '', phone):
            return ''
        from odoo.addons.pos_loyalty_card.wizard.loyalty_delete_confirm_wizard import normalize_phone
        dial, length = self.sudo()._get_loyalty_mobile_cfg()
        return normalize_phone(phone, dial, length)

    @api.model
    def _mart369_card_for(self, partner, create=False):
        """This customer's card, or an empty recordset.

        By partner first. Then by mobile number - a customer who got a card at
        the counter should find it here, not be given a second one - and the
        partner is linked when the card had none. A card that belongs to
        somebody else is never taken, even on a matching number: the number
        might have changed hands, the points did not.

        `create` makes one when there is none, and makes it silently: a card
        created active queues the counter's WhatsApp welcome, so it is created
        as a draft and switched on with a plain write, which does not.
        """
        if not partner:
            return self.browse()
        partner = partner.commercial_partner_id
        Card = self.sudo()
        card = Card.search([
            ('partner_id', '=', partner.id), ('is_deleted', '=', False),
        ], order='state asc, id', limit=1)
        if card:
            return card

        phone = self._mart369_phone(partner)
        if not phone:
            if create:
                _logger.info('mart369 loyalty: %s has no mobile number, so no card', partner.id)
            return Card.browse()

        card = Card.search([('phone', '=', phone), ('is_deleted', '=', False)], limit=1)
        if card:
            if card.partner_id and card.partner_id.commercial_partner_id != partner:
                _logger.warning('mart369 loyalty: card %s has %s but belongs to partner %s, not %s',
                                card.card_number, phone, card.partner_id.id, partner.id)
                return Card.browse()
            if not card.partner_id and create:
                # Only when writing is expected: the bill reads on a
                # read-only cursor and must not link anything.
                card.write({'partner_id': partner.id})
            return card

        if not create:
            return Card.browse()
        card = Card.create({
            'name': partner.name or phone,
            'phone': phone,
            'email': partner.email or False,
            'partner_id': partner.id,
            'state': 'draft',
        })
        card.write({'state': 'active'})
        _logger.info('mart369 loyalty: card %s made for partner %s', card.card_number, partner.id)
        return card

    # ----------------------------------------------------------- the money

    def _mart369_lock(self):
        """Take this card's row until the transaction ends, and re-read it."""
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM pos_loyalty_card WHERE id = %s FOR UPDATE', (self.id,))
        self.invalidate_recordset(['total_points'])
        return self

    def _mart369_held(self):
        """Points this customer's unpaid baskets are holding.

        Counted as still theirs: placing the order again gives them back
        first (sale_order.py `_mart369_place`), so the checkout can offer them.
        """
        self.ensure_one()
        rows = self.env['pos.loyalty.history'].sudo().search([
            ('card_id', '=', self.id), ('type', '=', 'redeemed'),
            ('sale_order_id.mart369_state', '=', 'draft'),
        ])
        return sum(rows.mapped('points'))

    def _mart369_redeemed_today(self):
        """Whether this card already spent points today - at the counter or
        online. The counter's rule (loyalty_card.py `_check_redemption_cooldown`),
        but blind to baskets that were never paid for: going back to change
        the delivery slot is not a second spend."""
        self.ensure_one()
        tz_name = self.env.user.tz or self.env.company.partner_id.tz or 'UTC'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC
        now = datetime.now(pytz.UTC).astimezone(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start.astimezone(pytz.UTC).replace(tzinfo=None)
        end_utc = (start + timedelta(days=1)).astimezone(pytz.UTC).replace(tzinfo=None)
        rows = self.env['pos.loyalty.history'].sudo().search([
            ('card_id', '=', self.id), ('type', '=', 'redeemed'),
            ('create_date', '>=', start_utc), ('create_date', '<', end_utc),
        ])
        return bool(rows.filtered(
            lambda h: not (h.sale_order_id and h.sale_order_id.mart369_state == 'draft')))

    def _mart369_write(self, points, kind, title, sub='', order=None, amount=0.0):
        """One history row. The balance is the counter's stored compute over
        these rows, so writing the row is moving the points."""
        self.ensure_one()
        points = round(points or 0.0, 2)
        if points <= 0:
            return self.env['pos.loyalty.history']
        return self.env['pos.loyalty.history'].sudo().create({
            'card_id': self.id,
            'points': points,
            'type': kind,
            'description': title,
            'mart369_title': title,
            'mart369_sub': sub or False,
            'amount': amount or 0.0,
            'sale_order_id': order.id if order else False,
        })

    # --------------------------------------------------------- for the app

    def _mart369_serialize(self, rule=None):
        self.ensure_one()
        rule = rule or self._mart369_rule()
        return {
            'number': self.card_number or '',
            'points': round(self.total_points or 0.0, 2),
            'value': rule._mart369_value(self.total_points) if rule else 0.0,
            'active': self.state == 'active',
        }
