# -*- coding: utf-8 -*-
"""The vendors' reply window (owner, 23 Nov 2026)."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_only_listed import ListedCase


@tagged('post_install', '-at_install')
class TestVendorWindow(ListedCase):

    def setUp(self):
        super().setUp()
        self.settings = self.env['sa.ai.settings'].sudo().get_settings()
        self.settings.write({'sourcing_window_minutes': 3, 'margin_percent': 20.0, 'price_approval_enabled': False})
        self.vendors = self.env['res.partner'].create([{'name': 'Zz V%s' % n, 'phone': '+9715000020%02d' % n} for n in range(5)])

    def _asked(self, left=0, **vals):
        """Asked 5 vendors; the window has `left` seconds to go."""
        return self._req('zzboard q77660', **dict({
            'product_id': self.product.id, 'state': 'sourcing', 'sourcing_vendor_ids': [(6, 0, self.vendors.ids)],
            'sourcing_deadline': fields.Datetime.now() + timedelta(seconds=left)}, **vals))

    def _price(self, req, n, price, ago=60, **vals):
        quote = self.env['sa.vendor.quote'].create(dict({
            'request_id': req.id, 'partner_id': self.vendors[n].id, 'price': price, 'matched_by': 'direct',
            'currency_id': req.currency_id.id or self.env.company.currency_id.id}, **vals))
        self.env.flush_all()
        self.env.cr.execute("UPDATE sa_vendor_quote SET create_date = (now() at time zone 'utc') - interval '%s seconds' WHERE id = %s",
                            [ago, quote.id])
        quote.invalidate_recordset(['create_date'])
        return quote

    def test_two_of_five(self):
        req = self._asked()
        b, a = self._price(req, 1, 22.0), self._price(req, 0, 20.0)
        req._close_sourcing()
        self.assertEqual((req.state, req.best_quote_id, req.quoted_price), ('quoted', a, 24.0))
        self.assertEqual((a.is_best, a.sa_rank, b.sa_rank, a.sa_in_window, a.sa_sell_price), (True, 1, 2, True, 24.0))
        self.assertTrue(req.sa_evaluated_on)
        self.assertEqual(req.sa_margin_used, 20.0)

    def test_not_before_its_time(self):
        req = self._asked(left=100)
        self._price(req, 0, 20.0)
        self.assertFalse(req._close_sourcing())
        self.assertEqual((req.state, req.sa_evaluated_on), ('sourcing', False))

    def test_equal_prices_the_earlier_one(self):
        req = self._asked()
        self._price(req, 0, 20.0, ago=10)
        early = self._price(req, 1, 20.0, ago=90)
        req._close_sourcing()
        self.assertEqual(req.best_quote_id, early)

    def test_the_newest_price_of_a_vendor(self):
        req = self._asked()
        old = self._price(req, 0, 15.0, ago=90)
        new = self._price(req, 0, 25.0, ago=30)
        other = self._price(req, 1, 22.0, ago=30)
        req._close_sourcing()
        self.assertEqual((req.best_quote_id, old.sa_rank, new.sa_rank), (other, 0, 2))

    def test_accept_does_not_start_the_window_again(self):
        req = self._asked(left=60)
        deadline = req.sourcing_deadline
        req._sa_vendor_window_again()
        req._sa_wechat_extend_window()
        req._sa_ask_vendor_price(self.session, '971500002000')
        self.assertEqual(req.sourcing_deadline, deadline)

    def test_a_held_price_is_not_waited_for(self):
        req = self._asked(sa_vendor_yes_ids=[(6, 0, self.vendors[0].ids)])
        req._sa_hold_price(self.vendors[0].id, self.vendors[0].phone, 'V0', 100.0, 'XXX')
        req._close_sourcing()
        self.assertTrue(req.sa_price_stalled)

    def test_yes_without_a_price_is_waited_for_once(self):
        req = self._asked(sa_vendor_yes_ids=[(6, 0, self.vendors[0].ids)])
        req._close_sourcing()
        self.assertEqual((req.state, req.sa_window_extended, req.sa_price_stalled), ('sourcing', True, False))
        self.assertGreater(req.sourcing_deadline, fields.Datetime.now() + timedelta(seconds=150))
        req.sourcing_deadline = fields.Datetime.now()
        req._close_sourcing()
        self.assertTrue(req.sa_price_stalled, 'then a person')

    def test_a_price_is_not_waited_past_for_a_yes(self):
        req = self._asked(sa_vendor_yes_ids=[(6, 0, self.vendors[1].ids)])
        self._price(req, 0, 20.0)
        req._close_sourcing()
        self.assertEqual(req.state, 'quoted')

    def test_nobody(self):
        req = self._asked()
        req._close_sourcing()
        self.assertEqual((req.sa_price_stalled, req.sa_evaluated_on), (True, False))

    def test_first_price_after_nobody_answered(self):
        req = self._asked()
        req._close_sourcing()
        quote = self._price(req, 0, 20.0, ago=0)
        req._sa_vendor_price_in(quote)
        req._close_sourcing()
        self.assertEqual((req.state, req.quoted_price, quote.sa_late), ('quoted', 24.0, False))

    def test_a_price_between_the_end_and_the_job(self):
        req = self._asked()
        req.sourcing_deadline = fields.Datetime.now() - timedelta(seconds=30)
        self._price(req, 0, 20.0, ago=5)
        req._close_sourcing()
        self.assertEqual(req.state, 'quoted', 'better than "needs a price"')
        req = self._asked()
        req.sourcing_deadline = fields.Datetime.now() - timedelta(seconds=30)
        a, b = self._price(req, 0, 20.0, ago=60), self._price(req, 1, 10.0, ago=5)
        req._close_sourcing()
        self.assertEqual(req.best_quote_id, a, 'in time wins over later')
        self.assertEqual(b.sa_rank, 0)

    def test_late_and_cheaper(self):
        req = self._asked()
        self._price(req, 0, 20.0)
        req._close_sourcing()
        dearer = self._price(req, 1, 30.0, ago=0)
        self.assertTrue(dearer.sa_late)
        self.assertFalse(req.sa_better_quote_id)
        late = self._price(req, 2, 18.0, ago=0)
        self.assertEqual((late.sa_late, req.sa_better_quote_id, req.quoted_price), (True, late, 24.0), 'shown, not used by itself')
        with self.assertRaises(UserError):
            dearer.action_sa_use_late()
        self.said.clear()
        late.action_sa_use_late()
        self.assertEqual((req.best_quote_id, round(req.quoted_price, 2)), (late, 21.6))
        self.assertTrue(any('better price' in s for s in self.said))

    def test_not_after_the_customer_answered(self):
        req = self._asked()
        self._price(req, 0, 20.0)
        req._close_sourcing()
        late = self._price(req, 2, 18.0, ago=0)
        req.state = 'awaiting_order_confirm'
        self.assertFalse(req.sa_better_quote_id)
        with self.assertRaises(UserError):
            late.action_sa_use_late()

    def test_a_late_price_can_be_typed_on_the_page(self):
        req = self._asked()
        self._price(req, 0, 20.0)
        req._close_sourcing()
        link = self.env['sa.confirm.link'].create({'request_id': req.id, 'kind': 'vendor', 'channel': 'whatsapp', 'partner_id': self.vendors[1].id})
        self.assertTrue(link._vendor_price_open())
        req.sa_evaluated_on = fields.Datetime.now() - timedelta(days=2)
        self.assertFalse(link._vendor_price_open())

    def test_two_closers(self):
        req = self._asked()
        self._price(req, 0, 20.0)
        with patch.object(self.env.registry['sa.group.request'], '_sa_lock_enquiry', lambda self: False):
            self.assertFalse(req._close_sourcing())
        self.assertEqual(req.state, 'sourcing')
        req._close_sourcing()
        said = list(self.said)
        req._close_sourcing()
        self.assertEqual(self.said, said, 'told once')

    def test_one_bad_enquiry_stops_no_other(self):
        bad, good = self._asked(), self._asked()
        self._price(good, 0, 20.0)
        real = self.env.registry['sa.group.request']._apply_winning_quote
        self._price(bad, 0, 20.0)

        def boom(rec, quote):
            if rec.id == bad.id:
                raise ValueError('x')
            return real(rec, quote)
        with patch.object(self.env.registry['sa.group.request'], '_apply_winning_quote', boom), self.assertLogs(level='ERROR'):
            self.env['sa.group.request']._cron_close_sourcing()
        self.assertEqual((bad.state, good.state), ('dropped', 'quoted'))

    def test_the_job_is_woken_at_the_deadline(self):
        req = self._asked(left=120)
        cron = self.env.ref('sales_automation.cron_sa_close_sourcing')
        before = self.env['ir.cron.trigger'].search([('cron_id', '=', cron.id)])
        req._sa_wake_at(req.sourcing_deadline)
        new = self.env['ir.cron.trigger'].search([('cron_id', '=', cron.id)]) - before
        self.assertEqual(new.mapped('call_at'), [req.sourcing_deadline + timedelta(seconds=1)])

    def test_quote_now(self):
        req = self._asked(left=300)
        self._price(req, 0, 20.0)
        req.action_close_sourcing_now()
        self.assertEqual(req.state, 'quoted')

    def test_screens(self):
        self.env['sa.vendor.quote'].get_views([(False, 'list'), (False, 'form')])
        self.env['sa.group.request'].get_views([(False, 'list'), (False, 'form')])


@tagged('post_install', '-at_install')
class TestPayLinkRule(ListedCase):

    def setUp(self):
        super().setUp()
        self.settings = self.env['sa.ai.settings'].sudo().get_settings()
        self.settings.write({'pay_link_in_stock': 'sign', 'pay_link_no_stock': 'accept'})
        self.partner = self.env['res.partner'].create({'name': 'Zz pays', 'phone': '+919800077744'})
        self.end = 'delivery'
        box = self
        for p in (patch.object(self.env.registry['sa.group.request'], '_sa_flow_end', lambda self: box.end),
                  patch.object(self.env.registry['sa.group.request'], '_sa_pay_link_any_state', lambda self, order: 'PAYLINK')):
            p.start()
            self.addCleanup(p.stop)

    def _order(self, stock=None):
        req = self._req('zzboard q77660', product_id=self.product.id, state='order_created', sa_sign_link_sent_on=fields.Datetime.now())
        order = self.env['sale.order'].create({'partner_id': self.partner.id, 'order_line': [
            (0, 0, {'product_id': self.product.product_variant_id.id, 'product_uom_qty': 1, 'price_unit': 10.0})]})
        req.order_id = order.id
        if stock is not None:
            p = patch.object(self.env.registry['sa.group.request'], '_sa_lines_in_stock', staticmethod(lambda order: stock))
            p.start()
            self.addCleanup(p.stop)
        return req, order

    def _signed(self, stock, in_stock, no_stock, end='delivery'):
        self.settings.write({'pay_link_in_stock': in_stock, 'pay_link_no_stock': no_stock})
        self.end = end
        req, order = self._order(stock)
        req._sa_group_signed(order)
        task = self.env['sa.after.task'].search([('request_id', '=', req.id), ('step', '=', 'signed')])
        return req, order, task.mode, bool(req.sa_pay_link_sent_on)

    def test_every_choice(self):
        for stock in (True, False):
            for rule in ('sign', 'accept', 'never'):
                other = 'never' if rule != 'never' else 'sign'
                args = (rule, other) if stock else (other, rule)
                req, order, mode, sent = self._signed(stock, *args)
                self.assertEqual(sent, rule == 'sign', (stock, rule))
                want = {'sign': 'pay' if stock else 'pay_goods'}.get(rule, 'wait' if stock else 'wait_goods')
                self.assertEqual(mode, want, (stock, rule))
                words = req._sa_signed_words(order, mode)
                self.assertEqual('PAYLINK' in words, rule == 'sign')

    def test_as_it_was(self):
        self.assertEqual(self._signed(True, 'sign', 'accept')[2:], ('pay', True))
        self.assertEqual(self._signed(False, 'sign', 'accept')[2:], ('wait_goods', False))

    def test_no_stock_says_that_it_is_reserved(self):
        req, order, mode, _sent = self._signed(False, 'sign', 'sign')
        self.assertIn('arranging', req._sa_signed_words(order, mode))

    def test_without_a_counter_accept_is_the_signature(self):
        self.assertEqual(self._signed(False, 'sign', 'accept', end='paid')[2:], ('pay_goods', True))
        self.assertFalse(self._signed(False, 'sign', 'never', end='paid')[3])
        for end in ('order', 'invoice'):
            self.assertEqual(self._signed(True, 'sign', 'sign', end=end)[2:], ('stop', False))

    def test_by_hand(self):
        req, order, _mode, _sent = self._signed(False, 'never', 'never')
        with patch.object(self.env.registry['sale.order'], '_has_to_be_signed', lambda self: False):
            self.assertTrue(req._sa_send_pay_link_now())
        self.assertTrue(req.sa_pay_link_sent_on)
        self.assertTrue(any('PAYLINK' in s for s in self.said))
        with patch.object(self.env.registry['sale.order'], '_has_to_be_signed', lambda self: True), self.assertRaises(UserError):
            req._sa_send_pay_link_now()
        with patch.object(self.env.registry['sa.group.request'], '_sa_order_is_paid', lambda self, o: True), self.assertRaises(UserError):
            req._sa_send_pay_link_now()

    def test_words_and_screen(self):
        self.assertIn('signs', self.settings.pay_link_words)
        view = self.env.ref('sales_automation.view_sa_settings_payments_form')
        self.env['sa.ai.settings'].get_view(view.id, 'form')
        self.assertIn('action_sa_send_pay_link', self.env['sale.order'].get_view(self.env.ref('sale.view_order_form').id, 'form')['arch'])
