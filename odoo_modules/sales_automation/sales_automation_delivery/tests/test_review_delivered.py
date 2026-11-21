# -*- coding: utf-8 -*-
"""The Delivered message carries "Rate your products" again (21 Nov 2026).

sa_rider_round2 replaced the base Delivered message and left the review line
out, so the link never went. For a group order the review goes as its own
message (the group keeps the Delivered words, the link goes to the private
chat); otherwise it rides on the Delivered message. Nothing is sent: the
customer messages are recorded instead."""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

REVIEW = "\n\n⭐ How was it? Rate your products: https://x.test/wa/review/1"


@tagged('post_install', '-at_install')
class TestReviewDelivered(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Zz Review Delivered', 'phone': '+919800055501'})
        product = self.env['product.product'].create({'name': 'Zz Review Delivered Tea', 'type': 'consu'})
        self.order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1, 'price_unit': 2.0})],
        })
        out = self.env.ref('stock.picking_type_out')
        self.job = self.env['stock.picking'].create({
            'partner_id': partner.id, 'picking_type_id': out.id,
            'location_id': out.default_location_src_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'sale_id': self.order.id,
        })
        self.told = []
        Picking = self.env.registry['stock.picking']
        for patcher in (
                patch.object(Picking, '_sa_tell_customer',
                             lambda rec, body, unique=False: self.told.append(body) or True),
                patch.object(Picking, '_sa_review_line', lambda rec: REVIEW)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_direct_order_gets_the_review_on_the_delivered_message(self):
        self.job._sa_notify_customer('delivered')
        self.assertEqual(len(self.told), 1)
        self.assertIn('delivered at', self.told[0])
        self.assertIn('Rate your products', self.told[0])

    def test_a_group_order_gets_the_review_as_its_own_message(self):
        SaleOrder = self.env.registry['sale.order']
        if not hasattr(SaleOrder, '_sa_group_enquiry'):
            self.skipTest('no group orders here')
        with patch.object(SaleOrder, '_sa_group_enquiry', lambda rec: rec.env['res.partner'].browse(1)):
            self.job._sa_notify_customer('delivered')
        self.assertEqual(len(self.told), 2)
        self.assertIn('delivered at', self.told[0])
        self.assertNotIn('Rate your products', self.told[0])
        self.assertIn('Rate your products', self.told[1])
