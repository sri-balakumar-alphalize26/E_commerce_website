# -*- coding: utf-8 -*-
"""The "Rate your products" line goes out once per order (13 Nov 2026) - but
only once it really went out. Before 17 Nov the once-per-order slot was taken
before the Delivered message was sent, so a customer with no phone, a missing
session or a refused send never got the link at all. Nothing is sent here: the
customer has no phone, so the message cannot leave."""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReviewOnce(TransactionCase):

    def setUp(self):
        super().setUp()
        self.guard = self.env['sa.outbox.guard'].sudo()
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        if settings and not settings.ask_review:
            settings.ask_review = True
        partner = self.env['res.partner'].create({'name': 'Zz Review Once Customer'})  # no phone
        product = self.env['product.product'].create({'name': 'Zz Review Once Tea', 'type': 'consu'})
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
        self.key = self.job._sa_review_guard_key()
        # the guard commits on its own connection: start and end clean
        self.guard.release(self.key)
        self.addCleanup(self.guard.release, self.key)

    def test_a_delivered_message_that_cannot_go_keeps_the_review_for_later(self):
        self.assertFalse(self.job._sa_notify_customer('delivered'), "no phone: nothing is sent")
        self.assertTrue(self.guard.claim(self.key, 60), "the once-per-order slot is still free")

    def test_the_review_line_is_given_once(self):
        self.assertIn('Rate your products', self.job._sa_review_line())
        self.assertEqual(self.job._sa_review_line(), '', "taken: not offered twice")
