# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import BuyCase


@tagged('post_install', '-at_install')
class TestVendorOrders(BuyCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(cls.env, 'zz-buy-manager', groups='base.group_user,sales_automation.group_sa_manager')

    def _row(self, line, user=None):
        Line = self.env['sa.buy.line'].with_user(user or self.manager)
        return next((r for r in Line.sa_vendor_orders()['rows'] if r['id'] == line.id), None)

    def test_ravi(self):
        order, req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        row = self._row(line)
        self.assertEqual((row['paid'], row['best']['vendor'], row['best']['cost'], row['best']['margin']),
                         (100.0, 'Zz Vendor A', 80.0, 20.0))
        self.assertEqual((row['asked'], row['replied'], row['no_reply'], row['better']), (5, 2, 3, False))
        self._price(req, 'E', 60.0, sa_late=True)
        row = self._row(line)
        self.assertEqual((row['best']['vendor'], row['best']['margin']), ('Zz Vendor E', 40.0))
        self.assertEqual(row['better'], {'vendor': 'Zz Vendor E', 'saving': 20.0, 'than': 'Zz Vendor A'})
        self.assertEqual([(p['vendor'], p['place'], p['quoted']) for p in row['prices']],
                         [('Zz Vendor E', 1, False), ('Zz Vendor A', 2, True), ('Zz Vendor B', 3, False)])
        self.assertTrue(row['prices'][0]['late'])
        self.assertEqual((req.state, req.agreed_price), ('order_created', 100.0))

    def test_a_small_saving_is_not_pointed_out(self):
        order, req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        self._price(req, 'E', 79.0)
        self.assertFalse(self._row(line)['better'])
        self.settings.late_min_saving_amount = 0.0
        self.assertEqual(self._row(line)['better']['saving'], 1.0)
        self._price(req, 'E', 80.0)
        self.assertFalse(self._row(line)['better'], 'the same price is not cheaper')

    def test_the_saving_is_the_whole_lines(self):
        order, req, _a = self._ravi(qty=5)
        line = order._sa_buy_lines_make()
        self._price(req, 'E', 76.0)
        self.assertEqual(self._row(line)['better']['saving'], 20.0)

    def test_the_newest_price_of_a_vendor_counts(self):
        order, req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        self._price(req, 'B', 70.0)
        row = self._row(line)
        self.assertEqual((row['replied'], row['best']['vendor'], row['best']['cost']), (2, 'Zz Vendor B', 70.0))

    def test_equal_prices_go_by_days(self):
        order, req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        self._price(req, 'C', 75.0, delay_days=3)
        self._price(req, 'D', 75.0, delay_days=1)
        self.assertEqual(self._row(line)['best']['vendor'], 'Zz Vendor D')

    def test_who_said_no(self):
        order, req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        self._price(req, 'E', 60.0)
        req.sa_vendor_no_ids = [(4, self.vendors['E'].id)]
        row = self._row(line)
        self.assertEqual((row['best']['vendor'], row['said_no'], row['no']), ('Zz Vendor A', 1, ['Zz Vendor E']))

    def test_dearer_than_paid_is_a_loss(self):
        order = self._order()
        req = self._ask(order=order)
        req.best_quote_id = self._price(req, 'A', 130.0)
        row = self._row(order._sa_buy_lines_make())
        self.assertTrue(row['loss'])
        self.assertEqual(row['best']['margin'], -30.0)

    def test_a_price_without_a_rate_is_never_the_best(self):
        order, req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        other = self.env['res.currency'].create({'name': 'ZZQ', 'symbol': 'Q', 'rounding': 0.01})
        self._price(req, 'E', 1.0, currency_id=other.id)
        row = self._row(line)
        self.assertEqual(row['best']['vendor'], 'Zz Vendor A')
        self.assertEqual((row['prices'][-1]['vendor'], row['prices'][-1]['cost'], row['prices'][-1]['margin']), ('Zz Vendor E', None, None))
        self.assertFalse(row['better'])
        self.env['res.currency.rate'].create({'currency_id': other.id, 'company_id': self.env.company.id,
                                              'name': fields.Date.today(), 'rate': 2.0})
        self._price(req, 'E', 100.0, currency_id=other.id)
        row = self._row(line)
        self.assertEqual((row['best']['vendor'], row['best']['cost']), ('Zz Vendor E', 50.0))

    def test_nobody_answered(self):
        order = self._order()
        self._ask(order=order)
        row = self._row(order._sa_buy_lines_make())
        self.assertEqual((row['best'], row['prices'], row['no_reply']), (False, [], 5))

    # ------------------------------------------------------------ red lines
    def test_the_warnings(self):
        Line = self.env['sa.buy.line'].with_user(self.manager)
        delivery = self.env['sa.delivery.settings'].sudo().get_settings()
        delivery.flow_end = 'delivery'
        self.assertFalse(Line.sa_vendor_orders()['warnings'])
        self.settings.pay_link_no_stock = 'accept'
        self.assertEqual(len(Line.sa_vendor_orders()['warnings']), 1)
        delivery.flow_end = 'order'
        self.assertEqual(len(Line.sa_vendor_orders()['warnings']), 2)

    # ------------------------------------------------------------ who sees it
    def test_only_sales_automation_users(self):
        outsider = new_test_user(self.env, 'zz-buy-out', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['sa.buy.line'].with_user(outsider).sa_vendor_orders()

    def test_a_user_sees_their_own_groups_and_changes_nothing(self):
        order, _req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        user = new_test_user(self.env, 'zz-buy-user', groups='base.group_user,sales_automation.group_sa_user')
        self.assertIsNone(self._row(line, user))
        self.employee.user_id = user
        self.assertEqual(self._row(line, user)['id'], line.id)
        with self.assertRaises(AccessError):
            line.with_user(user).write({'state': 'review'})
        with self.assertRaises(AccessError):
            line.with_user(self.manager).unlink()

    def test_another_companys_lines_are_not_shown(self):
        order, _req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        shop = self.env['res.company'].create({'name': 'Zz other shop'})
        self.env.flush_all()
        self.env.cr.execute('UPDATE sa_buy_line SET company_id = %s WHERE id = %s', [shop.id, line.id])
        self.env.invalidate_all()
        self.assertIsNone(self._row(line))

    def test_old_finished_ones_leave_the_screen(self):
        order, _req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        line.write({'state': 'cancelled'})
        self.assertTrue(self._row(line))
        self.env.flush_all()
        self.env.cr.execute('UPDATE sa_buy_line SET write_date = %s WHERE id = %s', [fields.Datetime.now() - timedelta(days=8), line.id])
        self.env.invalidate_all()
        self.assertIsNone(self._row(line))

    def test_looking_changes_and_sends_nothing(self):
        order, req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        self._price(req, 'E', 60.0)
        self.env.flush_all()

        def now():
            self.env.invalidate_all()
            return (line.read(), req.read(['state', 'agreed_price', 'quoted_price', 'best_quote_id', 'write_date']),
                    order.read(['amount_total', 'state', 'write_date']))
        before = now()
        self._row(line)
        self.env.flush_all()
        self.assertEqual(before, now())
        self.assertFalse(self.said or self.asked)
