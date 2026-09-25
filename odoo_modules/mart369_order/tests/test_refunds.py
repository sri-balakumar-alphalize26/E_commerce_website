"""Refunds: all of it, to the 369 Wallet, once (models/order_refund.py)."""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import Mart369OrderCase


@tagged('post_install', '-at_install')
class TestRefunds(Mart369OrderCase):

    def _wallet(self):
        return self.env['loyalty.card'].sudo()._mart369_wallet(self.partner).points

    def _delivered(self, order):
        while order.mart369_state not in ('out', 'delivered'):
            order.mart369_action_advance()
        order.mart369_action_deliver(order.sudo().mart369_otp_code)
        return order

    def _return(self, order, amount=None):
        return self.env['mart369.order.return'].create({
            'order_id': order.id, 'kind': 'refund', 'reason': 'Damaged',
            'amount': amount if amount is not None else order.amount_total,
        })

    def _finish(self, ret):
        while ret.state != 'done':
            ret.mart369_action_advance()

    def test_a_return_paid_by_upi_is_refunded_in_full_to_the_wallet(self):
        order = self._delivered(self._paid())
        before = self._wallet()
        ret = self._return(order)
        self._finish(ret)
        self.assertAlmostEqual(ret.refunded, order.mart369_paid, places=2)
        self.assertAlmostEqual(self._wallet(), before + order.mart369_paid, places=2,
                               msg='UPI money comes back too, not just the wallet part')
        notes = order.invoice_ids.filtered(lambda m: m.move_type == 'out_refund' and m.state == 'posted')
        self.assertTrue(notes, 'a credit note for the books')

    def test_never_more_than_was_paid(self):
        order = self._delivered(self._paid())
        first = self._return(order, amount=order.amount_total / 2)
        self._finish(first)
        second = self._return(order, amount=order.amount_total)  # asks for all of it again
        before = self._wallet()
        self._finish(second)
        self.assertAlmostEqual(first.refunded + second.refunded, order.mart369_paid, places=2)
        self.assertAlmostEqual(self._wallet() - before, second.refunded, places=2)
        self.assertEqual(order._mart369_refundable(), 0.0)

    def test_issuing_a_refund_twice_pays_once(self):
        order = self._delivered(self._paid())
        ret = self._return(order)
        self._finish(ret)
        after = self._wallet()
        ret._mart369_refund()
        self.assertAlmostEqual(self._wallet(), after, places=2)

    def test_a_paid_cancel_refunds_in_full_and_says_so(self):
        order = self._paid()
        before = self._wallet()
        order._mart369_cancel(reason='Store closed')
        self.assertAlmostEqual(order.mart369_cancel_refund, order.mart369_paid, places=2)
        self.assertAlmostEqual(self._wallet(), before + order.mart369_paid, places=2)
        cancel = order._mart369_serialize()['cancel']
        self.assertEqual(cancel['refundTo'], 'wallet', 'the page says where the money went')
        self.assertAlmostEqual(cancel['amount'], order.mart369_paid, places=2)

    def test_a_cash_cancel_refunds_nothing(self):
        order = self._place()
        self._cash(order)
        before = self._wallet()
        order._mart369_cancel(reason='Store closed')
        self.assertEqual(order.mart369_cancel_refund, 0.0)
        self.assertAlmostEqual(self._wallet(), before, places=2)
        self.assertEqual(order._mart369_serialize()['cancel']['refundTo'], '')

    def test_a_refund_is_not_capped_by_the_wallet_limit(self):
        self.env['ir.config_parameter'].sudo().set_param('mart369.wallet.limit', '10')
        order = self._paid()
        order._mart369_cancel(reason='Store closed')
        self.assertGreater(self._wallet(), 10, "the customer's own money comes back")
        card = self.env['loyalty.card'].sudo()._mart369_wallet(self.partner)
        with self.assertRaises(UserError):
            card._mart369_move(5, 'add', 'Top-up')  # adding money still respects it

    def _paid(self):
        order = self._place()
        self._pay(order)
        return order
