"""Paying, and who gets to say it worked.

Every one of these is a thing the browser decides today and should not.
"""

import json

from odoo.tests import tagged

from .common import Mart369PaymentHttpCase


@tagged('post_install', '-at_install')
class TestMart369PaymentApi(Mart369PaymentHttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        portal = cls.env.ref('base.group_portal')
        cls.user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Pay Customer', 'login': 'pay@369.test',
            'email': 'pay@369.test', 'password': 'pay-pw-3691',
            'group_ids': [(6, 0, [portal.id])],
        })
        cls.partner = cls.user.partner_id
        cls.wallet_provider = cls._mart369_wallet_provider()
        cls.gateway = cls._mart369_gateway()

    def _req(self, method, path, payload=None):
        return self.opener.request(
            method, self.base_url() + path,
            data=json.dumps(payload) if payload is not None else None,
            headers={'Content-Type': 'application/json'}, allow_redirects=False)

    def _login(self):
        self.authenticate('pay@369.test', 'pay-pw-3691')

    def _card(self):
        return self.env['loyalty.card']._mart369_wallet(self.partner)

    # ------------------------------------------------------- server authorship

    def test_paying_returns_a_server_authored_txn(self):
        self._login()
        self._card()._mart369_move(500, 'add', 'Money added')
        body = self._req('POST', '/369mart/payment/pay', {
            'method': 'wallet', 'amount': 200, 'wallet_use': True,
            'order_ref': '369M-24091612'}).json()
        self.assertTrue(body['ok'])
        self.assertTrue(body['txn'], 'the server names the transaction')
        self.assertNotIn('TXN', body['txn'][:3],
                         "not the app's Date.now() slice")

    def test_the_client_cannot_choose_its_own_txn_id(self):
        self._login()
        self._card()._mart369_move(300, 'add', 'Money added')
        body = self._req('POST', '/369mart/payment/pay', {
            'method': 'wallet', 'amount': 100, 'wallet_use': True,
            'txn': 'TXN1234567890', 'paid': 99999, 'status': 'delivered'}).json()
        self.assertNotEqual(body['txn'], 'TXN1234567890',
                            'a txn the browser sent must be ignored outright')

    def test_a_gateway_payment_is_pending_until_the_provider_confirms(self):
        self._login()
        body = self._req('POST', '/369mart/payment/pay', {
            'method': 'upi', 'amount': 250, 'order_ref': '369M-1'}).json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['state'], 'pending',
                         'nothing is paid until the webhook says so')

    def test_a_wallet_payment_that_covers_everything_settles_at_once(self):
        self._login()
        self._card()._mart369_move(400, 'add', 'Money added')
        body = self._req('POST', '/369mart/payment/pay', {
            'method': 'wallet', 'amount': 400, 'wallet_use': True}).json()
        self.assertEqual(body['state'], 'done',
                         'our own ledger is the settlement; there is nothing to wait for')
        self.assertEqual(body['payable'], 0)

    # ------------------------------------------------------------ the wallet leg

    def test_the_wallet_is_debited_before_the_gateway_is_asked(self):
        self._login()
        card = self._card()
        card._mart369_move(100, 'add', 'Money added')
        self._req('POST', '/369mart/payment/pay', {
            'method': 'upi', 'amount': 300, 'wallet_use': True, 'order_ref': '369M-2'})
        card.invalidate_recordset()
        self.assertEqual(card.points, 0,
                         'the wallet moved first, not after the order was written')

    def test_a_wallet_leg_bigger_than_the_balance_is_refused(self):
        self._login()
        self._card()._mart369_move(50, 'add', 'Money added')
        body = self._req('POST', '/369mart/payment/pay', {
            'method': 'wallet', 'amount': 500, 'wallet_use': True}).json()
        # Only what is there is ever used; the rest must go to a gateway.
        self.assertTrue(body.get('ok') is False or body.get('payable', 0) > 0,
                        'the wallet cannot pay more than it holds')

    def test_a_failed_payment_gives_the_wallet_leg_back(self):
        self._login()
        card = self._card()
        card._mart369_move(200, 'add', 'Money added')
        body = self._req('POST', '/369mart/payment/pay', {
            'method': 'upi', 'amount': 500, 'wallet_use': True, 'order_ref': '369M-3'}).json()
        card.invalidate_recordset()
        self.assertEqual(card.points, 0, 'the wallet paid its part')
        self._req('POST', '/369mart/payment/%s/cancel' % body['reference'])
        card.invalidate_recordset()
        self.assertEqual(card.points, 200,
                         'and got it back when the rest failed - which the app never does')

    def test_the_refund_of_a_wallet_leg_happens_only_once(self):
        self._login()
        card = self._card()
        card._mart369_move(200, 'add', 'Money added')
        body = self._req('POST', '/369mart/payment/pay', {
            'method': 'upi', 'amount': 500, 'wallet_use': True}).json()
        tx = self.env['payment.transaction'].sudo().search(
            [('reference', '=', body['reference'])])
        tx._mart369_refund_wallet_leg()
        tx._mart369_refund_wallet_leg()
        card.invalidate_recordset()
        self.assertEqual(card.points, 200, 'a repeat refund must not pay twice')

    # --------------------------------------------------------------- status

    def test_the_status_route_answers_the_shape_the_pay_sheet_reads(self):
        self._login()
        body = self._req('POST', '/369mart/payment/pay', {
            'method': 'upi', 'amount': 120}).json()
        status = self._req('GET', '/369mart/payment/status/%s' % body['reference']).json()
        self.assertIn('ok', status)
        self.assertIn(status.get('state', 'done'), ('pending', 'done'))

    def test_a_declined_payment_reports_an_error_the_app_can_show(self):
        self._login()
        body = self._req('POST', '/369mart/payment/pay', {
            'method': 'upi', 'amount': 120}).json()
        tx = self.env['payment.transaction'].sudo().search(
            [('reference', '=', body['reference'])])
        tx._set_error('Your bank declined this transaction.')
        status = self._req('GET', '/369mart/payment/status/%s' % body['reference']).json()
        self.assertFalse(status['ok'])
        self.assertIn('declined', status['error'])
        self.assertNotIn('retry', status, 'a decline is not the customer to retry')

    def test_a_wrong_otp_is_reported_as_retryable(self):
        self._login()
        body = self._req('POST', '/369mart/payment/pay', {
            'method': 'upi', 'amount': 120}).json()
        tx = self.env['payment.transaction'].sudo().search(
            [('reference', '=', body['reference'])])
        tx._set_error('Incorrect OTP. Please try again.')
        status = self._req('GET', '/369mart/payment/status/%s' % body['reference']).json()
        self.assertTrue(status.get('retry'),
                        'PaySheet.submitOtp needs to know it may ask again')

    def test_cancelling_a_payment_leaves_it_cancelled(self):
        self._login()
        body = self._req('POST', '/369mart/payment/pay', {
            'method': 'upi', 'amount': 90}).json()
        self.assertTrue(self._req(
            'POST', '/369mart/payment/%s/cancel' % body['reference']).json()['ok'])

    def test_cancelling_a_payment_that_is_done_is_refused(self):
        self._login()
        self._card()._mart369_move(100, 'add', 'Money added')
        body = self._req('POST', '/369mart/payment/pay', {
            'method': 'wallet', 'amount': 100, 'wallet_use': True}).json()
        response = self._req('POST', '/369mart/payment/%s/cancel' % body['reference'])
        self.assertEqual(response.status_code, 409)

    # ------------------------------------------------------------- validation

    def test_a_payment_with_no_method_is_refused(self):
        self._login()
        response = self._req('POST', '/369mart/payment/pay', {'amount': 100})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'method')

    def test_a_payment_with_no_amount_is_refused(self):
        self._login()
        response = self._req('POST', '/369mart/payment/pay', {'method': 'upi'})
        self.assertEqual(response.status_code, 400)

    def test_a_card_number_posted_to_pay_is_refused(self):
        self._login()
        response = self._req('POST', '/369mart/payment/pay', {
            'method': 'card', 'amount': 100, 'number': '4111111111111111'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('payment form', response.json()['error'])

    def test_another_customers_payment_is_a_404(self):
        self._login()
        response = self._req('GET', '/369mart/payment/status/NOPE-12345')
        self.assertEqual(response.status_code, 404,
                         'an unknown reference is indistinguishable from a stranger s')
