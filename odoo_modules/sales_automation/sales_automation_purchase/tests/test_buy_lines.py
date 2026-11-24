# -*- coding: utf-8 -*-
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.sa_buy_line import MOVES, STATES
from .common import BuyCase


@tagged('post_install', '-at_install')
class TestBuyLines(BuyCase):

    def test_a_paid_item_not_in_stock_is_on_the_list_once(self):
        order, req, _a = self._ravi()
        made = order._sa_buy_lines_make()
        self.assertEqual((made.state, made.qty, made.sell_unit, made.request_id), ('waiting', 1.0, 100.0, req))
        self.assertEqual(made.order_id, order)
        self.assertFalse(order._sa_buy_lines_make(), 'a second look makes nothing')
        self.assertEqual(len(req.sa_buy_line_ids), 1)

    def test_not_paid_or_not_confirmed_is_not_on_the_list(self):
        type(self).paid = False
        order, _req, _a = self._ravi()
        self.assertFalse(order._sa_buy_lines_make())
        type(self).paid = True
        draft = self._order(confirm=False)
        self._ask(order=draft)
        self.assertFalse(draft._sa_buy_lines_make())

    def test_an_order_without_an_enquiry_is_not_on_the_list(self):
        self.assertFalse(self._order()._sa_buy_lines_make())

    def test_everything_in_stock_is_not_on_the_list(self):
        self._stock(5)
        order, req, _a = self._ravi()
        self.assertFalse(order._sa_buy_lines_make())
        self.assertTrue(req.sa_buy_checked_on, 'looked at, so the sweep leaves it')

    def test_only_what_is_missing_is_bought(self):
        self._stock(2)
        order, _req, _a = self._ravi(qty=5)
        self.assertEqual(order._sa_buy_lines_make().qty, 3.0)

    def test_two_enquiries_on_one_order_line(self):
        order = self._order(qty=5)
        one, two = self._ask(2, order=order), self._ask(3, order=order)
        made = order._sa_buy_lines_make()
        self.assertEqual({line.request_id: line.qty for line in made}, {one: 2.0, two: 3.0})
        self.assertEqual(len(made.sale_line_id), 1)

    def test_two_enquiries_partly_in_stock_never_buy_too_much(self):
        self._stock(1)
        order = self._order(qty=5)
        self._ask(2, order=order)
        self._ask(3, order=order)
        self.assertEqual(sum(order._sa_buy_lines_make().mapped('qty')), 4.0)

    def test_the_line_at_the_agreed_price(self):
        order = self._order(qty=1, price=100.0, confirm=False)
        order.write({'order_line': [(0, 0, {'product_id': self.speaker.id, 'product_uom_qty': 1,
                                            'price_unit': 90.0, 'tax_ids': [(6, 0, [])]})]})
        order.action_confirm()
        req = self._ask(1, 90.0, order=order)
        self.assertEqual(order._sa_buy_lines_make().sell_unit, 90.0)
        self.assertEqual(req.sa_buy_line_ids.sale_line_id.price_unit, 90.0)

    def test_uncounted_goods_only_when_vendors_priced_them(self):
        thing = self.env['product.template'].create({'name': 'Zz uncounted', 'type': 'consu', 'is_storable': False}).product_variant_id
        order = self._order(product=thing)
        req = self._ask(order=order, product=thing)
        self.assertFalse(order._sa_buy_lines_make())
        req.best_quote_id = self._price(req, 'A', 80.0)
        self.assertEqual(order._sa_buy_lines_make().qty, 1.0)

    def test_nothing_of_the_order_changes(self):
        order, req, _a = self._ravi()
        line = order.order_line

        def now():
            return (order.amount_total, line.price_unit, order.state, req.state, req.agreed_price, req.best_quote_id,
                    self.speaker.qty_available, len(order.picking_ids), len(order.invoice_ids))
        before = now()
        order._sa_buy_lines_make()
        self._price(req, 'E', 60.0)
        self.env.invalidate_all()
        self.assertEqual(before, now())
        self.assertFalse(self.said or self.asked, 'nothing is sent')

    # ------------------------------------------------------------ the states
    def test_the_moves(self):
        order, _req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        self.env.flush_all()
        names = [s for s, _n in STATES]
        for old in names:
            for new in names:
                self.env.cr.execute('UPDATE sa_buy_line SET state = %s WHERE id = %s', [old, line.id])
                line.invalidate_recordset()
                if new == old or new in MOVES[old]:
                    line.write({'state': new})
                    self.env.flush_all()
                else:
                    with self.assertRaises(UserError, msg='%s -> %s' % (old, new)):
                        line.write({'state': new})

    def test_what_was_paid_is_frozen(self):
        order, _req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        with self.assertRaises(UserError):
            line.write({'sell_unit': 90.0})
        with self.assertRaises(UserError):
            line.write({'product_id': self.product.product_variant_id.id})
        line.write({'sell_unit': 100.0})

    def test_cancelling_the_order(self):
        order, _req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        order.write({'state': 'cancel'})
        self.assertEqual(line.state, 'cancelled')

    def test_cancelling_leaves_what_a_vendor_was_told(self):
        order, _req, _a = self._ravi()
        line = order._sa_buy_lines_make()
        for state in ('review', 'selected', 'po_draft', 'ordered'):
            line.write({'state': state})
        order.write({'state': 'cancel'})
        self.assertEqual(line.state, 'ordered')

    # ------------------------------------------------------------ when
    def test_the_sweep_takes_what_was_missed(self):
        _order, req, _a = self._ravi()
        self.env['sa.buy.line']._cron_buy_sweep()
        self.assertEqual(req.sa_buy_line_ids.state, 'waiting')
        _old_order, old, _a = self._ravi()
        old.sa_paid_on = fields.Datetime.now() - timedelta(days=5)
        self.env['sa.buy.line']._cron_buy_sweep()
        self.assertFalse(old.sa_buy_line_ids, 'older orders are left alone')

    def test_a_failure_never_stops_the_payment_and_is_tried_again(self):
        order, req, _a = self._ravi()
        with patch.object(self.env.registry['sale.order'], '_sa_buy_requests', side_effect=RuntimeError('zz')), \
                self.assertLogs('odoo.addons.sales_automation_purchase', 'ERROR'):
            self.assertFalse(req._sa_buy_check(order))
        self.assertFalse(req.sa_buy_checked_on)
        self.env['sa.buy.line']._cron_buy_sweep()
        self.assertTrue(req.sa_buy_line_ids)

    def test_the_payment_puts_it_on_the_list(self):
        order, req, _a = self._ravi()
        Request = self.env.registry['sa.group.request']
        with patch.object(Request, '_sa_paid_invoice', lambda self, o: o.invoice_ids), \
                patch.object(Request, '_sa_paid_send_invoice', lambda self, inv: True), \
                patch.object(Request, '_sa_paid_after', lambda self, o: True), \
                patch.object(Request, '_sa_pay_mail', lambda self, o: True):
            req.with_context(sa_after_now=True)._sa_group_confirmed(order)
        self.assertTrue(req.sa_paid_told_on)
        self.assertEqual(req.sa_buy_line_ids.qty, 1.0)
