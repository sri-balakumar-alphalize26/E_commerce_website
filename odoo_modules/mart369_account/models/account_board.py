"""The numbers above 369 Mart -> Reviews, Referrals and Rewards.

Same contract as the customer, payments and orders strips: one ORM call per
screen, tiles that switch the view's own named filters on. Kept identical so the
five strips stay interchangeable.
"""

from datetime import timedelta

from odoo import api, fields, models


class RatingRating(models.Model):
    _inherit = 'rating.rating'

    @api.model
    def mart369_review_dashboard(self):
        """Everything the reviews strip prints."""
        today = fields.Date.context_today(self)
        mine = [('res_model', '=', 'product.template'), ('consumed', '=', True)]

        all_reviews = self.search(mine)
        scores = all_reviews.mapped('rating')
        average = round(sum(scores) / len(scores), 1) if scores else 0.0
        unhappy = self.search_count(mine + [('rating', '<=', 2)])
        verified = self.search_count(mine + [('mart369_verified', '=', True)])
        total = len(all_reviews)

        return {
            'total': total,
            'average': average,
            'stars': int(round(average)),
            'unhappy': unhappy,
            'verified': verified,
            'verified_pct': round(verified * 100 / total) if total else 0,
            'with_photos': self.search_count(mine + [('mart369_photos', '>', 0)]),
            # The same three the console's tabs count, so the two screens
            # never disagree about how much is waiting.
            'pending': self.search_count(mine + [('mart369_state', '=', 'pending')]),
            'published': self.search_count(mine + [('mart369_state', '=', 'published')]),
            'hidden': self.search_count(mine + [('mart369_state', '=', 'hidden')]),
            'written': self._mart369_review_bars(today),
        }

    @api.model
    def _mart369_review_bars(self, days_back, days=14):
        """Reviews a day for the last fortnight, for the sparkline."""
        since = fields.Datetime.to_datetime(days_back - timedelta(days=days - 1))
        rows = self._read_group(
            [('res_model', '=', 'product.template'), ('consumed', '=', True),
             ('create_date', '>=', since)],
            groupby=['create_date:day'], aggregates=['__count'])
        counted = {}
        for when, count in rows:
            if when:
                counted[fields.Date.to_date(when)] = count
        out = []
        for offset in range(days - 1, -1, -1):
            day = days_back - timedelta(days=offset)
            out.append({'day': day.strftime('%d %b'), 'count': counted.get(day, 0)})
        return out


class Mart369Referral(models.Model):
    _inherit = 'mart369.referral'

    @api.model
    def mart369_referral_dashboard(self):
        currency = self.env.company.currency_id
        invited = self.search_count([('state', '=', 'invited')])
        joined = self.search_count([('state', '=', 'joined')])
        ordered_rows = self.search([('state', '=', 'ordered')])
        total = invited + joined + len(ordered_rows)
        return {
            'invited': invited,
            'joined': joined,
            'ordered': len(ordered_rows),
            'total': total,
            # Of everyone invited, how many went on to buy something. The number
            # that says whether referrals are worth running at all.
            'conversion': round(len(ordered_rows) * 100 / total) if total else 0,
            'paid': currency.format(sum(ordered_rows.mapped('reward'))),
            'reward': currency.format(self._mart369_reward()),
        }


class Mart369Scratch(models.Model):
    _inherit = 'mart369.scratch'

    @api.model
    def mart369_scratch_dashboard(self):
        currency = self.env.company.currency_id
        total = self.search_count([])
        unscratched = self.search_count([('scratched', '=', False)])
        cash = self.search([('scratched', '=', True), ('reward_type', '=', 'cash')])
        coupons = self.search_count(
            [('scratched', '=', True), ('reward_type', '=', 'coupon')])
        return {
            'total': total,
            'unscratched': unscratched,
            'scratched': total - unscratched,
            'paid': currency.format(sum(cash.mapped('amount'))),
            'paid_count': len(cash),
            'coupons': coupons,
            'nothing': self.search_count(
                [('scratched', '=', True), ('reward_type', '=', 'none')]),
        }
