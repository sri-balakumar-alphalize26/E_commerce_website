"""Name-or-email sign in, the small profile the storefront shows, and the
facts the 369 Mart -> Customers screen shows about each account.

``res.users.login`` must be unique, so it holds the email. The full name is
``name``. A customer may still type their name to sign in: if exactly one
customer account carries that name we use its login; if several do, the
caller tells them to use their email instead.
"""

from datetime import timedelta

import phonenumbers
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

AMBIGUOUS = object()

NEW_DAYS = 7        # signed up this recently -> "New"
DORMANT_DAYS = 60   # no sign-in for this long -> "Dormant"

STATUSES = [
    ('new', 'New'),
    ('active', 'Active'),
    ('dormant', 'Dormant'),
    ('archived', 'Archived'),
]


class ResUsers(models.Model):
    _inherit = 'res.users'

    mart369_password_hash = fields.Char(
        string='Password (hash)',
        compute='_compute_mart369_password_hash',
        groups='base.group_system',
        help="Odoo stores only a fingerprint of the password, never the password "
             "itself, and a fingerprint cannot be turned back into one. Shown for "
             "support checks only - use Change Password to set a new one.")

    # Stored so the list can filter on it and the board can group by it. It
    # depends on today's date, so a daily job and every sign-in refresh it.
    mart369_status = fields.Selection(
        STATUSES, string='Customer status', default='new', index=True, copy=False,
        group_expand='_mart369_expand_status',
        help="New: signed up in the last 7 days. Dormant: no sign-in for 60 days. "
             "Archived: sign-in blocked. Everyone else is Active.")

    mart369_currency_id = fields.Many2one(
        'res.currency', compute='_compute_mart369_orders', string='Order currency')
    mart369_order_count = fields.Integer(compute='_compute_mart369_orders', string='Orders')
    mart369_total_spent = fields.Monetary(
        compute='_compute_mart369_orders', currency_field='mart369_currency_id', string='Total spent')
    mart369_avg_order = fields.Monetary(
        compute='_compute_mart369_orders', currency_field='mart369_currency_id', string='Average order')
    mart369_last_order_date = fields.Datetime(compute='_compute_mart369_orders', string='Last order')
    mart369_address_count = fields.Integer(compute='_compute_mart369_orders', string='Addresses')

    mart369_country_code = fields.Char(compute='_compute_mart369_contact', string='Country code')
    mart369_phone_ok = fields.Boolean(compute='_compute_mart369_contact', string='Mobile checked')
    mart369_phone_display = fields.Char(compute='_compute_mart369_contact', string='Mobile number')
    mart369_seen_label = fields.Char(compute='_compute_mart369_contact', string='Last seen')
    mart369_since_label = fields.Char(compute='_compute_mart369_contact', string='Customer for')
    mart369_timeline = fields.Html(
        compute='_compute_mart369_timeline', sanitize=False, string='Activity')

    # ------------------------------------------------------------ password

    def _compute_mart369_password_hash(self):
        """``password`` computes to an empty string by design, so the stored
        hash has to be read straight from the column."""
        for user in self:
            user.mart369_password_hash = False
        stored = self.filtered('id')
        if not stored:
            return
        self.env.cr.execute(
            'SELECT id, password FROM res_users WHERE id IN %s', (tuple(stored.ids),))
        found = dict(self.env.cr.fetchall())
        for user in stored:
            user.mart369_password_hash = found.get(user.id) or ''

    # -------------------------------------------------------------- status

    @api.model
    def _mart369_expand_status(self, values, domain):
        """Always show the three live columns on the board, even when empty."""
        keys = ['new', 'active', 'dormant']
        if 'archived' in (values or []):
            keys.append('archived')
        return keys

    def _mart369_status_for(self, now):
        self.ensure_one()
        if not self.active:
            return 'archived'
        if self.create_date and self.create_date >= now - timedelta(days=NEW_DAYS):
            return 'new'
        seen = self.login_date or self.create_date
        if seen and seen < now - timedelta(days=DORMANT_DAYS):
            return 'dormant'
        return 'active'

    def _mart369_refresh_status(self):
        """Recompute the status, writing only the accounts that changed."""
        now = fields.Datetime.now()
        changed = {}
        for user in self.with_context(active_test=False).filtered('share'):
            status = user._mart369_status_for(now)
            if user.mart369_status != status:
                changed.setdefault(status, self.browse())
                changed[status] |= user
        for status, users in changed.items():
            users.sudo().with_context(mart369_status_refresh=True).write({'mart369_status': status})
        return True

    @api.model
    def _cron_mart369_refresh_status(self):
        users = self.sudo().with_context(active_test=False).search([('share', '=', True)])
        users._mart369_refresh_status()

    @api.model
    def _update_last_login(self):
        super()._update_last_login()
        user = self.env.user
        if user and user.share and not user._is_public():
            user.sudo()._mart369_refresh_status()

    def write(self, vals):
        if 'phone' in vals and vals['phone'] and not self.env.context.get('mart369_skip_phone'):
            for user in self.filtered('share'):
                ok, result = self.env['res.partner']._mart369_check_mobile(
                    vals['phone'], partner=user.partner_id, required=False)
                if not ok:
                    raise ValidationError(result)
                if len(self) == 1:
                    vals = dict(vals, phone=result)
        res = super().write(vals)
        if 'active' in vals and not self.env.context.get('mart369_status_refresh'):
            self._mart369_refresh_status()
        return res

    # ------------------------------------------------------------- figures

    @api.depends('partner_id')
    def _compute_mart369_orders(self):
        currency = self.env.company.currency_id
        stats = {}
        partners = self.partner_id.commercial_partner_id
        if partners and 'sale.order' in self.env:
            groups = self.env['sale.order'].sudo()._read_group(
                [('partner_id', 'child_of', partners.ids), ('state', '=', 'sale')],
                groupby=['partner_id'],
                aggregates=['__count', 'amount_total:sum', 'date_order:max'],
            )
            for partner, count, total, last in groups:
                key = partner.commercial_partner_id.id
                row = stats.setdefault(key, [0, 0.0, False])
                row[0] += count
                row[1] += total or 0.0
                if last and (not row[2] or last > row[2]):
                    row[2] = last
        for user in self:
            count, total, last = stats.get(user.partner_id.commercial_partner_id.id, (0, 0.0, False))
            user.mart369_currency_id = currency
            user.mart369_order_count = count
            user.mart369_total_spent = total
            user.mart369_avg_order = total / count if count else 0.0
            user.mart369_last_order_date = last
            partner = user.partner_id.sudo()
            user.mart369_address_count = len(partner.child_ids.filtered(
                lambda p: p.type in ('delivery', 'other'))) + (1 if partner.street else 0)

    @api.depends('phone', 'country_id', 'login_date', 'create_date')
    def _compute_mart369_contact(self):
        Partner = self.env['res.partner']
        now = fields.Datetime.now()
        for user in self:
            user.mart369_country_code = Partner._mart369_region(user.partner_id)
            user.mart369_phone_ok = bool(user.phone) and Partner._mart369_check_mobile(
                user.phone, partner=user.partner_id, required=False)[0]
            user.mart369_phone_display = user._mart369_pretty_phone()
            user.mart369_seen_label = user._mart369_ago(user.login_date, now) if user.login_date else _('Never signed in')
            user.mart369_since_label = user._mart369_ago(user.create_date, now) if user.create_date else ''

    @api.depends('create_date', 'login_date', 'phone')
    def _compute_mart369_timeline(self):
        for user in self:
            user.mart369_timeline = user._mart369_timeline_html() if user.id else False

    def _mart369_timeline_html(self):
        """Signup, sign-ins and orders, newest first, as a small list."""
        self.ensure_one()
        events = []
        if self.create_date:
            events.append((self.create_date, 'user-plus', 'blue', _('Created an account'),
                           _('Signed up on the storefront with %s', self.login)))
        logs = self.env['res.users.log'].sudo().search(
            [('create_uid', '=', self.id)], order='id desc', limit=5)
        for log in logs:
            events.append((log.create_date, 'sign-in', 'green', _('Signed in'), _('Storefront session')))
        if 'sale.order' in self.env:
            orders = self.env['sale.order'].sudo().search(
                [('partner_id', 'child_of', self.partner_id.commercial_partner_id.id)],
                order='date_order desc', limit=6)
            states = dict(orders._fields['state']._description_selection(self.env))
            for order in orders:
                amount = order.currency_id.format(order.amount_total) if order.currency_id else order.amount_total
                events.append((order.date_order, 'shopping-bag', 'orange',
                               _('Order %s', order.name), '%s · %s' % (amount, states.get(order.state, ''))))
        events.sort(key=lambda e: e[0], reverse=True)
        if not events:
            return Markup('<p class="text-muted">%s</p>') % _('Nothing yet.')
        rows = Markup('').join(
            Markup('<li class="o_mart369_tl_item">'
                   '<span class="o_mart369_tile o_mart369_tile_%s"><i class="fa fa-%s"></i></span>'
                   '<div><b>%s</b><small>%s</small></div>'
                   '<time>%s</time></li>') % (
                tone, icon, title, sub,
                fields.Datetime.context_timestamp(self, when).strftime('%d %b, %H:%M'))
            for when, icon, tone, title, sub in events[:12])
        return Markup('<ol class="o_mart369_timeline">%s</ol>') % rows

    # ------------------------------------------------------------ dashboard

    @api.model
    def mart369_customer_dashboard(self):
        """Numbers for the strip above the Customers list and board."""
        now = fields.Datetime.now()
        Users = self.sudo().with_context(active_test=False)
        public = self.env.ref('base.public_user', raise_if_not_found=False)
        base = [('share', '=', True)] + ([('id', '!=', public.id)] if public else [])
        live = Users.search(base + [('active', '=', True)])
        archived = Users.search_count(base + [('active', '=', False)])
        new_week = live.filtered(lambda u: u.create_date and u.create_date >= now - timedelta(days=NEW_DAYS))
        with_mobile = live.filtered('phone')
        ordered = 0
        if live and 'sale.order' in self.env:
            partners = self.env['sale.order'].sudo()._read_group(
                [('partner_id', 'child_of', live.partner_id.commercial_partner_id.ids),
                 ('state', '=', 'sale'), ('date_order', '>=', now - timedelta(days=30))],
                groupby=['partner_id'], aggregates=['__count'])
            ordered = len({p.commercial_partner_id.id for p, __ in partners})
        # sign-ups per day over the last 14 days, oldest first
        today = fields.Date.context_today(self)
        start = today - timedelta(days=13)
        per_day = {start + timedelta(days=i): 0 for i in range(14)}
        for user in live:
            if user.create_date:
                day = fields.Datetime.context_timestamp(self, user.create_date).date()
                if day in per_day:
                    per_day[day] += 1
        total = len(live)
        return {
            'total': total,
            'archived': archived,
            'new_week': len(new_week),
            'dormant': len(live.filtered(lambda u: u.mart369_status == 'dormant')),
            'ordered_30': ordered,
            'ordered_pct': round(ordered * 100 / total) if total else 0,
            'with_mobile': len(with_mobile),
            'mobile_pct': round(len(with_mobile) * 100 / total) if total else 0,
            'signups': [{'day': d.strftime('%d %b'), 'count': c} for d, c in per_day.items()],
        }

    # -------------------------------------------------------------- buttons

    def action_mart369_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_orders')
        action.update({
            'name': _('Orders of %s', self.name),
            'domain': [('partner_id', 'child_of', self.partner_id.commercial_partner_id.id)],
            'context': {'default_partner_id': self.partner_id.id, 'create': False},
        })
        return action

    def action_mart369_change_password(self):
        action = self.env['ir.actions.act_window']._for_xml_id('base.change_password_wizard_action')
        action['context'] = {'active_model': 'res.users', 'active_ids': self.ids, 'active_id': self.id}
        return action

    def _mart369_pretty_phone(self):
        """+919847021536 -> '+91 98470 21536', as people write it."""
        number = (self.phone or '').strip()
        if not number:
            return ''
        try:
            parsed = phonenumbers.parse(number, self.env['res.partner']._mart369_region(self.partner_id))
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        except phonenumbers.NumberParseException:
            return number

    def _mart369_ago(self, when, now):
        days = (now.date() - when.date()).days
        if days <= 0:
            return self.env._('Today')
        if days == 1:
            return self.env._('Yesterday')
        if days < 30:
            return self.env._('%s days ago', days)
        if days < 365:
            months = days // 30
            return self.env._('1 month ago') if months == 1 else self.env._('%s months ago', months)
        years = days // 365
        return self.env._('1 year ago') if years == 1 else self.env._('%s years ago', years)

    # ------------------------------------------------------------- sign in

    @api.model
    def _mart369_customers(self):
        """Storefront accounts: portal users, minus Odoo's own public user."""
        users = self.sudo().search([('share', '=', True), ('active', '=', True)])
        public = self.env.ref('base.public_user', raise_if_not_found=False)
        return users - public if public else users

    @api.model
    def _mart369_resolve_login(self, identifier):
        """Turn what the customer typed into an Odoo login.

        Returns the login, ``None`` for an empty value, or ``AMBIGUOUS`` when
        the name matches more than one account.
        """
        ident = (identifier or '').strip()
        if not ident:
            return None
        if '@' in ident:
            return ident
        matches = self._mart369_customers().filtered(
            lambda u: (u.name or '').strip().lower() == ident.lower())
        if len(matches) == 1:
            return matches.login
        if len(matches) > 1:
            return AMBIGUOUS
        # No such name: hand the raw value on so authenticate() fails normally.
        return ident

    def _mart369_profile(self):
        self.ensure_one()
        partner = self.partner_id
        return {
            'ok': True,
            'name': self.name,
            'email': self.email or self.login,
            'phone': partner.phone or '',
            'partner_id': partner.id,
        }

