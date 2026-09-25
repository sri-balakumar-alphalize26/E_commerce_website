"""What support needs before picking up the phone: is this customer a risk?

Four things, all on the customer's commercial partner:

* **Placed-order figures.** mart369_auth counts a customer's orders and spend
  from *confirmed* sale orders, because it cannot see the app's own states.
  But a cash-on-delivery order is placed long before anyone confirms it, so the
  list said "Orders 0" for a customer the badge said had "ordered 3 h ago".
  Here, where `mart369_state` is known, the figures count *placed* orders -
  anything past an unpaid basket and not cancelled - the same rule the badge
  and the profile use.
* **Risk.** How often they cancelled, how often the shop did, how often a
  rider was turned away at the door, how many orders came back.
* **Cash on delivery, off for one customer.** The quick-commerce answer to a
  customer who keeps refusing COD orders: the method is simply not offered.
* **Goodwill credit.** Staff put money in the wallet with a reason - one
  `reward` movement through the wallet's own writer, so it shows in the
  customer's wallet history like any other.
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

EDITOR_GROUP = 'website.group_website_designer'
REFUSED = 'Customer refused the order'
PLACED = [('mart369_state', 'not in', (False, 'draft', 'cancelled'))]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    mart369_cod_off = fields.Boolean(
        string='No cash on delivery',
        help="On: this customer is not offered cash on delivery - they pay online.")


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    def _mart369_provider_for(self, app_method, partner, amount, currency=None, order=None):
        if app_method == 'cod' and partner and partner.commercial_partner_id.mart369_cod_off:
            return self.browse()
        return super()._mart369_provider_for(app_method, partner, amount, currency=currency, order=order)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ------------------------------------------------------ placed figures

    def _compute_mart369_orders(self):
        super()._compute_mart369_orders()
        partners = self.partner_id.commercial_partner_id
        stats = {}
        if partners:
            groups = self.env['sale.order'].sudo()._read_group(
                [('partner_id', 'child_of', partners.ids)] + PLACED,
                groupby=['partner_id'],
                aggregates=['__count', 'amount_total:sum', 'mart369_placed_at:max'])
            for partner, count, total, last in groups:
                row = stats.setdefault(partner.commercial_partner_id.id, [0, 0.0, False])
                row[0] += count
                row[1] += total or 0.0
                if last and (not row[2] or last > row[2]):
                    row[2] = last
        for user in self:
            count, total, last = stats.get(user.partner_id.commercial_partner_id.id, (0, 0.0, False))
            user.mart369_order_count = count
            user.mart369_total_spent = total
            user.mart369_avg_order = total / count if count else 0.0
            user.mart369_last_order_date = last

    # ---------------------------------------------------------------- risk

    @api.model
    def _mart369_staff_check(self):
        if not self.env.user.has_group(EDITOR_GROUP):
            raise AccessError(self.env._('You do not have access to this.'))

    @api.model
    def _mart369_customer_partner(self, user_id):
        user = self.sudo().search(self._mart369_admin_base() + [('id', '=', int(user_id))], limit=1)
        if not user:
            raise UserError(self.env._('There is no such customer.'))
        return user.partner_id.commercial_partner_id

    @api.model
    def _mart369_risk(self, partner):
        Order = self.env['sale.order'].sudo()
        mine = [('partner_id', 'child_of', partner.id)]
        cancelled = Order.search(mine + [('mart369_state', '=', 'cancelled')])
        by_them = 0
        for order in cancelled:
            if order.mart369_returned:
                continue  # came back from the door - counted as returned
            # Whoever stamped the cancel: a shop account (share) is the customer.
            stamp = order.mart369_stamp_ids.filtered(lambda s: s.state == 'cancelled')[:1]
            if stamp and stamp.user_id and stamp.user_id.share:
                by_them += 1
        returned = len(cancelled.filtered('mart369_returned'))
        return {
            'placed': Order.search_count(mine + [('mart369_state', 'not in', (False, 'draft'))]),
            'delivered': Order.search_count(mine + [('mart369_state', '=', 'delivered')]),
            'cancelledByCustomer': by_them,
            'cancelledByShop': len(cancelled) - by_them - returned,
            'refused': Order.search_count(mine + [('mart369_failed_reason', '=', REFUSED)]),
            'failed': Order.search_count(mine + [('mart369_attempts', '>', 0)]),
            'returned': returned,
            'returnRequests': self.env['mart369.order.return'].sudo().search_count(
                [('partner_id', 'child_of', partner.id)]),
            'codOff': bool(partner.mart369_cod_off),
        }

    @api.model
    def _mart369_recent_placed(self, partner, limit=6):
        """The drawer's recent orders - placed ones, like every figure now."""
        orders = self.env['sale.order'].sudo().search(
            [('partner_id', 'child_of', partner.id)] + PLACED,
            order='mart369_placed_at desc, id desc', limit=limit)
        return [{
            'ref': o.mart369_ref or o.name,
            'at': int(o.mart369_placed_at.timestamp() * 1000) if o.mart369_placed_at else None,
            'total': o.currency_id.round(o.amount_total),
            'items': len(o._mart369_app_lines()),
            'method': o.mart369_method or '',
            'addressLabel': (o.partner_shipping_id.mart369_label or '')
            if o.partner_shipping_id != o.partner_id else '',
        } for o in orders]

    @api.model
    def mart369_admin_detail(self, user_id):
        row = super().mart369_admin_detail(user_id)
        if not row:
            return row
        partner = self._mart369_customer_partner(user_id)
        row['recent'] = self._mart369_recent_placed(partner)
        row['risk'] = self._mart369_risk(partner)
        return row

    @api.model
    def mart369_admin_profile(self, user_id):
        profile = super().mart369_admin_profile(user_id)
        partner = self._mart369_customer_partner(user_id)
        returns = self.env['mart369.order.return'].sudo().search(
            [('partner_id', 'child_of', partner.id)], order='id desc', limit=20)
        profile['returns'] = [r._mart369_admin_row() for r in returns]
        # `orders` on the profile is the list; the figure the list and drawer
        # show (placed, not cancelled) travels beside it.
        profile['orderCount'] = self.sudo().browse(int(user_id)).mart369_order_count
        return profile

    # ------------------------------------------------------------ writing

    @api.model
    def mart369_admin_set_cod(self, user_id, off):
        """Switch cash on delivery off (or back on) for this customer."""
        self._mart369_staff_check()
        partner = self._mart369_customer_partner(user_id)
        partner.sudo().mart369_cod_off = bool(off)
        return self._mart369_risk(partner)

    @api.model
    def mart369_admin_goodwill(self, user_id, amount, reason):
        """Put money in the customer's wallet, with a reason, as a reward."""
        self._mart369_staff_check()
        partner = self._mart369_customer_partner(user_id)
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            raise UserError(self.env._('The amount is a number.'))  # noqa: B904
        if amount <= 0:
            raise UserError(self.env._('The amount must be more than 0.'))
        reason = ' '.join(str(reason or '').split())[:120]
        if not reason:
            raise UserError(self.env._('Say why - the customer sees it in their wallet.'))
        Card = self.env['loyalty.card'].sudo()
        card = Card._mart369_wallet(partner)
        card._mart369_move(amount, 'reward', self.env._('Goodwill credit'),
                           sub=self.env._('%(reason)s · by %(who)s', reason=reason, who=self.env.user.name))
        return {'wallet': card._mart369_balance()}
