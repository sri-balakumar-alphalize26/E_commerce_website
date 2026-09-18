"""The customer's own details.

Three things live here: the profile write the app never had, the notification
preferences it collected and threw away, and a referral code that is actually a
code rather than a rearrangement of somebody's name.

On the referral code: the app built it in the browser from the user's name -
``"Demo User"`` became ``DEMOUS369`` (AccountExtras.jsx:843). Two customers
called Priya got the same code, and either of them renaming themselves changed
the code they had already sent to their friends. Here it is allocated once,
checked for collisions, and never derived from anything the customer can edit.
"""

import secrets

from odoo import api, fields, models
from odoo.exceptions import UserError

# No I, O, 0 or 1: the code is read off a screen and typed by somebody else.
CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
CODE_BODY = 6
CODE_SUFFIX = '369'

# What the app's prefs screen collects (SEED_PREFS, accountStore.js:99).
PREF_FIELDS = ('orders', 'offers', 'wallet', 'whatsapp', 'email', 'sms')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # --------------------------------------------------------- notifications

    mart369_notify_orders = fields.Boolean(
        string='Order updates', default=True,
        help="Always on in the app: a customer cannot turn off being told where "
             "their order is.")
    mart369_notify_offers = fields.Boolean(string='Offers', default=True)
    mart369_notify_wallet = fields.Boolean(string='Wallet', default=True)
    mart369_notify_whatsapp = fields.Boolean(string='WhatsApp', default=True)
    mart369_notify_email = fields.Boolean(string='Email', default=False)
    mart369_notify_sms = fields.Boolean(string='SMS', default=True)

    mart369_read_ids = fields.Char(
        string='Read notifications', copy=False,
        help="Ids the customer has opened, comma separated. Ids rather than "
             "records because most notifications are derived from orders and "
             "have nothing of their own to flag.")
    mart369_dismissed_ids = fields.Char(string='Dismissed notifications', copy=False)

    # ------------------------------------------------------------- referrals

    mart369_referral_code = fields.Char(
        string='Referral code', copy=False, index=True, readonly=True,
        help="What this customer's friends type. Allocated once and never "
             "changes, even if they rename themselves.")
    mart369_referred_by_id = fields.Many2one(
        'res.partner', string='Referred by', copy=False, ondelete='set null')
    mart369_referral_ids = fields.One2many(
        'mart369.referral', 'partner_id', string='Invites sent', copy=False)
    mart369_referral_count = fields.Integer(
        string='Invites', compute='_compute_mart369_referrals', store=True)

    _mart369_code_uniq = models.Constraint(
        'unique (mart369_referral_code)',
        'That referral code is already in use.',
    )

    @api.depends('mart369_referral_ids')
    def _compute_mart369_referrals(self):
        for partner in self:
            partner.mart369_referral_count = len(partner.mart369_referral_ids)

    # ---------------------------------------------------------- the profile

    def _mart369_write_profile(self, values):
        """Save the three fields the app's profile form edits.

        Returns (True, None) or (False, (message, field)). The app shows
        "Saved" the moment it calls this and has no error UI at all, so a
        failure has to be reported as a real HTTP failure rather than folded
        into an ok response the screen would ignore.
        """
        self.ensure_one()
        Partner = self.env['res.partner']
        write = {}

        if 'name' in values:
            name = (values.get('name') or '').strip()
            if not name:
                return False, (self.env._('Enter your name.'), 'name')
            write['name'] = name

        if 'phone' in values:
            ok, phone = Partner._mart369_check_mobile(
                values.get('phone'), partner=self, required=False)
            if not ok:
                return False, (phone, 'phone')
            write['phone'] = phone

        email_error = None
        if 'email' in values:
            email = (values.get('email') or '').strip()
            if not email:
                return False, (self.env._('Enter your email.'), 'email')
            email_error = self._mart369_move_login(email)
            if email_error:
                return False, email_error
            write['email'] = email

        if write:
            self.sudo().write(write)
        return True, None

    def _mart369_move_login(self, email):
        """Keep `login` with `email`, or refuse.

        Signing up sets `login` to the email (auth_api.py:88), so the address on
        the profile screen *is* how this customer signs in. Letting the two drift
        would leave someone signing in with an address their own account no
        longer shows - so they move together, and a clash is refused rather than
        resolved.
        """
        self.ensure_one()
        user = self.env['res.users'].sudo().with_context(active_test=False).search(
            [('partner_id', '=', self.id)], limit=1)
        if not user:
            return None
        if (user.login or '').strip().lower() == email.lower():
            return None
        clash = self.env['res.users'].sudo().with_context(active_test=False).search_count([
            ('login', '=ilike', email), ('id', '!=', user.id),
        ])
        if clash:
            return self.env._('An account already uses that email.'), 'email'
        user.write({'login': email, 'email': email})
        return None

    # ----------------------------------------------------------- the prefs

    def _mart369_prefs(self):
        """The flat boolean map the prefs screen reads."""
        self.ensure_one()
        return {key: bool(self['mart369_notify_%s' % key]) for key in PREF_FIELDS}

    def _mart369_write_prefs(self, values):
        """Only the keys the app knows, and never `orders`.

        The app draws the orders switch locked on (PREFS, AccountExtras.jsx:763),
        so accepting a value for it would let an API caller turn off something
        the screen says cannot be turned off.
        """
        self.ensure_one()
        write = {}
        for key in PREF_FIELDS:
            if key == 'orders' or key not in values:
                continue
            write['mart369_notify_%s' % key] = bool(values[key])
        if write:
            self.sudo().write(write)
        return self._mart369_prefs()

    # ---------------------------------------------------- read / dismissed

    def _mart369_ids(self, field):
        self.ensure_one()
        raw = self[field] or ''
        return [part for part in raw.split(',') if part]

    def _mart369_add_ids(self, field, ids):
        """Remember ids without letting the column grow forever."""
        self.ensure_one()
        current = self._mart369_ids(field)
        merged = list(dict.fromkeys(current + [str(i) for i in ids if i]))
        self.sudo().write({field: ','.join(merged[-500:])})
        return merged

    # -------------------------------------------------------- the code

    def _mart369_code(self):
        """This customer's referral code, allocating one the first time."""
        self.ensure_one()
        if self.mart369_referral_code:
            return self.mart369_referral_code
        Partner = self.env['res.partner'].sudo()
        for __ in range(12):
            body = ''.join(secrets.choice(CODE_ALPHABET) for __ in range(CODE_BODY))
            code = body + CODE_SUFFIX
            if not Partner.with_context(active_test=False).search_count(
                    [('mart369_referral_code', '=', code)]):
                self.sudo().write({'mart369_referral_code': code})
                return code
        # 32^6 codes and a dozen tries: reaching here means something is wrong
        # with the random source, not that the space is full.
        raise UserError(self.env._('Could not allocate a referral code.'))

    @api.model
    def _mart369_by_code(self, code):
        code = (code or '').strip().upper()
        if not code:
            return self.browse()
        return self.sudo().search([('mart369_referral_code', '=', code)], limit=1)

    def _mart369_referral_stats(self):
        """The four numbers the referrals screen prints."""
        self.ensure_one()
        rows = self.mart369_referral_ids
        ordered = len(rows.filtered(lambda r: r.state == 'ordered'))
        joined = len(rows.filtered(lambda r: r.state != 'invited'))
        reward = self.env['mart369.referral']._mart369_reward()
        return {
            'ordered': ordered,
            'joined': joined,
            'earned': ordered * reward,
            'pending': (joined - ordered) * reward,
        }

