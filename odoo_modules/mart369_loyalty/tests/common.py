"""Fixtures for the loyalty tests.

mart369_order's, plus a customer with a mobile number (a card is keyed by it)
and one known rule: spend 100, earn 10; 10 points to the rupee; 100 points to
start spending; up to all of the order. The fixture basket is 4 x 50 of the
Quick product, which comes to 200 in items and 30 for delivery.
"""

import json

from odoo.tests import HttpCase, TransactionCase

from odoo.addons.mart369_order.tests.common import Mart369OrderFixtures

PHONE = '+919876543210'


class Mart369LoyaltyFixtures(Mart369OrderFixtures):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner.sudo().write({'phone': PHONE})
        cls.env['pos.loyalty.card.settings'].sudo().get_settings().write({'enable_loyalty': True})
        Rule = cls.env['pos.loyalty.rule'].sudo()
        cls.rule = Rule.get_active_rule() or Rule.create({'name': 'Test rule'})
        cls.rule.write({
            'is_active': True, 'spend_amount': 100.0, 'points_earned': 10.0,
            'min_redeem_points': 100.0, 'points_per_currency': 10.0,
            'max_redeem_percent': 100.0,
        })
        cls.config = cls.env['mart369.config'].sudo()._get()
        cls.config.write({
            'loyalty_enabled': True, 'loyalty_redeem': True,
            'loyalty_earn_on': 'delivered', 'loyalty_settle_days': 7,
        })
        # Cards a previous run or the database already holds for this number.
        cls.env['pos.loyalty.card'].sudo().search([('phone', '=', PHONE)])._hard_unlink()

    # ------------------------------------------------------------ helpers

    def _card(self):
        return self.env['pos.loyalty.card']._mart369_card_for(self.partner)

    def _give(self, points):
        """Points the customer already has - earned at the counter, say."""
        card = self.env['pos.loyalty.card']._mart369_card_for(self.partner, create=True)
        card._mart369_write(points, 'earned', 'At the store')
        return card

    def _earn_on(self, step):
        self.config.loyalty_earn_on = step

    def _bill(self, use_points=False, items=None):
        return self.env['mart369.cart'].sudo().with_context(
            mart369_partner_id=self.partner.id, mart369_use_points=use_points,
        )._mart369_bill(items or {str(self.quick_product.id): 4})

    def _deliver(self, order):
        while order.mart369_state != 'out':
            order.mart369_action_advance()
        order.mart369_action_deliver(order.sudo().mart369_otp_code)
        return order


class Mart369LoyaltyCase(Mart369LoyaltyFixtures, TransactionCase):
    pass


class Mart369LoyaltyHttpCase(Mart369LoyaltyFixtures, HttpCase):

    def _req(self, method, path, payload=None):
        return self.opener.request(
            method, self.base_url() + path,
            data=json.dumps(payload) if payload is not None else None,
            headers={'Content-Type': 'application/json'}, allow_redirects=False)
