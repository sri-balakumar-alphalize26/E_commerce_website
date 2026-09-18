"""Fixtures for the account tests.

Builds on mart369_order's, because almost everything here needs a real order
behind it: a review is only verified if the customer bought the thing, a scratch
card is only minted when an order is delivered, and a referral only pays when
the friend's first order is paid for.
"""

from odoo.tests import HttpCase, TransactionCase

from odoo.addons.mart369_order.tests.common import Mart369OrderFixtures


class Mart369AccountFixtures(Mart369OrderFixtures):

    def _delivered(self, **overrides):
        """An order all the way through to delivered, the way a card is minted."""
        order = self._place(**overrides)
        self._pay(order)
        for __ in range(3):
            order.mart369_action_advance()
        return order

    def _review(self, product=None, **values):
        """Write a review the way the route does."""
        body = {'stars': 5, 'title': 'Very good', 'text': 'Arrived cold and fresh.',
                'tags': ['Fresh'], 'photos': 0}
        body.update(values)
        return self.env['rating.rating']._mart369_write_review(
            self.partner, product or self.quick_product, body)

    def _other_customer(self):
        """A second signed-up customer, for the ownership tests."""
        return self.other.partner_id


class Mart369AccountCase(Mart369AccountFixtures, TransactionCase):
    pass


class Mart369AccountHttpCase(Mart369AccountFixtures, HttpCase):
    pass
