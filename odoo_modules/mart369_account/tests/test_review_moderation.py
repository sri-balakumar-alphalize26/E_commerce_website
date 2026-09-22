"""Moderation: whether the shop shows a review.

The interesting tests here are the two that ask a *different* screen. A hidden
review leaving the product page is the obvious half; a hidden review leaving the
star on every card is the half that is easy to miss, because the card reads its
own copy of the domain in another module entirely
(mart369_catalog RATING_DOMAIN, mart369_product REVIEW_DOMAIN).
"""

from odoo.tests import tagged

from .common import Mart369AccountCase


@tagged('post_install', '-at_install')
class TestMart369ReviewModeration(Mart369AccountCase):

    def _page_reviews(self, product=None):
        payload = self.env['mart369.product.page'].sudo().payload(
            product or self.quick_product)
        return payload['d'].get('reviews') or []

    def _card(self, product=None):
        """The rating the card carries, straight off `RATING_DOMAIN`."""
        product = product or self.quick_product
        return product.sudo()._mart369_signal_map().get(product.id, {})

    # ----------------------------------------------------------- the default

    def test_a_new_review_is_published_straight_away(self):
        """The policy: publish now, read the queue afterwards. A page that
        waits for somebody to work a queue goes quiet the first week nobody
        does."""
        row = self._review(text='Sweet and cheap')
        self.assertEqual(row.mart369_state, 'published')
        self.assertEqual(len(self._page_reviews()), 1, 'visible without a click')

    # -------------------------------------------------------------- hiding

    def test_hiding_takes_it_off_the_product_page(self):
        row = self._review()
        row.mart369_state = 'hidden'
        self.assertEqual(self._page_reviews(), [])

    def test_hiding_also_takes_its_score_off_the_card(self):
        """The regression this file exists for.

        `RATING_DOMAIN` in mart369_catalog is a second, unimported copy of the
        product page's domain. Filter one and not the other and the review is
        invisible while its one star still drags the average down on every
        listing in the shop.
        """
        row = self._review(stars=1)
        self.assertEqual(self._card().get('ratingCount'), 1)

        row.mart369_state = 'hidden'
        self.assertEqual(self._card().get('ratingCount'), 0,
                         'a hidden review counts for nothing, anywhere')

    def test_waiting_is_not_shown_either(self):
        row = self._review()
        row.mart369_state = 'pending'
        self.assertEqual(self._page_reviews(), [],
                         "only 'published' is published")

    # ------------------------------------------------------- whose call it is

    def test_editing_a_hidden_review_does_not_republish_it(self):
        """Otherwise retyping your review is a one-click way to undo a
        moderator, and nothing in the app would say it had happened."""
        row = self._review()
        row.mart369_state = 'hidden'
        again = self._review(stars=4, title='Second go', text='Trying again')
        self.assertEqual(again, row, 'still the same review')
        self.assertEqual(again.rating, 4, 'their words did change')
        self.assertEqual(again.mart369_state, 'hidden', 'the state did not')

    def test_an_order_rating_is_never_moderated(self):
        """A different `res_model`, and it never reaches a product page.

        It does carry a state - the field has a default and every row on the
        table gets one - but nothing reads it, and the staff screens must not
        offer it as something to work on. Being absent from the console's list
        is the part that matters, not what the column happens to say.
        """
        order = self._delivered()
        row = self.env['rating.rating']._mart369_rate_order(
            self.partner, order, {'stars': 5, 'comment': 'Quick'})
        self.assertEqual(row.res_model, 'sale.order')

        listed = self.env['rating.rating'].sudo().mart369_admin_list()
        self.assertNotIn(row.id, [r['id'] for r in listed['reviews']],
                         'not a product review, so not for staff to moderate')

    # --------------------------------------------------------- what staff see

    def test_the_console_list_sees_every_state_and_counts_them_all(self):
        """The screen exists to change the state, so the state must not also
        be what hides rows from it."""
        Reviews = self.env['rating.rating'].sudo()
        before = Reviews.mart369_admin_list()['counts']

        mine = self._review()
        mine.mart369_state = 'hidden'

        payload = Reviews.mart369_admin_list()
        self.assertEqual(payload['counts']['hidden'], before['hidden'] + 1)
        self.assertIn(mine.id, [r['id'] for r in payload['reviews']],
                      'hidden is still listed - the screen exists to unhide it')

        only_published = Reviews.mart369_admin_list(state='published')
        self.assertNotIn(mine.id, [r['id'] for r in only_published['reviews']])
        self.assertEqual(only_published['counts']['hidden'],
                         before['hidden'] + 1,
                         'the tiles count everything, not the filtered rows')

    def test_the_console_row_names_the_product_and_the_customer(self):
        mine = self._review()
        listed = self.env['rating.rating'].sudo().mart369_admin_list()['reviews']
        row = next(r for r in listed if r['id'] == mine.id)
        self.assertEqual(row['product'], self.quick_product.display_name)
        self.assertEqual(row['by'], self.partner.name)
        self.assertEqual(row['state'], 'published')

    def test_the_admin_shape_does_not_leak_into_the_shopper_one(self):
        """`_mart369_serialize` is a customer reading their own reviews back.
        Who wrote a review is not part of that."""
        row = self._review()
        shopper = row._mart369_serialize()
        self.assertNotIn('by', shopper)
        self.assertNotIn('productId', shopper)
        self.assertIn('state', shopper,
                      'they are told why nobody else can see it')

    def test_searching_matches_the_product_name(self):
        """`res_id` is a bare integer, not a relation, so the product name
        cannot be walked in a domain and is searched separately."""
        mine = self._review()
        hit = self.env['rating.rating'].sudo().mart369_admin_list(
            q=self.quick_product.name)
        self.assertIn(mine.id, [r['id'] for r in hit['reviews']])
        miss = self.env['rating.rating'].sudo().mart369_admin_list(
            q='nothing in this shop is called this')
        self.assertEqual(miss['reviews'], [])
