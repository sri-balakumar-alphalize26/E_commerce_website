"""Points on the bill.

`mart369.cart._mart369_bill` is the one place a basket is priced - the cart page
asks it, and placing an order asks it again and refuses an order that comes out
dearer. So spending points is priced here too, the way a coupon is, and the
order that follows carries the same number as a line (sale_order.py).

Who is asking, and whether they want to spend, arrive in the context
(`mart369_partner_id`, `mart369_use_points`): the bill's own signature has no
customer in it, because a guest can price a basket too.
"""

import math

from odoo import api, models


def _floor2(value):
    return math.floor((value or 0.0) * 100 + 1e-6) / 100


class Mart369Cart(models.AbstractModel):
    _inherit = 'mart369.cart'

    @api.model
    def _mart369_bill(self, items, coupon=None, slot_fee=0.0, address=None):
        bill = super()._mart369_bill(items, coupon=coupon, slot_fee=slot_fee, address=address)
        bill['points'] = self._mart369_points_block(bill)
        off = bill['points']['off'] if bill['points'] else 0.0
        if off:
            bill['total'] = round(max(0.0, bill['total'] - off), 2)
            bill['saved'] = round(bill['saved'] + off, 2)
        return bill

    @api.model
    def _mart369_points_block(self, bill):
        """What this customer could spend on this bill, and whether they are.

        None for a guest, or when loyalty is off. Otherwise always a block, so
        the checkout can say *why* points cannot be used rather than just not
        offering them: `reason` is one of '', 'off', 'none', 'inactive', 'min',
        'today', 'small'.
        """
        Card = self.env['pos.loyalty.card'].sudo()
        partner_id = self.env.context.get('mart369_partner_id')
        if not partner_id or not Card._mart369_enabled():
            return None
        rule = Card._mart369_rule()
        if not rule:
            return None
        partner = self.env['res.partner'].sudo().browse(partner_id).exists()
        if not partner:
            return None
        card = Card._mart369_card_for(partner)
        config = self.env['mart369.config'].sudo()._get()
        per_rupee = rule._mart369_per_rupee()
        minimum = rule.min_redeem_points or 0.0
        # The counter treats an unset maximum as the whole order.
        max_percent = rule.max_redeem_percent or 100.0

        balance = round(card.total_points + card._mart369_held(), 2) if card else 0.0
        before = bill['total']
        # No more than the rule's share of the order, and never below zero.
        cap_value = _floor2(min(before, before * max_percent / 100.0))
        usable = _floor2(min(balance, cap_value * per_rupee))

        reason = ''
        if not config.loyalty_redeem:
            reason = 'off'
        elif not card:
            reason = 'none'
        elif card.state != 'active':
            reason = 'inactive'
        elif card._mart369_redeemed_today():
            # Before the balance: somebody who has just spent their points
            # wants to hear "tomorrow", not "you need more".
            reason = 'today'
        elif balance < minimum or balance <= 0:
            reason = 'min'
        elif usable < minimum or usable <= 0:
            # Enough points, but this order is too small to take them.
            reason = 'small'
        if reason:
            usable = 0.0
        value = min(rule._mart369_value(usable), before)

        applied = bool(usable and self.env.context.get('mart369_use_points'))
        off = value if applied else 0.0
        # What the order earns: the items, less the coupon and the points,
        # without delivery - the same base sale_order.py earns on.
        base = max(0.0, bill['items'] - (bill.get('couponOff') or 0.0) - off)
        return {
            'card': bool(card),
            'number': card.card_number or '' if card else '',
            'balance': balance,
            'balanceValue': rule._mart369_value(balance),
            'usable': usable,
            'usableValue': value,
            'applied': applied,
            'spend': usable if applied else 0.0,
            'off': off,
            'reason': reason,
            'min': minimum,
            'perRupee': per_rupee,
            'maxPercent': max_percent,
            'earn': rule._mart369_points_for(base) if config.loyalty_enabled else 0.0,
            'earnOn': config.loyalty_earn_on or 'delivered',
        }
