"""The 369 Mart role replaces Odoo's own "Role" line on the user form.

Odoo 19's line (User / Administrator) is a computed selection over two groups,
set by an onchange that swaps them in `group_ids` (base/models/res_users.py,
`_compute_role` / `_onchange_role`). This one works the same way and takes its
place:

- `mart369_role`: User / Packer / Manager / Owner. One choice, because each
  includes the one before. **Owner is Odoo's Administrator too** (the group
  implies base.group_system), so picking it keeps everything Odoo's line gave;
  picking anything else takes the Administrator right away, as Odoo's "User"
  did.
- `mart369_accountant`, `mart369_rider`: ticks, because somebody can pack and
  also do the books.

Seller is not here: a seller is a portal login, and this block is hidden for
portal users. It stays in the 369 Mart section lower down.
"""

from odoo import api, fields, models

CHAIN = [
    ('packer', 'mart369_roles.group_packer'),
    ('manager', 'mart369_roles.group_manager'),
    ('owner', 'mart369_roles.group_owner'),
]


class ResUsers(models.Model):
    _inherit = 'res.users'

    mart369_role = fields.Selection(
        [('user', 'User'), ('packer', 'Packer'), ('manager', 'Manager'), ('owner', 'Owner')],
        string='369 Mart role', compute='_compute_mart369_role', readonly=False,
        help="User: an Odoo login with no 369 Mart screens. Packer: packs orders. "
             "Manager: runs the shop day to day and approves sellers' products. "
             "Owner: everything, including payments, store details, who has which "
             "role, and Odoo's own settings. Each includes the one before.")
    mart369_accountant = fields.Boolean(
        string='Accountant', compute='_compute_mart369_role', readonly=False,
        help="Payments, wallets, invoices, refunds and reports.")
    mart369_rider = fields.Boolean(
        string='Rider', compute='_compute_mart369_role', readonly=False,
        help="Only their own deliveries: close each with the customer's code.")

    @api.depends('group_ids')
    def _compute_mart369_role(self):
        for user in self:
            role = 'user'
            for key, xmlid in CHAIN:          # highest wins: owner last
                if user.has_group(xmlid):
                    role = key
            user.mart369_role = role
            user.mart369_accountant = user.has_group('mart369_roles.group_accountant')
            user.mart369_rider = user.has_group('mart369_roles.group_rider')

    def _mart369_new_group(self, xmlid):
        return self.env['res.groups'].new(origin=self.env.ref(xmlid))

    @api.onchange('mart369_role')
    def _onchange_mart369_role(self):
        chain = {key: self._mart369_new_group(xmlid) for key, xmlid in CHAIN}
        admin = self._mart369_new_group('base.group_system')
        internal = self._mart369_new_group('base.group_user')
        for user in self:
            if user.share:
                continue
            groups = user.group_ids - sum(chain.values(), self.env['res.groups']) - admin - internal
            groups += internal
            if user.mart369_role in chain:
                groups += chain[user.mart369_role]
            user.group_ids = groups

    @api.onchange('mart369_accountant', 'mart369_rider')
    def _onchange_mart369_extra(self):
        accountant = self._mart369_new_group('mart369_roles.group_accountant')
        rider = self._mart369_new_group('mart369_roles.group_rider')
        for user in self:
            if user.share:
                continue
            groups = user.group_ids - accountant - rider
            if user.mart369_accountant:
                groups += accountant
            if user.mart369_rider:
                groups += rider
            user.group_ids = groups
