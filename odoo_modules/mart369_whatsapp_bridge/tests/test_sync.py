"""Two state machines, one parcel."""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import Mart369BridgeCase


@tagged('post_install', '-at_install')
class TestWhatsappOrders(Mart369BridgeCase):
    """The console driving a WhatsApp order's real delivery job."""

    def test_advance_drives_the_job(self):
        order = self._wa_order()
        job = self._job(order)
        self.assertEqual(job.sa_delivery_state, 'awaiting_shop')
        self.assertEqual(order.mart369_state, 'placed')

        order.mart369_action_advance()          # -> packed = shop Ready
        self.assertIn(job.sa_delivery_state, ('ready', 'to_assign', 'offered'))
        self.assertEqual(order.mart369_state, 'packed')

        order.mart369_action_advance()          # -> out
        self.assertEqual(job.sa_delivery_state, 'out_for_delivery')
        self.assertEqual(order.mart369_state, 'out')

    def test_advance_never_reaches_delivered(self):
        order = self._wa_order()
        order.mart369_action_advance()
        order.mart369_action_advance()
        with self.assertRaises(UserError):
            order.mart369_action_advance()

    def test_deliver_needs_the_stacks_code(self):
        order = self._wa_order()
        order.mart369_action_advance()
        order.mart369_action_advance()          # out; the stack issued a code
        job = self._job(order)
        with self.assertRaisesRegex(UserError, 'not right'):
            order.mart369_action_deliver('000000')
        code = self.env['sa.delivery.otp'].sudo()._issue(job, 'delivery')
        order.mart369_action_deliver(code)
        self.assertEqual(order.mart369_state, 'delivered')
        self.assertEqual(job.sa_delivery_state, 'delivered')
        self.assertEqual(job.state, 'done')

    def test_no_website_side_effects(self):
        """Delivered without a scratch card, points, wallet or website
        message - those belong to website customers."""
        order = self._wa_order()
        order.mart369_action_advance()
        order.mart369_action_advance()
        job = self._job(order)
        code = self.env['sa.delivery.otp'].sudo()._issue(job, 'delivery')
        before = len(self.wa_sent)
        order.mart369_action_deliver(code)
        # The stack says "Delivered. Thank you!" to its own customer; the
        # website notifier must have added nothing on top.
        stack_texts = [b for __, b in self.wa_sent[before:]]
        self.assertFalse(
            [b for b in stack_texts if 'Track it' in b or '369 Mart' in b],
            'the website notifier spoke to a WhatsApp customer')
        if 'mart369.scratch.card' in self.env:
            self.assertFalse(self.env['mart369.scratch.card'].sudo().search(
                [('partner_id', '=', order.partner_id.id)]))

    def test_cancel_cancels_the_job(self):
        order = self._wa_order()
        job = self._job(order)
        order._mart369_cancel(reason='Customer asked to cancel')
        self.assertEqual(order.state, 'cancel')
        self.assertEqual(job.sa_delivery_state, 'cancelled')
        self.assertEqual(order.mart369_state, 'cancelled')

    def test_mapping_respects_the_flow_constraint(self):
        """Every stage maps to a state the order's own flow accepts."""
        order = self._wa_order()
        job = self._job(order)
        Order = self.env['sale.order']
        stages = [s for s, __ in job._fields['sa_delivery_state'].selection
                  if s != 'none']
        for mode, flow in (('quick', ('placed', 'packed', 'out')),
                           ('all', ('placed', 'shipped', 'out'))):
            for stage in stages:
                job.with_context(mart369_bridge='push').write(
                    {'sa_delivery_state': stage})
                state = Order._mart369_bridge_map(mode, job)
                if state in ('delivered', 'cancelled') or state is None:
                    continue
                self.assertIn(state, flow,
                              '%s/%s mapped to %s' % (mode, stage, state))


@tagged('post_install', '-at_install')
class TestWebsiteOrders(Mart369BridgeCase):
    """Website orders through the counter screen and the rider app."""

    def test_job_is_fixed_at_dispatch(self):
        order = self._web_order()
        job = self._job(order)
        self.assertTrue(job)
        self.assertEqual(job.sa_delivery_kind, 'quick')
        self.assertEqual(job.sa_cod_amount, 0.0, 'a prepaid order told the '
                         'rider to collect money')
        self.assertEqual(job.sudo().sa_last_delivery_code,
                         order.sudo().mart369_otp_code)

    def test_cod_job_collects_the_total(self):
        order = self._web_order(cash=True, ref='369M-TESTC')
        job = self._job(order)
        self.assertEqual(job.sa_cod_amount, order.amount_total)
        self.assertEqual(order.mart369_method, 'cod')

    def test_console_advance_pushes_the_job(self):
        order = self._web_order()
        job = self._job(order)
        order.mart369_action_advance()          # placed -> packed
        self.assertIn(job.sa_delivery_state, ('ready', 'to_assign', 'offered'))
        order.mart369_action_advance()          # packed -> out
        self.assertEqual(job.sa_delivery_state, 'out_for_delivery')

    def test_stack_messages_are_silenced_for_website(self):
        order = self._web_order()
        job = self._job(order)
        before = list(self.wa_sent)
        job.sa_shop_accept()
        job.sa_shop_ready()
        # The shop's "approved" and "packed" texts went to nobody; the
        # website notifier speaks instead (test_notify).
        new = [b for __, b in self.wa_sent[len(before):]]
        self.assertFalse([b for b in new if 'approved' in b or 'packed and ready' in b])

    def test_rider_moves_pull_the_order(self):
        order = self._web_order()
        job = self._job(order)
        job.sa_shop_accept()
        job.sa_shop_ready()
        self.assertEqual(order.mart369_state, 'packed')
        job.sa_set_state('out_for_delivery')
        self.assertEqual(order.mart369_state, 'out')
        # And never backwards: a re-offer does not unpack the order.
        job.write({'sa_delivery_state': 'offered'})
        self.assertEqual(order.mart369_state, 'out')

    def test_one_code_for_the_doorstep(self):
        order = self._web_order()
        job = self._job(order)
        order.mart369_action_advance()
        order.mart369_action_advance()          # out
        # The stack's own code path hands back the website's code.
        ok, __, code = job.sa_issue_delivery_otp()
        self.assertTrue(ok)
        self.assertEqual(code, order.sudo().mart369_otp_code)
        ok, __ = job.sa_verify_otp('delivery', 'wrong1')
        self.assertFalse(ok)
        ok, __ = job.sa_verify_otp('delivery', code)
        self.assertTrue(ok)
        job.sa_set_state('delivered')
        self.assertEqual(order.mart369_state, 'delivered')
        self.assertTrue(order.sudo().mart369_otp_used_at)

    def test_console_deliver_still_works(self):
        """The website's own door-code path is untouched by the bridge."""
        order = self._web_order()
        code = order.sudo().mart369_otp_code
        order.mart369_action_advance()
        order.mart369_action_advance()
        order.mart369_action_deliver(code)
        self.assertEqual(order.mart369_state, 'delivered')
        self.assertEqual(self._job(order).sa_delivery_state, 'delivered')

    def test_store_cancel_refunds_through_the_website(self):
        order = self._web_order()
        job = self._job(order)
        job.sa_action_cancel(reason='Store closed')
        self.assertEqual(order.mart369_state, 'cancelled')
        # The website's cancel ran, so the money went to the wallet.
        self.assertTrue(order.mart369_cancel_refund or order.mart369_paid == 0)
