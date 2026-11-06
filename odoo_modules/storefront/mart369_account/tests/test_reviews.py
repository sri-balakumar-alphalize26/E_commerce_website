"""Reviews.

The first test is the one that matters: a review the product page cannot see is
the same bug this module exists to fix, just moved one layer down.
"""

from odoo.tests import tagged

from .common import Mart369AccountCase


@tagged('post_install', '-at_install')
class TestMart369Reviews(Mart369AccountCase):

    def test_a_written_review_really_shows_on_the_product_page(self):
        """The test this module exists for.

        REVIEW_DOMAIN wants consumed, not internal, and at least one star. Miss
        any one and the review saves and is never seen again - which looks
        exactly like the bug it was meant to fix. So this asks the product page
        itself rather than re-stating the domain and proving nothing.
        """
        self._review(title='Lovely', text='Sweet and cheap')
        payload = self.env['mart369.product.page'].sudo().payload(self.quick_product)
        reviews = payload['d'].get('reviews') or []
        self.assertEqual(len(reviews), 1, 'the page can see it')
        self.assertEqual(reviews[0]['text'], 'Sweet and cheap')
        self.assertEqual(reviews[0]['stars'], 5)

    def test_a_product_with_no_reviews_still_says_so_honestly(self):
        payload = self.env['mart369.product.page'].sudo().payload(self.express_product)
        self.assertEqual(payload['d'].get('reviews'), [],
                         'no reviews is an empty list, never invented ones')

    def test_a_review_carries_what_the_app_collected(self):
        row = self._review(title='Lovely', text='Sweet and cheap', tags=['Fresh'])
        payload = row._mart369_serialize()
        self.assertEqual(payload['stars'], 5)
        self.assertEqual(payload['title'], 'Lovely')
        self.assertEqual(payload['text'], 'Sweet and cheap')
        self.assertEqual(payload['tags'], ['Fresh'])

    def test_reviewing_twice_edits_rather_than_duplicates(self):
        """The app reads `myReviews[p.id]`, so one review per product is not a
        rule we may bend."""
        first = self._review(stars=5)
        second = self._review(stars=2, title='Changed my mind')
        self.assertEqual(first, second)
        self.assertEqual(second.rating, 2)
        self.assertEqual(self.env['rating.rating'].sudo().search_count([
            ('res_model', '=', 'product.template'),
            ('res_id', '=', self.quick_product.id),
            ('partner_id', '=', self.partner.id),
        ]), 1)

    def test_tags_that_do_not_belong_to_the_score_are_dropped(self):
        """The app offers a different set above and below three stars, so a
        one-star review tagged "Fresh" did not come from its own form."""
        row = self._review(stars=1, tags=['Fresh', 'Damaged'])
        self.assertEqual(row.mart369_tags, 'Damaged')

    def test_a_review_is_verified_only_when_they_really_bought_it(self):
        self._delivered()
        bought = self._review(product=self.quick_product)
        self.assertTrue(bought.mart369_verified)

        not_bought = self._review(product=self.express_product, stars=4)
        self.assertFalse(not_bought.mart369_verified,
                         'nothing in any order of theirs is this product')

    def test_stars_are_held_to_one_through_five(self):
        self.assertEqual(self._review(stars=99).rating, 5)
        self.env['rating.rating'].sudo().search([
            ('partner_id', '=', self.partner.id)]).unlink()
        self.assertEqual(self._review(stars=-4).rating, 1)

    # ------------------------------------------------------------ the order

    def test_an_order_rating_is_the_same_kind_of_record(self):
        """Two disconnected rating systems in the app; one model in Odoo."""
        order = self._delivered()
        row = self.env['rating.rating']._mart369_rate_order(
            self.partner, order, {'stars': 4, 'comment': 'Rider was quick',
                                  'tags': ['On-time delivery']})
        self.assertEqual(row.res_model, 'sale.order')
        self.assertEqual(row.res_id, order.id)
        self.assertEqual(row.rating, 4)
        self.assertEqual(row.feedback, 'Rider was quick')

    def test_rating_an_order_twice_edits_the_same_record(self):
        order = self._delivered()
        Rating = self.env['rating.rating']
        first = Rating._mart369_rate_order(self.partner, order, {'stars': 3})
        second = Rating._mart369_rate_order(self.partner, order, {'stars': 5})
        self.assertEqual(first, second)
        self.assertEqual(second.rating, 5)

    def test_a_product_review_and_an_order_rating_do_not_collide(self):
        order = self._delivered()
        self._review()
        self.env['rating.rating']._mart369_rate_order(self.partner, order, {'stars': 4})
        self.assertEqual(self.env['rating.rating'].sudo().search_count(
            [('partner_id', '=', self.partner.id)]), 2,
            'same model, different res_model - both survive')
