# -*- coding: utf-8 -*-
"""The vendor's day and the customer's day (24 Nov 2026)."""
from datetime import datetime, timedelta

import pytz

from odoo import fields
from odoo.addons.sales_automation_delivery.controllers.delivery_job import SaDeliveryJob
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from . import test_self_link


@tagged('post_install', '-at_install')
class TestTwoDays(test_self_link.LinkCase):

    def setUp(self):
        super().setUp()
        self.job.write({'sa_delivery_state': 'awaiting_shop'})
        self.env.company.partner_id.tz = 'Asia/Muscat'
        self.env.user.tz = 'Asia/Kolkata'
        self.settings = self.env['sa.ai.settings'].sudo().get_settings()
        self.today = fields.Date.to_date(self.job._sa_supply_now()['date'])

    def _set(self, vendor, customer=None, **kw):
        return self._act('supply_set', partner_id=self.kumar.id, cost=20.0, promised_date=fields.Date.to_string(vendor),
                         customer_date=customer and fields.Date.to_string(customer), send=True, **kw)

    def _day(self):
        return pytz.UTC.localize(self.job.sa_promised_on).astimezone(pytz.timezone('Asia/Muscat')).date()

    def test_days_of_the_configuration(self):
        for days, kind in ((0, 'quick'), (2, 'express')):
            self.settings.supply_customer_days = days
            self.job.sa_supply_waiting = False
            self._set(self.today)
            self.assertEqual((self.job.sa_supply_day, self._day(), self.job.sa_delivery_kind),
                             (self.today, self.today + timedelta(days=days), kind))
            self.assertTrue(self.job.sa_promise_day_only)

    def test_the_vendor_is_told_the_vendors_day_only(self):
        self.settings.supply_customer_days = 3
        self._set(self.today + timedelta(days=1))
        body = next(b for p, b in self.sent if p == self.kumar.phone)
        self.assertIn((self.today + timedelta(days=1)).strftime('%a %d %b %Y'), body)
        self.assertNotIn((self.today + timedelta(days=4)).strftime('%d %b'), body)
        self.assertNotRegex(body, r'\d:\d\d')

    def test_a_typed_day(self):
        self._set(self.today, self.today + timedelta(days=5))
        self.assertEqual(self._day(), self.today + timedelta(days=5))

    def test_not_before_the_vendor(self):
        for vendor, customer in ((2, 1), (0, -3)):
            with self.assertRaises(UserError):
                self._set(self.today + timedelta(days=vendor), self.today + timedelta(days=customer))
        self.assertFalse(self.job.sa_supply_waiting or self.sent)

    def test_no_time_for_the_customer(self):
        self._set(self.today, self.today + timedelta(days=2))
        tr = SaDeliveryJob()._track_values(self.job)
        self.assertTrue(tr['promise'].startswith('Delivery on'), tr['promise'])
        self.assertNotRegex(tr['promise'] + tr['eta_tail'], r'\d:\d\d')
        self.assertFalse(self.job.sa_track_payload()['eta']['window_to'])
        words = self.req._sa_ss_when(self.job.sa_promised_on, self.env.company, self.job.sa_promise_day_only)
        self.assertEqual(words, (self.today + timedelta(days=2)).strftime('%a %d %b'))

    def test_own_stock_keeps_its_time(self):
        self.job.write({'sa_promised_on': fields.Datetime.now() + timedelta(hours=2), 'sa_delivery_kind': 'quick'})
        self.assertRegex(SaDeliveryJob()._track_values(self.job)['promise'], r'\d:\d\d')
        self.assertTrue(self.job.sa_track_payload()['eta']['window_to'])

    def test_the_same_day_in_both_zones(self):
        at = self.job._sa_promise_at('2026-11-24')
        self.assertEqual(at, datetime(2026, 11, 24, 17, 0))
        for zone in ('Asia/Muscat', 'Asia/Kolkata'):
            self.assertEqual(pytz.UTC.localize(at).astimezone(pytz.timezone(zone)).day, 24)

    def test_the_popup_knows_the_days(self):
        self.settings.supply_customer_days = 4
        self.assertEqual(self.env['stock.picking'].sa_store_supply_options(self.job.id)['now']['customer_days'], 4)

    def test_wrong_settings(self):
        for days in (-1, 61):
            with self.assertRaises(ValidationError):
                self.settings.web_save({'supply_customer_days': days}, {'supply_customer_days': {}})    # as the screen saves
