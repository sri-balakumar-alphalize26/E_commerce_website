# -*- coding: utf-8 -*-
"""Automatic or Manual, and who wins when prices are equal (24 Nov 2026)."""
import psycopg2
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_only_listed import ListedCase
from . import test_vendor_window


@tagged('post_install', '-at_install')
class TestVendorChoice(ListedCase):
    _asked = test_vendor_window.TestVendorWindow._asked
    _price = test_vendor_window.TestVendorWindow._price

    def setUp(self):
        super().setUp()
        self.settings = self.env['sa.ai.settings'].sudo().get_settings()
        self.settings.write({'sourcing_window_minutes': 3, 'margin_percent': 20.0, 'price_approval_enabled': False, 'vendor_choice_mode': 'auto'})
        self.vendors = self.env['res.partner'].create([{'name': 'Zz V%s' % n, 'phone': '+9715000020%02d' % n} for n in range(5)])

    def _same_second(self, *quotes):
        self.env.cr.execute("UPDATE sa_vendor_quote SET create_date = date_trunc('second', now() at time zone 'utc') - interval '60 seconds' "
                            "WHERE id IN %s", [tuple(q.id for q in quotes)])
        self.env.invalidate_all()

    def _bought(self, n, times):
        for _x in range(times):
            req = self._asked()
            quote = self._price(req, n, 9.0)
            order = self.env['sale.order'].create({'partner_id': self.vendors[4].id, 'state': 'sale'})
            req.write({'best_quote_id': quote.id, 'order_id': order.id, 'state': 'order_created'})

    def test_automatic_is_the_default(self):
        self.assertEqual(self.env['sa.ai.settings'].new({}).vendor_choice_mode, 'auto')

    def test_lowest_and_why(self):
        req = self._asked()
        self._price(req, 0, 25.0)
        low = self._price(req, 1, 20.0)
        req._close_sourcing()
        self.assertEqual((req.best_quote_id, req.sa_selected_by, req.sa_selected_reason), (low, 'auto', 'lowest_price'))

    def test_only_one(self):
        req = self._asked()
        self._price(req, 0, 30.0)
        req._close_sourcing()
        self.assertEqual(req.sa_selected_reason, 'only_price')

    def test_tie_first_beats_bought_more(self):
        self._bought(0, 3)
        req = self._asked()
        self._price(req, 0, 20.0, ago=10)
        first = self._price(req, 1, 20.0, ago=40)
        req._close_sourcing()
        self.assertEqual((req.best_quote_id, req.sa_selected_reason), (first, 'tie_first'))

    def test_tie_same_second_bought_more(self):
        self._bought(2, 2)
        self._bought(1, 1)
        req = self._asked()
        quotes = [self._price(req, n, 20.0) for n in range(3)]
        self._same_second(*quotes)
        req._close_sourcing()
        self.assertEqual((req.best_quote_id, req.sa_selected_reason), (quotes[2], 'tie_bought'))

    def test_bought_is_of_the_same_product(self):
        self._bought(1, 2)
        other = self.env['product.template'].create({'name': 'Zz another product'})
        self.env['sa.group.request'].search([('state', '=', 'order_created'), ('best_quote_id.partner_id', '=', self.vendors[1].id)]).product_id = other
        req = self._asked()
        self.assertFalse(req._sa_bought_map().get((req.product_id.id, self.vendors[1].id)))

    def test_all_the_same_is_always_the_same(self):
        req = self._asked()
        a, b = self._price(req, 0, 20.0), self._price(req, 1, 20.0)
        self._same_second(a, b)
        req._close_sourcing()
        self.assertEqual((req.best_quote_id, req.sa_selected_reason), (a, 'tie_fixed_order'))

    def test_changing_the_price_loses_the_place(self):
        req = self._asked()
        self._price(req, 0, 20.0, ago=90)
        b = self._price(req, 1, 19.0, ago=60)
        self._price(req, 0, 19.0, ago=30)
        req._close_sourcing()
        self.assertEqual((req.best_quote_id, req.sa_selected_reason), (b, 'tie_first'))

    # -------------------------------------------------------- by hand
    def _manual(self):
        self.settings.vendor_choice_mode = 'manual'
        req = self._asked()
        low, high = self._price(req, 0, 20.0), self._price(req, 1, 25.0)
        with patch.object(self.env.registry['sa.group.request'], '_quote_customer', lambda *a, **k: self.fail('told')):
            req._close_sourcing()
        return req, low, high

    def test_manual_sends_nothing(self):
        req, _low, _high = self._manual()
        self.assertEqual((req.state, req.sa_vendor_choice_pending, req.sourcing_deadline, req.best_quote_id.id), ('sourcing', True, False, False))

    def test_the_dearer_one_by_hand(self):
        req, _low, high = self._manual()
        req._sa_choose_vendor(high)
        self.assertEqual((req.state, req.best_quote_id, req.quoted_price, req.sa_vendor_choice_pending), ('quoted', high, 30.0, False))
        self.assertEqual((req.sa_selected_by, req.sa_selected_user_id), ('manual', self.env.user))
        with self.assertRaises(UserError):
            req._sa_choose_vendor(high)

    def test_manual_does_not_wait(self):
        self.settings.vendor_choice_mode = 'manual'
        req = self._asked(left=100)
        quote = self._price(req, 0, 20.0)
        req._sa_choose_vendor(quote)
        self.assertEqual((req.state, req.best_quote_id, req.quoted_price), ('quoted', quote, 24.0))

    def test_automatic_cannot_be_chosen_by_hand(self):
        req = self._asked(left=100)
        with self.assertRaises(UserError):
            req._sa_choose_vendor(self._price(req, 0, 20.0))

    def test_not_another_enquirys_price(self):
        req, _low, _high = self._manual()
        other = self._price(self._asked(), 2, 5.0)
        with self.assertRaises(UserError):
            req._sa_choose_vendor(other)

    def test_an_older_price_cannot_be_chosen(self):
        req, low, _high = self._manual()
        self._price(req, 0, 22.0, ago=1)
        with self.assertRaises(UserError):
            req._sa_choose_vendor(low)

    def test_switching_sends_nothing(self):
        req, _low, _high = self._manual()
        self.settings.vendor_choice_mode = 'auto'
        req._cron_close_sourcing()
        self.assertTrue(req.sa_vendor_choice_pending)

    # -------------------------------------------------------- 1GG
    def test_a_broken_transaction_drops_only_after_five(self):
        req = self._asked()
        self._price(req, 0, 20.0)

        def broken(rec):
            raise psycopg2.errors.InFailedSqlTransaction('current transaction is aborted')
        with patch.object(self.env.registry['sa.group.request'], '_close_sourcing', broken):
            for n in range(1, 5):
                req._cron_close_sourcing()
                self.assertEqual((req.state, req.sa_close_tries), ('sourcing', n))
        req._cron_close_sourcing()
        self.assertEqual(req.state, 'quoted', 'closed at the next run')
        again = self._asked()
        self._price(again, 0, 20.0)
        with patch.object(self.env.registry['sa.group.request'], '_close_sourcing', broken):
            for _n in range(5):
                again._cron_close_sourcing()
        self.assertEqual((again.state, again.drop_reason), ('dropped', 'error'))
