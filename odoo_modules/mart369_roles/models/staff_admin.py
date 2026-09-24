"""Staff & roles, for the 369 Mart page (Odoo desk and the app's console).

The same thing the user form's Role line does, in one place the Owner can run
the whole team from: who works here, their role, the Accountant and Rider
ticks, and which shops (companies) they work in.

- **Owner only.** Every method checks it and raises otherwise - roles are who
  may touch money and settings, so nobody below Owner may hand them out.
- **Writes groups exactly like the form.** `_mart369_role_groups` is the one
  place that turns (role, accountant, rider) into groups; the form's onchange
  uses the same list of groups, so the two can never set different rights.
- **There is always an Owner.** The last one cannot be moved down, otherwise
  nobody could ever change a role again.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .res_users import CHAIN

ROLES = ('user', 'packer', 'manager', 'owner')

# Said on the page under the dropdown - the same words as the form's help.
ROLE_HELP = {
    'user': "An Odoo login with no 369 Mart screens.",
    'packer': "Packs orders: sees what to pack and marks it packed.",
    'manager': "Runs the shop day to day and approves sellers' products.",
    'owner': "Everything: payments, store details, staff and Odoo settings.",
}


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ------------------------------------------------------------- the fence

    @api.model
    def _mart369_check_owner(self):
        if self.env.su:
            return  # server-side code (installs, crons), never a browser request
        if not self.env.user.has_group('mart369_roles.group_owner'):
            raise AccessError(_("Only the Owner can change staff and roles."))

    # --------------------------------------------------------------- groups

    def _mart369_role_groups(self, role, accountant, rider):
        """Write the groups for this role on these users, the form's way."""
        chain = {key: self.env.ref(xmlid) for key, xmlid in CHAIN}
        accountant_g = self.env.ref('mart369_roles.group_accountant')
        rider_g = self.env.ref('mart369_roles.group_rider')
        admin = self.env.ref('base.group_system')
        internal = self.env.ref('base.group_user')
        for user in self:
            ops = [(3, g.id) for g in chain.values()]
            ops += [(3, admin.id), (3, accountant_g.id), (3, rider_g.id), (4, internal.id)]
            if role in chain:
                ops.append((4, chain[role].id))
            if accountant:
                ops.append((4, accountant_g.id))
            if rider:
                ops.append((4, rider_g.id))
            user.write({'group_ids': ops})

    # -------------------------------------------------------------- reading

    def _mart369_staff_row(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name or '',
            'email': self.login or '',
            'role': self.mart369_role or 'user',
            'accountant': bool(self.mart369_accountant),
            'rider': bool(self.mart369_rider),
            'companies': [{'id': c.id, 'name': c.name} for c in self.company_ids],
            'lastSeen': int(self.login_date.timestamp() * 1000) if self.login_date else None,
            'invited': not self.login_date,
            'me': self.id == self.env.uid,
        }

    @api.model
    def mart369_staff_list(self, q=None):
        """Everyone internal, with their role - Owner only."""
        self._mart369_check_owner()
        domain = [('share', '=', False)]
        term = (q or '').strip()
        if term:
            domain += ['|', ('name', 'ilike', term), ('login', 'ilike', term)]
        users = self.search(domain, order='name')
        counts = {key: 0 for key in ROLES}
        for user in users:
            counts[user.mart369_role or 'user'] += 1
        return {
            'rows': [u._mart369_staff_row() for u in users],
            'counts': counts,
            'companies': [{'id': c.id, 'name': c.name}
                          for c in self.env['res.company'].search([])],
            'help': ROLE_HELP,
        }

    # -------------------------------------------------------------- writing

    @api.model
    def mart369_staff_set(self, user_id, role, accountant=False, rider=False, company_ids=None):
        """Change one person's role, ticks and shops. Returns their new row."""
        self._mart369_check_owner()
        if role not in ROLES:
            raise UserError(_("Pick a role: User, Packer, Manager or Owner."))
        user = self.browse(int(user_id)).exists()
        if not user or user.share:
            raise UserError(_("That person is not on the staff."))
        owner = self.env.ref('mart369_roles.group_owner')
        if role != 'owner' and user in owner.all_user_ids:
            others = owner.all_user_ids.filtered(lambda u: not u.share and u.active) - user
            if not others:
                raise UserError(_(
                    "%s is the only Owner. Make someone else Owner first, "
                    "otherwise nobody could change roles any more.", user.name))
        user.sudo()._mart369_role_groups(role, accountant, rider)
        if company_ids is not None:
            ids = [int(i) for i in company_ids]
            if not ids:
                raise UserError(_("Pick at least one shop."))
            vals = {'company_ids': [(6, 0, ids)]}
            if user.company_id.id not in ids:
                vals['company_id'] = ids[0]
            user.sudo().write(vals)
        return user._mart369_staff_row()

    @api.model
    def mart369_staff_invite(self, name, email, role='user', accountant=False, rider=False):
        """Add a new staff member and send Odoo's invitation email."""
        self._mart369_check_owner()
        name = (name or '').strip()
        email = (email or '').strip().lower()
        if len(name) < 2:
            raise UserError(_("Enter their name."))
        if '@' not in email:
            raise UserError(_("Enter a valid email address."))
        if role not in ROLES:
            raise UserError(_("Pick a role: User, Packer, Manager or Owner."))
        Users = self.sudo().with_context(active_test=False)
        if Users.search_count([('login', '=ilike', email)]):
            raise UserError(_("Somebody already signs in with that email."))
        user = Users.with_context(no_reset_password=True).create({
            'name': name, 'login': email, 'email': email,
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        user._mart369_role_groups(role, accountant, rider)
        try:
            user.action_reset_password()   # Odoo's own "set your password" invite
        except Exception:  # noqa: BLE001 - no mail server: still added, just not emailed
            pass
        return user._mart369_staff_row()

    # ---------------------------------------------------- the app's "me" call

    def _mart369_profile(self):
        """The console reads `role` to know who may open Staff & roles."""
        data = super()._mart369_profile()
        data['role'] = self.mart369_role or 'user'
        return data
