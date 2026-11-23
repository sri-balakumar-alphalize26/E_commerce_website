# -*- coding: utf-8 -*-
"""23 Nov 2026: "Done!" only once signed and paid; the slot answers without a
page; a paid order never offers Pay again; the address form opened from the
sign page has a Back button. Nothing is sent."""
from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestOrderPageFlow(HttpCase):

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
            'name': 'SA page flow', 'gateway_api_key': 'x', 'instance_name': 'sa-page-flow',
            'phone_number': '919811122233'})
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz Page Flow', 'group_jid': '120363000000000011@g.us',
            'session_id': session.id, 'group_type': 'customer'})
        cls.product = env['product.product'].create({'name': 'Zz Flow Mouse', 'list_price': 5.0})
        cls.second = env['product.product'].create({'name': 'Zz Flow Keyboard', 'list_price': 7.0})
        cls.india = env.ref('base.in')
        cls.tn = cls.india.state_ids.filtered(lambda s: s.code == 'TN')[:1]
        env['sa.ai.settings'].get_settings().write({
            'address_link_enabled': True, 'address_link_minutes': 30, 'pincode_country_id': cls.india.id})

    def setUp(self):
        super().setUp()
        self.said.clear()
        self.asked.clear()
        self.customer = self.env['res.partner'].create({
            'name': 'Karthick', 'phone': '+919800088811', 'country_id': self.india.id})
        self.home = self.env['res.partner'].create({
            'name': 'Karthick', 'parent_id': self.customer.id, 'phone': '+919800088811',
            'type': 'other' if self.customer._sa_shop_book() else 'delivery', 'street': '13a, beach road',
            'street2': 'Kollam', 'city': 'Dindigul', 'zip': '624001', 'country_id': self.india.id,
            'state_id': self.tn.id, 'sa_addr_label': 'Home'})
        self.order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {'product_id': p.id, 'product_uom_qty': 1})
                           for p in (self.product, self.second)]})
        self.request = self.env['sa.group.request'].create({
            'group_id': self.group.id, 'requester_phone': '919800088811', 'requester_name': 'Karthick',
            'raw_text': 'mouse', 'state': 'order_created', 'order_id': self.order.id})

    def _start(self):
        self.request._sa_group_details_start(self.order)

    def _page(self, extra=''):
        return self.url_open('/my/orders/%s?access_token=%s%s' % (self.order.id, self.order.access_token, extra)).text

    def _csrf(self, html):
        return html.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]

    # ------------------------------------------------------------ Done!
    def test_the_sign_message_carries_every_item_and_no_done(self):
        self._start()
        self.assertEqual(len(self.said), 1, self.said)
        body = self.said[0]
        for text in (self.order.name, 'Zz Flow Mouse', 'Zz Flow Keyboard', 'Total:', 'sign your order'):
            self.assertIn(text, body)
        self.assertNotIn('is placed', body)
        self.assertNotIn('Details saved', body, 'nothing was asked')

    def test_details_saved_is_said_when_they_were_asked(self):
        self.request._sa_details_done(self.order)
        self.assertIn('Details saved, thank you Karthick', self.said[0])
        self.assertNotIn('is placed', self.said[0])

    def test_done_comes_once_with_the_payment(self):
        if not self.env['account.journal'].search([('type', '=', 'sale'), ('company_id', '=', self.order.company_id.id)]):
            self.skipTest('no sales journal in this database')
        self._start()
        self.said.clear()
        Request = self.env.registry['sa.group.request']
        Report = self.env.registry['ir.actions.report']
        with patch.object(Request, '_sa_send_doc', lambda self, send, note='': 'group'), \
                patch.object(Report, '_render_qweb_pdf', lambda self, *a, **kw: (b'pdf', 'pdf')), \
                patch.object(Request, '_sa_paid_menu', lambda self, order: True):
            self.order.order_line.write({'qty_delivered': 1})
            self.order.state = 'sale'
            self.request.with_context(sa_after_now=True)._sa_group_confirmed(self.order)
            self.request.with_context(sa_after_now=True)._sa_group_confirmed(self.order)
        done = [b for b in self.said if 'is placed' in b]
        self.assertEqual(len(done), 1, self.said)
        for text in ('Done! Your order *%s*' % self.order.name, 'Zz Flow Mouse', 'Zz Flow Keyboard', 'Payment received'):
            self.assertIn(text, done[0])

    # ------------------------------------------------------------ slots
    def _slot(self, error='', chosen='a', headers=None, **data):
        Order = self.env.registry['sale.order']
        with patch.object(Order, '_sa_portal_set_slot', lambda self, key: error), \
                patch.object(Order, '_sa_portal_slots', lambda self: {'chips': [], 'chosen': chosen}):
            return self.url_open('/my/orders/%s/slot' % self.order.id, data=data, headers=headers, allow_redirects=False)

    def test_a_slot_is_answered_without_a_page(self):
        self._start()
        csrf = self._csrf(self._page())
        head = {'X-Requested-With': 'fetch'}
        res = self._slot(headers=head, csrf_token=csrf, access_token=self.order.access_token, slot_key='a')
        self.assertEqual(res.json()['ok'], True)
        self.assertEqual(res.json()['chosen'], 'a')
        res = self._slot(error='That slot is full', chosen='b', headers=head, csrf_token=csrf,
                         access_token=self.order.access_token, slot_key='a')
        self.assertEqual((res.json()['ok'], res.json()['error'], res.json()['chosen']), (False, 'That slot is full', 'b'))
        res = self._slot(headers=head, csrf_token=csrf, access_token='wrong', slot_key='a')
        self.assertEqual(res.status_code, 404)
        res = self._slot(headers=head, access_token=self.order.access_token, slot_key='a')
        self.assertEqual(res.status_code, 400, 'the csrf token is still needed')
        res = self._slot(csrf_token=csrf, access_token=self.order.access_token, slot_key='a')
        self.assertIn(res.status_code, (302, 303), 'the plain form still gets the page')

    def test_the_page_script_is_in_the_bundle(self):
        js = self.env['ir.qweb']._get_asset_bundle('web.assets_frontend', css=False, js=True, assets_params={})
        names = [a.url for a in js.javascripts]
        self.assertTrue([n for n in names if n and n.endswith('/sa_portal_order.js')], 'loaded with the website')

    # ------------------------------------------------------------ paid
    def test_an_old_pay_address_of_a_paid_order_shows_paid(self):
        self._start()
        self.order.state = 'sale'
        with patch.object(self.env.registry['sa.group.request'], '_sa_order_is_paid', lambda self, o: True):
            self.assertEqual(self.order._sa_portal_page(payment_amount=12.0)['step'], 'done')
        self.assertEqual(self.order._sa_portal_page(payment_amount=12.0)['step'], 'pay', 'unpaid: unchanged')

    # ------------------------------------------------------------ the form
    def _form_link(self):
        self._start()
        return self.order._sa_portal_addr_link('edit', self.home).sudo()

    def test_the_form_from_the_sign_page_has_back(self):
        link = self._form_link()
        html = self.url_open('/wa/address/%s' % link.token).text
        self.assertGreaterEqual(html.count('data-sa-back="1"'), 2, 'top and bottom')
        self.assertIn('/my/orders/%s' % self.order.id, html)
        self.assertIn('Leave without saving?', html)
        self.env.invalidate_all()
        self.assertFalse(link.used_on, 'looking and going back saves nothing')
        self.assertTrue(link._alive())

    def test_a_form_with_errors_keeps_back(self):
        link = self._form_link()
        html = self.url_open('/wa/address/%s' % link.token, data={'name': ''}).text
        self.assertIn('data-sa-back="1"', html)

    def test_an_expired_form_from_the_sign_page_goes_back_to_the_order(self):
        link = self._form_link()
        link.active = False
        res = self.url_open('/wa/address/%s' % link.token)
        self.assertEqual(res.status_code, 410)
        self.assertIn('/my/orders/%s' % self.order.id, res.text)
        self.assertNotIn('wa.me', res.text)

    def test_a_chat_form_has_no_back_and_no_private_chat(self):
        self.request.write({'sa_book_step': 'form'})
        link = self.env['sa.address.link'].sudo().create({
            'request_id': self.request.id, 'mode': 'add', 'back': 'order',
            'expires_on': self.env.cr.now().replace(tzinfo=None).replace(year=2099)})
        html = self.url_open('/wa/address/%s' % link.token).text
        self.assertNotIn('data-sa-back', html)
        link.active = False
        html = self.url_open('/wa/address/%s' % link.token).text
        self.assertNotIn('wa.me', html)
        self.assertIn('Zz Page Flow group in WhatsApp', html)
        self.group.invite_url = 'https://chat.whatsapp.com/AbCdEf'
        html = self.url_open('/wa/address/%s' % link.token).text
        self.assertIn('https://chat.whatsapp.com/AbCdEf', html)
