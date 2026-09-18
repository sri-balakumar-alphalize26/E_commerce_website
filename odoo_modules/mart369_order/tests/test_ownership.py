"""The test most worth failing loudly.

An order carries a name, a phone number, a home address and a basket. The routes
find one by the number the app holds, so the only thing standing between a
guessed order number and somebody else's doorstep is `_own()`.

A miss must be **404, not 403**: 403 confirms the order exists, which is half of
what someone probing for one wants to know.
"""

import json

from odoo.tests import tagged

from .common import Mart369OrderHttpCase


@tagged('post_install', '-at_install')
class TestMart369Ownership(Mart369OrderHttpCase):

    def _get(self, path):
        response = self.url_open(path)
        return response.status_code, self._payload(response)

    def _post(self, path, body=None):
        response = self.url_open(
            path, data=json.dumps(body or {}),
            headers={'Content-Type': 'application/json'})
        return response.status_code, self._payload(response)

    def _payload(self, response):
        try:
            return response.json()
        except ValueError:
            return {}

    def setUp(self):
        super().setUp()
        self.order = self._place()
        self._pay(self.order)
        self.authenticate('someone.else@369mart.test', 'someone-else-369')

    # ----------------------------------------------------- somebody else's

    def test_another_customers_order_is_not_found(self):
        status, payload = self._get('/369mart/orders/%s' % self.order.mart369_ref)
        self.assertEqual(status, 404, 'not 403 - that would confirm it exists')
        self.assertFalse(payload.get('ok'))

    def test_another_customers_order_cannot_be_cancelled(self):
        status, __ = self._post('/369mart/orders/%s/cancel' % self.order.mart369_ref)
        self.assertEqual(status, 404)
        self.order.invalidate_recordset()
        self.assertEqual(self.order.mart369_state, 'placed', 'and it is untouched')

    def test_another_customers_order_cannot_be_returned(self):
        status, __ = self._post(
            '/369mart/orders/%s/return' % self.order.mart369_ref,
            {'reason': 'Trying it on'})
        self.assertEqual(status, 404)
        self.assertFalse(self.env['mart369.order.return'].search(
            [('order_id', '=', self.order.id)]))

    def test_another_customers_invoice_is_not_found(self):
        status, __ = self._get('/369mart/orders/%s/invoice' % self.order.mart369_ref)
        self.assertEqual(status, 404)

    def test_another_customers_order_is_not_in_their_history(self):
        status, payload = self._get('/369mart/orders')
        self.assertEqual(status, 200)
        self.assertEqual(payload.get('orders'), [])

    # ------------------------------------------------------------- made up

    def test_a_made_up_order_number_is_not_found(self):
        status, __ = self._get('/369mart/orders/369M-DOESNOTEXIST')
        self.assertEqual(status, 404)

    # ------------------------------------------------------------- own ones

    def test_a_customer_can_read_their_own_order(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._get('/369mart/orders/%s' % self.order.mart369_ref)
        self.assertEqual(status, 200)
        self.assertEqual(payload['order']['id'], self.order.mart369_ref)

    def test_a_basket_that_was_never_paid_for_is_not_an_order_yet(self):
        """A draft exists in the database, but the app has not been told."""
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        draft = self._place(ref='369M-DRAFT')
        self.assertEqual(draft.mart369_state, 'draft')
        status, __ = self._get('/369mart/orders/369M-DRAFT')
        self.assertEqual(status, 404)

    def test_signing_out_gets_you_nothing(self):
        """auth='user' sends an anonymous caller to the login page, which is
        itself a 200 - so the status is not the thing to assert. What matters is
        that no order comes back with it."""
        self.authenticate(None, None)
        response = self.url_open('/369mart/orders/%s' % self.order.mart369_ref)
        self.assertIn('/web/login', response.url, 'bounced to the login page')
        # Not asserted on the body: the login page echoes the path back in its
        # own redirect= parameter, order number and all. What matters is that no
        # order came back, so the test asks whether this is the JSON at all.
        self.assertNotIn('application/json', response.headers.get('Content-Type', ''))
        self.assertFalse(self.order.partner_shipping_id.street in response.text,
                         'no part of the order leaves the server')
