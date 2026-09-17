"""Name-or-email sign in, and the small profile the storefront shows.

``res.users.login`` must be unique, so it holds the email. The full name is
``name``. A customer may still type their name to sign in: if exactly one
customer account carries that name we use its login; if several do, the
caller tells them to use their email instead.
"""

from odoo import api, fields, models

AMBIGUOUS = object()


class ResUsers(models.Model):
    _inherit = 'res.users'

    mart369_password_hash = fields.Char(
        string='Password (hash)',
        compute='_compute_mart369_password_hash',
        groups='base.group_system',
        help="Odoo stores only a fingerprint of the password, never the password "
             "itself, and a fingerprint cannot be turned back into one. Shown for "
             "support checks only - use Change Password to set a new one.")

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
