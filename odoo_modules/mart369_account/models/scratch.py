"""Scratch cards.

The app shipped four of these as seed data and had no code path that ever made
a fifth (accountStore.js:75-83). Orders never minted one, so a customer's
rewards screen was the same four cards forever, and scratching one moved a
number in localStorage.

Here an order mints a card when it is delivered, and scratching it is a server
action that really pays into the 369 Wallet - through the same
`loyalty.card._mart369_move()` that mart369_order uses for refunds, so wallet
money has exactly one way in and out.
"""

import secrets

from odoo import api, fields, models
from odoo.exceptions import UserError

REWARD_CHOICES = [
    ('cash', 'Wallet cash'),
    ('coupon', 'Coupon'),
    ('none', 'Better luck next time'),
]

# What a delivered order can win, and how often. Deliberately mostly nothing:
# a scratch card that always pays is a discount with extra steps.
DEFAULT_ODDS = (
    ('none', 55),
    ('cash', 35),
    ('coupon', 10),
)
CASH_AMOUNTS = (10.0, 20.0, 25.0, 50.0)

ODDS_PARAM = 'mart369_account.scratch_cash_odds'


class Mart369Scratch(models.Model):
    _name = 'mart369.scratch'
    _description = '369 Mart Scratch Card'
    _order = 'create_date desc, id desc'
    _rec_name = 'origin'

    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, ondelete='cascade', index=True)
    origin = fields.Char(
        string='From', required=True,
        help="Where the card came from, as the app prints it - e.g. "
             "Order #369M-9001.")
    order_id = fields.Many2one('sale.order', string='Order', ondelete='set null')

    reward_type = fields.Selection(
        REWARD_CHOICES, string='Reward', required=True, default='none')
    amount = fields.Float(string='Amount', help="For a cash reward.")
    coupon_id = fields.Many2one('mart369.coupon', string='Coupon', ondelete='set null')

    scratched = fields.Boolean(string='Scratched', default=False, copy=False)
    scratched_at = fields.Datetime(string='Scratched at', copy=False, readonly=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)

    _order_uniq = models.Constraint(
        'unique (order_id)',
        'That order has already produced a scratch card.',
    )

    # ------------------------------------------------------------- minting

    @api.model
    def _mart369_mint_for_order(self, order):
        """One card per delivered order, decided here rather than in a browser."""
        if not order or not order.partner_id:
            return self.browse()
        existing = self.sudo().search([('order_id', '=', order.id)], limit=1)
        if existing:
            return existing
        values = self._mart369_roll()
        values.update({
            'partner_id': order.partner_id.id,
            'order_id': order.id,
            'origin': self.env._('Order #%s', order.mart369_ref or order.name),
        })
        return self.sudo().create(values)

    @api.model
    def _mart369_roll(self):
        """What this card is worth. Decided at minting, not at scratching, so
        the prize cannot change depending on when somebody looks at it."""
        roll = secrets.randbelow(100)
        running = 0
        picked = 'none'
        for kind, weight in DEFAULT_ODDS:
            running += weight
            if roll < running:
                picked = kind
                break
        if picked == 'cash':
            return {'reward_type': 'cash',
                    'amount': CASH_AMOUNTS[secrets.randbelow(len(CASH_AMOUNTS))]}
        if picked == 'coupon':
            coupon = self.env['mart369.coupon'].sudo().search(
                [('active', '=', True)], limit=1, order='sequence, id')
            if coupon:
                return {'reward_type': 'coupon', 'coupon_id': coupon.id}
        return {'reward_type': 'none'}

    # ---------------------------------------------------------- scratching

    def _mart369_scratch(self):
        """Reveal it, and pay it. Once."""
        self.ensure_one()
        if self.scratched:
            # Not an error: the app reveals optimistically and may ask twice.
            return self
        self.sudo().write({'scratched': True, 'scratched_at': fields.Datetime.now()})
        if self.reward_type == 'cash' and self.amount:
            card = self.env['loyalty.card'].sudo()._mart369_wallet(self.partner_id)
            if not card:
                raise UserError(self.env._('This account has no 369 Wallet yet.'))
            card._mart369_move(
                self.amount, 'reward', self.env._('Scratch card reward'),
                sub=self.env._('From %s', (self.origin or '').lower()))
        return self

    # --------------------------------------------------------- serializing

    def _mart369_serialize(self):
        """One card of the app's `369mart.rewards.scratch` array."""
        self.ensure_one()
        reward = {'type': self.reward_type}
        if self.reward_type == 'cash':
            reward['amount'] = self.currency_id.round(self.amount or 0.0)
        elif self.reward_type == 'coupon' and self.coupon_id:
            reward['code'] = self.coupon_id.code
            reward['title'] = self.coupon_id.title
        return {
            'id': str(self.id),
            'from': self.origin or '',
            'reward': reward,
            'scratched': bool(self.scratched),
            'at': int(self.create_date.timestamp() * 1000) if self.create_date else None,
        }

    @api.model
    def _mart369_rewards_for(self, partner):
        """The whole rewards payload: the cards, and the coupon codes won."""
        cards = self.sudo().search([('partner_id', '=', partner.id)])
        won = cards.filtered(
            lambda c: c.scratched and c.reward_type == 'coupon' and c.coupon_id)
        return {
            'scratch': [card._mart369_serialize() for card in cards],
            'won': list(dict.fromkeys(won.mapped('coupon_id.code'))),
        }
