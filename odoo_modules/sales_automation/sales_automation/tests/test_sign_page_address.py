# -*- coding: utf-8 -*-
"""The delivery address on the sign page (23 Nov 2026): the default is used
without a question in the chat; until they sign, the customer picks, edits or
adds one on the page - only their own, only while it is open. Nothing sent."""
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

GROUP = '120363000000000022@g.us'
PHONE = '919800077700'
SIGNATURE = ('iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAFElEQVR4nGP8//8/AwwwMSAB3BwAlm4DBfIlvvkAAAAASUVORK5CYII=')      # a 4 x 4 white PNG


@tagged('post_install', '-at_install')
class TestSignPageAddress(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.said, cls.asked = [], []
        Request = env.registry['sa.group.request']
        for p in (patch.object(Request, '_say', lambda self, body, addressed=True: cls.said.append(body) or True),
                  patch.object(Request, '_ask', lambda self, body, buttons: cls.asked.append(body) or True)):
            p.start()
            cls.addClassCleanup(p.stop)
        session = env['whatsapp.session'].sudo().create({
            'name': 'SA sign page', 'gateway_api_key': 'x', 'instance_name': 'sa-sign-page'})
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz Sign Page', 'group_jid': GROUP, 'session_id': session.id, 'group_type': 'customer'})
        cls.product = env['product.product'].create({'name': 'Zz Sign Mouse', 'list_price': 5.0})
        cls.india = env.ref('base.in')
        cls.tn = cls.india.state_ids.filtered(lambda s: s.code == 'TN')[:1]
        env['sa.ai.settings'].get_settings().write({'address_link_enabled': True, 'address_link_minutes': 30,
                                                    'pincode_country_id': cls.india.id})

    def setUp(self):
        super().setUp()
        self.said.clear()
        self.asked.clear()
        self.customer = self.env['res.partner'].create({
            'name': 'Karthick', 'phone': '+' + PHONE, 'country_id': self.india.id})
        self.home = self._addr('13a, beach road', 'Home')
        self.work = self._addr('7, office street', 'Work')
        self.order, self.request = self._new_order()

    def _addr(self, street, label, parent=None):
        parent = parent or self.customer
        vals = {'name': 'Karthick', 'parent_id': parent.id, 'phone': '+' + PHONE,
                'type': 'other' if parent._sa_shop_book() else 'delivery',
                'street': street, 'street2': 'Kollam', 'city': 'Dindigul', 'zip': '624001',
                'country_id': self.india.id, 'state_id': self.tn.id, 'sa_addr_label': label}
        return self.env['res.partner'].create(vals)

    def _new_order(self):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 1})]})
        req = self.env['sa.group.request'].create({
            'group_id': self.group.id, 'requester_phone': PHONE, 'requester_name': 'Karthick',
            'raw_text': 'mouse', 'state': 'order_created', 'order_id': order.id})
        return order, req

    def _start(self):
        self.request._sa_group_details_start(self.order)

    def _sign(self, order):
        order.write({'signed_on': fields.Datetime.now(), 'signed_by': 'Karthick', 'signature': SIGNATURE})

    # ------------------------------------------------------------ chat
    def test_two_saved_addresses_no_question_straight_to_sign(self):
        self._start()
        self.assertFalse(self.asked, 'no poll')
        self.assertEqual(len(self.said), 1, self.said)
        self.assertIn('sign your order', self.said[0])
        self.assertIn('Deliver to: *Home*', self.said[0])
        self.assertNotIn('beach road', self.said[0], 'the label only, it may be in the group')
        self.assertEqual(self.order.partner_shipping_id, self.home)
        self.assertFalse(self.request.sa_details_pending)

    def test_the_default_wins(self):
        if not self.customer._sa_shop_book():
            # without the shop module: the address of the latest order
            other, _req = self._new_order()
            other.partner_shipping_id = self.work
        else:
            self.work._mart369_set_default()
        self._start()
        self.assertEqual(self.order.partner_shipping_id, self.work)

    def test_a_new_customer_is_asked_in_the_chat(self):
        (self.home | self.work).write({'active': False})
        self._start()
        self.assertTrue(self.request.sa_details_pending)
        self.assertFalse(self.request.sa_sign_link_sent_on)
        self.assertFalse([b for b in self.said if 'sign your order' in b])

    # ------------------------------------------------------------ rules
    def test_pick_another_of_mine(self):
        self._start()
        self.said.clear()
        self.assertEqual(self.order._sa_portal_use_address(self.work), '')
        self.assertEqual(self.order.partner_shipping_id, self.work)
        self.assertFalse(self.said or self.asked, 'nothing said in the chat')

    def test_somebody_elses_address_is_refused(self):
        self._start()
        other = self.env['res.partner'].create({'name': 'Other', 'phone': '+919811100000'})
        theirs = self._addr('1, elsewhere', 'Home', parent=other)
        self.assertTrue(self.order._sa_portal_use_address(theirs))
        self.assertEqual(self.order.partner_shipping_id, self.home)
        with self.assertRaises(UserError):
            self.order._sa_portal_addr_link('edit', theirs)
        self.assertNotIn(theirs.id, [r['id'] for r in self.order._sa_portal_addresses()['rows']])

    def test_closed_after_signing_cancelling_or_paying(self):
        self._start()
        link = self.order._sa_portal_addr_link('add')
        self.assertTrue(link._alive())
        self._sign(self.order)
        self.assertFalse(self.order._sa_addr_open())
        self.assertFalse(link._alive(), 'an open form closes with the signature')
        self.assertTrue(self.order._sa_portal_use_address(self.work))
        self.assertEqual(self.order.partner_shipping_id, self.home)
        order, req = self._new_order()
        req._sa_group_details_start(order)
        self.assertTrue(order._sa_addr_open())
        with patch.object(self.env.registry['sa.group.request'], '_sa_order_is_paid', lambda self, o: True):
            self.assertFalse(order._sa_addr_open())
        order.state = 'cancel'
        self.assertFalse(order._sa_addr_open())

    def test_not_for_orders_that_are_not_whatsapp_group_orders(self):
        order = self.env['sale.order'].create({'partner_id': self.customer.id, 'require_signature': True})
        self.assertFalse(order._sa_addr_open())
        self.assertEqual(order._sa_portal_addresses(), {'open': False, 'rows': []})

    def test_an_edited_address_takes_the_unsigned_orders_with_it(self):
        self._start()
        unsigned, req = self._new_order()
        req._sa_group_details_start(unsigned)
        signed, req = self._new_order()
        req._sa_group_details_start(signed)
        self._sign(signed)
        new = self._addr('13h, beach road', 'Home')
        self.request._sa_move_open_orders(self.home, new)
        self.assertEqual(unsigned.partner_shipping_id, new)
        self.assertEqual(signed.partner_shipping_id, self.home)

    # ------------------------------------------------------------ the page
    def _page(self):
        res = self.url_open('/my/orders/%s?access_token=%s' % (self.order.id, self.order.access_token))
        self.assertEqual(res.status_code, 200)
        return res.text

    def _post(self, csrf, **data):
        data.update(csrf_token=csrf, access_token=data.get('access_token', self.order.access_token))
        res = self.url_open('/my/orders/%s/address' % self.order.id, data=data)
        self.env.invalidate_all()
        return res

    def _csrf(self, html):
        return html.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]

    def test_the_page_lists_and_changes_it(self):
        self._start()
        html = self._page()
        self.assertIn('Change delivery address', html)
        self.assertIn('7, office street', html)
        res = self._post(self._csrf(html), do='use', address_id=str(self.work.id))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.order.partner_shipping_id, self.work)

    def test_a_wrong_token_changes_nothing(self):
        self._start()
        csrf = self._csrf(self._page())
        res = self._post(csrf, do='use', address_id=str(self.work.id), access_token='wrong')
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self.order.partner_shipping_id, self.home)

    def test_a_junk_address_id_is_refused(self):
        self._start()
        csrf = self._csrf(self._page())
        for junk in ('', 'abc', '-1', '999999999'):
            res = self._post(csrf, do='use', address_id=junk)
            self.assertIn('not available', res.text)
        self.assertEqual(self.order.partner_shipping_id, self.home)

    def test_no_change_box_after_signing(self):
        self._start()
        self._sign(self.order)
        self.env.flush_all()
        self.assertNotIn('Change delivery address', self._page())

    def test_add_from_the_page_saves_quietly_and_comes_back(self):
        self._start()
        self.said.clear()
        res = self._post(self._csrf(self._page()), do='add')
        self.assertIn('/wa/address/', res.url)
        link = self.env['sa.address.link'].search([('request_id', '=', self.request.id), ('back', '=', 'page')])
        self.assertEqual(len(link), 1)
        form = {'label': 'Other', 'country': 'IN', 'name': 'Karthick', 'phone': PHONE[-10:], 'alt': '',
                'pin': '624003', 'line': '15/2', 'area': 'Adiyanuthu Road', 'town': 'Dindigul',
                'state_id': str(self.tn.id), 'landmark': '', 'lat': '', 'lng': ''}
        res = self.url_open('/wa/address/%s' % link.sudo().token, data=form)
        self.env.invalidate_all()
        self.assertIn('/my/orders/%s' % self.order.id, res.url, 'back on the sign page')
        self.assertEqual(self.order.partner_shipping_id.street, '15/2')
        self.assertFalse(self.said or self.asked, 'nothing said in the chat')
        self.assertTrue(link.used_on)

    # ------------------------------------- with the shop modules, as on live
    def test_edit_from_the_page(self):
        self._start()
        signed, req = self._new_order()
        req._sa_group_details_start(signed)
        self._sign(signed)
        self.env.flush_all()
        self.said.clear()
        res = self._post(self._csrf(self._page()), do='edit', address_id=str(self.home.id))
        self.assertIn('/wa/address/', res.url)
        link = self.env['sa.address.link'].search([('request_id', '=', self.request.id), ('back', '=', 'page')])
        self.assertEqual((link.mode, link.target_id), ('edit', self.home))
        form = {'label': 'Home', 'country': 'IN', 'name': 'Karthick', 'phone': PHONE[-10:], 'alt': '',
                'pin': '624001', 'line': '13h, beach road', 'area': 'Kollam', 'town': 'Dindigul',
                'state_id': str(self.tn.id), 'landmark': '', 'lat': '', 'lng': ''}
        res = self.url_open('/wa/address/%s' % link.sudo().token, data=form)
        self.env.invalidate_all()
        self.assertIn('/my/orders/%s' % self.order.id, res.url)
        ship = self.order.partner_shipping_id
        self.assertEqual(ship.street, '13h, beach road')
        self.assertTrue(ship.active, 'never an archived address on an open order')
        self.assertFalse(self.said or self.asked)

    def test_the_default_is_marked(self):
        if not self.customer._sa_shop_book():
            self.skipTest('the shop address module is not installed')
        self.work._mart369_set_default()
        self._start()
        rows = {r['id']: r for r in self.order._sa_portal_addresses()['rows']}
        self.assertTrue(rows[self.work.id]['default'])
        self.assertTrue(rows[self.work.id]['chosen'])
        self.assertFalse(rows[self.home.id]['default'])
        self.assertIn('default', self._page())

    def test_quick_or_express_is_decided_again(self):
        if 'qe_decided' not in self.order._fields:
            self.skipTest('Quick / Express is not installed')
        Area = self.env['sa.qe.service.area']
        Area.search([('pincode', 'in', ('624001', '699999'))]).unlink()
        Area.create([{'pincode': '624001', 'quick': True}, {'pincode': '699999', 'quick': False}])
        self.work.zip = '699999'
        self._start()
        self.order._qe_decide()
        self.assertEqual(self.order.qe_mode, 'quick')
        self.assertEqual(self.order._sa_portal_use_address(self.work), '')
        self.assertEqual(self.order.qe_mode, 'express')
        fees = self.order.order_line.filtered(lambda l: l.qe_kind == 'fee')
        self.assertLessEqual(len(fees), 1, 'never two delivery fees')

    def test_the_page_still_draws_with_slots_after_a_change(self):
        self._start()
        self.assertEqual(self.order._sa_portal_use_address(self.work), '')
        slots = self.order._sa_portal_slots()
        self.assertIn('chips', slots)
        html = self._page()
        self.assertIn('7, office street', html)
        self.assertIn('Change delivery address', html)
