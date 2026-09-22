"""The numbers above 369 Mart -> Reviews, Referrals and Rewards.

Same contract as the customer, payments and orders strips: one ORM call per
screen, tiles that switch the view's own named filters on. Kept identical so the
five strips stay interchangeable.
"""

from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


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
            # The same two numbers unformatted. The backend strip prints the
            # strings above; the app console does its own formatting through
            # lib/money.js, and cannot do arithmetic on "Rs 1,200.00" or
            # reformat it for a customer in another currency.
            # float(), because sum([]) is an int and a screen that does
            # arithmetic on this should get the same type either way.
            'paid_amount': float(sum(ordered_rows.mapped('reward'))),
            'reward_amount': self._mart369_reward(),
            # The whole currency, not its name. `money()` in lib/money.js wants
            # {symbol, position, decimals, locale}; handed a bare "OMR" it finds
            # no symbol and quietly falls back to printing the number on its
            # own - so the console showed 150 where the backend strip showed
            # 150.000 ر.ع. Same helper the rewards payload uses.
            'currency': self.env['mart369.serializable']._mart369_shop_currency(),
        }

    # ------------------------------------------------- the app's console

    # Read-only. The model's ACLs give write to `sales_team.group_sale_salesman`
    # while the admin controller guards on `website.group_website_designer` -
    # two different groups, which is harmless while nothing here writes. Anybody
    # adding a write below should expect an AccessError and fix the guard rather
    # than reach for sudo.
    ADMIN_TABS = ('all', 'invited', 'joined', 'ordered')

    @api.model
    def mart369_admin_list(self, state='all', q=''):
        """The rows and the tiles in one call, filtered on the server.

        One call rather than a list plus counts: the tiles are the tabs, and
        fetching them apart is how the two end up disagreeing while a reward
        is being paid between the requests.
        """
        domain = []
        if state in ('invited', 'joined', 'ordered'):
            domain.append(('state', '=', state))
        q = (q or '').strip()
        if q:
            domain += ['|', '|',
                       ('name', 'ilike', q),
                       ('contact', 'ilike', q),
                       ('partner_id.name', 'ilike', q)]
        rows = self.search(domain, limit=200)
        return {
            'rows': [row._mart369_admin_row() for row in rows],
            'tiles': self.mart369_referral_dashboard(),
            'counts': {
                'all': self.search_count([]),
                'invited': self.search_count([('state', '=', 'invited')]),
                'joined': self.search_count([('state', '=', 'joined')]),
                'ordered': self.search_count([('state', '=', 'ordered')]),
            },
        }

    def _mart369_admin_row(self):
        self.ensure_one()
        return {
            'id': self.id,
            'friend': self.name or '',
            'contact': self.contact or '',
            'state': self.state,
            'invitedBy': self.partner_id.display_name or '',
            'inviterCode': self.partner_id.sudo().mart369_referral_code or '',
            'joinedAs': self.joined_partner_id.display_name or '',
            'order': self.order_id.name or '',
            'reward': self.reward or 0.0,
            # Formatted as well as raw: the backend desk prints it straight,
            # the app console formats the number itself through lib/money.js.
            'rewardText': self.currency_id.format(self.reward) if self.reward else '',
            # Epoch milliseconds, like `_mart369_serialize` - the console
            # formats dates itself and a naive string would be read as UTC
            # by the browser and printed five and a half hours early.
            'at': int(self.create_date.timestamp() * 1000) if self.create_date else None,
        }

    # ----------------------------------------------------------- the reward

    @api.model
    def mart369_admin_set_reward(self, amount):
        """What one successful referral pays, from now on.

        **The one deliberate sudo in this module.** The amount lives in
        `ir.config_parameter`, which only `base.group_system` may write - so
        without it the setting would be editable by nobody who actually runs
        the shop, which is the whole point of putting it on a screen. The group
        check below is the fence; exactly one parameter is elevated.

        Either group, because the two front ends are fenced differently: the
        backend desk sits behind the salesman group the model's ACLs use, and
        the app console behind the website designer group every admin
        controller in the suite checks. This is the shop-wide marketing number
        both of them show, and one place to write it is how the two stay
        agreed.

        Rewards already paid keep what they were worth - the amount is copied
        onto the row when it is paid - so this only changes what is paid next.
        """
        if not (self.env.user.has_group('sales_team.group_sale_salesman')
                or self.env.user.has_group('website.group_website_designer')):
            raise AccessError(self.env._("You do not have access to this."))
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            raise ValidationError(self.env._("Enter the reward as a number."))
        if amount < 0:
            raise ValidationError(self.env._("A reward cannot be negative."))
        self.env['ir.config_parameter'].sudo().set_param(
            'mart369_account.referral_reward', str(amount))
        return self.mart369_referral_dashboard()

    # ------------------------------------------------------------ demo data

    @api.model
    def _mart369_load_demo(self):
        """A few invites to look at, built from whatever customers exist.

        In Python rather than as records, for the reason `mart369_cart`'s deal
        demo gives: an invite needs two real partners and this module ships
        none, so an XML `ref` would tie it to whichever demo data happened to
        be installed.

        Does nothing once there is a single invite, so a shop that has started
        referring people never sprouts examples on upgrade.

        The rewarded one is paid through `_mart369_pay`, the same path a real
        first order takes, rather than having its reward written straight onto
        the row. A "Paid out" tile counting money that never reached a wallet
        is exactly the invented number these screens must not have.
        """
        if self.with_context(active_test=False).search_count([]):
            return False
        # People, not their delivery addresses: an address is a child partner
        # with its own name ("Addr A"), and an example invite from one would
        # read as nonsense. Whoever has bought most comes first, so the
        # examples hang off a customer the shop recognises.
        partners = self.env['res.partner'].search([
            ('is_company', '=', False),
            ('parent_id', '=', False),
            ('name', '!=', False),
            '|', ('customer_rank', '>', 0), ('user_ids.share', '=', True),
        ], order='customer_rank desc, id', limit=4)
        if len(partners) < 2:
            # Nobody to invite anybody. The empty state explains itself.
            return False

        inviter = partners[0]
        inviter._mart369_code()

        rows = self.create([{
            'partner_id': inviter.id,
            'name': self.env._('Meera (an example)'),
            'contact': 'meera@example.com',
            'state': 'invited',
        }, {
            'partner_id': inviter.id,
            'name': partners[1].name,
            'contact': partners[1].email or partners[1].phone or '',
            'state': 'joined',
            'joined_partner_id': partners[1].id,
        }])

        if len(partners) > 2:
            reward = self._mart369_reward()
            paid = self.create({
                'partner_id': inviter.id,
                'name': partners[2].name,
                'contact': partners[2].email or partners[2].phone or '',
                'state': 'ordered',
                'joined_partner_id': partners[2].id,
                'reward': reward,
            })
            paid._mart369_pay(reward)
            rows |= paid
        return bool(rows)


