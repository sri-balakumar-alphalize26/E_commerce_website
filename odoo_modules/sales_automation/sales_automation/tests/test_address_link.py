# -*- coding: utf-8 -*-
"""The private address form link (21 Nov 2026, models/sa_address_link.py).

A group order that needs a new address also sends the customer a link -
privately when their number is known, in the group otherwise - to a form like
the shop's Delivery Address page. Saving it puts the address on the order and
the group moves on; the link then works no more. The group questions keep
working beside it.

Nothing is sent: the gateway is mocked, as in mart369_whatsapp_bridge.
"""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import HttpCase, tagged

GROUP = '120363000000000077@g.us'
PHONE = '919800022233'


@tagged('post_install', '-at_install')
class TestAddressLink(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.sent = []      # (to, text) of every text "sent"
        cls.polls = []     # (to, payload) of everything else "sent"
        Session = env.registry['whatsapp.session']

        def send_message(self, phone, message):
            cls.sent.append((phone, message))
            return True

        def mentioning(self, phone, message, mention=''):
            cls.sent.append((phone, message))
            return True

        def payload(self, action, data, *a, **kw):
            cls.polls.append((action, data))
            return True

        for patcher in (
                patch.object(Session, 'send_message', send_message),
                patch.object(Session, 'sa_send_text_mentioning', mentioning),
                patch.object(Session, '_send_payload', payload),
                patch.object(Session, '_gateway_call', lambda self, *a, **kw: {}),
                patch.object(env.registry['sa.outbox.guard'], 'claim',
                             lambda self, key, seconds=60: True),
                patch.object(env.registry['sa.group.request'], '_sa_pincode_lookup',
                             lambda self, pin, country: {
                                 'city': 'Dindigul',
                                 'state_id': country.state_ids.filtered(
                                     lambda s: s.code == 'TN')[:1].id})):
            patcher.start()
            cls.addClassCleanup(patcher.stop)
        # the shop's own pincode lookup, when its address module is installed
        Partner = env.registry['res.partner']
        if hasattr(Partner, '_mart369_pincode_lookup'):
            tn_id = env.ref('base.in').state_ids.filtered(lambda s: s.code == 'TN')[:1].id
            patcher = patch.object(Partner, '_mart369_pincode_lookup', lambda self, pin: {
                'ok': True, 'pin': pin, 'town': 'Dindigul', 'state_id': tn_id,
                'state': 'Tamil Nadu', 'areas': ['Adiyanuthu']})
            patcher.start()
            cls.addClassCleanup(patcher.stop)

        session = env['whatsapp.session'].sudo().create({
            'name': 'SA address link test', 'gateway_api_key': 'x',
            'instance_name': 'sa-addr-link-test'})
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz Address Link', 'group_jid': GROUP,
            'session_id': session.id, 'group_type': 'customer'})
        cls.product = env['product.template'].create({
            'name': 'Zz Address Link Laptop', 'list_price': 600.0, 'type': 'consu'})
        cls.india = env.ref('base.in')
        cls.tn = cls.india.state_ids.filtered(lambda s: s.code == 'TN')[:1]
        settings = env['sa.ai.settings'].get_settings()
        settings.write({'address_link_enabled': True, 'address_link_minutes': 30,
                        'pincode_prefixes': False, 'pincode_country_id': cls.india.id})

    def setUp(self):
        super().setUp()
        self.sent.clear()
        self.polls.clear()
        # a first-time customer: no address at all
        self.customer = self.env['res.partner'].create({
            'name': 'Sri', 'phone': '+' + PHONE, 'country_id': self.india.id})
        self.order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {'product_id': self.product.product_variant_id.id,
                                   'product_uom_qty': 1})],
        })
        self.request = self.env['sa.group.request'].create({
            'group_id': self.group.id, 'requester_phone': PHONE,
            'requester_name': 'Sri', 'raw_text': 'laptop', 'product_id': self.product.id,
            'state': 'order_created', 'order_id': self.order.id})

    # ------------------------------------------------------------ helpers
    def url_open(self, *args, **kwargs):
        res = super().url_open(*args, **kwargs)
        # the page wrote through its own environment: read it fresh
        self.env.invalidate_all()
        return res

    def _open_book(self):
        self.request._sa_book_open('order')
        return self.request.sa_addr_link_ids[:1]

    def _form(self, **over):
        # the shop form's fields (components/home/AddressForm.jsx)
        data = {'label': 'Home', 'country': 'IN', 'name': 'Sri', 'phone': PHONE[-10:],
                'alt': '', 'pin': '624003', 'line': '15/2', 'area': 'Adiyanuthu Road',
                'town': 'Dindigul', 'state_id': str(self.tn.id), 'landmark': 'near the temple',
                'lat': '10.3624', 'lng': '77.9695'}
        data.update(over)
        return data

    def _path(self, link):
        return '/wa/address/%s' % link.sudo().token

    # ------------------------------------------------------------ sending
    def test_a_new_customer_gets_the_link_privately_and_the_group_a_note(self):
        link = self._open_book()
        self.assertTrue(link, 'a link is made for a first-time customer')
        self.assertEqual(link.sent_to, 'private')
        private = [t for to, t in self.sent if to == PHONE]
        self.assertEqual(len(private), 1, self.sent)
        self.assertIn(self._path(link), private[0].replace('%2F', '/'))
        group = [t for to, t in self.sent if to == GROUP]
        self.assertTrue(any('private chat' in t for t in group), group)
        self.assertFalse(any(link.sudo().token in t for t in group), 'the link is not in the group')
        # form only: no "answer here" and no Home / Work / Other poll
        self.assertFalse(any('answer here' in t.lower() for t in group), group)
        self.assertFalse(self.polls, 'no poll in the group')
        self.assertEqual(self.request.sa_book_step, 'form')

    def test_a_hidden_number_gets_the_link_and_the_questions_in_the_group(self):
        self.request.write({'requester_is_lid': True, 'requester_lid': '1234@lid'})
        link = self._open_book()
        self.assertEqual(link.sent_to, 'group')
        self.assertFalse([1 for to, t in self.sent if to == PHONE])
        self.assertTrue(any(link.sudo().token in t for to, t in self.sent if to == GROUP))
        self.assertEqual(self.request.sa_book_step, 'label', 'the group questions as before')

    def test_writing_in_the_group_meanwhile_points_at_the_private_chat(self):
        link = self._open_book()
        self.sent.clear()
        self.request._sa_book_take('15/2 Adiyanuthu')
        group = [t for to, t in self.sent if to == GROUP]
        self.assertTrue(any('private chat' in t for t in group), group)
        self.assertEqual(self.request.sa_book_step, 'form')
        self.assertEqual(self.request.sa_addr_link_ids, link, 'the same link, not a new one')

    def test_an_expired_form_gets_a_new_link_when_they_write(self):
        old = self._open_book()
        old.expires_on = fields.Datetime.now() - timedelta(minutes=1)
        self.sent.clear()
        self.request._sa_book_take('hello?')
        links = self.request.with_context(active_test=False).sa_addr_link_ids
        new = links - old
        self.assertEqual(len(new), 1)
        self.assertEqual(new.sent_to, 'private')
        self.assertTrue(any(new.sudo().token in t for to, t in self.sent if to == PHONE))
        self.assertEqual(self.request.sa_book_step, 'form')

    def test_cancel_in_the_group_still_cancels(self):
        link = self._open_book()
        with patch.object(type(self.request), '_sa_cancel_deal', lambda self: True) as _x:
            self.request._sa_book_take('cancel')
        self.assertFalse(self.request.sa_book_step)
        self.assertFalse(link.active)

    def test_switched_off_nothing_changes(self):
        self.env['sa.ai.settings'].get_settings().address_link_enabled = False
        link = self._open_book()
        self.assertFalse(link)
        self.assertEqual(self.request.sa_book_step, 'label')

    def test_the_link_is_sent_once_per_address_step(self):
        self._open_book()
        st = self.request._sa_book_state()
        self.request._sa_book_start_add(st)    # "Start over" in the group
        self.assertEqual(len(self.request.sa_addr_link_ids), 1)
        self.assertEqual(self.request.sa_book_step, 'form')

    # ------------------------------------------------------------ the page
    def test_the_page_shows_the_form(self):
        link = self._open_book()
        res = self.url_open(self._path(link))
        self.assertEqual(res.status_code, 200)
        self.assertIn('Delivery address', res.text)
        self.assertIn('Sri', res.text)
        self.assertIn(PHONE[-10:], res.text)
        self.assertEqual(link.open_count, 1)

    def test_saving_the_form_puts_the_address_on_the_order(self):
        link = self._open_book()
        self.sent.clear()
        res = self.url_open(self._path(link), data=self._form())
        self.assertEqual(res.status_code, 200)
        self.assertIn('Address saved', res.text)
        self.assertIn('WhatsApp group', res.text)
        addr = self.order.partner_shipping_id
        self.assertEqual(addr.street, '15/2')
        self.assertEqual(addr.street2, 'Adiyanuthu Road')
        self.assertEqual(addr.zip, '624003')
        self.assertEqual(addr.city, 'Dindigul')
        self.assertEqual(addr.name, 'Sri')
        self.assertEqual(addr.state_id, self.tn)
        self.assertAlmostEqual(addr.partner_latitude, 10.3624, places=4)
        self.assertTrue(self.request.sa_book_done)
        self.assertFalse(self.request.sa_book_step)
        self.assertTrue(link.used_on)
        self.assertEqual(link.address_id, addr)
        group = [t for to, t in self.sent if to == GROUP]
        self.assertTrue(any('Address saved from the form' in t for t in group), group)

    def test_the_link_works_once(self):
        link = self._open_book()
        self.url_open(self._path(link), data=self._form())
        first = self.order.partner_shipping_id
        res = self.url_open(self._path(link), data=self._form(line='99, Other street'))
        self.assertIn('Address saved', res.text, 'the saved page again, nothing new')
        self.assertEqual(self.order.partner_shipping_id, first)
        self.assertEqual(first.street, '15/2')

    def test_an_expired_link_saves_nothing(self):
        link = self._open_book()
        link.expires_on = fields.Datetime.now() - timedelta(minutes=1)
        res = self.url_open(self._path(link), data=self._form())
        self.assertEqual(res.status_code, 410)
        self.assertFalse(link.used_on)
        self.assertEqual(self.request.sa_book_step, 'form')

    def test_answering_in_the_group_closes_the_link(self):
        link = self._open_book()
        addr = self.env['res.partner'].create({
            'name': 'Sri', 'parent_id': self.customer.id, 'type': 'delivery',
            'street': '1, Main road', 'zip': '624001'})
        self.request._sa_book_finish(addr, self.request._sa_book_state())
        self.assertFalse(link.active)
        res = self.url_open(self._path(link), data=self._form())
        self.assertEqual(res.status_code, 410)
        self.assertEqual(self.order.partner_shipping_id, addr)

    def test_a_bad_pincode_comes_back_with_the_values_kept(self):
        link = self._open_book()
        res = self.url_open(self._path(link), data=self._form(pin='62400'))
        self.assertEqual(res.status_code, 200)
        self.assertNotIn('Address saved', res.text)
        self.assertIn('Adiyanuthu Road', res.text, 'what was typed is kept')
        self.assertIn('class="err"', res.text)
        self.assertIn('Enter a 6-digit postcode', res.text)
        self.assertFalse(link.used_on)
        self.assertEqual(self.request.sa_book_step, 'form')

    def test_the_pincode_fills_city_and_state(self):
        link = self._open_book()
        res = self.url_open('%s/pincode?pin=624003' % self._path(link))
        data = res.json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data.get('town'), 'Dindigul')
        self.assertEqual(data.get('state_id'), self.tn.id)

    def test_a_wrong_token_is_not_found(self):
        res = self.url_open('/wa/address/%s' % ('x' * 32))
        self.assertEqual(res.status_code, 404)

    def test_the_doorway_lets_the_link_through(self):
        link = self._open_book()
        res = self.url_open('/scoped_app/wa-link?db=%s&to=%s' % (
            self.env.cr.dbname, self._path(link)))
        self.assertEqual(res.status_code, 200)
        self.assertIn('Delivery address', res.text)

    # ------------------------------------------------- the shop form's rules
    def _errors(self, **over):
        link = self._open_book()
        res = self.url_open(self._path(link), data=self._form(**over))
        self.assertNotIn('Address saved', res.text)
        self.assertFalse(link.used_on)
        return res.text

    def test_the_required_fields_say_what_is_missing(self):
        text = self._errors(name='', line='', area='', town='', state_id='')
        for message in ("Enter the receiver&#x27;s name", 'Enter the house no., building or apartment',
                        'Enter the street or area', 'Enter the city, district or town',
                        'Pick a state'):
            self.assertIn(message, text)

    def test_the_mobile_must_have_ten_digits(self):
        self.assertIn('Enter a 10-digit mobile number', self._errors(phone='98000'))

    def test_the_alternate_number_must_differ(self):
        self.assertIn('Use a different number, or leave it empty', self._errors(alt=PHONE[-10:]))

    def test_the_page_has_the_shop_form_fields(self):
        link = self._open_book()
        text = self.url_open(self._path(link)).text
        for name in ('country', 'name', 'phone', 'alt', 'pin', 'line', 'area', 'town', 'state_id',
                     'landmark', 'lat', 'lng'):
            self.assertIn('name="%s"' % name, text)
        self.assertIn('Pick on map', text)
        self.assertIn('+91', text)

    def test_the_map_search_lists_places(self):
        link = self._open_book()
        answer = [{'display_name': 'Adiyanuthu, Dindigul, Tamil Nadu', 'lat': '10.36', 'lon': '77.97'}]

        class Reply:
            def raise_for_status(self):
                return None

            def json(self):
                return answer

        with patch('odoo.addons.sales_automation.models.sa_address_link.requests.get',
                   return_value=Reply()) as asked:
            data = self.url_open('%s/search?q=adiyanuthu&country=IN' % self._path(link)).json()
        self.assertEqual(data['places'], [{'name': 'Adiyanuthu, Dindigul, Tamil Nadu', 'lat': 10.36, 'lng': 77.97}])
        self.assertEqual(asked.call_args.kwargs['params']['countrycodes'], 'in')
        self.assertNotIn(PHONE, str(asked.call_args), 'nothing personal leaves with the search')
        text = self.url_open(self._path(link)).text
        self.assertIn('id="placeq"', text)

    def test_the_country_changes_the_rules(self):
        link = self._open_book()
        data = self.url_open('%s/meta?country=OM' % self._path(link)).json()
        self.assertEqual(data['country']['code'], 'OM')
        self.assertEqual(data['phone']['dial'], '+968')
        self.assertFalse(data['pin_length'])

    # ------------------------------------- change a saved address, and the menu
    def _saved_address(self, street='1, Old Street', zip_code='624001'):
        return self.env['res.partner'].create({
            'name': 'Sri', 'parent_id': self.customer.id, 'type': 'delivery', 'phone': '+' + PHONE,
            'street': street, 'street2': 'Old Area', 'zip': zip_code, 'city': 'Dindigul',
            'state_id': self.tn.id, 'country_id': self.india.id})

    def test_edit_sends_the_form_filled_in_with_that_address(self):
        old = self._saved_address()
        self.request._sa_book_open('order', force_list=True)
        self.sent.clear()
        self.request._sa_book_start_edit(self.request._sa_book_state(), old)
        link = self.request.sa_addr_link_ids[:1]
        self.assertEqual((link.mode, link.back, link.target_id), ('edit', 'order', old))
        self.assertEqual(link.sent_to, 'private')
        self.assertEqual(self.request.sa_book_step, 'form')
        group = [t for to, t in self.sent if to == GROUP]
        self.assertTrue(any('change your' in t and 'private chat' in t for t in group), group)
        page = self.url_open(self._path(link)).text
        self.assertIn('Change address', page)
        self.assertIn('value="1, Old Street"', page)
        self.assertIn('value="624001"', page)

    def test_saving_an_edit_changes_that_address(self):
        old = self._saved_address()
        self.request._sa_book_open('order', force_list=True)
        self.request._sa_book_start_edit(self.request._sa_book_state(), old)
        link = self.request.sa_addr_link_ids[:1]
        self.sent.clear()
        res = self.url_open(self._path(link), data=self._form(line='22, New Street', pin='624001'))
        self.assertIn('Address updated', res.text)
        addr = self.order.partner_shipping_id
        self.assertEqual(addr.street, '22, New Street')
        self.assertEqual(addr.parent_id, self.customer)
        self.assertEqual(len(self.customer.child_ids.filtered('active')), 1, 'changed, not added')
        group = [t for to, t in self.sent if to == GROUP]
        self.assertTrue(any('Address updated from the form' in t for t in group), group)

    def test_add_from_the_menu_uses_the_form(self):
        self.request._sa_book_open('menu', force_list=True)
        link = self.request.sa_addr_link_ids[:1]
        self.assertEqual((link.mode, link.back), ('add', 'menu'))
        self.assertEqual(self.request.sa_book_step, 'form')
        page = self.url_open(self._path(link)).text
        self.assertNotIn('For order', page)
        self.sent.clear()
        res = self.url_open(self._path(link), data=self._form())
        self.assertIn('Address saved', res.text)
        self.assertTrue(link.used_on)
        self.assertEqual(link.address_id.street, '15/2')
        group = [t for to, t in self.sent if to == GROUP]
        self.assertTrue(any('Delivery address set' in t for t in group), group)

    def test_edit_from_the_menu_uses_the_form(self):
        old = self._saved_address()
        self.request._sa_book_open('menu', force_list=True)
        self.request._sa_book_start_edit(self.request._sa_book_state(), old)
        link = self.request.sa_addr_link_ids[:1]
        self.assertEqual((link.mode, link.back, link.target_id), ('edit', 'menu', old))
        res = self.url_open(self._path(link), data=self._form(line='7, Menu Street', pin='624001'))
        self.assertIn('Address updated', res.text)
        self.assertEqual(link.address_id.street, '7, Menu Street')

    def test_switching_from_add_to_edit_gives_a_new_link(self):
        old = self._saved_address()
        self.request._sa_book_open('order', force_list=True)
        st = self.request._sa_book_state()
        self.request._sa_book_start_add(st)
        add = self.request.sa_addr_link_ids[:1]
        self.request._sa_book_start_edit(self.request._sa_book_state(), old)
        links = self.request.with_context(active_test=False).sa_addr_link_ids
        self.assertFalse(add.active, 'the first link stops working')
        self.assertEqual((links - add).mode, 'edit')

    # ------------------- no read-back after the form; sign, then pay (21 Nov 2026)
    def _form_saved_in_details(self):
        """An order at its details step whose address comes from the form."""
        self.request.write({'sa_details_pending': True})
        link = self._open_book()
        self.sent.clear()
        self.url_open(self._path(link), data=self._form())
        return link

    def test_after_the_form_the_sign_link_comes_without_a_read_back(self):
        self._form_saved_in_details()
        self.assertEqual(self.request.profile_step, 'done')
        self.assertFalse(self.request.sa_details_pending)
        self.assertTrue(self.request.sa_sign_link_sent_on)
        everything = '\n'.join(t for to, t in self.sent)
        self.assertNotIn('Please check your details', everything)
        self.assertTrue(any('sign' in t.lower() and '%2Fmy%2Forders' in t for to, t in self.sent if to == PHONE),
                        'the sign link went privately')

    def test_from_the_menu_nothing_is_signed(self):
        self.request._sa_book_open('menu', force_list=True)
        link = self.request.sa_addr_link_ids[:1]
        self.url_open(self._path(link), data=self._form())
        self.assertFalse(self.request.sa_sign_link_sent_on)

    def _sign(self):
        import json
        order = self.order
        order._portal_ensure_token()
        png = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA'
               '60e6kgAAAABJRU5ErkJggg==')
        res = self.url_open('/my/orders/%s/accept?access_token=%s' % (order.id, order.access_token),
                            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {
                                'name': 'Sri', 'signature': png}}),
                            headers={'Content-Type': 'application/json'})
        return res.json().get('result') or {}

    def test_signing_opens_the_payment_when_the_pay_link_went(self):
        if 'sa.delivery.settings' in self.env:
            self.env['sa.delivery.settings'].sudo().get_settings().flow_end = 'paid'
        self._form_saved_in_details()
        result = self._sign()
        self.assertFalse(result.get('error'), result)
        self.assertEqual(self.order.state, 'sale')
        if not self.request.sa_pay_link_sent_on:
            self.skipTest('no pay link in this database (flow end / stock rules)')
        self.assertIn('payment_amount=', result.get('redirect_url', ''))
        group = [t for to, t in self.sent if to == GROUP]
        self.assertTrue(any('payment link' in t for t in group), group)

    def test_no_payment_is_opened_when_none_is_asked(self):
        if 'sa.delivery.settings' not in self.env:
            self.skipTest('the flow ends at payment without the delivery module')
        self.env['sa.delivery.settings'].sudo().get_settings().flow_end = 'order'
        self._form_saved_in_details()
        result = self._sign()
        self.assertFalse(result.get('error'), result)
        self.assertFalse(self.request.sa_pay_link_sent_on)
        self.assertNotIn('payment_amount=', result.get('redirect_url', ''))
        self.assertFalse(self.order._sa_portal_status()['pay_url'], 'no Pay button either')
