"""The console's Settings screen.

**It saves to the real records.** The screen used to keep its own copy and save
nowhere. Store must land on the company, the cash limit on the COD provider's
`maximum_amount` - the number the checkout enforces - and alerts on the shared
settings record.

**It cannot switch on a gateway without keys.** Cash on delivery and the wallet
need none; anything else switched on from here would send a customer to a
payment page that fails.

**Who may look.** A shopper is refused, not handed the shop's GSTIN.
"""

import json

from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAdminSettings(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Config = self.env['mart369.config']
        self.cod = self.env.ref('delivery.payment_provider_cod')

    def test_store_saves_to_the_company(self):
        self.Config.mart369_admin_save('store', {'name': 'Kochi Hub', 'gstin': '32AAZCA2582P1ZW',
                                                 'city': 'Kochi'})
        self.assertEqual(self.env.company.name, 'Kochi Hub')
        self.assertEqual(self.env.company.vat, '32AAZCA2582P1ZW')
        store = self.Config.mart369_admin_settings()['store']
        self.assertEqual(store['city'], 'Kochi')
        with self.assertRaises(UserError):
            self.Config.mart369_admin_save('store', {'name': '  '})

    def test_alerts_save_to_the_settings_record(self):
        self.Config.mart369_admin_save('alerts', {'lowStock': False})
        self.assertFalse(self.Config._get().alert_low_stock)
        alerts = self.Config.mart369_admin_settings()['alerts']
        self.assertEqual(alerts, {'newOrder': True, 'lowStock': False})

    def test_cod_limit_is_the_providers_own(self):
        self.Config.mart369_admin_save('pay', {'codLimit': 2500})
        self.assertEqual(self.cod.maximum_amount, 2500)
        self.assertEqual(self.Config.mart369_admin_settings()['pay']['codLimit'], 2500)
        with self.assertRaises(UserError):
            self.Config.mart369_admin_save('pay', {'codLimit': -1})

    def test_cod_can_be_switched_on_and_off(self):
        self.cod.state = 'disabled'
        self.Config.mart369_admin_save('pay', {'providers': {str(self.cod.id): True}})
        self.assertEqual(self.cod.state, 'enabled')
        self.assertTrue(self.cod.is_published)
        self.Config.mart369_admin_save('pay', {'providers': {str(self.cod.id): False}})
        self.assertEqual(self.cod.state, 'disabled')

    def test_a_gateway_without_keys_cannot_be_switched_on(self):
        gateway = self.env['payment.provider'].create({
            'name': 'Some Gateway', 'code': 'none', 'state': 'test'})
        # Listed, because it is in test mode - and it can be switched off.
        ids = [p['id'] for p in self.Config.mart369_admin_settings()['pay']['providers']]
        self.assertIn(gateway.id, ids)
        self.Config.mart369_admin_save('pay', {'providers': {str(gateway.id): False}})
        self.assertEqual(gateway.state, 'disabled')
        # Off now and not one this screen may turn on.
        with self.assertRaises(UserError):
            self.Config.mart369_admin_save('pay', {'providers': {str(gateway.id): True}})

    def test_unknown_group_is_refused(self):
        with self.assertRaises(UserError):
            self.Config.mart369_admin_save('nonsense', {})


@tagged('post_install', '-at_install')
class TestAdminSettingsRoutes(HttpCase):

    def test_a_shopper_is_refused(self):
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Settings Snoop', 'login': 'settings.snoop@example.com',
            'password': 'settings-snoop-369',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        self.authenticate('settings.snoop@example.com', 'settings-snoop-369')
        self.assertEqual(self.url_open('/369mart/admin/settings').status_code, 403)
        res = self.url_open('/369mart/admin/settings/store', data=json.dumps({'name': 'Hacked'}),
                            headers={'Content-Type': 'application/json'})
        self.assertEqual(res.status_code, 403)
        self.assertNotEqual(self.env.company.name, 'Hacked')

    def test_staff_read_and_save(self):
        self.authenticate('admin', 'admin')
        body = self.url_open('/369mart/admin/settings').json()
        self.assertTrue(body['ok'])
        # other modules add groups of their own (mart369_auth: customers)
        self.assertLessEqual({'store', 'alerts', 'pay'}, set(body['settings']))
        res = self.url_open('/369mart/admin/settings/alerts', data=json.dumps({'newOrder': False}),
                            headers={'Content-Type': 'application/json'}).json()
        self.assertTrue(res['ok'])
        self.assertFalse(res['settings']['alerts']['newOrder'])
