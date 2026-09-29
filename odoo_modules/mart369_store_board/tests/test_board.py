"""369 Mart › Sales has one Orders entry, and it opens on the Counter."""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBoardMenu(TransactionCase):

    def _sales_orders_menus(self):
        sales = self.env.ref('mart369.menu_mart369_sales')
        return self.env['ir.ui.menu'].search(
            [('parent_id', '=', sales.id), ('name', '=', 'Orders')])

    def test_one_orders_entry_and_it_opens_the_counter(self):
        menus = self._sales_orders_menus()
        self.assertEqual(len(menus), 1, 'one Orders under Sales, not two')
        self.assertEqual(menus, self.env.ref('mart369_store_board.menu_mart369_orders_counter'))
        action = self.env.ref('mart369_store_board.action_mart369_orders_board')
        self.assertEqual(menus.action, action)
        self.assertEqual(action.tag, 'mart369_store_board.orders_board')

    def test_the_desk_menu_is_switched_off_not_removed(self):
        desk = self.env.ref('mart369_order.menu_mart369_orders')
        self.assertFalse(desk.active, 'hidden while the Counter owns Orders')
        # The desk itself is still there, one toggle away.
        self.assertTrue(self.env.ref('mart369_order.action_mart369_order_desk'))

    def test_uninstall_gives_the_desk_menu_back(self):
        from odoo.addons.mart369_store_board.hooks import uninstall_hook
        uninstall_hook(self.env)
        self.assertTrue(self.env.ref('mart369_order.menu_mart369_orders').active)
