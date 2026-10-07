"""A website order hears the WhatsApp journey - and gets its door code there."""

from odoo.tests import tagged

from .common import Mart369BridgeCase

CUSTOMER = '+96891230011'           # the account's own number
CUSTOMER_DIGITS = '96891230011'
ADDRESS_DIGITS = '919876543210'     # the fixture address: '+91 98765 43210'


@tagged('post_install', '-at_install')
class TestWebOrderWhatsapp(Mart369BridgeCase):

    def setUp(self):
        super().setUp()
        self.partner.phone = CUSTOMER
        self.partner.mart369_notify_whatsapp = True

    def _ready_job(self, **overrides):
        order = self._web_order(whatsapp=True, **overrides)
        job = self._job(order)
        job.sa_shop_accept()
        job.sa_shop_ready()
        self.wa_sent.clear()
        return order, job

    def _to(self, digits):
        return [body for phone, body in self.wa_sent if phone == digits]

    # ---------------------------------------------------------------- steps

    def test_rider_steps_reach_the_customer_once(self):
        order, job = self._ready_job()
        job.sa_set_state('accepted')
        job.sa_set_state('picked')
        job.sa_set_state('out_for_delivery')
        texts = self._to(CUSTOMER_DIGITS)
        self.assertEqual(len([t for t in texts if 'is bringing your order' in t]), 1)
        self.assertEqual(len([t for t in texts if 'has been collected' in t]), 1)
        self.assertEqual(len([t for t in texts if 'is out for delivery with' in t]), 1)
        # The website's own "out for delivery" stays quiet: one voice.
        self.assertFalse([t for t in texts if t.startswith('Order #')
                          and 'out for delivery' in t])
        # The address phone hears the door code, never the steps.
        self.assertFalse([t for t in self._to(ADDRESS_DIGITS)
                          if 'is bringing your order' in t])

    def test_shop_messages_stay_with_the_website(self):
        order = self._web_order(whatsapp=True)
        job = self._job(order)
        self.wa_sent.clear()
        job.sa_shop_accept()
        self.assertFalse(self._to(CUSTOMER_DIGITS))

    def test_switch_off_silences_that_step(self):
        self.env['mart369.config'].sudo()._get().mart369_wa_on_shipped = False
        order, job = self._ready_job(ref='369M-TESTOFF')
        job.sa_set_state('accepted')
        job.sa_set_state('out_for_delivery')
        texts = self._to(CUSTOMER_DIGITS)
        self.assertFalse([t for t in texts if 'is bringing your order' in t])
        self.assertTrue([t for t in texts if 'is out for delivery with' in t])

    def test_opted_out_hears_no_steps(self):
        self.partner.mart369_notify_whatsapp = False
        order, job = self._ready_job(ref='369M-TESTOPT')
        job.sa_set_state('accepted')
        self.assertFalse([t for t in self._to(CUSTOMER_DIGITS)
                          if 'is bringing your order' in t])

    # ----------------------------------------------------------------- code

    def test_code_goes_to_customer_and_address(self):
        order, job = self._ready_job(ref='369M-TESTCODE')
        code = order.sudo().mart369_otp_code
        self.assertTrue(code)
        job.sa_set_state('out_for_delivery')
        self.assertEqual(len([t for t in self._to(CUSTOMER_DIGITS) if code in t]), 1)
        self.assertEqual(len([t for t in self._to(ADDRESS_DIGITS) if code in t]), 1)
        self.assertEqual(job.sa_last_delivery_code, code)

    def test_one_number_written_two_ways_is_one_send(self):
        self.partner.phone = '+91 98765 43210'
        self.address.phone = '+919876543210'
        order, job = self._ready_job(ref='369M-TESTSAME')
        code = order.sudo().mart369_otp_code
        ok, __, sent_code = job.sa_issue_delivery_otp()
        self.assertTrue(ok)
        self.assertEqual(sent_code, code)
        self.assertEqual(len([b for __, b in self.wa_sent if code in b]), 1)

    def test_opted_out_still_gets_the_code(self):
        self.partner.mart369_notify_whatsapp = False
        order, job = self._ready_job(ref='369M-TESTKEY')
        code = order.sudo().mart369_otp_code
        ok, __, __ = job.sa_issue_delivery_otp()
        self.assertTrue(ok)
        self.assertTrue([t for t in self._to(CUSTOMER_DIGITS) if code in t])

    def test_resend_sends_the_same_code_again(self):
        order, job = self._ready_job(ref='369M-TESTRES')
        code = order.sudo().mart369_otp_code
        job.sa_issue_delivery_otp()
        job.sa_issue_delivery_otp()
        self.assertEqual(len([t for t in self._to(CUSTOMER_DIGITS) if code in t]), 2)

    def test_no_session_says_so(self):
        order, job = self._ready_job(ref='369M-TESTNOS')
        self.env['whatsapp.session'].sudo().search([]).write({'active': False})
        ok, message, code = job.sa_issue_delivery_otp()
        self.assertFalse(ok)
        self.assertTrue(code)
        self.assertIn('in their app', message)

    # --------------------------------------------------------- group orders

    def test_whatsapp_group_orders_keep_their_own_code(self):
        order = self._wa_order(phone='+919876500077')
        job = self._job(order)
        self.wa_sent.clear()
        ok, __, code = job.sa_issue_delivery_otp()
        self.assertTrue(code)
        self.assertFalse(order.mart369_ref)
        self.assertTrue([b for __, b in self.wa_sent if code in b])
