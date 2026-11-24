# -*- coding: utf-8 -*-
"""Ordering from a vendor after the sale order (24 Nov 2026)."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.sales_automation.tests.test_only_listed import ListedCase
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestSupplyChoice(ListedCase):

    def setUp(self):
        super().setUp()
        self.settings = self.env['sa.ai.settings'].sudo().get_settings()
        self.settings.write({'margin_percent': 20.0, 'supply_mode': 'manual', 'vendor_choice_mode': 'auto', 'price_approval_enabled': False,
                             'supply_auto_start': 'paid', 'supply_auto_wait': 10, 'supply_auto_margin': 5.0, 'supply_auto_limit': 500.0})
        self.kumar, self.alpha, self.third, self.fourth = self.env['res.partner'].create(
            [{'name': 'Zz S%s' % n, 'phone': '+97150000410%s' % n} for n in range(4)])
        self.customer = self.env['res.partner'].create({'name': 'Zz buyer'})
        Picking = self.env.registry['stock.picking']
        self.sent, self.refused = [], False

        def send(rec, phone, body):
            if self.refused:
                return False
            self.sent.append((phone, body))
            return True
        for p in (patch.object(Picking, '_sa_tell_customer', lambda rec, *a, **k: True),
                  patch.object(Picking, '_sa_store_notify', lambda rec, *a, **k: True),
                  patch.object(Picking, '_sa_session', lambda rec: self.session),
                  patch.object(self.env.registry['whatsapp.session'], 'send_message', send)):
            p.start()
            self.addCleanup(p.stop)
        self.req, self.order, self.job = self._order()
        self.q20 = self._price(self.kumar, 20.0, 600)
        self.q24 = self._price(self.alpha, 24.0, 500)
        self.q20.is_best = True
        self.req.write({'best_quote_id': self.q20.id, 'sa_evaluated_on': fields.Datetime.now() - timedelta(minutes=5)})

    def _order(self, qty=1, more=False):
        req = self._req('zzboard q77660', product_id=self.product.id, state='order_created')
        req.sourcing_vendor_ids = [(6, 0, (self.kumar | self.alpha | self.third | self.fourth).ids)]
        lines = [(0, 0, {'product_id': self.product.product_variant_id.id, 'product_uom_qty': qty, 'price_unit': 24.0, 'tax_ids': [(5,)]})]
        if more:
            other = self.env['product.template'].create({'name': 'Zz other', 'type': 'consu', 'is_storable': True})
            lines.append((0, 0, {'product_id': other.product_variant_id.id, 'product_uom_qty': 1, 'price_unit': 5.0}))
        order = self.env['sale.order'].create({'partner_id': self.customer.id, 'order_line': lines})
        order.action_confirm()
        req.order_id = order
        job = order.picking_ids[:1]
        job.write({'sa_delivery_state': 'awaiting_shop'})
        return req, order, job

    def _price(self, partner, price, ago=0, req=None):
        req = req or self.req
        quote = self.env['sa.vendor.quote'].create({
            'request_id': req.id, 'partner_id': partner.id, 'price': price, 'matched_by': 'direct', 'vendor_phone': partner.phone,
            'currency_id': req.currency_id.id or self.env.company.currency_id.id})
        self.env.flush_all()
        self.env.cr.execute("UPDATE sa_vendor_quote SET create_date = (now() at time zone 'utc') - interval '%s seconds' WHERE id = %s", [ago, quote.id])
        self.env.invalidate_all()
        return quote

    def _pick(self, job=None):
        return (job or self.job)._sa_supply_prices()['recommended']

    # -------------------------------------------------------- the popup
    def test_the_chosen_one_while_nobody_is_lower(self):
        self.assertEqual((self._pick()['vendor_id'], self._pick()['total']), (self.kumar.id, 20.0))

    def test_a_late_lower_price_is_recommended(self):
        self._price(self.third, 19.0)
        pick = self._pick()
        self.assertEqual((pick['vendor_id'], pick['late'], pick['why']), (self.third.id, True, '1.00 less than Zz S0'))
        self.assertEqual(self.req.best_quote_id, self.q20, "the customer's price is not touched")
        self.assertFalse(self.said, 'the customer is not told')

    def test_a_late_higher_price_is_only_shown(self):
        self._price(self.fourth, 22.0)
        prices = self.job._sa_supply_prices()
        self.assertEqual(prices['recommended']['vendor_id'], self.kumar.id)
        self.assertIn((self.fourth.id, True), [(c['vendor_id'], c['late']) for c in prices['cards']])

    def test_the_same_price_later(self):
        self._price(self.third, 20.0)
        self.assertEqual(self._pick()['vendor_id'], self.kumar.id)

    def test_several_products_recommend_nothing(self):
        req, _order, job = self._order(more=True)
        self._price(self.kumar, 20.0, req=req)
        prices = job._sa_supply_prices()
        self.assertFalse(prices['recommended'])
        self.assertTrue(prices['why'] and prices['cards'])

    def test_quantity(self):
        req, _order, job = self._order(qty=3)
        self._price(self.kumar, 20.0, req=req)
        self.assertEqual((self._pick(job)['total'], job._sa_supply_prices()['sell']), (60.0, 72.0))

    def test_options_for_the_screen(self):
        data = self.env['stock.picking'].sa_store_supply_options(self.job.id)
        self.assertIn(self.kumar.id, [v['id'] for v in data['vendors']])
        self.assertEqual(data['prices']['recommended']['vendor_id'], self.kumar.id)

    def test_any_vendor_and_the_order_is_sent_once(self):
        self.env['stock.picking'].sa_store_act(self.job.id, 'supply_set', partner_id=self.alpha.id, cost=24.0,
                                               promised_date=fields.Date.to_string(fields.Date.today()), send=True)
        self.assertEqual((self.job.sa_supply_partner_id, self.job.sa_supply_waiting, self.job.sa_supply_by), (self.alpha, True, 'person'))
        self.assertEqual([p for p, _b in self.sent], [self.alpha.phone])
        self.assertIn('24.00', self.sent[0][1])
        self.assertTrue(self.job.sa_supply_sent_on)

    def test_the_line_while_the_goods_are_awaited(self):
        self.env['stock.picking'].sa_store_act(self.job.id, 'supply_set', partner_id=self.kumar.id, cost=20.0)
        self.assertIn('Waiting for the goods from Zz S0', self.job.sa_stage_text)
        self.assertNotIn('Dispatch', self.job.sa_stage_text)

    def test_who_was_asked_here(self):
        with patch.object(self.env.registry['stock.picking'], 'sa_store_queue', lambda rec, shop=None: {}):
            self.env['stock.picking'].sa_store_supply_ask(self.job.id, [self.vendor.id])
        data = self.env['stock.picking'].sa_store_supply_options(self.job.id)
        self.assertEqual([a['id'] for a in data['asked']], [self.vendor.id])
        self.assertEqual(self.job._sa_board_extra()['supply_asked_names'], self.vendor.name)
        self.assertEqual(self.job.sa_delivery_state, 'awaiting_shop', 'asked and left: not accepted')

    def test_asked_with_the_price_link(self):
        if not hasattr(self.env['sa.group.request'], '_sa_ask_vendor_confirm'):
            return
        Request, asked = self.env.registry['sa.group.request'], []
        self.req._sa_confirm_settings().sudo().write({'confirm_vendor_enabled': True})
        with patch.object(Request, '_sa_ask_vendor_confirm', lambda rec, session, vendor, name, qty, ask: asked.append((rec.id, vendor.id, qty)) or True), \
                patch.object(self.env.registry['stock.picking'], 'sa_store_queue', lambda rec, shop=None: {}):
            self.env['stock.picking'].sa_store_supply_ask(self.job.id, [self.vendor.id])
        self.assertEqual(asked, [(self.req.id, self.vendor.id, 1)])
        self.assertIn(self.vendor, self.req.sourcing_vendor_ids)
        self.assertFalse(self.sent, 'the link only, not the text as well')
        self.assertTrue(self.req._sa_supply_price_open(self.vendor))
        self.assertFalse(self.req._sa_supply_price_open(self.alpha))
        self._price(self.vendor, 18.0)
        pick = self._pick()
        self.assertEqual((pick['vendor_id'], pick['late']), (self.vendor.id, True))
        self.job.sa_supply_asked_on = fields.Datetime.now() - timedelta(days=2)
        self.assertFalse(self.req._sa_supply_price_open(self.vendor))

    def test_several_products_are_asked_in_words(self):
        _req, _order, job = self._order(more=True)
        with patch.object(self.env.registry['stock.picking'], 'sa_store_queue', lambda rec, shop=None: {}):
            self.env['stock.picking'].sa_store_supply_ask(job.id, [self.vendor.id])
        self.assertEqual([p for p, _b in self.sent], [self.vendor.phone])

    def test_the_chat_of_the_order(self):
        self.assertEqual(self.job._sa_board_extra()['request_id'], self.req.id)

    def test_no_past_day(self):
        for days, ok in ((-1, False), (0, True), (3, True)):
            day = fields.Date.to_string(fields.Date.context_today(self.job) + timedelta(days=days))
            if ok:
                self.env['stock.picking'].sa_store_act(self.job.id, 'supply_set', partner_id=self.kumar.id, cost=20.0, promised_date=day)
            else:
                with self.assertRaises(UserError):
                    self.env['stock.picking'].sa_store_act(self.job.id, 'supply_set', partner_id=self.kumar.id, cost=20.0, promised_date=day)

    def test_unticked_sends_nothing(self):
        self.env['stock.picking'].sa_store_act(self.job.id, 'supply_set', partner_id=self.kumar.id, cost=20.0)
        self.assertTrue(self.job.sa_supply_waiting)
        self.assertFalse(self.sent)

    def test_a_failed_send_keeps_the_order(self):
        self.refused = True
        self.env['stock.picking'].sa_store_act(self.job.id, 'supply_set', partner_id=self.kumar.id, cost=20.0, send=True)
        self.assertTrue(self.job.sa_supply_waiting)
        self.assertIn('Not sent', self.job.sa_supply_send_note)
        self.assertFalse(self.job.sa_supply_sent_on)

    # -------------------------------------------------------- by itself
    def _auto(self, paid_ago=20, **vals):
        self.settings.write(dict({'supply_mode': 'auto'}, **vals))
        self.settings.supply_auto_since = fields.Datetime.now() - timedelta(hours=1)
        at = fields.Datetime.now() - timedelta(minutes=paid_ago)
        p = patch.object(self.env.registry['stock.picking'], '_sa_supply_trigger', lambda rec, s: at if rec == self.job else False)
        p.start()
        self.addCleanup(p.stop)
        q = patch.object(self.env.registry['stock.picking'], 'sa_store_company_options', lambda rec, job_id: [{'ok': False}])
        q.start()
        self.addCleanup(q.stop)

    def _run(self):
        self.env['stock.picking']._cron_sa_supply_auto()

    def test_manual_orders_nothing(self):
        self._auto()
        self.settings.supply_mode = 'manual'
        self._run()
        self.assertFalse(self.job.sa_supply_waiting or self.sent)

    def test_the_lowest_is_ordered_once(self):
        self._price(self.third, 19.0)
        self._auto()
        self._run()
        self._run()
        self.assertEqual((self.job.sa_supply_partner_id, self.job.sa_supply_cost, self.job.sa_supply_by), (self.third, 19.0, 'auto'))
        self.assertEqual([p for p, _b in self.sent], [self.third.phone])

    def test_not_before_the_wait(self):
        self._auto(paid_ago=5)
        self._run()
        self.assertFalse(self.job.sa_supply_waiting or self.sent)

    def test_not_an_order_from_before_the_switch(self):
        self._auto(paid_ago=120)
        self._run()
        self.assertFalse(self.job.sa_supply_waiting or self.sent)

    def test_our_stock_comes_first(self):
        self._auto()
        with patch.object(self.env.registry['stock.picking'], 'sa_store_company_options', lambda rec, job_id: [{'ok': True}]):
            self._run()
        self.assertFalse(self.job.sa_supply_waiting or self.sent or self.job.sa_supply_auto_stop)

    def _stops(self, words, **vals):
        self._auto(**vals)
        self._run()
        self._run()
        self.assertFalse(self.job.sa_supply_waiting or self.sent)
        self.assertIn(words, self.job.sa_supply_auto_stop)

    def test_stops_for_the_margin(self):
        self._stops('margin', supply_auto_margin=50.0)

    def test_stops_for_the_amount(self):
        self._stops('above', supply_auto_limit=10.0)

    def test_stops_without_a_number(self):
        self.kumar.phone = False
        self._stops('no WhatsApp number')

    def test_stops_without_a_price(self):
        self.req.best_quote_id = False
        (self.q20 | self.q24).unlink()
        self._stops('No vendor has given a price')

    def test_stops_when_it_is_not_sent(self):
        self.refused = True
        self._stops('Not sent')

    def test_trigger(self):
        self.settings.supply_auto_start = 'signed'
        self.assertFalse(self.job._sa_supply_trigger(self.settings))
        self.order.signed_on = fields.Datetime.now()
        self.assertEqual(self.job._sa_supply_trigger(self.settings), self.order.signed_on)
        self.settings.supply_auto_start = 'paid'
        self.assertFalse(self.job._sa_supply_trigger(self.settings), 'not paid, and cash never counts')

    def test_switching_on_sets_the_start(self):
        self.settings.supply_auto_since = False
        self.settings.supply_mode = 'auto'
        self.assertTrue(self.settings.supply_auto_since)
