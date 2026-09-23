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
        """An order all the way through to delivered, the way a card is minted.

        The last step is not an advance any more. `mart369_action_advance`
        stops at out-for-delivery on purpose and the close needs the code the
        shop issued, so this does what the rider does: reads it off the order
        and hands it back. Same walk as mart369_order's own `_deliver`.
        """
        order = self._place(**overrides)
        self._pay(order)
        while order.mart369_state != 'out':
            order.mart369_action_advance()
        order.mart369_action_deliver(order.sudo().mart369_otp_code)
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
