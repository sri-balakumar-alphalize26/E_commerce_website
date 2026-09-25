from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMart369Customers(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.country_id = cls.env.ref('base.in')
        portal = cls.env.ref('base.group_portal')
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.meera = Users.create({'name': 'Meera Nair', 'login': 'meera@example.com',
                                  'email': 'meera@example.com', 'group_ids': [(6, 0, [portal.id])]})
        cls.joseph = Users.create({'name': 'Joseph Varghese', 'login': 'joseph@example.com',
                                   'email': 'joseph@example.com', 'group_ids': [(6, 0, [portal.id])]})

    def _age(self, user, days):
        self.env.cr.execute("UPDATE res_users SET create_date = %s WHERE id = %s",
                            (fields.Datetime.now() - timedelta(days=days), user.id))
        user.invalidate_recordset(['create_date'])

    def test_new_active_dormant_archived(self):
        self.meera._mart369_refresh_status()
        self.assertEqual(self.meera.mart369_status, 'new')

        self._age(self.meera, 45)
        self.meera._mart369_refresh_status()
        self.assertEqual(self.meera.mart369_status, 'active', 'New lasts 30 days by default')

        self._age(self.joseph, 120)
        self.joseph._mart369_refresh_status()
        self.assertEqual(self.joseph.mart369_status, 'dormant', 'never signed in for 120 days')

        self.joseph.action_archive()
        self.assertEqual(self.joseph.mart369_status, 'archived')
        self.joseph.action_unarchive()
        self.assertEqual(self.joseph.mart369_status, 'dormant')

    def test_the_days_come_from_settings_and_apply_at_once(self):
        config = self.env['mart369.config']._get()
        config.write({'customer_new_days': 30, 'customer_dormant_days': 90})
        self._age(self.meera, 20)
        self._age(self.joseph, 70)
        (self.meera | self.joseph)._mart369_refresh_status()
        self.assertEqual(self.meera.mart369_status, 'new')
        self.assertEqual(self.meera._mart369_new_days_left(), 10, '30 days, 20 gone')
        self.assertEqual(self.joseph.mart369_status, 'active', '70 quiet days is not yet 90')
        self.assertIsNone(self.joseph._mart369_new_days_left())

        # Saving from the Settings screen recomputes everyone there and then.
        Config = self.env['mart369.config']
        Config.mart369_admin_save('customers', {'newDays': 14, 'dormantDays': 60})
        self.assertEqual(self.meera.mart369_status, 'active', 'New for 14 days: 20 is past it')
        self.assertEqual(self.joseph.mart369_status, 'dormant', 'quiet 70 days, Dormant after 60')
        self.assertEqual(Config.mart369_admin_settings()['customers'], {'newDays': 14, 'dormantDays': 60})

        with self.assertRaises(UserError):
            Config.mart369_admin_save('customers', {'newDays': 0})

        row = self.meera._mart369_admin_row()
        self.assertIn('newDaysLeft', row)

    def test_mobile_is_checked_and_normalised(self):
        self.meera.phone = '98470 21536'
        self.assertEqual(self.meera.phone, '+919847021536')
        self.assertTrue(self.meera.mart369_phone_ok)
        with self.assertRaises(ValidationError):
            self.meera.phone = '1234567890'

    def test_dashboard_numbers(self):
        self.joseph.phone = '+919633710485'
        data = self.env['res.users'].mart369_customer_dashboard()
        self.assertGreaterEqual(data['total'], 2)
        self.assertGreaterEqual(data['new_week'], 2)
        self.assertEqual(len(data['signups']), 14)
        self.assertGreaterEqual(data['with_mobile'], 1)

    def test_profile_fields_compute(self):
        self.assertEqual(self.meera.mart369_order_count, 0)
        self.assertEqual(self.meera.mart369_seen_label, 'Never signed in')
        self.assertIn('Created an account', str(self.meera.mart369_timeline))
