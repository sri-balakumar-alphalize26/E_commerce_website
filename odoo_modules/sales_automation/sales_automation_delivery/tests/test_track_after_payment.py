# -*- coding: utf-8 -*-
"""The live tracking link waits for the payment (owner, 22 Nov 2026).

An order to be paid online gets the link only once paid; cash on delivery
gets it straight away, like any online shop. Nothing is sent here: the
customer has no phone, so no message can leave."""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTrackAfterPayment(TransactionCase):

    def setUp(self):
        super().setUp()
        self.guard = self.env['sa.outbox.guard'].sudo()
        self.partner = self.env['res.partner'].create({'name': 'Zz Track Paid Customer'})  # no phone
        product = self.env['product.product'].create({'name': 'Zz Track Paid Tea', 'type': 'consu'})
        self.order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1, 'price_unit': 2.0})],
        })
        out = self.env.ref('stock.picking_type_out')
        self.job = self.env['stock.picking'].create({
            'partner_id': self.partner.id, 'picking_type_id': out.id,
            'location_id': out.default_location_src_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'sale_id': self.order.id,
        })
        if not self.job.sa_track_url:
            self.job.sudo().write({'sa_track_token': 'zz-track-paid-token'})
            self.job.invalidate_recordset(['sa_track_url', 'sa_job_url'])
        self.assertTrue(self.job.sa_track_url)
        self.key = 'tracklink|%s' % self.job.id
        # the guard commits on its own connection: start and end clean
        self.guard.release(self.key)
        self.addCleanup(self.guard.release, self.key)

    def _pay_online(self):
        """The WhatsApp order was sent a pay link: it is to be paid online."""
        session = self.env['whatsapp.session'].sudo().create({
            'name': 'Zz Track Paid Session', 'gateway_api_key': 'zz-track-paid-key'})
        group = self.env['sa.sales.group'].sudo().create({
            'name': 'Zz Track Paid Group', 'group_jid': 'zz-track-paid@g.us',
            'session_id': session.id, 'group_type': 'customer'})
        self.env['sa.group.request'].sudo().create({
            'group_id': group.id, 'requester_phone': '+96890000088', 'raw_text': 'tea',
            'order_id': self.order.id, 'sa_pay_link_sent_on': '2026-11-22 08:00:00'})

    def _mark_paid(self):
        provider = self.env['payment.provider'].sudo().search([], limit=1)
        method = self.env['payment.method'].sudo().search([], limit=1)
        if not provider or not method:
            self.skipTest('no payment provider to pay with')
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': provider.id, 'payment_method_id': method.id,
            'amount': self.order.amount_total, 'currency_id': self.order.currency_id.id,
            'partner_id': self.partner.id, 'reference': 'ZZ-TRACK-PAID-%s' % self.order.id,
            'sale_order_ids': [(6, 0, [self.order.id])]})
        tx.write({'state': 'done'})
        self.job.invalidate_recordset(['sa_is_paid'])
        self.assertTrue(self.job.sa_is_paid)

    def test_cash_on_delivery_gets_the_link_straight_away(self):
        # a WhatsApp order never sent a pay link pays at the door
        self.assertFalse(self.job._sa_track_waits_payment())
        self.assertEqual(self.job.sa_track_link_once(), self.job.sa_track_url)
        self.assertFalse(self.job.sa_track_held)

    def test_a_pay_online_order_is_held_until_paid(self):
        self._pay_online()
        self.assertTrue(self.job._sa_track_waits_payment())
        self.assertEqual(self.job.sa_track_link_once(), '', "not paid: no link yet")
        self.assertTrue(self.job.sa_track_held, "the link is owed")
        self.assertTrue(self.guard.claim(self.key, 60), "nothing was claimed while it waited")
        self.guard.release(self.key)
        self._mark_paid()
        self.assertFalse(self.job._sa_track_waits_payment())
        self.assertEqual(self.job.sa_track_link_once(), self.job.sa_track_url, "paid: the link goes out")
        self.assertFalse(self.job.sa_track_held)

    def test_a_held_link_that_cannot_be_sent_stays_owed(self):
        self._pay_online()
        self.job.sa_track_link_once()
        self._mark_paid()
        self.job.sudo().with_context(sa_quiet=True).write({'sa_delivery_state': 'accepted'})
        with patch.object(type(self.job), '_sa_tell_customer', lambda *a, **kw: False):
            self.job._sa_track_send_held()    # the message cannot leave
        self.assertTrue(self.job.sa_track_held, "still owed")
        self.assertTrue(self.guard.claim(self.key, 60), "the once-only slot was given back")
