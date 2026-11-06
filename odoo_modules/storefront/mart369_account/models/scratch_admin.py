"""What the app's own admin console reads, and what the rewards desk draws.

A scratch card is money. Scratching one credits the 369 Wallet out of the
shop's pocket, so the staff screens built on this are **read-only**: they
answer "what have we paid out, and what is still waiting to be opened", and
there is deliberately nothing here that mints, edits or voids a card. A screen
that can create a prize is a screen that can quietly pay somebody.

Two things kept apart on purpose.

**The shopper's serializer is not widened.** `_mart369_serialize()` is what a
customer's own rewards page receives. Growing it to carry the customer's name
and which order it came from is how one staff screen ends up leaking the next
customer's. Staff get their own shape, built here.

**Money is never added across currencies.** A card keeps the currency it was
minted in, so a prize already promised cannot be revalued by a later change of
company currency. Totals are therefore summed per currency and converted once,
and the payload carries the number *and* its currency rather than a string -
the console formats through lib/money.js and cannot do arithmetic on "₹1,200".
"""

from odoo import api, fields, models

# Which cards each tab is asking for. 'unscratched' is the one the screen
# opens on: prizes the shop has committed to and nobody has opened yet.
TABS = {
    'unscratched': [('scratched', '=', False)],
    'cash': [('scratched', '=', True), ('reward_type', '=', 'cash')],
    'coupon': [('scratched', '=', True), ('reward_type', '=', 'coupon')],
    'nothing': [('scratched', '=', True), ('reward_type', '=', 'none')],
    'all': [],
}

MAX_ROWS = 100


class Mart369ScratchAdmin(models.Model):
    _inherit = 'mart369.scratch'

    # ------------------------------------------------------------- the money

    @api.model
    def _mart369_paid_in_company(self, cards):
        """What a set of cash cards comes to, in the company's currency.

        Summed per currency and converted once. Adding the raw amounts would
        put rupees and dollars in the same total and print the answer with
        whatever symbol the company happens to use.
        """
        company = self.env.company.currency_id
        today = fields.Date.context_today(self)
        total = 0.0
        for currency in cards.mapped('currency_id'):
            mine = cards.filtered(lambda c, cur=currency: c.currency_id == cur)
            total += currency._convert(
                sum(mine.mapped('amount')), company, self.env.company, today)
        return company.round(total)

    # --------------------------------------------------------- serializing

    def _mart369_admin_row(self):
        """One card as the staff screens draw it."""
        self.ensure_one()
        return {
            'id': self.id,
            'customer': self.partner_id.display_name or 'Someone',
            'origin': self.origin or '',
            'order': self.order_id.mart369_ref or None,
            'reward': self.reward_type,
            # The number and its currency travel together, so neither screen
            # has to guess which one a prize was promised in.
            'amount': self.currency_id.round(self.amount or 0.0),
            'currency': self.currency_id.name or '',
            'coupon': self.coupon_id.code or None,
            'scratched': bool(self.scratched),
            'mintedAt': int(self.create_date.timestamp() * 1000) if self.create_date else None,
            'scratchedAt': int(self.scratched_at.timestamp() * 1000) if self.scratched_at else None,
        }

    # ------------------------------------------------------------ reading

    @api.model
    def _mart369_admin_domain(self, tab=None, q=None):
        domain = list(TABS.get(tab or 'unscratched', TABS['unscratched']))
        term = (q or '').strip()
        if term:
            domain += ['|', ('partner_id.name', 'ilike', term),
                       ('origin', 'ilike', term)]
        return domain

    @api.model
    def mart369_admin_list(self, tab=None, q=None, limit=30, offset=0):
        """One page of the cards, and the tile counts above them."""
        domain = self._mart369_admin_domain(tab=tab, q=q)
        limit = max(1, min(int(limit or 30), MAX_ROWS))
        offset = max(0, int(offset or 0))
        cards = self.search(domain, limit=limit, offset=offset,
                            order='create_date desc, id desc')
        payload = self.mart369_admin_counts()
        payload.update({
            'cards': [c._mart369_admin_row() for c in cards],
            'total': self.search_count(domain),
            'limit': limit,
            'offset': offset,
        })
        return payload

    @api.model
    def mart369_admin_counts(self):
        """The tiles, and the number on each tab.

        `search_count` for the tallies - the sidebar badge asks every minute
        and wants numbers, not cards. The payout is the one thing that has to
        read rows, because it is a sum.
        """
        counts = {key: self.search_count(where) for key, where in TABS.items()}
        paid_cards = self.search(TABS['cash'])
        shop = self.env['mart369.serializable']._mart369_shop_currency()
        return {
            'counts': counts,
            # The raw number, so the console can format it and the desk can
            # too, each in its own way. Never a pre-formatted string.
            'paidAmount': self._mart369_paid_in_company(paid_cards),
            'paidCount': len(paid_cards),
            'currency': shop,
        }
