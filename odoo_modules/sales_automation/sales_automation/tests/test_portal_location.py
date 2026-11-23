# -*- coding: utf-8 -*-
"""The map location on the order page (23 Nov 2026) and how long links work."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.http import Request
from odoo.tests import HttpCase, tagged

PHONE = '919800077733'


class LinkCase(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.said = []
        Req = env.registry['sa.group.request']
        for p in (patch.object(Req, '_say', lambda self, body, addressed=True: cls.said.append(body) or True),
                  patch.object(Req, '_ask', lambda self, body, buttons: True)):
            p.start()
            cls.addClassCleanup(p.stop)
        session = env['whatsapp.session'].sudo().create({
            'name': 'SA loc', 'gateway_api_key': 'x', 'instance_name': 'sa-loc'})
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz Loc', 'group_jid': '120363000000000066@g.us', 'session_id': session.id,
            'group_type': 'customer'})
        cls.product = env['product.product'].create({
            'name': 'Zz Loc Mouse', 'list_price': 5.0, 'is_storable': True, 'invoice_policy': 'order'})

    def setUp(self):
        super().setUp()
        self.said.clear()
        self.customer = self.env['res.partner'].create({
            'name': 'Karthick', 'phone': '+' + PHONE, 'street': '13a, beach road'})
        self.order = self._order()
        self.req = self.env['sa.group.request'].create({
            'group_id': self.group.id, 'requester_phone': PHONE, 'requester_name': 'Karthick', 'raw_text': 'mouse',
            'state': 'order_created', 'order_id': self.order.id, 'sa_sign_link_sent_on': fields.Datetime.now()})

    def _order(self):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id, 'require_signature': True, 'require_payment': False,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 1})]})
        order._portal_ensure_token()
        return order

    def _confirm(self):
        self.order.write({'signed_by': 'K', 'signed_on': fields.Datetime.now()})
        self.order.with_context(sa_after_no_thread=True).action_confirm()

    def _url(self, tail='', order=None):
        order = order or self.order
        return '/my/orders/%s%s?access_token=%s' % (order.id, tail, order.access_token)

    def _ago(self, **kw):
        return fields.Datetime.now() - timedelta(**kw)


@tagged('post_install', '-at_install')
class TestPortalLocation(LinkCase):

    def _post(self, lat='11.0168', lng='76.9558', token=None, csrf=True, order=None):
        self.authenticate(None, None)
        order = order or self.order
        data = {'access_token': token or order.access_token, 'lat': lat, 'lng': lng}
        if csrf:
            data['csrf_token'] = Request.csrf_token(self)
        res = self.url_open('/my/orders/%s/location' % order.id, data=data, headers={'X-Requested-With': 'fetch'})
        self.env.invalidate_all()
        return res

    def test_the_mark_until_there_is_one(self):
        html = self.url_open(self._url()).text
        self.assertIn('Location not added', html)
        self.assertIn('data-has="0"', html)
        self.customer.write({'partner_latitude': 11.0, 'partner_longitude': 76.0})
        self.assertIn('data-has="1"', self.url_open(self._url()).text)

    def test_the_message_no_longer_asks(self):
        self.req._sa_details_done(self.order)
        self.assertTrue(self.said)
        self.assertNotIn('send your location', ' '.join(self.said).lower())

    def test_saved_on_the_address_of_this_order(self):
        res = self._post()
        self.assertEqual(res.json(), {'ok': True, 'error': '', 'reload': False})
        self.assertAlmostEqual(self.order.partner_shipping_id.partner_latitude, 11.0168, places=4)

    def test_still_after_signing_until_the_rider_has_it(self):
        self._confirm()
        job = self.order.picking_ids[:1]
        self.assertTrue(self.order._sa_loc_open())
        self.assertTrue(self._post(lat='12.5').json()['ok'])
        if 'sa_delivery_state' in job._fields:
            job.sa_delivery_state = 'picked'
            self.assertFalse(self.order._sa_loc_open())
            self.assertFalse(self._post(lat='13.5').json()['ok'])
            self.assertAlmostEqual(self.order.partner_shipping_id.partner_latitude, 12.5, places=4)

    def test_refused(self):
        for lat, lng in (('', ''), ('abc', '1'), ('91', '10'), ('10', '181'), ('0', '0'), ('nan', '1'), ('inf', '1')):
            self.assertFalse(self._post(lat, lng).json()['ok'], (lat, lng))
        self.assertFalse(self.order.partner_shipping_id.partner_latitude)
        self.assertEqual(self._post(token='wrong').status_code, 404)
        self.assertGreaterEqual(self._post(csrf=False).status_code, 400)
        self.assertFalse(self.order.partner_shipping_id.partner_latitude)

    def test_a_website_order_has_no_card(self):
        order = self._order()
        self.assertFalse(order._sa_portal_location()['open'])
        self.assertFalse(self._post(order=order).json()['ok'])
        self.assertNotIn('sa-loc-form', self.url_open(self._url(order=order)).text)

    def test_a_cancelled_order_is_closed(self):
        self.order._action_cancel()
        self.assertFalse(self.order._sa_loc_open())


@tagged('post_install', '-at_install')
class TestLinkExpiry(LinkCase):

    def _gone(self, url):
        self.authenticate(None, None)
        res = self.url_open(url)
        return res.status_code == 410 and 'This link has expired' in res.text

    def test_an_open_order_never(self):
        self.order.sudo().write({'create_date': self._ago(days=60)})
        self.assertFalse(self._gone(self._url()))
        self._confirm()
        self.req.sa_pay_link_sent_on = self._ago(days=40)
        self.order.signed_on = self._ago(days=40)
        self.assertFalse(self.order._sa_link_expired(), 'still to pay')

    def test_cancelled_a_week_ago(self):
        self.order._action_cancel()
        self.assertTrue(self.order.sa_cancelled_on)
        self.order.sa_cancelled_on = self._ago(days=7, minutes=-1)
        self.assertFalse(self._gone(self._url()))
        self.order.sa_cancelled_on = self._ago(days=7, minutes=1)
        self.assertTrue(self._gone(self._url()))
        self.assertTrue(self._gone(self._url() + '&report_type=pdf'))

    def test_delivered_a_week_ago(self):
        self._confirm()
        job = self.order.picking_ids[:1]
        if 'sa_delivery_state' not in job._fields:
            self.skipTest('no delivery module')
        job.write({'sa_delivery_state': 'delivered', 'sa_delivered_on': self._ago(days=8)})
        Order = self.env.registry['sale.order']
        status = Order._sa_portal_status
        with patch.object(Order, '_sa_portal_status', lambda rec: dict(status(rec), paid=True)):
            self.assertTrue(self.order._sa_link_expired())
            self.assertTrue(self._gone(self._url()))
            self.assertTrue(self._gone('/wa/review/%s?access_token=%s' % (self.order.id, self.order.access_token)))
            job.sa_delivered_on = self._ago(days=6)
            self.assertFalse(self.order._sa_link_expired())
            job.write({'sa_delivery_state': 'dispatched'})
            self.assertFalse(self.order._sa_link_expired(), 'on its way')

    def test_our_people_still_see_it(self):
        self.order._action_cancel()
        self.order.sa_cancelled_on = self._ago(days=30)
        self.authenticate('admin', 'admin')
        self.assertNotIn('This link has expired', self.url_open(self._url()).text)

    def test_website_orders_unchanged(self):
        order = self._order()
        order._action_cancel()
        order.sa_cancelled_on = self._ago(days=300)
        self.assertFalse(self._gone(self._url(order=order)))

    def test_address_form(self):
        link = self.env['sa.address.link'].create({
            'request_id': self.req.id, 'back': 'page', 'expires_on': self._ago(days=8)})
        link.write({'used_on': self._ago(days=6), 'address_id': self.customer.id, 'used_ua': 'phone'})
        self.assertIn('Address saved', self.url_open('/wa/address/%s' % link.token).text)
        link.used_on = self._ago(days=8)
        self.assertTrue(self._gone('/wa/address/%s' % link.token))
        self.env['sa.address.link']._cron_links_clean()
        self.assertFalse(link.used_ua)
        self.assertTrue(link.used_on, 'the proof stays')
