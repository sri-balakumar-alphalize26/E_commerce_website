"""Pop-ups (models/push.py).

The cryptography itself is checked against an independent implementation
outside Odoo; these check the shop's side of it: who gets a browser, that an
order step sends to the right customer's browsers and nobody else's, and that
a browser which has gone away is forgotten.
"""

import base64
import json
import os
from unittest.mock import patch

from odoo.tests import tagged

from .common import Mart369AccountCase, Mart369AccountHttpCase


def _browser_keys():
    """What a real browser hands over when it says yes."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b64 = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
    return {'p256dh': b64(public), 'auth': b64(os.urandom(16))}


class _Response:
    def __init__(self, status):
        self.status_code = status
        self.text = ''


@tagged('post_install', '-at_install')
class TestMart369Push(Mart369AccountCase):

    def setUp(self):
        super().setUp()
        self.push = self.env['mart369.push']
        self.Sub = self.env['mart369.push.subscription'].sudo()

    def _subscribe(self, partner=None, endpoint='https://push.example.com/abc'):
        return self.push._mart369_subscribe(
            partner or self.partner, {'endpoint': endpoint, 'keys': _browser_keys()}, 'Test browser')

    def test_the_shop_key_is_made_once_and_kept(self):
        first = self.push._mart369_public_key()
        self.assertEqual(len(base64.urlsafe_b64decode(first + '==')), 65)
        self.assertEqual(self.push._mart369_public_key(), first,
                         'a new key would cut off every browser already signed up')

    def test_a_browser_is_remembered_once(self):
        row = self._subscribe()
        self.assertEqual(row.partner_id, self.partner)
        again = self._subscribe()
        self.assertEqual(again, row, 'the same browser is one row, not two')

    def test_a_shared_computer_moves_to_whoever_signed_in(self):
        self._subscribe()
        row = self._subscribe(partner=self._other_customer())
        self.assertEqual(row.partner_id, self._other_customer())
        self.assertEqual(self.Sub.search_count([('endpoint', '=', row.endpoint)]), 1)

    def test_nonsense_is_not_remembered(self):
        for body in ({'endpoint': 'http://plain.example.com/x', 'keys': _browser_keys()},
                     {'endpoint': 'https://push.example.com/x', 'keys': {'p256dh': 'abc', 'auth': 'def'}},
                     {'endpoint': 'https://push.example.com/x'}):
            self.assertFalse(self.push._mart369_subscribe(self.partner, body))

    def test_turning_off_only_touches_your_own(self):
        row = self._subscribe()
        self.assertFalse(self.push._mart369_unsubscribe(self._other_customer(), row.endpoint))
        self.assertTrue(row.exists())
        self.assertTrue(self.push._mart369_unsubscribe(self.partner, row.endpoint))
        self.assertFalse(row.exists())

    def test_an_order_step_goes_to_that_customers_browsers_only(self):
        mine = self._subscribe()
        self._subscribe(partner=self._other_customer(), endpoint='https://push.example.com/theirs')
        sent = []
        with patch.object(type(self.push), '_mart369_send_later', lambda self, jobs: sent.extend(jobs)):
            order = self._place()
            self._pay(order)
        self.assertTrue(sent, 'placing the order sends a pop-up')
        self.assertEqual({job['sub'] for job in sent}, {mine.id})
        message = json.loads(sent[-1]['payload'])
        self.assertEqual(message['title'], 'Order confirmed')
        self.assertIn(order.mart369_ref, message['body'])
        self.assertEqual(message['url'], '/track/%s' % order.mart369_ref)
        self.assertEqual(message['id'], 'n-%s-placed' % order.mart369_ref,
                         "the bell's id, so opening the pop-up marks that row read")

    def test_packed_says_packed_but_marks_the_confirmed_row(self):
        order = self._place()
        message = self.push._mart369_order_message(order, 'packed')
        self.assertEqual(message['title'], 'Order packed')
        self.assertEqual(message['id'], 'n-%s-placed' % order.mart369_ref)

    def test_no_browser_no_send(self):
        order = self._place()
        self.assertEqual(self.push._mart369_jobs(
            self.partner, self.push._mart369_order_message(order, 'placed')), [])

    def test_a_browser_that_has_gone_away_is_forgotten(self):
        kept = self._subscribe()
        gone = self._subscribe(endpoint='https://push.example.com/gone')
        jobs = self.push._mart369_jobs(self.partner, {'title': 't', 'body': 'b', 'url': '/'})

        def post(url, **kwargs):
            self.assertEqual(kwargs['headers']['Content-Encoding'], 'aes128gcm')
            self.assertTrue(kwargs['headers']['Authorization'].startswith('vapid t='))
            return _Response(410 if url.endswith('/gone') else 201)

        with patch('odoo.addons.mart369_account.models.push.requests.post', post):
            results = self.push._mart369_deliver(jobs)
        self.assertEqual(results[kept.id], 'sent')
        self.assertEqual(results[gone.id], 'gone')
        self.assertTrue(kept.last_sent)
        self.assertFalse(gone.exists())

    def test_a_push_service_that_is_down_does_not_raise(self):
        self._subscribe()
        jobs = self.push._mart369_jobs(self.partner, {'title': 't', 'body': 'b', 'url': '/'})

        def post(url, **kwargs):
            raise ConnectionError('no route')

        with patch('odoo.addons.mart369_account.models.push.requests.post', post):
            results = self.push._mart369_deliver(jobs)
        self.assertEqual(list(results.values()), ['failed'])


@tagged('post_install', '-at_install')
class TestMart369PushRoutes(Mart369AccountHttpCase):

    def _req(self, path, method='GET', body=None):
        response = self.opener.request(
            method, self.base_url() + path,
            data=json.dumps(body or {}) if method != 'GET' else None,
            headers={'Content-Type': 'application/json'}, timeout=30)
        return response.status_code, response.json()

    def test_sign_up_and_off_through_the_routes(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._req('/369mart/push/key')
        self.assertEqual(status, 200)
        self.assertTrue(payload['key'])

        body = {'endpoint': 'https://push.example.com/route', 'keys': _browser_keys()}
        status, __ = self._req('/369mart/push/subscribe', 'POST', body)
        self.assertEqual(status, 201)
        Sub = self.env['mart369.push.subscription'].sudo()
        self.assertEqual(Sub.search([('endpoint', '=', body['endpoint'])]).partner_id, self.partner)

        status, __ = self._req('/369mart/push/unsubscribe', 'POST', {'endpoint': body['endpoint']})
        self.assertEqual(status, 200)
        self.assertFalse(Sub.search_count([('endpoint', '=', body['endpoint'])]))

    def test_a_bad_address_is_refused(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._req('/369mart/push/subscribe', 'POST', {'endpoint': 'nope'})
        self.assertEqual(status, 400)
        self.assertEqual(payload['field'], 'endpoint')

    def test_test_pop_up_without_a_browser_says_so(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._req('/369mart/push/test', 'POST')
        self.assertEqual(status, 404)
        self.assertFalse(payload['ok'])

    def test_signed_out_cannot_sign_up(self):
        response = self.url_open('/369mart/push/subscribe', data=json.dumps({}),
                                 headers={'Content-Type': 'application/json'})
        self.assertNotEqual(response.status_code, 201)