class Mart369Scratch(models.Model):
    _inherit = 'mart369.scratch'

    @api.model
    def mart369_scratch_dashboard(self):
        total = self.search_count([])
        unscratched = self.search_count([('scratched', '=', False)])
        cash = self.search([('scratched', '=', True), ('reward_type', '=', 'cash')])
        coupons = self.search_count(
            [('scratched', '=', True), ('reward_type', '=', 'coupon')])

        # Summed per currency, then converted, rather than adding the raw
        # numbers together: a card keeps the currency it was minted in, so
        # `sum(cash.mapped('amount'))` was adding rupees to dollars and
        # printing the answer with whatever symbol the company happens to use.
        company = self.env.company.currency_id
        today = fields.Date.context_today(self)
        paid = 0.0
        for currency in cash.mapped('currency_id'):
            in_this = cash.filtered(lambda c, cur=currency: c.currency_id == cur)
            paid += currency._convert(
                sum(in_this.mapped('amount')), company, self.env.company, today)

        return {
            'total': total,
            'unscratched': unscratched,
            'scratched': total - unscratched,
            'paid': company.format(paid),
            'paid_count': len(cash),
            'coupons': coupons,
            'nothing': self.search_count(
                [('scratched', '=', True), ('reward_type', '=', 'none')]),
        }
