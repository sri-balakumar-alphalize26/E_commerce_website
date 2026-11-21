"""Several items in one WhatsApp order, and the way back to the group."""

import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from .common import Mart369BridgeCase

PHONE = '+919876500041'
ADD = '➕ ADD ANOTHER ITEM'


@tagged('post_install', '-at_install')
class TestCart(Mart369BridgeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].sudo().create({'name': 'Cart Customer', 'phone': PHONE})
        cls.second = cls.env['product.template'].sudo().create({
            'name': 'Bridge Cart Kettle', 'sale_ok': True, 'type': 'consu',
            'is_published': True, 'list_price': 30.0})

    def setUp(self):
        super().setUp()
        Req = type(self.env['sa.group.request'])
        AutoReply = type(self.env['wa.auto.reply'])
        test = self

        def create_order(this, desk, conv, product, qty, existing, unit_price=None):
            return test.env['sale.order'].sudo().create({
                'partner_id': test.partner.id,
                'order_line': [(0, 0, {'product_id': product.product_variant_id.id,
                                       'product_uom_qty': qty, 'price_unit': unit_price})]})

        self.asked = []
        for target, name, value in (
                (AutoReply, '_create_sale_order', create_order),
                (Req, '_ensure_conversation', lambda this: test.env['wa.conversation'].new({})),
                (Req, '_is_existing_contact', lambda this, conv: False),
                (Req, '_assess_availability', lambda this, *a, **kw: True),
                (Req, '_sa_group_details_start', lambda this, order: True)):
            p = patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        real_ask = Req._ask

        def ask(this, body, buttons):
            test.asked.append((body, [b['title'] for b in buttons]))
            return real_ask(this, body, buttons)
        p = patch.object(Req, '_ask', ask)
        p.start()
        self.addCleanup(p.stop)

    def _item(self, product, qty, price):
        return self.env['sa.group.request'].sudo().create({
            'group_id': self.wa_group.id, 'requester_phone': PHONE,
            'raw_text': product.name, 'product_id': product.id,
            'qty': qty, 'quoted_price': price, 'state': 'awaiting_order_confirm'})

    def _said(self, words):
        return any(words in body for __, body in self.wa_sent)

    # ------------------------------------------------------------------
    def test_the_summary_offers_add_another_item(self):
        first = self._item(self.quick_product, 2, 50.0)
        first._ask_order_confirm()
        self.assertEqual(self.asked[-1][1], ['CONFIRM', ADD, 'CHANGE'])

    def test_add_another_item_keeps_it_and_asks_again(self):
        first = self._item(self.quick_product, 2, 50.0)
        first._on_deal_reply(ADD)
        self.assertEqual(first.state, 'in_cart')
        menu = json.loads(first.sa_menu_json)
        # 21 Nov 2026: NEW ORDER offers no POPULAR NOW / ALL CATEGORIES
        self.assertNotIn('\U0001F4C2 ALL CATEGORIES', menu)
        self.assertNotIn('⭐ POPULAR NOW', menu)
        self.assertIn('\U0001F3E0 MAIN MENU', menu)
        texts = [b for b, _t in self.asked] + [m for _p, m in self.wa_sent]
        self.assertTrue([t for t in texts if 'Your cart' in t], texts)

    def test_the_next_summary_lists_the_whole_cart(self):
        first = self._item(self.quick_product, 2, 50.0)
        first._on_deal_reply(ADD)
        second = self._item(self.second, 1, 30.0)
        second._ask_order_confirm()
        body = self.asked[-1][0]
        self.assertIn(self.quick_product.name, body)
        self.assertIn(self.second.name, body)
        self.assertIn('130.00', body)

    def test_confirm_makes_one_order_with_every_item(self):
        first = self._item(self.quick_product, 2, 50.0)
        first._on_deal_reply(ADD)
        second = self._item(self.second, 1, 30.0)
        second._on_deal_reply('CONFIRM')
        order = second.order_id
        self.assertTrue(order)
        lines = order.order_line.filtered('product_id')
        self.assertEqual(len(lines), 2)
        by_product = {l.product_id.product_tmpl_id: l for l in lines}
        self.assertEqual(by_product[self.quick_product].product_uom_qty, 2)
        self.assertAlmostEqual(by_product[self.quick_product].price_unit, 50.0)
        self.assertAlmostEqual(by_product[self.second].price_unit, 30.0)
        self.assertEqual(first.order_id, order)
        self.assertEqual(first.state, 'order_created')
        self.assertEqual(second.state, 'order_created')
        self.assertTrue(self._said(self.quick_product.name) and self._said(self.second.name),
                        'the "Done!" names every item')

    def test_a_single_item_order_is_unchanged(self):
        only = self._item(self.second, 3, 30.0)
        only._on_deal_reply('CONFIRM')
        self.assertEqual(len(only.order_id.order_line.filtered('product_id')), 1)

    def test_done_names_the_variant_picked(self):
        attr = self.env['product.attribute'].sudo().create({
            'name': 'Cart Size', 'create_variant': 'always',
            'value_ids': [(0, 0, {'name': 'Cart Small'}), (0, 0, {'name': 'Cart Large'})]})
        tmpl = self.env['product.template'].sudo().create({
            'name': 'Bridge Cart Jug', 'sale_ok': True, 'type': 'consu', 'is_published': True,
            'list_price': 10.0,
            'attribute_line_ids': [(0, 0, {'attribute_id': attr.id, 'value_ids': [(6, 0, attr.value_ids.ids)]})]})
        large = tmpl.product_variant_ids.filtered(
            lambda v: v.product_template_attribute_value_ids.name == 'Cart Large')
        item = self._item(tmpl, 1, 10.0)
        item.sa_variant_id = large
        item._on_deal_reply('CONFIRM')
        self.assertTrue(self._said(large.display_name), 'the "Done!" names %s' % large.display_name)

    # ------------------------------------------------ the same item twice
    def test_the_same_item_added_twice_is_one_cart_line(self):
        first = self._item(self.quick_product, 2, 50.0)
        first._on_deal_reply(ADD)
        again = self._item(self.quick_product, 1, 50.0)
        again._on_deal_reply(ADD)
        self.assertEqual(first.qty, 3)
        self.assertEqual(again.state, 'dropped')
        self.assertTrue(self._said('now x 3'))
        third = self._item(self.second, 1, 30.0)
        self.assertEqual(third._sa_cart_items(), first)

    def test_the_same_item_at_confirm_joins_its_line(self):
        first = self._item(self.quick_product, 2, 50.0)
        first._on_deal_reply(ADD)
        again = self._item(self.quick_product, 1, 50.0)
        again._ask_order_confirm()
        self.assertIn('x 3 = 150.00', self.asked[-1][0])
        again._on_deal_reply('CONFIRM')
        lines = again.order_id.order_line.filtered('product_id')
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.product_uom_qty, 3)
        self.assertAlmostEqual(lines.price_unit, 50.0)

    def test_a_different_price_stays_its_own_line(self):
        first = self._item(self.quick_product, 2, 50.0)
        first._on_deal_reply(ADD)
        bargained = self._item(self.quick_product, 1, 45.0)
        bargained._on_deal_reply('CONFIRM')
        lines = bargained.order_id.order_line.filtered('product_id')
        self.assertEqual(sorted(lines.mapped('price_unit')), [45.0, 50.0])

    def test_cancel_before_confirm_clears_the_cart(self):
        first = self._item(self.quick_product, 2, 50.0)
        first._on_deal_reply(ADD)
        second = self._item(self.second, 1, 30.0)
        second._sa_cancel_deal()
        self.assertEqual(first.state, 'dropped')

    def test_an_old_cart_item_is_left_out(self):
        first = self._item(self.quick_product, 2, 50.0)
        first._on_deal_reply(ADD)
        self.env.flush_all()
        self.env.cr.execute("UPDATE sa_group_request SET write_date = %s WHERE id = %s",
                            [fields.Datetime.now() - timedelta(hours=7), first.id])
        first.invalidate_recordset()
        second = self._item(self.second, 1, 30.0)
        self.assertFalse(second._sa_cart_items())

    def test_another_members_cart_is_not_mine(self):
        first = self._item(self.quick_product, 2, 50.0)
        first._on_deal_reply(ADD)
        stranger = self.env['sa.group.request'].sudo().create({
            'group_id': self.wa_group.id, 'requester_phone': '+919876500999',
            'raw_text': 'x', 'product_id': self.second.id, 'qty': 1, 'quoted_price': 30.0,
            'state': 'awaiting_order_confirm'})
        self.assertFalse(stranger._sa_cart_items())

    # ---------------------------------------------- back to the group
    def _page_button(self):
        from odoo.addons.sales_automation_confirm.controllers.confirm_page import _back_button
        req = self._item(self.second, 1, 30.0)
        link = self.env['sa.confirm.link'].sudo().create({'request_id': req.id, 'kind': 'customer'})
        return _back_button(link)

    def test_after_accept_the_page_goes_back_to_the_group(self):
        self.wa_group.invite_url = 'https://chat.whatsapp.com/BridgeTestInvite'
        html = self._page_button()
        self.assertIn('https://chat.whatsapp.com/BridgeTestInvite', html)
        self.assertIn('Back to WhatsApp group', html)

    def test_without_an_invite_link_it_opens_whatsapp(self):
        self.wa_group.invite_url = False
        html = self._page_button()
        self.assertIn('whatsapp://', html)
        self.assertIn('Open WhatsApp', html)
