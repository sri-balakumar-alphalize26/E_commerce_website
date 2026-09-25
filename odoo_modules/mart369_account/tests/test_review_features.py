"""Reviews like the big marketplaces: the filter, photos and video with limits,
staff replies, shopper votes, and the report block."""

import base64
import io
import struct

from PIL import Image

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import HttpCase


def _png(size=(2400, 1800)):
    buf = io.BytesIO()
    Image.new('RGB', size, (200, 30, 30)).save(buf, 'PNG')
    return base64.b64encode(buf.getvalue()).decode()


def _mp4(seconds, pad=0):
    """Just enough MP4 for the length to be read: an mvhd box, version 0."""
    body = b'\x00' + b'\x00\x00\x00' + struct.pack('>IIII', 0, 0, 1000, int(seconds * 1000))
    box = struct.pack('>I', 8 + len(body)) + b'mvhd' + body
    return base64.b64encode(b'\x00\x00\x00\x18ftypisom' + box + b'\x00' * pad).decode()


@tagged('post_install', '-at_install')
class TestReviewFeatures(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Rating = self.env['rating.rating']
        self.Config = self.env['mart369.config']
        self.product = self.env['product.template'].create({'name': 'Review Feature Mouse', 'list_price': 40.0})
        self.author = self.env['res.partner'].create({'name': 'Author'})
        self.others = [self.env['res.partner'].create({'name': 'Shopper %s' % i}) for i in range(3)]

    def _review(self, text='Works well', title='Good', stars=4, partner=None):
        return self.Rating._mart369_write_review(partner or self.author, self.product,
                                                 {'stars': stars, 'title': title, 'text': text})

    # ------------------------------------------------------------- the filter

    def test_clean_goes_live_and_flagged_waits_with_the_reason(self):
        self.assertEqual(self._review().mart369_state, 'published')
        other = self.env['product.template'].create({'name': 'Other'})
        for text, why in [('call me on 98450 11223', 'phone number'),
                          ('see www.cheap-stuff.xyz', 'link or e-mail'),
                          ('what a f*ck up', 'abusive words'),
                          ('இது தேவடியா பொருள்', 'abusive words')]:
            row = self.Rating._mart369_write_review(
                self.env['res.partner'].create({'name': why}), other, {'stars': 1, 'text': text})
            self.assertEqual(row.mart369_state, 'pending', text)
            self.assertIn(why, row.mart369_held_reason, text)

    def test_staff_words_hold_too_and_a_fixed_review_goes_live(self):
        self.Config.mart369_admin_save('reviews', {'blockedWords': 'rubbishbrand\nகேவலம்'})
        row = self._review(text='Total rubbishbrand stuff')
        self.assertEqual(row.mart369_state, 'pending')
        row = self._review(text='Actually fine after all')
        self.assertEqual(row.mart369_state, 'published', 'the author fixed it')
        row = self._review(text='ரொம்ப கேவலம்')
        self.assertEqual(row.mart369_state, 'pending', 'Tamil words from Settings hold it')

    def test_a_hidden_review_stays_hidden_when_edited(self):
        row = self._review()
        self.Rating.mart369_admin_moderate(row.id, 'hidden', 'Spam')
        self.assertEqual(row.mart369_hidden_reason, 'Spam')
        row = self._review(text='clean words now')
        self.assertEqual(row.mart369_state, 'hidden')
        with self.assertRaises(UserError):
            self.Rating.mart369_admin_moderate(row.id, 'hidden', 'Because')

    # --------------------------------------------------------- photos, video

    def test_media_limits_from_settings_are_enforced(self):
        self.Config.mart369_admin_save('reviews', {'maxPhotos': 2, 'photoMb': 5, 'video': True,
                                                   'videoSeconds': 30, 'videoMb': 1})
        row = self._review()
        photo = row._mart369_add_media('a.png', 'image/png', _png())
        self.assertEqual(photo.state, 'pending', 'waits for staff')
        stored = Image.open(io.BytesIO(base64.b64decode(photo.attachment_id.datas)))
        self.assertLessEqual(max(stored.size), 1600, 'shrunk before saving')
        row._mart369_add_media('b.png', 'image/png', _png((400, 300)))
        with self.assertRaises(UserError):
            row._mart369_add_media('c.png', 'image/png', _png((400, 300)))  # third photo
        with self.assertRaises(UserError):
            row._mart369_add_media('x.gif', 'image/gif', _png((10, 10)))    # wrong type
        with self.assertRaises(UserError):
            row._mart369_add_media('long.mp4', 'video/mp4', _mp4(45))      # too long
        with self.assertRaises(UserError):
            row._mart369_add_media('big.mp4', 'video/mp4', _mp4(10, pad=2 * 1024 * 1024))  # too big
        video = row._mart369_add_media('ok.mp4', 'video/mp4', _mp4(12))
        self.assertAlmostEqual(video.seconds, 12, places=1)
        with self.assertRaises(UserError):
            row._mart369_add_media('two.mp4', 'video/mp4', _mp4(5))        # one video only
        self.Config.mart369_admin_save('reviews', {'video': False})
        other = self._review(partner=self.others[0])
        with self.assertRaises(UserError):
            other._mart369_add_media('v.mp4', 'video/mp4', _mp4(5))

    def test_staff_approve_and_removing_deletes_the_file(self):
        row = self._review()
        keep = row._mart369_add_media('a.png', 'image/png', _png((400, 300)))
        drop = row._mart369_add_media('b.png', 'image/png', _png((400, 300)))
        attachment = drop.attachment_id
        self.Rating.mart369_admin_media(keep.id, 'approve')
        self.Rating.mart369_admin_media(drop.id, 'remove')
        self.assertFalse(attachment.exists(), 'the file is gone, not just hidden')
        page = self.env['mart369.product.page'].reviews(self.product, {'reviews'}, {})
        media = page['reviews'][0]['media']
        self.assertEqual([m['id'] for m in media], [keep.id], 'only approved media is public')

    # ------------------------------------------------ reply, votes, report

    def test_reply_shows_on_the_product_page(self):
        row = self._review()
        self.Rating.mart369_admin_reply(row.id, 'Thanks - glad it works!')
        entry = self.env['mart369.product.page'].reviews(self.product, {'reviews'}, {})['reviews'][0]
        self.assertEqual(entry['reply'], 'Thanks - glad it works!')
        self.assertEqual(entry['id'], row.id)
        self.assertIn('verified', entry)

    def test_one_vote_each_and_three_reports_send_it_back(self):
        row = self._review()
        self.assertTrue(row._mart369_vote(self.others[0], 'helpful'))
        self.assertFalse(row._mart369_vote(self.others[0], 'helpful'), 'once per customer')
        self.assertEqual(row.mart369_helpful, 1)
        with self.assertRaises(UserError):
            row._mart369_vote(self.author, 'helpful')
        for other in self.others:
            row._mart369_vote(other, 'report', 'Spam or advertising')
        self.assertEqual(row.mart369_reports, 3)
        self.assertEqual(row.mart369_state, 'pending')
        self.assertIn('reported', row.mart369_held_reason)

    def test_the_report_block(self):
        tags = 'Damaged,Poor quality'
        for i in range(3):
            p = self.env['res.partner'].create({'name': 'Rater %s' % i})
            self.Rating._mart369_write_review(p, self.product, {'stars': 1, 'text': 'broke', 'tags': tags})
        report = self.Rating.mart369_admin_list()['report']
        self.assertIn(self.product.id, [w['productId'] for w in report['worst']])
        complaints = {c['tag']: c['count'] for c in report['complaints']}
        self.assertGreaterEqual(complaints.get('Damaged', 0), 3)

    def test_settings_save_and_refuse(self):
        self.Config.mart369_admin_save('reviews', {'maxPhotos': 3, 'videoMb': 10})
        self.assertEqual(self.Config.mart369_admin_settings()['reviews']['maxPhotos'], 3)
        with self.assertRaises(UserError):
            self.Config.mart369_admin_save('reviews', {'photoMb': 0})


@tagged('post_install', '-at_install')
class TestReviewMediaRoute(HttpCase):

    def test_waiting_media_is_not_public(self):
        product = self.env['product.template'].create({'name': 'Route Mouse', 'list_price': 10.0})
        author = self.env['res.partner'].create({'name': 'Route Author'})
        row = self.env['rating.rating']._mart369_write_review(author, product, {'stars': 5, 'text': 'great'})
        media = row._mart369_add_media('a.png', 'image/png', _png((200, 200)))
        url = '/369mart/reviews/photo/%d' % media.id
        self.assertEqual(self.url_open(url).status_code, 404, 'waiting: not public')
        self.env['rating.rating'].mart369_admin_media(media.id, 'approve')
        res = self.url_open(url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.headers['Content-Type'].startswith('image/'))
