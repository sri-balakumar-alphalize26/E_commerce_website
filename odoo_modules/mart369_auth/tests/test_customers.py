from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
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

        self._age(self.meera, 30)
        self.meera._mart369_refresh_status()
        self.assertEqual(self.meera.mart369_status, 'active')

        self._age(self.joseph, 120)
        self.joseph._mart369_refresh_status()
        self.assertEqual(self.joseph.mart369_status, 'dormant', 'never signed in for 120 days')

        self.joseph.action_archive()
        self.assertEqual(self.joseph.mart369_status, 'archived')
        self.joseph.action_unarchive()
        self.assertEqual(self.joseph.mart369_status, 'dormant')

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
