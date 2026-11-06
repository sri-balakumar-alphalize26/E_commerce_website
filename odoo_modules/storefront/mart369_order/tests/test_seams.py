"""The three seams mart369_payment left open, now filled.

Each test here corresponds to a docstring in
mart369_payment/models/payment_transaction.py that says "mart369_order overrides
this to ...". If one fails, that promise is broken.
"""

from odoo.tests import tagged

from .common import Mart369OrderCase


@tagged('post_install', '-at_install')
class TestMart369Seams(Mart369OrderCase):

    # ------------------------------------------------------- what to charge

    def test_the_charge_is_read_off_the_order_not_the_browser(self):
        order = self._place()
        amount, client_priced = self.env['payment.transaction']._mart369_amount_for(
            order.mart369_ref, 1.0)
        self.assertEqual(amount, order.amount_total,
                         'the order decides, not the 1.00 that was claimed')
        self.assertFalse(client_priced, 'and it is no longer the browser pricing it')

    def test_a_reference_with_no_order_behind_it_still_works(self):
        """Wallet top-ups have no order. The old behaviour has to survive."""
        amount, client_priced = self.env['payment.transaction']._mart369_amount_for(
            '369M-NOTHING', 250)
        self.assertEqual(amount, 250)
        self.assertTrue(client_priced)

    # ------------------------------------------------------------ being paid

    def test_paying_places_the_order(self):
        order = self._place()
        self._pay(order)
        self.assertEqual(order.mart369_state, 'placed')
        self.assertTrue(order.mart369_placed_at)
        self.assertEqual(order.mart369_stamp_ids.mapped('state'), ['placed'])

    def test_paying_stamps_the_money_onto_the_order(self):
        order = self._place()
        tx = self._pay(order)
        self.assertEqual(order.mart369_paid, order.amount_total)
        self.assertEqual(order.mart369_txn, tx.mart369_txn)

    def test_paying_issues_a_delivery_code(self):
        order = self._place()
        self._pay(order)
        self.assertTrue(order.sudo().mart369_otp_hash)
        self.assertTrue(order.mart369_otp_at)

    def test_a_repeated_webhook_does_not_place_the_order_twice(self):
        """Providers resend. That is normal, not an error."""
        order = self._place()
        tx = self._pay(order)
        first_code = order.sudo().mart369_otp_hash
        placed_at = order.mart369_placed_at

        tx._post_process()
        tx._post_process()

        self.assertEqual(order.mart369_stamp_ids.mapped('state'), ['placed'],
                         'stamped once, however many times the webhook arrives')
        self.assertEqual(order.mart369_placed_at, placed_at)
        self.assertEqual(order.sudo().mart369_otp_hash, first_code,
                         'and the customer is not handed a new code')

    def test_paying_confirms_the_order_in_odoo_too(self):
        order = self._place()
        self._pay(order)
        self.assertEqual(order.state, 'sale', 'so stock and invoicing can happen')

    # --------------------------------------------------------- not being paid

    def test_a_failed_payment_leaves_the_order_unplaced(self):
        order = self._place()
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': self.gateway.id,
            'payment_method_id': self.method.id,
            'partner_id': self.partner.id,
            'amount': order.amount_total,
            'currency_id': order.currency_id.id,
            'operation': 'online_direct',
            'mart369_kind': 'order',
            'mart369_order_ref': order.mart369_ref,
        })
        tx._set_canceled()
        tx._post_process()
        self.assertEqual(order.mart369_state, 'draft')
        self.assertFalse(order.mart369_slot_key, 'and the window it held is free')

    def test_a_failed_retry_does_not_unplace_an_order_already_paid_for(self):
        order = self._place()
        self._pay(order)
        later = self.env['payment.transaction'].sudo().create({
            'provider_id': self.gateway.id,
            'payment_method_id': self.method.id,
            'partner_id': self.partner.id,
            'amount': order.amount_total,
            'currency_id': order.currency_id.id,
            'operation': 'online_direct',
            'mart369_kind': 'order',
            'mart369_order_ref': order.mart369_ref,
        })
        later._set_canceled()
        later._post_process()
        self.assertEqual(order.mart369_state, 'placed')

    # ------------------------------------------------------- the transaction

    def test_a_payment_resolves_to_its_order(self):
        """mart369_order_ref was free text because there was no record behind
        it. Now there is."""
        order = self._place()
        tx = self._pay(order)
        self.assertEqual(tx.mart369_order_id, order)
