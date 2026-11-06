"""The customer list in the app's own console.

Three things are pinned, and they are the three that would not announce
themselves when they break:

**Who may look.** These routes list every customer's email and phone. The group
check is the only fence, so a shopper must be refused, not handed a list.

**Filters are the shop, not the page.** A tab or an area that only filtered the
rows already sent would look right on a small test database and be wrong on a
real one - so each filter is checked against records outside the first page.

**One customer's money stays on their own row.** Wallet and spend are joined
in batches; a join that slipped would show a stranger's balance.
"""

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged


class _Customers:

    @classmethod
    def _customers(cls, env):
        portal = env.ref('base.group_portal')
        Users = env['res.users'].with_context(no_reset_password=True)

        def make(name, login, city):
            user = Users.create({'name': name, 'login': login, 'email': login,
                                 'group_ids': [(6, 0, [portal.id])]})
            user.partner_id.city = city
            return user

        return (make('Meera Nair', 'meera.admin@example.com', 'Kakkanad'),
                make('Joseph Varghese', 'joseph.admin@example.com', 'Edappally'))


@tagged('post_install', '-at_install')
class TestAdminCustomerList(TransactionCase, _Customers):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.meera, cls.joseph = cls._customers(cls.env)
        cls.Users = cls.env['res.users']

    def _ids(self, **kw):
        return {r['id'] for r in self.Users.mart369_admin_list(limit=200, **kw)['rows']}

    def test_row_carries_what_the_table_draws(self):
        row = self.meera._mart369_admin_row({})
        # Other modules add to the row (mart369_address: addressCount).
        self.assertLessEqual({'id', 'name', 'email', 'phone', 'area', 'orders', 'spent',
                              'wallet', 'last', 'joined', 'status', 'newDaysLeft', 'lastPlaced'}, set(row))
        self.assertEqual(row['area'], 'Kakkanad')

    def test_only_storefront_accounts(self):
        ids = self._ids()
        self.assertIn(self.meera.id, ids)
        self.assertNotIn(self.env.ref('base.user_admin').id, ids, 'staff are not customers')
        public = self.env.ref('base.public_user', raise_if_not_found=False)
        if public:
            self.assertNotIn(public.id, ids)

    def test_tabs_are_domains(self):
        self.meera.mart369_status = 'dormant'
        self.joseph.mart369_status = 'active'
        self.assertIn(self.meera.id, self._ids(tab='dormant'))
        self.assertNotIn(self.joseph.id, self._ids(tab='dormant'))

    def test_area_search_and_joined(self):
        self.assertEqual(self._ids(area='Kakkanad') & {self.meera.id, self.joseph.id},
                         {self.meera.id})
        self.assertIn(self.joseph.id, self._ids(q='Edappally'))
        self.env.cr.execute("UPDATE res_users SET create_date = %s WHERE id = %s",
                            (fields.Datetime.now() - timedelta(days=200), self.joseph.id))
        self.joseph.invalidate_recordset(['create_date'])
        self.assertNotIn(self.joseph.id, self._ids(joined='3m'))
        self.assertIn(self.joseph.id, self._ids(joined='year'))
        self.assertIn('Kakkanad', self.Users.mart369_admin_list()['areas'])

    def test_wallet_stays_on_its_own_row(self):
        meera_key = self.meera.partner_id.commercial_partner_id.id
        with patch.object(type(self.Users), '_mart369_admin_wallets',
                          lambda self, partners=None: {meera_key: 500.0}):
            rows = {r['id']: r for r in self.Users.mart369_admin_list(limit=200)['rows']}
            self.assertEqual(rows[self.meera.id]['wallet'], 500.0)
            self.assertEqual(rows[self.joseph.id]['wallet'], 0.0)
            self.assertEqual(self._ids(wallet='1') & {self.meera.id, self.joseph.id},
                             {self.meera.id})

    def test_tiles_count_the_shop_not_the_filter(self):
        everyone = self.Users.mart369_admin_list()['counts']['all']
        page = self.Users.mart369_admin_list(q='Meera Nair')
        self.assertEqual(page['counts']['all'], everyone)
        self.assertLess(page['total'], everyone + 1)


@tagged('post_install', '-at_install')
class TestAdminCustomerRoutes(HttpCase, _Customers):

    def setUp(self):
        super().setUp()
        self.meera, self.joseph = self._customers(self.env)
        self.meera.password = 'meera-pass-369'

    def test_a_shopper_is_refused(self):
        self.authenticate('meera.admin@example.com', 'meera-pass-369')
        for path in ('/369mart/admin/customers',
                     '/369mart/admin/customers/%d' % self.joseph.id):
            res = self.url_open(path)
            self.assertEqual(res.status_code, 403, path)
            self.assertNotIn('joseph', res.text.lower())

    def test_staff_see_the_list_and_one_customer(self):
        self.authenticate('admin', 'admin')
        res = self.url_open('/369mart/admin/customers?area=Kakkanad')
        self.assertEqual(res.status_code, 200)
        names = [r['name'] for r in res.json()['rows']]
        self.assertIn('Meera Nair', names)
        self.assertNotIn('Joseph Varghese', names)
        one = self.url_open('/369mart/admin/customers/%d' % self.meera.id).json()
        self.assertEqual(one['customer']['name'], 'Meera Nair')
        self.assertEqual(one['customer']['recent'], [])
        staff = self.env.ref('base.user_admin').id
        self.assertEqual(self.url_open('/369mart/admin/customers/%d' % staff).status_code, 404,
                         'a staff account is not a customer')
