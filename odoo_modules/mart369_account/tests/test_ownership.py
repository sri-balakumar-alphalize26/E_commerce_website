"""The test most worth failing loudly.

Reviews, invites, scratch cards and a wishlist are all one customer's own
things. Every route finds them *within* the signed-in customer's records rather
than finding them and then checking - so a guessed id is simply not there.

A miss must be **404, not 403**: 403 confirms the record exists, which is half
of what someone probing for one wants to know.
"""

import json

from odoo.tests import tagged

from .common import Mart369AccountHttpCase


@tagged('post_install', '-at_install')
class TestMart369AccountOwnership(Mart369AccountHttpCase):

    def _req(self, path, method='GET', body=None):
        response = self.opener.request(
            method, self.base_url() + path,
            data=json.dumps(body or {}) if method != 'GET' else None,
            headers={'Content-Type': 'application/json'}, timeout=30)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return response.status_code, payload

    def setUp(self):
        super().setUp()
        self.order = self._delivered()
        self.card = self.env['mart369.scratch'].sudo().search(
            [('order_id', '=', self.order.id)], limit=1)
        self.review = self._review()
        self.authenticate('someone.else@369mart.test', 'someone-else-369')

    # ------------------------------------------------------ somebody else's

    def test_another_customers_scratch_card_cannot_be_scratched(self):
        status, __ = self._req(
            '/369mart/rewards/%s/scratch' % self.card.id, 'POST')
        self.assertEqual(status, 404, 'not 403 - that would confirm it exists')
        self.card.invalidate_recordset()
        self.assertFalse(self.card.scratched, 'and it is untouched')

    def test_another_customers_review_cannot_be_deleted(self):
        status, __ = self._req(
            '/369mart/reviews/%s' % self.quick_product.id, 'DELETE')
        self.assertEqual(status, 404)
        self.assertTrue(self.review.exists(), 'and it survives')

    def test_another_customers_order_cannot_be_rated(self):
        status, __ = self._req(
            '/369mart/orders/%s/rate' % self.order.mart369_ref, 'POST', {'stars': 1})
        self.assertEqual(status, 404)

    def test_another_customers_reviews_are_not_in_their_list(self):
        status, payload = self._req('/369mart/reviews')
        self.assertEqual(status, 200)
        self.assertEqual(payload.get('reviews'), {})

    def test_another_customers_rewards_are_not_in_their_list(self):
        status, payload = self._req('/369mart/rewards')
        self.assertEqual(status, 200)
        self.assertEqual(payload.get('scratch'), [])

    def test_another_customers_notifications_are_not_in_their_feed(self):
        status, payload = self._req('/369mart/notifications')
        self.assertEqual(status, 200)
        ids = ' '.join(row['id'] for row in payload.get('notifications', []))
        self.assertNotIn(self.order.mart369_ref, ids)

    def test_another_customers_invites_are_not_in_their_list(self):
        self.env['mart369.referral'].sudo().create({
            'partner_id': self.partner.id, 'name': 'Their Friend'})
        status, payload = self._req('/369mart/referrals')
        self.assertEqual(status, 200)
        self.assertEqual(payload.get('referrals'), [])

    # ------------------------------------------------------------- made up

    def test_a_made_up_scratch_card_is_not_found(self):
        status, __ = self._req('/369mart/rewards/99999999/scratch', 'POST')
        self.assertEqual(status, 404)

    # ------------------------------------------------------------ their own

    def test_a_customer_can_read_their_own_reviews(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._req('/369mart/reviews')
        self.assertEqual(status, 200)
        self.assertIn(str(self.quick_product.id), payload['reviews'])

    def test_a_customer_gets_their_own_referral_code(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._req('/369mart/referrals')
        self.assertEqual(status, 200)
        self.assertTrue(payload['code'].endswith('369'))
        self.assertEqual(payload['code'], self.partner.mart369_referral_code)
