# -*- coding: utf-8 -*-
"""The purchase behind "order it in" (24 Nov 2026)."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.sales_automation.tests.test_only_listed import ListedCase
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged


@tagged('post_install', '-at_install')
class TestBuy(ListedCase):

    def setUp(self):
        super().setUp()
        self.kumar, self.alpha = self.env['res.partner'].create([
            {'name': 'Zz B Kumar', 'phone': '+971500005101', 'email': 'zz@example.com'}, {'name': 'Zz B Alpha', 'phone': '+971500005102'}])
        self.customer = self.env['res.partner'].create({'name': 'Zz B buyer'})
        Picking = self.env.registry['stock.picking']
        self.sent = []
        for p in (patch.object(Picking, '_sa_tell_customer', lambda rec, *a, **k: True),
                  patch.object(Picking, '_sa_store_notify', lambda rec, *a, **k: True),
                  patch.object(Picking, '_sa_session', lambda rec: self.session),
                  patch.object(self.env.registry['whatsapp.session'], 'send_message', lambda rec, phone, body: self.sent.append((phone, body)) or True)):
            p.start()
            self.addCleanup(p.stop)
        self.env['sa.ai.settings'].sudo().get_settings().write({'supply_mode': 'manual'})
        self.mails = self.env['mail.mail'].search_count([])

    def _job(self, qty=1, product=None, more=False):
        product = product or self.product
        lines = [(0, 0, {'product_id': product.product_variant_id.id, 'product_uom_qty': qty, 'price_unit': 24.0, 'tax_ids': [(5,)]})]
        if more:
            other = self.env['product.template'].create({'name': 'Zz B other', 'type': 'consu', 'is_storable': True})
            lines.append((0, 0, {'product_id': other.product_variant_id.id, 'product_uom_qty': 1, 'price_unit': 5.0, 'tax_ids': [(5,)]}))
        order = self.env['sale.order'].create({'partner_id': self.customer.id, 'order_line': lines})
        order.action_confirm()
        job = order.picking_ids[:1]
        job.write({'sa_delivery_state': 'awaiting_shop'})
        return job

    def _set(self, job, partner=None, cost=20.0, **kw):
        return self.env['stock.picking'].sa_store_act(job.id, 'supply_set', partner_id=(partner or self.kumar).id, cost=cost, **kw)

    def _arrived(self, job, **kw):
        return self.env['stock.picking'].sa_store_act(job.id, 'supply_arrived', **kw)

    def _stock(self, product=None):
        product = (product or self.product).product_variant_id
        product.invalidate_recordset()
        return product.qty_available

    def test_made_and_confirmed_once(self):
        job = self._job()
        day = fields.Date.context_today(job) + timedelta(days=2)
        self._set(job, promised_date=fields.Date.to_string(day))
        po = job.sa_supply_po_id
        self.assertEqual((po.partner_id, po.state, po.company_id, po.amount_untaxed), (self.kumar, 'purchase', job.company_id, 20.0))
        self.assertEqual((po.order_line.product_id, po.order_line.product_qty, po.order_line.price_unit), (self.product.product_variant_id, 1, 20.0))
        self.assertIn(job.sale_id.name, po.origin)
        job._sa_buy_make()
        self.env['stock.picking'].sa_store_act(job.id, 'supply_po')
        self.assertEqual(self.env['purchase.order'].search_count([('partner_id', '=', self.kumar.id)]), 1)
        self.assertEqual(self.env['mail.mail'].search_count([]), self.mails, 'no email')
        self.assertFalse(self.sent, 'no message')

    def test_the_price_for_several_pieces(self):
        job = self._job(qty=3)
        self._set(job, cost=60.0)
        self.assertEqual((job.sa_supply_po_id.order_line.product_qty, job.sa_supply_po_id.order_line.price_unit), (3, 20.0))

    def test_arrived_brings_stock_and_a_draft_bill(self):
        job = self._job()
        self._set(job)
        before = self._stock()
        self._arrived(job)
        self.assertEqual(self._stock(), before + 1)
        self.assertFalse(job.sa_supply_waiting)
        self.assertEqual(job.state, 'assigned', 'kept for the customer')
        bill = job.sa_supply_po_id.invoice_ids
        self.assertEqual((len(bill), bill.state, bill.amount_untaxed), (1, 'draft', 20.0))
        self._arrived(job)
        self.assertEqual((self._stock(), len(job.sa_supply_po_id.invoice_ids)), (before + 1, 1), 'a second tap does nothing')

    def test_the_goods_are_kept_for_their_own_order(self):
        older, job = self._job(), self._job()
        older.action_assign()
        self._set(job)
        self._arrived(job)
        self.assertEqual(job.state, 'assigned')
        self.assertNotEqual(older.state, 'assigned', 'it waited longer, but the goods were not bought for it')

    def test_a_part_is_kept_too(self):
        older, job = self._job(), self._job(qty=3)
        older.action_assign()
        self._set(job, cost=60.0)
        self._arrived(job, qty=2)
        self.assertEqual(sum(job.move_ids.mapped('quantity')), 2)
        self.assertNotEqual(older.state, 'assigned')

    def test_cancelling_the_purchase_keeps_the_delivery(self):
        job = self._job()
        self._set(job)
        job._sa_buy_cancel('zz')
        self.assertEqual(job.sa_supply_po_id.state, 'cancel')
        self.assertNotIn(job.state, ('cancel', 'done'))
        product = self.product.product_variant_id
        self.env['stock.quant']._update_available_quantity(product, job.location_id, 1)
        job.action_assign()
        self.assertEqual(job.state, 'assigned', 'stock of ours can be used again')

    def test_a_part_came(self):
        job = self._job(qty=3)
        self._set(job, cost=60.0)
        before = self._stock()
        self._arrived(job, qty=2)
        self.assertEqual((self._stock(), job.sa_supply_waiting), (before + 2, True))
        self.assertIn('2 of 3', job.sa_supply_po_note)
        self._arrived(job, qty=1)
        self.assertEqual((self._stock(), job.sa_supply_waiting), (before + 3, False))
        self.assertEqual(sum(job.sa_supply_po_id.invoice_ids.mapped('amount_untaxed')), 60.0)
        self.assertEqual(set(job.sa_supply_po_id.invoice_ids.mapped('state')), {'draft'})

    def test_first_the_purchase_then_the_goods(self):
        job = self._job()
        job.write({'sa_supply_waiting': True, 'sa_supply_partner_id': self.kumar.id, 'sa_supply_cost': 20.0})
        self.assertTrue(job._sa_board_extra()['arrive_stop'])
        with self.assertRaises(UserError):
            self._arrived(job)
        self.assertTrue(job.sa_supply_waiting)
        self.env['stock.picking'].sa_store_act(job.id, 'supply_po')
        self.assertFalse(job._sa_board_extra()['arrive_stop'])
        self._arrived(job)
        self.assertFalse(job.sa_supply_waiting)

    def test_not_more_than_ordered(self):
        job = self._job()
        self._set(job)
        for qty in (2, -1):
            with self.assertRaises(UserError):
                self._arrived(job, qty=qty)
        self.assertTrue(job.sa_supply_waiting)

    def test_several_products_are_a_draft(self):
        job = self._job(more=True)
        self._set(job, cost=30.0)
        self.assertEqual((job.sa_supply_po_id.state, len(job.sa_supply_po_id.order_line)), ('draft', 2))
        with self.assertRaises(UserError):
            self._arrived(job)

    def test_no_vendor_no_purchase_and_as_before(self):
        job = self._job()
        self.env['stock.picking'].sa_store_act(job.id, 'supply_set', cost=20.0)
        self.assertFalse(job.sa_supply_po_id)
        self.assertIn('no vendor', job.sa_supply_po_note)
        before = self._stock()
        self._arrived(job)
        self.assertEqual((self._stock(), job.sa_supply_waiting), (before, False))

    def test_a_failure_keeps_the_order(self):
        job = self._job()

        def broken(rec):
            raise UserError('zz broken')
        with patch.object(self.env.registry['purchase.order'], 'button_confirm', broken):
            self._set(job)
        self.assertTrue(job.sa_supply_waiting)
        self.assertFalse(job.sa_supply_po_id)
        self.assertIn('zz broken', job.sa_supply_po_note)
        self.assertTrue(job._sa_board_extra()['po_can_make'])
        self.env['stock.picking'].sa_store_act(job.id, 'supply_po')
        self.assertEqual(job.sa_supply_po_id.state, 'purchase')

    def test_another_vendor(self):
        job = self._job()
        self._set(job)
        first = job.sa_supply_po_id
        self._set(job, partner=self.alpha, cost=24.0)
        self.assertEqual((first.state, job.sa_supply_po_id.partner_id, job.sa_supply_po_id.amount_untaxed), ('cancel', self.alpha, 24.0))

    def test_cancelled_before_the_goods(self):
        job = self._job()
        self._set(job)
        job.action_cancel()
        self.assertEqual(job.sa_supply_po_id.state, 'cancel')

    def test_cancelled_after_the_goods(self):
        job = self._job()
        self._set(job)
        self._arrived(job)
        job.action_cancel()
        self.assertEqual(job.sa_supply_po_id.state, 'purchase')
        self.assertIn('stays', job.sa_supply_po_note)

    def test_serial_numbers_are_typed_in_odoo(self):
        product = self.env['product.template'].create({'name': 'Zz B serial', 'type': 'consu', 'is_storable': True, 'tracking': 'serial'})
        job = self._job(product=product)
        self._set(job)
        self.assertTrue(job._sa_board_extra()['po']['receipt_url'])
        with self.assertRaises(UserError):
            self._arrived(job)
        self.assertTrue(job.sa_supply_waiting)

    def test_a_counter_user_without_purchase_rights(self):
        user = new_test_user(self.env, 'zz_buy_counter', groups='base.group_user,stock.group_stock_user,sales_team.group_sale_salesman')
        job = self._job()
        self.env['stock.picking'].with_user(user).sa_store_act(job.id, 'supply_set', partner_id=self.kumar.id, cost=20.0)
        self.assertEqual(job.sa_supply_po_id.state, 'purchase')
        self.assertFalse(job.with_user(user).sudo(False)._sa_board_extra()['po']['can_open'])

    def test_the_vendor_gets_the_number_in_one_message(self):
        job = self._job()
        self._set(job, send=True)
        self.assertEqual([p for p, _b in self.sent], [self.kumar.phone])
        self.assertIn('Purchase: *%s*' % job.sa_supply_po_id.name, self.sent[0][1])

    def test_without_a_purchase_the_message_still_goes(self):
        job = self._job()

        def broken(rec):
            raise UserError('zz broken')
        with patch.object(self.env.registry['purchase.order'], 'button_confirm', broken):
            self._set(job, send=True)
        self.assertEqual(len(self.sent), 1)
        self.assertNotIn('Purchase:', self.sent[0][1])

    def _automatic(self, job):
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        settings.write({'supply_mode': 'auto', 'supply_auto_wait': 0, 'supply_auto_margin': 0.0, 'supply_auto_limit': 0.0})
        settings.supply_auto_since = fields.Datetime.now() - timedelta(hours=1)
        Picking, quote = self.env.registry['stock.picking'], self.env['sa.vendor.quote'].create({
            'request_id': self._req('zzboard q77660', product_id=self.product.id).id, 'partner_id': self.kumar.id, 'price': 20.0,
            'matched_by': 'direct', 'currency_id': self.env.company.currency_id.id})
        prices = {'cards': [], 'why': '', 'sell': 24.0, 'currency': 'X', 'qty': 1, 'chosen': False, 'recommended': {
            'quote_id': quote.id, 'vendor_id': self.kumar.id, 'vendor': 'Zz B Kumar', 'unit': 20.0, 'total': 20.0, 'why': 'lowest price',
            'late': False, 'phone': True}}
        for p in (patch.object(Picking, '_sa_supply_prices', lambda rec: prices),
                  patch.object(Picking, '_sa_supply_trigger', lambda rec, s: fields.Datetime.now() - timedelta(minutes=5) if rec == job else False),
                  patch.object(Picking, 'sa_store_company_options', lambda rec, i: [])):
            p.start()
            self.addCleanup(p.stop)
        self.env['stock.picking']._cron_sa_supply_auto()

    def test_automatic_sends_the_number(self):
        job = self._job()
        self._automatic(job)
        self.assertEqual((len(self.sent), job.sa_supply_waiting, job.sa_supply_po_id.state), (1, True, 'purchase'))
        self.assertIn(job.sa_supply_po_id.name, self.sent[0][1])
        self.assertEqual(self.env['purchase.order'].search_count([('partner_id', '=', self.kumar.id)]), 1)

    def test_automatic_not_sent_leaves_no_purchase(self):
        job = self._job()
        with patch.object(self.env.registry['whatsapp.session'], 'send_message', lambda rec, phone, body: False):
            self._automatic(job)
        self.assertFalse(job.sa_supply_waiting or job.sa_supply_partner_id)
        self.assertIn('Not sent', job.sa_supply_auto_stop)
        self.assertFalse(self.env['purchase.order'].search_count([('partner_id', '=', self.kumar.id)]))

    def test_automatic_makes_one_too(self):
        job = self._job()
        self.env['stock.picking'].sa_store_supply_set(job.id, partner_id=self.kumar.id, cost=20.0, by='auto', reason='lowest price')
        self.assertEqual((job.sa_supply_po_id.state, job.sa_supply_by), ('purchase', 'auto'))

    def test_orders_that_wait_already(self):
        job = self._job()
        job.write({'sa_supply_waiting': True, 'sa_supply_partner_id': self.kumar.id, 'sa_supply_cost': 20.0})
        self.assertTrue(job._sa_board_extra()['po_can_make'])
        self.assertFalse(job.sa_supply_po_id, 'nothing by itself')
        self.env['stock.picking'].sa_store_act(job.id, 'supply_po')
        self.assertTrue(job.sa_supply_po_id)
