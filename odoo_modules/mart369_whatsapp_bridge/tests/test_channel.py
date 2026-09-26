"""Which door - and whether the console can see both."""

from odoo.tests import tagged

from .common import Mart369BridgeCase


@tagged('post_install', '-at_install')
class TestChannel(Mart369BridgeCase):

    def test_website_order_is_website(self):
        order = self._web_order()
        self.assertEqual(order.mart369_channel, 'website')

    def test_group_enquiry_order_is_whatsapp(self):
        order = self._wa_order()
        self.assertEqual(order.mart369_channel, 'whatsapp')
        self.assertFalse(order.mart369_ref)

    def test_reverse_only_link_is_whatsapp(self):
        """The stack sometimes only writes enquiry -> order, never the
        reverse. The channel must see that direction too."""
        order = self._wa_order(confirm=False)
        request = order.sa_group_request_id
        order.sa_group_request_id = False
        request.order_id = order
        order.invalidate_recordset(['mart369_channel'])
        self.assertEqual(order.mart369_channel, 'whatsapp')

    def test_confirmed_wa_order_reaches_the_board(self):
        order = self._wa_order()
        self.assertEqual(order.mart369_state, 'placed')
        board = self.env['sale.order'].search(
            self.env['sale.order']._mart369_board_domain())
        self.assertIn(order, board)
        rows = self.env['sale.order'].mart369_admin_list(tab='needs')
        self.assertIn(order.name, [r['ref'] for r in rows['orders']])

    def test_draft_wa_order_stays_off_the_board(self):
        order = self._wa_order(confirm=False)
        self.assertFalse(order.mart369_state)
        board = self.env['sale.order'].search(
            self.env['sale.order']._mart369_board_domain())
        self.assertNotIn(order, board)

    def test_channel_filter(self):
        web = self._web_order()
        wa = self._wa_order()
        Order = self.env['sale.order']
        wa_rows = Order.mart369_admin_list(tab='all', channel='whatsapp')
        refs = [r['ref'] for r in wa_rows['orders']]
        self.assertIn(wa.name, refs)
        self.assertNotIn(web.mart369_ref, refs)
        web_rows = Order.mart369_admin_list(tab='all', channel='website')
        refs = [r['ref'] for r in web_rows['orders']]
        self.assertIn(web.mart369_ref, refs)
        self.assertNotIn(wa.name, refs)

    def test_find_by_name(self):
        wa = self._wa_order()
        found = self.env['sale.order']._mart369_admin_find(wa.name)
        self.assertEqual(found, wa)
        # And the website's own lookups are untouched.
        web = self._web_order()
        self.assertEqual(
            self.env['sale.order']._mart369_admin_find(web.mart369_ref), web)

    def test_row_and_detail_shapes(self):
        wa = self._wa_order()
        row = wa._mart369_admin_row()
        self.assertEqual(row['channel'], 'whatsapp')
        self.assertEqual(row['ref'], wa.name)
        self.assertIn('wa', row)
        self.assertEqual(row['wa']['group'], self.wa_group.name)
        detail = wa._mart369_admin_detail()
        self.assertFalse(detail['canRemove'])
        self.assertFalse(detail['canReplace'])

    def test_console_staff_need_no_stack_rights(self):
        """The board is read by website staff, who have no access to the
        WhatsApp stack's models - a WhatsApp order on the list must not
        cost them an AccessError (it did, on 26 Sep, reading sa_group_id)."""
        self._wa_order()
        staff = self.env['res.users'].sudo().create({
            'name': 'Console Staff',
            'login': 'console.staff@369mart.test',
            'group_ids': [(4, self.env.ref('base.group_user').id),
                          (4, self.env.ref('website.group_website_designer').id),
                          (4, self.env.ref('sales_team.group_sale_manager').id)],
        })
        rows = self.env['sale.order'].with_user(staff).mart369_admin_list(
            tab='needs')
        self.assertTrue([r for r in rows['orders']
                         if r['channel'] == 'whatsapp' and r.get('wa')])

    def test_search_finds_wa_orders_by_name(self):
        wa = self._wa_order()
        rows = self.env['sale.order'].mart369_admin_list(tab='all', q=wa.name)
        self.assertIn(wa.name, [r['ref'] for r in rows['orders']])
