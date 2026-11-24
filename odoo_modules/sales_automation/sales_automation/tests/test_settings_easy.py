# -*- coding: utf-8 -*-
"""Vendors & Customer Replies: the example, and what cannot work (23 Nov 2026)."""
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSettingsEasy(TransactionCase):

    def setUp(self):
        super().setUp()
        self.settings = self.env['sa.ai.settings'].sudo().get_settings()
        self.settings.write({'margin_percent': 20.0, 'min_margin_percent': 5.0, 'bargain_enabled': True,
                             'sourcing_window_minutes': 10, 'customer_reply_minutes': 0, 'price_approval_enabled': True,
                             'price_approval_tolerance_percent': 0.0, 'pay_remind_minutes': 60, 'pay_remind_max': 2,
                             'price_escalation_phone': False})

    def _save(self, **vals):
        return self.settings.web_save(vals, {'easy_example': {}})

    def test_the_example_follows_the_numbers(self):
        self.assertIn('120.00', self.settings.easy_example)
        self.assertIn('10 minutes', self.settings.easy_example)
        row = self._save(margin_percent=50.0, sourcing_window_minutes=5, price_approval_enabled=False, customer_reply_minutes=30)[0]
        for words in ('150.00', '5 minutes', 'at once', '30 minutes'):
            self.assertIn(words, row['easy_example'])
        self.assertIn('No reminder', self._save(pay_remind_minutes=0)[0]['easy_example'])
        self.assertIn('5%', self._save(price_approval_enabled=True, price_approval_tolerance_percent=5.0)[0]['easy_example'])

    def test_what_cannot_work_is_refused(self):
        for vals, words in (
                ({'sourcing_window_minutes': 0}, 'wait for prices'), ({'sourcing_window_minutes': 2000}, '1440'),
                ({'margin_percent': -1.0}, 'add normally'), ({'margin_percent': 2.0}, 'always be left'),
                ({'price_approval_tolerance_percent': 150.0}, '0 to 100'), ({'customer_reply_minutes': 2}, '5 to 1440'),
                ({'customer_reply_minutes': -5}, '5 to 1440'), ({'pay_remind_minutes': 1}, 'remind after'),
                ({'pay_remind_max': 50}, '0 to 10'), ({'price_escalation_phone': '12345'}, 'whole phone number')):
            with self.assertRaisesRegex(ValidationError, words, msg=str(vals)), self.env.cr.savepoint():
                self._save(**vals)

    def test_what_works_is_saved(self):
        self._save(sourcing_window_minutes=15, margin_percent=25.0, customer_reply_minutes=60, pay_remind_minutes=0, pay_remind_max=0,
                   price_escalation_phone='+971501234567')
        self.assertEqual((self.settings.sourcing_window_minutes, self.settings.margin_percent), (15, 25.0))

    def test_only_what_is_changed_is_checked(self):
        self.settings.sourcing_window_minutes = 0          # an old value, by code as before
        self._save(margin_percent=30.0)
        self.assertEqual(self.settings.margin_percent, 30.0)

    def test_the_page_opens(self):
        view = self.env.ref('sales_automation.view_sa_settings_vendor_form')
        self.env['sa.ai.settings'].get_views([(view.id, 'form')])
        self.assertIn('product categories', self.settings.easy_vendors)
        self.assertEqual(self.settings.action_sa_open_categories()['res_model'], 'product.category')
