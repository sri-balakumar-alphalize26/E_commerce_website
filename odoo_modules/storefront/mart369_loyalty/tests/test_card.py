"""Which card an online order earns on.

One card per customer, whichever door they came in by: the counter keys cards
by mobile number, so an online customer with a card from the till must find
that card - and must never find somebody else's.
"""

from unittest.mock import patch

from odoo.tests import tagged

from .common import PHONE, Mart369LoyaltyCase


@tagged('post_install', '-at_install')
class TestLoyaltyCard(Mart369LoyaltyCase):

    def test_first_earn_makes_one_card_silently(self):
        """The card emails itself on an *active* create when card emails are
        on. A card made by an order must not message the customer out of
        nowhere, even then."""
        self.env['pos.loyalty.card.settings'].sudo().get_settings().email_card_enabled = True
        self.assertFalse(self._card())
        Card = type(self.env['pos.loyalty.card'])
        with patch.object(Card, '_email_card', autospec=True, return_value=True) as sent:
            order = self._place()
            self._pay(order)
            self._deliver(order)
        card = self._card()
        self.assertEqual(len(card), 1)
        self.assertEqual(card.state, 'active')
        self.assertEqual(card.phone, PHONE)
        self.assertEqual(card.partner_id, self.partner)
        sent.assert_not_called()

    def test_a_counter_card_with_the_same_number_is_reused(self):
        Card = self.env['pos.loyalty.card'].sudo()
        counter = Card.create({'name': 'At the till', 'phone': '+91 98765 43210'})
        counter.write({'partner_id': False})
        found = Card._mart369_card_for(self.partner, create=True)
        self.assertEqual(found, counter)
        self.assertEqual(counter.partner_id, self.partner, "The card was not linked.")

    def test_somebody_elses_card_is_never_taken(self):
        """Same number, different person: the number may have changed hands,
        the points did not. No card, and no second card with that number."""
        Card = self.env['pos.loyalty.card'].sudo()
        theirs = Card.create({'name': 'Someone Else', 'phone': PHONE,
                              'partner_id': self.other.partner_id.id})
        self.assertFalse(Card._mart369_card_for(self.partner, create=True))
        order = self._place()
        self._pay(order)
        self._deliver(order)
        self.assertFalse(order.mart369_points_earned)
        self.assertFalse(theirs.history_ids)

    def test_no_mobile_number_no_card(self):
        self.partner.sudo().phone = False
        order = self._place()
        self._pay(order)
        self._deliver(order)
        self.assertFalse(self._card())
        self.assertFalse(order.mart369_points_earned)
