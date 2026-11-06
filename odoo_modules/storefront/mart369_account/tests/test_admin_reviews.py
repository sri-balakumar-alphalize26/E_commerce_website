"""The staff side of reviews, over HTTP.

Two things are worth pinning here, and neither would announce itself.

**Who may look.** These routes have no per-shopper fence - that is the point of
them - so the group check is the only thing between a shopper and every review
in the shop, with the customers' names attached. A shopper is refused rather
than handed an empty list.

**What the console may write.** Staff moderate a review; they do not edit one.
The allow-list is a single field, and a request carrying stars or new words
must change nothing - otherwise "the store rewrote my review" is one careless
form away.
"""

import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}

LIST = '/369mart/admin/reviews'


@tagged('post_install', '-at_install')
class TestAdminReviews(HttpCase):

    def setUp(self):
        super().setUp()
        self.product = self.env['product.template'].create({
            'name': 'Admin Review Test Product',
            'list_price': 40.0,
        })
        self.customer = self.env['res.partner'].create({'name': 'Reviewer'})
        self.review = self.env['rating.rating']._mart369_write_review(
            self.customer, self.product,
            {'stars': 2, 'title': 'Not great', 'text': 'Arrived warm.'})
        self.shopper = self.env['res.users'].sudo().create({
            'name': 'A Shopper',
            'login': 'mart369_review_shopper',
            'password': 'mart369_review_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    # ------------------------------------------------------------- acting

    def _send(self, method, path, payload=None):
        return self.url_open(
            path, data=json.dumps(payload or {}), headers=HEADERS, method=method)

    def _patch(self, payload, review=None):
        return self._send(
            'PATCH', '%s/%s' % (LIST, (review or self.review).id), payload)

    # ------------------------------------------------------------- the lock

    def test_a_shopper_is_refused_every_admin_route(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        self.authenticate('mart369_review_shopper', 'mart369_review_shopper')
        self.assertEqual(self.url_open(LIST).status_code, 403)
        self.assertEqual(self._patch({'state': 'hidden'}).status_code, 403)
        self.assertEqual(self.review.mart369_state, 'published',
                         'and nothing moved')

    def test_signed_out_is_sent_to_the_sign_in_page(self):
        """`auth='user'` answers 303 to /web/login rather than 401, and
        `url_open` follows it - so what proves the fence held is where the
        request landed, not its status code."""
        response = self.url_open(LIST)
        self.assertIn('/web/login', response.url)
        self.assertNotIn('"ok": true', response.text)
        self.assertEqual(self.review.mart369_state, 'published')

    # --------------------------------------------------------- the one write

    def test_staff_can_hide_and_publish_again(self):
        self.authenticate('admin', 'admin')

        hidden = self._patch({'state': 'hidden'})
        self.assertEqual(hidden.status_code, 200)
        self.assertTrue(hidden.json()['ok'])
        self.assertEqual(self.review.mart369_state, 'hidden')
        self.assertEqual(hidden.json()['review']['state'], 'hidden',
                         'the row comes back, so the screen need not guess')

        back = self._patch({'state': 'published'})
        self.assertEqual(back.status_code, 200)
        self.assertEqual(self.review.mart369_state, 'published')

    def test_the_console_cannot_rewrite_a_customers_review(self):
        """The allow-list is one field. Everything else is theirs."""
        self.authenticate('admin', 'admin')
        response = self._patch({
            'state': 'published',
            'rating': 5,
            'feedback': 'Actually it was wonderful',
            'mart369_title': 'Wonderful',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.review.rating, 2)
        self.assertEqual(self.review.feedback, 'Arrived warm.')
        self.assertEqual(self.review.mart369_title, 'Not great')

    def test_a_state_that_is_not_one_of_the_three_is_refused(self):
        self.authenticate('admin', 'admin')
        response = self._patch({'state': 'deleted'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'state')
        self.assertEqual(self.review.mart369_state, 'published')

    def test_a_made_up_review_is_a_404(self):
        self.authenticate('admin', 'admin')
        response = self._send('PATCH', '%s/%s' % (LIST, 88888888),
                              {'state': 'hidden'})
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------ the list

    def test_the_badge_route_answers_without_listing_anything(self):
        """Its own route so the sidebar does not pull every review once a
        minute to print one number."""
        self.authenticate('admin', 'admin')
        payload = self.url_open(LIST + '/counts').json()
        self.assertTrue(payload['ok'])
        self.assertIn('pending', payload['counts'])
        self.assertGreaterEqual(payload['counts']['published'], 1)
        self.assertNotIn('reviews', payload, 'counts only')

    def test_the_badge_route_is_not_read_as_a_review_id(self):
        """'counts' sits where an id goes, so route order is load-bearing."""
        self.authenticate('mart369_review_shopper', 'mart369_review_shopper')
        self.assertEqual(self.url_open(LIST + '/counts').status_code, 403)

    def test_the_list_carries_what_the_screen_draws(self):
        self.authenticate('admin', 'admin')
        payload = self.url_open(LIST).json()
        self.assertTrue(payload['ok'])
        mine = [r for r in payload['reviews'] if r['id'] == self.review.id]
        self.assertEqual(len(mine), 1)
        row = mine[0]
        self.assertEqual(row['product'], self.product.display_name)
        self.assertEqual(row['by'], 'Reviewer')
        self.assertEqual(row['stars'], 2)
        self.assertEqual(row['state'], 'published')
        self.assertIn('pending', payload['counts'])
        self.assertIn('average', payload)
