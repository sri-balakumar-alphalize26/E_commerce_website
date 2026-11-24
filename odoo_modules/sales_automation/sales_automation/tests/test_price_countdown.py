# -*- coding: utf-8 -*-
"""Two prices: goes by itself after the countdown, once (24 Nov 2026)."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from . import test_vendor_window
from .test_only_listed import ListedCase


@tagged('post_install', '-at_install')
class TestPriceCountdown(ListedCase):
    _asked = test_vendor_window.TestVendorWindow._asked
    _price = test_vendor_window.TestVendorWindow._price

    def setUp(self):
        super().setUp()
        self.settings = self.env['sa.ai.settings'].sudo().get_settings()
        self.settings.write({'sourcing_window_minutes': 3, 'margin_percent': 20.0, 'price_approval_enabled': True,
                             'price_approval_tolerance_percent': 0.0, 'vendor_choice_mode': 'auto', 'margin_rules_enabled': False,
                             'price_auto_minutes': 1, 'price_auto_max_below': 50.0})
        self.vendors = self.env['res.partner'].create([{'name': 'Zz V%s' % n, 'phone': '+9715000040%02d' % n} for n in range(3)])

    def _held(self, page=130.0, cost=100.0):
        self.product.list_price = page
        req = self._asked()
        self._price(req, 0, cost)
        with patch.object(self.env.registry['sa.group.request'], '_catalog_price', lambda rec, product, existing=False: page):
            req._close_sourcing()
        self.assertTrue(req.sa_price_choice_pending)
        return req

    def _over(self, req):
        req.sa_price_auto_on = fields.Datetime.now() - timedelta(seconds=1)
        self.env['sa.group.request']._cron_close_sourcing()

    def test_goes_once(self):
        req = self._held()
        self.assertTrue(0 < req._sa_price_seconds_left() <= 60)
        self._over(req)
        self.assertEqual((req.sa_price_choice_pending, req.sa_price_choice, req.quoted_price), (False, 'vendor', 120.0))
        self.assertFalse(req.sa_price_auto_on)
        told = len(self.said)
        self.env['sa.group.request']._cron_close_sourcing()
        self.assertEqual(len(self.said), told)

    def test_not_before_the_time(self):
        req = self._held()
        self.env['sa.group.request']._cron_close_sourcing()
        self.assertTrue(req.sa_price_choice_pending)

    def test_a_button_stops_it(self):
        req = self._held()
        req._sa_apply_price_choice('page', source='test')
        self.assertFalse(req.sa_price_auto_on)
        self._over(req)
        self.assertEqual((req.sa_price_choice, req.quoted_price), ('page', 130.0))

    def test_waits_for_a_person(self):
        for vals, page, cost in (({'vendor_choice_mode': 'auto', 'price_auto_minutes': 0}, 130.0, 100.0), ({'price_auto_minutes': 1}, 1999.0, 10.0)):
            self.settings.write(vals)
            req = self._held(page, cost)
            self.assertFalse(req.sa_price_auto_on)
            self.assertEqual(req._sa_price_seconds_left(), -1)
            self.env['sa.group.request']._cron_close_sourcing()
            self.assertTrue(req.sa_price_choice_pending)

    def test_the_limit_is_the_price_with_the_margin(self):
        self.assertTrue(self._held(120.0, 50.0).sa_price_auto_on)       # 60 of 120: exactly half
        self.assertFalse(self._held(121.0, 50.0).sa_price_auto_on)

    def test_dearer_than_the_page_goes(self):
        self.assertTrue(self._held(50.0, 100.0).sa_price_auto_on)

    def test_switched_to_manual_meanwhile(self):
        req = self._held()
        self.settings.vendor_choice_mode = 'manual'
        self._over(req)
        self.assertTrue(req.sa_price_choice_pending)
        self.assertFalse(req.sa_price_auto_on)

    def test_closed_meanwhile(self):
        req = self._held()
        req.state = 'dropped'
        told = len(self.said)
        self._over(req)
        self.assertEqual((len(self.said), req.state), (told, 'dropped'))

    def test_somebody_else_has_it(self):
        req = self._held()
        with patch.object(self.env.registry['sa.group.request'], '_sa_lock_enquiry', lambda rec: False):
            self._over(req)
            self.assertTrue(req.sa_price_choice_pending)
            with self.assertRaises(UserError):
                req._sa_apply_price_choice('page')

    def test_one_that_fails_waits_for_a_person(self):
        req = self._held()

        def broken(rec, quote):
            raise ValueError('zz')
        with patch.object(self.env.registry['sa.group.request'], '_apply_winning_quote', broken), self.assertLogs(level='ERROR'):
            self._over(req)
        self.assertTrue(req.sa_price_choice_pending)
        self.assertFalse(req.sa_price_auto_on)

    def test_wrong_settings(self):
        for vals in ({'price_auto_minutes': -1}, {'price_auto_minutes': 2000}, {'price_auto_max_below': 101.0}):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                self.settings.web_save(vals, {'id': {}})
