"""The loyalty card without Point of Sale or a WhatsApp of its own, and its
screens under 369 Mart."""

from odoo.tests import tagged

from .common import Mart369LoyaltyCase


@tagged('post_install', '-at_install')
class TestNoPos(Mart369LoyaltyCase):

    def test_the_card_does_not_need_point_of_sale(self):
        module = self.env['ir.module.module'].sudo().search([('name', '=', 'pos_loyalty_card')])
        self.assertNotIn('point_of_sale', module.dependencies_id.mapped('name'))
        self.assertNotIn('order_id', self.env['pos.loyalty.history']._fields)

    def test_the_card_leaves_whatsapp_to_the_gateway(self):
        """It used to redefine whatsapp.session and friends on top of the
        shop's WhatsApp connector. No record of those models is its own now."""
        own = self.env['ir.model.data'].sudo().search([
            ('module', '=', 'pos_loyalty_card'), ('model', '=', 'ir.model'),
            ('name', '=like', 'model_whatsapp%')])
        self.assertFalse(own)
        self.assertNotIn('pos.loyalty.whatsapp.service', self.env)

    def test_the_screens_live_under_369_mart(self):
        root = self.env.ref('mart369.menu_mart369_root')
        self.assertEqual(self.env.ref('mart369_loyalty.menu_mart369_loyalty').parent_id, root)
        cards = self.env.ref('mart369_loyalty.menu_mart369_loyalty_cards')
        self.assertEqual(cards.action, self.env.ref('pos_loyalty_card.action_loyalty_card'))
        self.assertFalse(self.env.ref('pos_loyalty_card.menu_loyalty_root').active,
                         "The card's own app is still in the bar.")

    def test_a_manager_can_open_the_cards(self):
        manager = self.env.ref('mart369_roles.group_manager')
        self.assertIn(self.env.ref('pos_loyalty_card.group_loyalty_manager'), manager.all_implied_ids)
