"""Moving an order on, cancelling it, and the delivery code.

Also the two things in mart369_cart that could not work until this module
existed: slot capacity and coupon usage. Both had a guard in them saying so.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import Mart369OrderCase


@tagged('post_install', '-at_install')
class TestMart369Flow(Mart369OrderCase):

    # -------------------------------------------------------------- the flow

    def test_an_order_walks_the_steps_the_app_draws(self):
        order = self._place()
        self._pay(order)
        for expected in ('packed', 'out', 'delivered'):
            order.mart369_action_advance()
            self.assertEqual(order.mart369_state, expected)

    def test_an_express_order_is_shipped_rather_than_packed(self):
        order = self._place(
            items={str(self.express_product.id): 1}, mode='all', ref='369M-EXP')
        self._pay(order)
        order.mart369_action_advance()
        self.assertEqual(order.mart369_state, 'shipped',
                         'Express skips packed, exactly as STEPS does')

    def test_a_delivered_order_cannot_be_moved_on(self):
        order = self._place()
        self._pay(order)
        for __ in range(3):
            order.mart369_action_advance()
        with self.assertRaises(UserError):
            order.mart369_action_advance()

    def test_every_step_is_stamped_once(self):
        order = self._place()
        self._pay(order)
        order.mart369_action_advance()
        order.mart369_action_advance()
        self.assertEqual(order.mart369_stamp_ids.mapped('state'),
                         ['placed', 'packed', 'out'])

    def test_the_timeline_survives_being_read_again(self):
        """The app used to work the timeline out from a timer, so it was a
        different story on every reload."""
        order = self._place()
        self._pay(order)
        order.mart369_action_advance()
        first = order._mart369_serialize()['timeline']
        order.invalidate_recordset()
        self.assertEqual(first, order._mart369_serialize()['timeline'])

    # ------------------------------------------------------------ the doorstep

    def test_the_delivery_code_works_once(self):
        order = self._place()
        self._pay(order)
        code = order._mart369_issue_otp()
        self.assertTrue(order._mart369_check_otp(code))
        self.assertFalse(order._mart369_check_otp(code), 'a used code is spent')

    def test_a_wrong_delivery_code_is_refused(self):
        order = self._place()
        self._pay(order)
        code = order._mart369_issue_otp()
        wrong = '000000' if code != '000000' else '111111'
        self.assertFalse(order._mart369_check_otp(wrong))

    def test_the_delivery_code_is_not_stored_in_the_clear(self):
        order = self._place()
        code = order._mart369_issue_otp()
        self.assertNotEqual(order.sudo().mart369_otp_hash, code)
        self.assertNotIn(code, order.sudo().mart369_otp_hash or '')

    def test_the_delivery_code_cannot_be_worked_out_from_the_order(self):
        """It used to be hash(order.id + "otp"), so anyone holding an order
        number could compute the code for that doorstep."""
        one, two = self._place(), self._place(ref='369M-TEST2')
        self.assertNotEqual(one._mart369_issue_otp(), two._mart369_issue_otp())

    # ------------------------------------------------------------ cancelling

    def test_an_order_can_be_cancelled_while_it_is_only_placed(self):
        order = self._place()
        self._pay(order)
        order._mart369_cancel(reason='Changed my mind')
        self.assertEqual(order.mart369_state, 'cancelled')

    def test_an_order_cannot_be_cancelled_once_it_is_packed(self):
        order = self._place()
        self._pay(order)
        order.mart369_action_advance()
        with self.assertRaises(UserError):
            order._mart369_cancel()

    def test_cancelling_gives_the_delivery_window_back(self):
        order = self._place()
        self._pay(order)
        order._mart369_cancel()
        self.assertFalse(order.mart369_slot_key)

    # --------------------------------------------------------------- coupons

    def _coupon(self, **overrides):
        values = {
            'code': 'TEST20',
            'title': '20% off',
            'kind': 'percent',
            'value': 20.0,
            'min_spend': 100.0,
        }
        values.update(overrides)
        return self.env['mart369.coupon'].sudo().create(values)

    def test_a_coupon_is_only_spent_once_the_order_is_paid_for(self):
        """So an abandoned basket does not burn a code."""
        coupon = self._coupon()
        order = self._place(coupon='TEST20', ref='369M-CPN')
        self.assertEqual(coupon.used_count, 0, 'not yet - it is not paid for')
        self._pay(order)
        self.assertEqual(coupon.used_count, 1)

    def test_cancelling_gives_the_coupon_back(self):
        coupon = self._coupon(code='TEST21')
        order = self._place(coupon='TEST21', ref='369M-CPN2')
        self._pay(order)
        order._mart369_cancel()
        self.assertEqual(coupon.used_count, 0)

    def test_a_coupon_past_its_per_customer_cap_is_refused(self):
        self._coupon(code='ONCE', limit_per_customer=1)
        first = self._place(coupon='ONCE', ref='369M-ONCE1')
        self._pay(first)
        with self.assertRaises(UserError):
            self._place(coupon='ONCE', ref='369M-ONCE2')

    def test_a_coupon_the_basket_does_not_qualify_for_is_simply_not_applied(self):
        self._coupon(code='BIG', min_spend=100000.0)
        order = self._place(coupon='BIG', ref='369M-BIG')
        self.assertFalse(order.mart369_coupon_id)
        self.assertEqual(order.amount_total, 230.0)

    # ----------------------------------------------------------------- slots

    def test_a_full_delivery_window_is_refused(self):
        """mart369_cart's capacity check short-circuited because
        mart369_slot_key did not exist. It exists now."""
        slot = self.env['mart369.delivery.slot'].sudo().create({
            'key': 'test-window',
            'top': 'Today',
            'sub': '6 - 8 PM',
            'kind': 'window',
            'mode': 'quick',
            'from_hour': 18.0,
            'to_hour': 20.0,
            'day_offset': 0,
            'capacity': 1,
        })
        first = self._place(slot_key='test-window', ref='369M-SLOT1')
        self.assertEqual(first.mart369_slot_key, 'test-window')
        self.assertTrue(first.mart369_slot_day)

        self.assertTrue(slot._mart369_is_full(fields.Datetime.now()),
                        'one order has taken the only place')
        with self.assertRaises(UserError):
            self._place(slot_key='test-window', ref='369M-SLOT2')

    # ------------------------------------------------------------------ late

    def test_an_order_past_its_promise_is_late(self):
        order = self._place()
        self._pay(order)
        order.write({'mart369_due_at': fields.Datetime.now() - timedelta(hours=1)})
        self.assertTrue(order.mart369_late)
        self.assertIn(order, self.env['sale.order'].search([('mart369_late', '=', True)]))

    def test_a_delivered_order_is_never_late(self):
        order = self._place()
        self._pay(order)
        order.write({'mart369_due_at': fields.Datetime.now() - timedelta(hours=1)})
        for __ in range(3):
            order.mart369_action_advance()
        self.assertFalse(order.mart369_late, 'it arrived; that is the end of it')
