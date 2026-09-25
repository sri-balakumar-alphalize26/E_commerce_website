"""The console's customer profile (models/customer_profile.py)."""

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import Mart369OrderCase


@tagged('post_install', '-at_install')
class TestCustomerProfile(Mart369OrderCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The shared test customer is an internal user; the Customers screens
        # list storefront (portal) accounts only, so make this one a shopper.
        cls.customer.sudo().write({'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])]})

    def _profile(self):
        return self.env['res.users'].mart369_admin_profile(self.customer.id)

    def test_every_placed_order_is_listed_and_a_draft_is_not(self):
        self.assertEqual(self._profile()['orders'], [])
        order = self._place()
        if order.mart369_state == 'draft':
            self.assertEqual(self._profile()['orders'], [], 'an unpaid basket is not an order')
            self._pay(order)
        profile = self._profile()
        self.assertEqual([o['ref'] for o in profile['orders']], [order.mart369_ref])
        self.assertEqual(profile['orderTotal'], 1)
        # The drawer's own detail comes along, so the two never disagree.
        self.assertEqual(profile['id'], self.customer.id)
        self.assertIn('addresses', profile)

    def test_no_wallet_is_made_just_by_looking(self):
        Card = self.env['loyalty.card'].sudo()
        before = Card.search_count([('partner_id', '=', self.partner.commercial_partner_id.id)])
        self.assertEqual(self._profile()['walletMoves'], [])
        self.assertEqual(Card.search_count([('partner_id', '=', self.partner.commercial_partner_id.id)]), before)

    def test_a_shopper_cannot_read_a_profile(self):
        with self.assertRaises(AccessError):
            self.env['res.users'].with_user(self.customer).mart369_admin_profile(self.customer.id)
