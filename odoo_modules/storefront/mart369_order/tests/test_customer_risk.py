"""Placed-order figures, risk, cash on delivery per customer, goodwill credit
(models/customer_risk.py)."""

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import Mart369OrderCase


@tagged('post_install', '-at_install')
class TestCustomerRisk(Mart369OrderCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The Customers screens list storefront (portal) accounts only.
        cls.customer.sudo().write({'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])]})
        cls.Users = cls.env['res.users']

    def _placed(self, ref="369M-RISK1"):
        order = self._place(ref=ref)
        if order.mart369_state == 'draft':
            self._pay(order)
        self.assertEqual(order.mart369_state, 'placed')
        return order

    def _risk(self):
        return self.Users.mart369_admin_detail(self.customer.id)['risk']

    # ------------------------------------------------------ placed figures

    def test_a_placed_order_counts_before_anyone_confirms_it(self):
        user = self.customer.sudo()
        self.assertEqual(user.mart369_order_count, 0)
        order = self._placed()
        user.invalidate_recordset(['mart369_order_count', 'mart369_total_spent'])
        self.assertEqual(user.mart369_order_count, 1)
        self.assertEqual(user.mart369_total_spent, order.amount_total)
        detail = self.Users.mart369_admin_detail(self.customer.id)
        self.assertEqual([o['ref'] for o in detail['recent']], [order.mart369_ref])
        # Cancelled, it stops counting.
        order.sudo()._mart369_cancel('Out of stock')
        user.invalidate_recordset(['mart369_order_count', 'mart369_total_spent'])
        self.assertEqual(user.mart369_order_count, 0)

    # ---------------------------------------------------------------- risk

    def test_who_cancelled_is_told_apart(self):
        mine = self._placed("369M-RISK1")
        mine.with_user(self.customer).sudo()._mart369_cancel('Changed my mind')
        theirs = self._placed("369M-RISK2")
        theirs.sudo()._mart369_cancel('Out of stock')
        risk = self._risk()
        self.assertEqual(risk['cancelledByCustomer'], 1)
        self.assertEqual(risk['cancelledByShop'], 1)
        self.assertEqual(risk['placed'], 2)

    def test_a_refusal_at_the_door_is_counted(self):
        order = self._placed()
        order.sudo().write({'mart369_failed_reason': 'Customer refused the order',
                            'mart369_attempts': 1})
        risk = self._risk()
        self.assertEqual(risk['refused'], 1)
        self.assertEqual(risk['failed'], 1)

    # ----------------------------------------------------- cash on delivery

    def test_cod_off_is_not_offered(self):
        Provider = self.env['payment.provider']
        risk = self.Users.mart369_admin_set_cod(self.customer.id, True)
        self.assertTrue(risk['codOff'])
        self.assertTrue(self.partner.commercial_partner_id.mart369_cod_off)
        self.assertFalse(Provider._mart369_provider_for('cod', self.partner, 100.0))
        self.assertFalse(self.Users.mart369_admin_set_cod(self.customer.id, False)['codOff'])

    # ------------------------------------------------------------ goodwill

    def test_goodwill_is_a_reward_with_its_reason(self):
        result = self.Users.mart369_admin_goodwill(self.customer.id, 25, 'Late delivery')
        self.assertEqual(result['wallet'], 25.0)
        card = self.env['loyalty.card'].sudo()._mart369_wallet(self.partner)
        row = card._mart369_ledger()[0]._mart369_serialize()
        self.assertEqual(row['kind'], 'reward')
        self.assertEqual(row['title'], 'Goodwill credit')
        self.assertIn('Late delivery', row['sub'])
        profile = self.Users.mart369_admin_profile(self.customer.id)
        self.assertEqual(profile['walletMoves'][0]['title'], 'Goodwill credit')

    def test_goodwill_needs_an_amount_and_a_reason(self):
        with self.assertRaises(UserError):
            self.Users.mart369_admin_goodwill(self.customer.id, 0, 'Nothing')
        with self.assertRaises(UserError):
            self.Users.mart369_admin_goodwill(self.customer.id, 10, '  ')

    def test_a_shopper_cannot_switch_cod_or_give_money(self):
        Users = self.Users.with_user(self.customer)
        with self.assertRaises(AccessError):
            Users.mart369_admin_set_cod(self.customer.id, False)
        with self.assertRaises(AccessError):
            Users.mart369_admin_goodwill(self.customer.id, 1000, 'Treat myself')
