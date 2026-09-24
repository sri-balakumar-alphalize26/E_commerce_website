"""The 369 Mart roles: the Role line on the user form, and the Staff page.

Pinned because each one fails quietly:
- the Role line replaces Odoo's User / Administrator, so Owner must carry the
  Administrator right and anything below it must drop it - otherwise saving a
  form would silently hand out, or take away, control of Odoo;
- a Manager must keep today's staff check (website designer), or every admin
  route locks them out without saying why;
- only the Owner may change roles, and the last Owner can never be moved down.
"""

import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, HttpCase, TransactionCase, tagged


class _Staff:

    @classmethod
    def _user(cls, env, login, role='user'):
        user = env['res.users'].with_context(no_reset_password=True).create({
            'name': login.split('@')[0].title(), 'login': login, 'password': login,
            'group_ids': [(6, 0, [env.ref('base.group_user').id])],
        })
        user._mart369_role_groups(role, False, False)
        return user


@tagged('post_install', '-at_install')
class TestMart369Roles(TransactionCase, _Staff):

    def _group(self, name):
        return self.env.ref('mart369_roles.group_' + name)

    def test_staff_roles_are_one_chain(self):
        packer, manager, owner = (self._group(n) for n in ('packer', 'manager', 'owner'))
        self.assertIn(packer, owner.all_implied_ids)
        self.assertIn(manager, owner.all_implied_ids)
        self.assertIn(packer, manager.all_implied_ids)

    def test_owner_is_odoos_administrator(self):
        self.assertIn(self.env.ref('base.group_system'), self._group('owner').all_implied_ids)
        self.assertNotIn(self.env.ref('base.group_system'), self._group('manager').all_implied_ids)

    def test_manager_keeps_todays_staff_access(self):
        designer = self.env.ref('website.group_website_designer')
        self.assertIn(designer, self._group('manager').all_implied_ids)
        self.assertNotIn(designer, self._group('packer').all_implied_ids)

    def test_admin_is_owner(self):
        self.assertEqual(self.env.ref('base.user_admin').mart369_role, 'owner')

    def test_seller_is_a_portal_login(self):
        seller = self._group('seller')
        self.assertIn(self.env.ref('base.group_portal'), seller.all_implied_ids)
        self.assertNotIn(self.env.ref('base.group_user'), seller.all_implied_ids)

    def test_form_role_swaps_the_groups(self):
        user = self._user(self.env, 'form.user@example.com', 'owner')
        self.assertTrue(user.has_group('base.group_system'))
        with Form(user, view='base.view_users_form') as form:
            form.mart369_role = 'packer'
            form.mart369_rider = True
        self.assertEqual(user.mart369_role, 'packer')
        self.assertFalse(user.has_group('base.group_system'), 'packer is not an Odoo admin')
        self.assertTrue(user.has_group('base.group_user'))
        self.assertTrue(user.mart369_rider)
        with Form(user, view='base.view_users_form') as form:
            form.mart369_role = 'user'
        self.assertFalse(user.has_group('mart369_roles.group_packer'))

    def test_form_shows_our_role_instead_of_odoos(self):
        arch = self.env['res.users'].get_view(self.env.ref('base.view_users_form').id)['arch']
        self.assertIn('mart369_role', arch)

    def test_install_hook_gives_everyone_a_role(self):
        from odoo.addons.mart369_roles import _mart369_give_roles
        admin = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Old Admin', 'login': 'old.admin@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_system').id])],
        })
        staff = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Old Staff', 'login': 'old.staff@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('website.group_website_designer').id])],
        })
        _mart369_give_roles(self.env)
        self.assertEqual(admin.mart369_role, 'owner')
        self.assertEqual(staff.mart369_role, 'manager')

    # ---------------------------------------------------------- staff page

    def _as_owner(self):
        return self.env['res.users'].with_user(self.env.ref('base.user_admin'))

    def test_only_the_owner_may_change_roles(self):
        manager = self._user(self.env, 'mgr@example.com', 'manager')
        other = self._user(self.env, 'other@example.com')
        with self.assertRaises(AccessError):
            self.env['res.users'].with_user(manager).mart369_staff_list()
        with self.assertRaises(AccessError):
            self.env['res.users'].with_user(manager).mart369_staff_set(other.id, 'owner')

    def test_owner_sets_role_like_the_form(self):
        user = self._user(self.env, 'set.me@example.com')
        row = self._as_owner().mart369_staff_set(user.id, 'manager', True, False)
        self.assertEqual(row['role'], 'manager')
        self.assertTrue(row['accountant'])
        self.assertTrue(user.has_group('website.group_website_designer'))
        self.assertFalse(user.has_group('base.group_system'))

    def test_the_last_owner_stays_owner(self):
        Users = self._as_owner()
        owners = self._group('owner').all_user_ids.filtered(lambda u: not u.share)
        # Make admin the only Owner, then try to move them down.
        for u in owners - self.env.ref('base.user_admin'):
            u._mart369_role_groups('user', False, False)
        with self.assertRaises(UserError):
            Users.mart369_staff_set(self.env.ref('base.user_admin').id, 'manager')

    def test_invite_adds_staff_with_the_role(self):
        row = self._as_owner().mart369_staff_invite('New Packer', 'new.packer@example.com', 'packer')
        user = self.env['res.users'].browse(row['id'])
        self.assertEqual(user.mart369_role, 'packer')
        self.assertFalse(user.share)
        with self.assertRaises(UserError):
            self._as_owner().mart369_staff_invite('Again', 'new.packer@example.com', 'packer')


@tagged('post_install', '-at_install')
class TestMart369StaffRoutes(HttpCase, _Staff):

    def test_routes_are_owner_only(self):
        self._user(self.env, 'route.mgr@example.com', 'manager')
        self.authenticate('route.mgr@example.com', 'route.mgr@example.com')
        self.assertEqual(self.url_open('/369mart/admin/staff').status_code, 403)

    def test_owner_reads_and_me_has_role(self):
        self.authenticate('admin', 'admin')
        body = self.url_open('/369mart/admin/staff').json()
        self.assertTrue(body['ok'])
        self.assertIn('admin', [r['email'] for r in body['rows']])
        self.assertEqual(self.url_open('/369mart/auth/me').json()['role'], 'owner')
