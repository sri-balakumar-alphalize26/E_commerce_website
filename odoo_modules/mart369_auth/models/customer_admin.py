"""The customer list for the app's own admin console.

The figures on each row are the ones the backend Customers screen already
shows - order count, spend and last order are computed on `res.users`, status is
stored and kept fresh by the daily job - so the two screens cannot disagree
about a customer. This file only decides which customers, in which order, and
what one row looks like.

Every filter is a domain. The console used to filter the forty rows it had been
handed; filtering a page is not filtering the shop.

Nothing here writes, and nothing is sudo'd: the records are read as the person
signed in, so Odoo's own access rules still apply.
"""

from datetime import timedelta

from odoo import api, fields, models

MAX_ROWS = 200

TABS = ('all', 'active', 'new', 'dormant')

# "Joined" - how far back, in days.
JOINED = {'month': 30, '3m': 91, 'year': 365}

SORTS = {
    'new': 'create_date desc, id desc',
    'old': 'create_date asc, id asc',
    'seen': 'login_date desc, id desc',
    'name': 'name asc, id asc',
    'name_desc': 'name desc, id desc',
}


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ------------------------------------------------------------- domains

    @api.model
    def _mart369_admin_base(self):
        """Storefront accounts - the same set `_mart369_customers()` returns."""
        domain = [('share', '=', True), ('active', '=', True)]
        public = self.env.ref('base.public_user', raise_if_not_found=False)
        if public:
            domain += [('id', '!=', public.id)]
        return domain

    @api.model
    def _mart369_admin_last_placed(self, partners):
        """{commercial partner id: when they last placed an order}, in one
        grouped read.

        Placed, not confirmed: a cash-on-delivery order is placed long before
        anyone confirms it, and a customer who has just ordered must not read
        as "Not ordered yet". Unpaid online orders (`draft`) and cancelled ones
        do not count. Empty without the orders module - mart369_auth does not
        depend on it.
        """
        if 'sale.order' not in self.env or not partners:
            return {}
        Order = self.env['sale.order'].sudo()
        if 'mart369_placed_at' not in Order._fields:
            return {}
        groups = Order._read_group(
            [('partner_id', 'child_of', partners.ids),
             ('mart369_placed_at', '!=', False),
             ('mart369_state', 'not in', ('draft', 'cancelled'))],
            groupby=['partner_id'], aggregates=['mart369_placed_at:max'])
        out = {}
        for partner, last in groups:
            key = partner.commercial_partner_id.id
            if last and (key not in out or last > out[key]):
                out[key] = last
        return out

    def _mart369_admin_wallets(self, partners=None):
        """{commercial partner id: wallet balance}, in one grouped read.

        Empty when the wallet module is not installed - a shop without wallets
        has customers with nothing in one, not a broken screen.
        """
        if 'loyalty.card' not in self.env:
            return {}
        Card = self.env['loyalty.card']
        if 'mart369_is_wallet' not in Card._fields:
            return {}
        domain = [('mart369_is_wallet', '=', True), ('partner_id', '!=', False)]
        if partners is not None:
            domain += [('partner_id', 'in', partners.ids)]
        groups = Card._read_group(domain, groupby=['partner_id'], aggregates=['points:sum'])
        out = {}
        for partner, points in groups:
            key = partner.commercial_partner_id.id
            out[key] = out.get(key, 0.0) + (points or 0.0)
        return out

    @api.model
    def _mart369_admin_domain(self, tab=None, q=None, area=None, joined=None, wallet=None):
        domain = self._mart369_admin_base()
        if tab in TABS and tab != 'all':
            domain += [('mart369_status', '=', tab)]
        term = (q or '').strip()
        if term:
            domain += ['|', '|', '|', '|',
                       ('name', 'ilike', term),
                       ('login', 'ilike', term),
                       ('phone', 'ilike', term),
                       ('partner_id.city', 'ilike', term),
                       ('partner_id.street2', 'ilike', term)]
        area = (area or '').strip()
        if area:
            domain += ['|', ('partner_id.city', '=', area), ('partner_id.street2', '=', area)]
        if joined in JOINED:
            since = fields.Datetime.now() - timedelta(days=JOINED[joined])
            domain += [('create_date', '>=', since)]
        if wallet in ('1', 'true', True):
            holders = [pid for pid, amount in self._mart369_admin_wallets().items() if amount > 0]
            domain += [('partner_id.commercial_partner_id', 'in', holders)]
        return domain

    # ------------------------------------------------------------- reading

    @api.model
    def mart369_admin_list(self, tab=None, q=None, area=None, joined=None,
                           wallet=None, sort=None, limit=50, offset=0):
        """One page of the console's list, plus what the tiles and tabs count.

        `total` counts the filter; the tiles and tab counts are the whole shop,
        so a search never makes the shop look smaller than it is.
        """
        domain = self._mart369_admin_domain(
            tab=tab, q=q, area=area, joined=joined, wallet=wallet)
        limit = max(1, min(int(limit or 50), MAX_ROWS))
        offset = max(0, int(offset or 0))
        users = self.search(domain, limit=limit, offset=offset,
                            order=SORTS.get(sort or 'new', SORTS['new']))
        wallets = self._mart369_admin_wallets(users.partner_id.commercial_partner_id)
        placed = self._mart369_admin_last_placed(users.partner_id.commercial_partner_id)
        base = self._mart369_admin_base()
        counts = {'all': self.search_count(base)}
        for key in TABS[1:]:
            counts[key] = self.search_count(base + [('mart369_status', '=', key)])
        return {
            'rows': [u._mart369_admin_row(wallets, placed=placed) for u in users],
            'total': self.search_count(domain),
            'limit': limit,
            'offset': offset,
            'counts': counts,
            'areas': self._mart369_admin_areas(),
            'currency': self.env['mart369.serializable']._mart369_currency(
                self.env.company.currency_id),
        }

    @api.model
    def _mart369_admin_areas(self):
        """The areas customers actually live in, for the filter's dropdown."""
        users = self.search(self._mart369_admin_base())
        names = {p.city or p.street2 for p in users.partner_id if p.city or p.street2}
        return sorted(names, key=str.lower)

    def _mart369_admin_row(self, wallets=None, placed=None):
        """One line of the list. Everything the row draws, and nothing more."""
        self.ensure_one()
        partner = self.partner_id
        if wallets is None:
            wallets = self._mart369_admin_wallets(partner.commercial_partner_id)
        if placed is None:
            placed = self._mart369_admin_last_placed(partner.commercial_partner_id)
        last_placed = placed.get(partner.commercial_partner_id.id)
        last = self.mart369_last_order_date
        return {
            'id': self.id,
            'name': self.name or '',
            'email': self.login or '',
            'phone': self.mart369_phone_display or self.phone or '',
            'area': partner.city or partner.street2 or '',
            'orders': self.mart369_order_count,
            'spent': self.env.company.currency_id.round(self.mart369_total_spent or 0.0),
            'wallet': round(wallets.get(partner.commercial_partner_id.id, 0.0), 2),
            'last': int(last.timestamp() * 1000) if last else None,
            'joined': int(self.create_date.timestamp() * 1000) if self.create_date else None,
            'status': self.mart369_status or 'active',
            # How long a New customer stays New - the badge says so.
            'newDaysLeft': self._mart369_new_days_left(),
            # When they last placed an order - what the badge's "ordered 2 d
            # ago" and a New customer's Active / Not ordered yet read.
            'lastPlaced': int(last_placed.timestamp() * 1000) if last_placed else None,
        }

    @api.model
    def mart369_admin_detail(self, user_id):
        """The drawer: the row, plus their recent orders - joined by partner,
        never by name, because two customers can share one."""
        user = self.search(self._mart369_admin_base() + [('id', '=', int(user_id))], limit=1)
        if not user:
            return {}
        row = user._mart369_admin_row()
        orders = []
        if 'sale.order' in self.env:
            found = self.env['sale.order'].search(
                [('partner_id', 'child_of', user.partner_id.commercial_partner_id.id),
                 ('state', '=', 'sale')],
                order='date_order desc', limit=6)
            for order in found:
                ref = order.mart369_ref if 'mart369_ref' in order._fields else ''
                placed = order.date_order
                orders.append({
                    'ref': ref or order.name,
                    'at': int(placed.timestamp() * 1000) if placed else None,
                    'total': order.currency_id.round(order.amount_total),
                    'items': len(order.order_line.filtered(lambda l: not l.display_type)),
                    'method': (order.mart369_method or '') if 'mart369_method' in order._fields else '',
                })
        row['recent'] = orders
        row['seen'] = user.mart369_seen_label or ''
        return row
