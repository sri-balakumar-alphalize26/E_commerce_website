"""The reviews desk, and the two filters it added.

The desk itself is thin - it calls `mart369_admin_list` and draws what comes
back - so what is worth pinning here is the filtering, plus the one rule the
screen would be useless without: **narrowing the list must not change the
tiles**. A "Waiting 3" that fell to 0 because somebody ticked "With photos"
would stop answering the only question the tile is there to answer.

Counts are measured as a delta, never against zero: this database already
holds reviews from the demo data and from whatever anybody seeded.
"""

from odoo.tests import tagged

from .common import Mart369AccountCase, Mart369AccountHttpCase


@tagged('post_install', '-at_install')
class TestReviewFilters(Mart369AccountCase):

    def _ids(self, **kwargs):
        listed = self.env['rating.rating'].sudo().mart369_admin_list(**kwargs)
        return [r['id'] for r in listed['reviews']]

    def test_verified_and_unverified_are_both_askable(self):
        """Tri-state, not a truthy flag. `False` has to be able to mean
        "only the ones nobody can prove bought it"."""
        self._delivered()
        bought = self._review(product=self.quick_product)
        self.assertTrue(bought.mart369_verified)
        not_bought = self._review(product=self.express_product, stars=4)
        self.assertFalse(not_bought.mart369_verified)

        self.assertIn(bought.id, self._ids(verified=True))
        self.assertNotIn(not_bought.id, self._ids(verified=True))

        self.assertIn(not_bought.id, self._ids(verified=False))
        self.assertNotIn(bought.id, self._ids(verified=False))

    def test_photos_filters_both_ways(self):
        with_shots = self._review(product=self.quick_product, photos=2)
        without = self._review(product=self.express_product, stars=4, photos=0)

        self.assertIn(with_shots.id, self._ids(photos=True))
        self.assertNotIn(without.id, self._ids(photos=True))
        self.assertIn(without.id, self._ids(photos=False))

    def test_asking_for_neither_is_the_old_behaviour(self):
        """A screen that never sends them must see exactly what it saw."""
        mine = self._review()
        self.assertIn(mine.id, self._ids())
        self.assertIn(mine.id, self._ids(verified=None, photos=None))

    def test_the_filters_combine(self):
        self._delivered()
        both = self._review(product=self.quick_product, photos=1)
        self.assertTrue(both.mart369_verified)
        only_verified = self._review(
            product=self.express_product, stars=4, photos=0)

        hits = self._ids(verified=True, photos=True)
        self.assertIn(both.id, hits)
        self.assertNotIn(only_verified.id, hits)

    def test_filtering_does_not_move_the_tiles(self):
        """The rule the desk would be useless without."""
        Reviews = self.env['rating.rating'].sudo()
        self._review(product=self.quick_product, photos=0)

        wide = Reviews.mart369_admin_list()
        narrow = Reviews.mart369_admin_list(photos=True)

        self.assertEqual(narrow['counts'], wide['counts'],
                         'the tiles count every review, not the filtered ones')
        self.assertEqual(narrow['average'], wide['average'])
        self.assertLess(len(narrow['reviews']), len(wide['reviews']),
                        'and the list really did narrow')

    def test_a_filter_still_respects_the_tab(self):
        mine = self._review(product=self.quick_product, photos=1)
        mine.mart369_state = 'hidden'
        self.assertNotIn(mine.id, self._ids(state='published', photos=True))
        self.assertIn(mine.id, self._ids(state='hidden', photos=True))


@tagged('post_install', '-at_install')
class TestReviewDeskTour(Mart369AccountHttpCase):

    def test_the_desk_moderates_a_review(self):
        """Seeds its own review: nothing ships a published one, and the tour
        needs a row it is allowed to take down."""
        review = self._review(title='Desk tour', text='Something to hide.')
        review.mart369_state = 'published'

        # Generous, because the first request rebuilds the asset bundle.
        self.start_tour('/odoo/mart-reviews', 'mart369_review_desk',
                        login='admin', timeout=600)

        self.assertEqual(review.mart369_state, 'hidden',
                         'the screen really wrote to the model')
