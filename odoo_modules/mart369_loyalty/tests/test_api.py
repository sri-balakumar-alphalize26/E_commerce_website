"""The routes: a customer's own card only, points on their own bill, and the
settings kept to staff."""

from odoo.tests import tagged

from .common import Mart369LoyaltyHttpCase


@tagged('post_install', '-at_install')
class TestLoyaltyApi(Mart369LoyaltyHttpCase):

    def _login(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')

    def test_the_points_screen_shows_only_my_card(self):
        self._give(120)
        self._login()
        res = self._req('GET', '/369mart/loyalty')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['card']['points'], 120.0)
        self.assertEqual(data['card']['value'], 12.0)
        self.assertEqual(data['rule']['perRupee'], 10.0)
        self.assertEqual(len(data['history']), 1)

        self.authenticate('someone.else@369mart.test', 'someone-else-369')
        data = self._req('GET', '/369mart/loyalty').json()
        self.assertIsNone(data['card'])
        self.assertEqual(data['history'], [])

    def test_the_bill_route_prices_my_points(self):
        self._give(500)
        body = {'items': {str(self.quick_product.id): 4}, 'usePoints': True}
        guest = self._req('POST', '/369mart/cart/bill', body).json()
        self.assertIsNone(guest['points'])
        self._login()
        mine = self._req('POST', '/369mart/cart/bill', body).json()
        self.assertEqual(mine['points']['off'], 50.0)
        self.assertEqual(mine['total'], 180.0)

    def test_settings_are_for_staff(self):
        self._login()
        res = self._req('POST', '/369mart/admin/settings/loyalty', {'earnOn': 'placed'})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.config.loyalty_earn_on, 'delivered')

    def test_staff_choose_the_step(self):
        self.authenticate('admin', 'admin')
        res = self._req('POST', '/369mart/admin/settings/loyalty',
                        {'earnOn': 'out', 'settleDays': 10})
        data = res.json()
        self.assertTrue(data['ok'], data)
        self.assertEqual(data['settings']['loyalty']['earnOn'], 'out')
        self.assertEqual(len(data['settings']['loyalty']['options']), 5)
        bad = self._req('POST', '/369mart/admin/settings/loyalty', {'earnOn': 'whenever'})
        self.assertEqual(bad.status_code, 400)
