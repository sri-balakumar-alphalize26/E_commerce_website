"""The console's review routes (controllers/review_admin_api.py): the same
moderation, reply and photo actions the Odoo desk takes, over HTTP."""

import base64
import json

from odoo.tests import tagged

from .common import Mart369AccountHttpCase

HEADERS = {'Content-Type': 'application/json'}


@tagged('post_install', '-at_install')
class TestReviewConsoleRoutes(Mart369AccountHttpCase):

    def _post(self, path, body=None):
        return self.url_open(path, data=json.dumps(body or {}), headers=HEADERS)

    def _media(self, review):
        att = self.env['ir.attachment'].sudo().create({
            'name': 'photo.png', 'datas': base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'0' * 20),
            'mimetype': 'image/png'})
        return self.env['mart369.review.media'].sudo().create({
            'rating_id': review.id, 'attachment_id': att.id, 'kind': 'photo', 'state': 'pending'})

    def test_hide_needs_a_reason_and_publish_clears_it(self):
        review = self._review()
        self.authenticate('admin', 'admin')
        r = self._post('/369mart/admin/reviews/%s/moderate' % review.id, {'state': 'hidden'})
        self.assertEqual(r.status_code, 400)
        r = self._post('/369mart/admin/reviews/%s/moderate' % review.id, {'state': 'hidden', 'reason': 'Spam'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['review']['hiddenReason'], 'Spam')
        r = self._post('/369mart/admin/reviews/%s/moderate' % review.id, {'state': 'published'})
        self.assertEqual(r.json()['review']['state'], 'published')
        self.assertEqual(r.json()['review']['hiddenReason'], '')

    def test_reply_is_saved_and_empty_removes_it(self):
        review = self._review()
        self.authenticate('admin', 'admin')
        r = self._post('/369mart/admin/reviews/%s/reply' % review.id, {'text': 'Thank you!'})
        self.assertEqual(r.json()['review']['reply'], 'Thank you!')
        self.assertTrue(r.json()['review']['replyBy'])
        r = self._post('/369mart/admin/reviews/%s/reply' % review.id, {'text': '  '})
        self.assertEqual(r.json()['review']['reply'], '')

    def test_a_photo_is_approved_then_removed(self):
        review = self._review()
        media = self._media(review)
        self.authenticate('admin', 'admin')
        r = self._post('/369mart/admin/reviews/media/%s' % media.id, {'action': 'approve'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['review']['mediaWaiting'], 0)
        r = self._post('/369mart/admin/reviews/media/%s' % media.id, {'action': 'remove'})
        self.assertEqual(r.json()['review']['media'], [])
        self.assertFalse(media.exists())

    def test_a_shopper_is_refused(self):
        review = self._review()
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        for path, body in (('/369mart/admin/reviews/%s/moderate' % review.id, {'state': 'hidden', 'reason': 'Spam'}),
                           ('/369mart/admin/reviews/%s/reply' % review.id, {'text': 'mine'})):
            self.assertEqual(self._post(path, body).status_code, 403)
        self.assertFalse(review.publisher_comment)
