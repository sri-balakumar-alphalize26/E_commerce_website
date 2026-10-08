"""The review routes the shop's own pages now call, over real HTTP.

The product page's Helpful button only changed itself on screen, and the
review form's "+ Photo" uploaded nothing. They call these now; the model
behind them is tested in test_review_features.py.
"""

import json

from odoo.tests import tagged

from .common import Mart369AccountHttpCase
from .test_review_features import _png


@tagged('post_install', '-at_install')
class TestReviewRoutes(Mart369AccountHttpCase):

    def _req(self, path, method='POST', body=None):
        response = self.opener.request(
            method, self.base_url() + path, data=json.dumps(body or {}),
            headers={'Content-Type': 'application/json'}, timeout=30)
        return response.status_code, response.json()

    def setUp(self):
        super().setUp()
        self.review = self._review()
        self.assertEqual(self.review.mart369_state, 'published')

    def test_helpful_is_saved_once_per_customer(self):
        self.authenticate('someone.else@369mart.test', 'someone-else-369')
        status, payload = self._req('/369mart/reviews/%d/vote' % self.review.id, body={'kind': 'helpful'})
        self.assertEqual(status, 200)
        self.assertEqual((payload['counted'], payload['helpful']), (True, 1))
        status, payload = self._req('/369mart/reviews/%d/vote' % self.review.id, body={'kind': 'helpful'})
        self.assertEqual((payload['counted'], payload['helpful']), (False, 1), 'a second tap is not a second vote')

    def test_your_own_review_cannot_be_voted_up(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._req('/369mart/reviews/%d/vote' % self.review.id, body={'kind': 'helpful'})
        self.assertEqual(status, 400)
        self.assertFalse(payload['ok'])

    def test_a_photo_uploaded_from_the_form_waits_for_the_shop(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        status, payload = self._req('/369mart/reviews/%d/media' % self.quick_product.id, body={
            'name': 'front.jpg', 'mime': 'image/png', 'data': 'data:image/png;base64,' + _png((400, 300))})
        self.assertEqual(status, 201, payload)
        self.assertEqual(payload['media']['state'], 'pending')
        public = self.env['mart369.product.page'].reviews(self.quick_product, {'reviews'}, {})['reviews'][0]
        self.assertEqual(public['media'], [], 'not public until staff approve it')

        status, payload = self._req('/369mart/reviews/media/%d' % payload['media']['id'], 'DELETE')
        self.assertEqual(status, 200)
        self.review.invalidate_recordset()
        self.assertFalse(self.review.mart369_media_ids)

    def test_someone_elses_review_gets_no_photos_from_you(self):
        self.authenticate('someone.else@369mart.test', 'someone-else-369')
        status, __ = self._req('/369mart/reviews/%d/media' % self.quick_product.id, body={
            'name': 'x.png', 'mime': 'image/png', 'data': _png((40, 30))})
        self.assertEqual(status, 404, 'they have no review of it to add to')
        self.review.invalidate_recordset()
        self.assertFalse(self.review.mart369_media_ids)
