"""One proven number, one customer: signing in by number, and joining."""

import json
import re
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from .common import Mart369BridgeCase, Mart369BridgeFixtures

WA = '+919700880011'        # a WhatsApp-only customer
HEADERS = {'Content-Type': 'application/json'}


@tagged('post_install', '-at_install')
class TestPhoneLink(Mart369BridgeCase):

    def _wa_contact(self, phone=WA, street='5 Old Road', zip_code='624005'):
        order = self._wa_order(phone=phone)
        order.partner_id.write({'street': street, 'zip': zip_code})
        return order

    def _delivery_children(self, partner):
        return partner.child_ids.filtered(lambda c: c.active and c.type == 'delivery')

    # ------------------------------------------------------------ the postman

    def test_the_code_goes_out_on_whatsapp(self):
        outcome = self.env['res.partner']._mart369_send_login_code(WA, '482913')
        self.assertEqual(outcome, 'sent')
        phone, body = self.wa_sent[-1]
        self.assertEqual(phone, WA.lstrip('+'))
        self.assertIn('482913', body)

    def test_no_session_says_none(self):
        # Faked, not switched off: the running server shares those sessions.
        Notify = self.env.registry['mart369.whatsapp']
        with patch.object(Notify, '_mart369_session',
                          lambda self: self.env['whatsapp.session']):
            self.assertEqual(
                self.env['res.partner']._mart369_send_login_code(WA, '482913'), 'none')

    # ----------------------------------------------------------- the owner

    def test_whatsapp_only_customer_owns_the_number(self):
        order = self._wa_contact()
        partner, user = self.env['res.partner']._mart369_phone_owner(WA)
        self.assertEqual(partner, order.partner_id)
        self.assertFalse(user)

    def test_number_typed_without_country_code_is_the_same(self):
        Partner = self.env['res.partner']
        # The national number alone, as someone typed it, is the same number.
        self.assertTrue(Partner._mart369_same_number('9123 0099', '+96891230099'))
        self.assertTrue(Partner._mart369_same_number('09700880011', WA))
        # The same digits in another country are another person.
        self.assertFalse(Partner._mart369_same_number('+9689700880011', WA))
        self.assertFalse(Partner._mart369_same_number('+96891230099', '+9191230099'))

    def test_guards_keep_suppliers_and_logins_out(self):
        supplier = self.env['res.partner'].sudo().create({
            'name': 'Parts Supplier', 'phone': WA, 'supplier_rank': 3})
        self.assertFalse(supplier._mart369_joinable())
        staffish = self.env['res.users'].sudo().create({
            'name': 'Someone With Login', 'login': 'login.holder@369mart.test'})
        staffish.partner_id.phone = WA
        self.assertFalse(staffish.partner_id._mart369_joinable())
        self.assertFalse(self.env['res.partner']._mart369_wa_customers(WA))

    # ----------------------------------------------------------------- join

    def test_proving_the_number_joins_the_whatsapp_contact(self):
        order = self._wa_contact()
        src = order.partner_id
        result = self.partner._mart369_prove_phone(WA)
        self.assertFalse(src.exists(), 'the WhatsApp contact is folded in')
        self.assertEqual(order.partner_id, self.partner)
        self.assertGreaterEqual(result['orders'], 1)
        self.assertEqual(result['merged'], 1)
        # Its doorstep is in the book, and its order still goes there.
        shipping = order.partner_shipping_id
        self.assertEqual(shipping.parent_id, self.partner)
        self.assertEqual(shipping.street, '5 Old Road')
        self.assertEqual(shipping.mart369_label, 'WhatsApp')
        self.assertLessEqual(len(self._delivery_children(self.partner)), 1)
        self.assertTrue(self.partner.mart369_phone_verified)

    def test_the_same_address_is_not_added_twice(self):
        self.address.write({'street': '5 Old Road', 'zip': '624005'})
        before = len(self.partner._mart369_book())
        self._wa_contact()
        self.partner._mart369_prove_phone(WA)
        self.assertEqual(len(self.partner._mart369_book()), before)

    def test_wallets_add_up(self):
        if 'loyalty.card' not in self.env or not hasattr(
                self.env['loyalty.card'], '_mart369_wallet'):
            self.skipTest('no 369 Mart wallet here')
        order = self._wa_contact()
        Card = self.env['loyalty.card'].sudo()
        theirs = Card._mart369_wallet(order.partner_id).with_context(mart369_wallet_move=True)
        mine = Card._mart369_wallet(self.partner).with_context(mart369_wallet_move=True)
        theirs.points, mine.points = 40.0, 60.0
        self.partner._mart369_prove_phone(WA)
        self.assertEqual(Card._mart369_wallet(self.partner).points, 100.0)

    def test_a_contact_with_a_login_is_never_joined(self):
        other = self.env['res.users'].sudo().create({
            'name': 'Other Account', 'login': 'other.acc@369mart.test'})
        other.partner_id.phone = WA
        self.partner._mart369_prove_phone(WA)
        self.assertTrue(other.partner_id.exists())

    # ------------------------------------------------------------- the chat

    # Every lookup of a WhatsApp number goes through the stack's
    # res.partner._sa_phone_matches (tracker 1.3.0); this module's override
    # is where the "proven numbers only" rule lives.

    def test_unproven_account_no_longer_catches_the_chat(self):
        self.partner.phone = WA     # typed at signup, never proven
        found = self.env['res.partner']._sa_phone_matches(WA)
        self.assertNotIn(self.partner, found)

    def test_proven_account_catches_the_chat(self):
        self.partner.with_context(mart369_phone_proven=True).write(
            {'phone': WA, 'mart369_phone_verified': True})
        found = self.env['res.partner']._sa_phone_matches(WA)
        self.assertEqual(found[:1], self.partner)

    def test_the_clean_up_cron_is_gone(self):
        """The stack's lookup keeps the chat off unproven accounts now, so
        nothing is left for a 15-minute join to fold in."""
        self.assertFalse(self.env.ref(
            'mart369_whatsapp_bridge.ir_cron_mart369_join_duplicates',
            raise_if_not_found=False))

    # ------------------------------------------------------------ the book

    def test_a_street_written_on_the_customer_joins_the_book(self):
        self.partner.write({'street': '77 New Street', 'zip': '624007'})
        book = self.partner._mart369_book()
        default = book.filtered('mart369_default')
        self.assertEqual(default.street, '77 New Street')
        self.assertEqual(len(book.filtered(lambda a: a.street == '77 New Street')), 1)

    # ------------------------------------------------- one address, once

    def _home(self, street='Beach Road, beach, kollam, Kerala', pin='691001'):
        self.address.write({'street': street, 'zip': pin, 'mart369_label': 'Home'})
        return self.address

    def test_spelling_and_commas_are_the_same_address(self):
        a = self.partner._mart369_book_add_once({'street': 'beach road,kollam,691001', 'zip': '691001'})
        b = self.partner._mart369_book_add_once({'street': 'Beach road,Kollam, 691001', 'zip': '691001'})
        self.assertEqual(a, b)

    def test_the_pin_is_said_once(self):
        a = self.partner._mart369_book_add_once({'street': 'beach road,kollam,691001', 'zip': '691001'})
        self.assertEqual(a.street, 'beach road,kollam')
        self.assertEqual(a.zip, '691001')

    def test_a_shorter_whatsapp_address_reuses_home(self):
        home = self._home()
        found = self.partner._mart369_book_add_once({'street': 'beach road,kollam,691001', 'zip': '691001'})
        self.assertEqual(found, home)

    def test_different_door_numbers_stay_apart(self):
        a = self.partner._mart369_book_add_once({'street': '12 Beach Road, Kollam', 'zip': '691001'})
        b = self.partner._mart369_book_add_once({'street': '14 Beach Road, Kollam', 'zip': '691001'})
        self.assertNotEqual(a, b)

    def test_tidy_folds_old_duplicates_and_keeps_home(self):
        home = self._home()
        add = self.partner._mart369_add_address
        one = add({'name': 'x', 'street': 'beach road,kollam,691001', 'zip': '691001',
                   'mart369_label': 'WhatsApp'})
        two = add({'name': 'x', 'street': 'Beach road,Kollam, 691001', 'zip': '691001',
                   'mart369_label': 'WhatsApp'})
        two._mart369_set_default()
        order = self._web_order()
        order.sudo().partner_shipping_id = two
        folded = self.partner._mart369_book_tidy()
        self.assertEqual(folded, one | two)
        book = self.partner._mart369_book()
        self.assertIn(home, book)
        self.assertNotIn(one, book)
        self.assertTrue(home.mart369_default, 'the default moves to the address that stays')
        # The old order still shows where it went.
        self.assertEqual(order.partner_shipping_id, two)
        self.assertIn('Beach road', order.partner_shipping_id.street)

    def test_tidy_leaves_places_the_customer_saved(self):
        self._home(street='5 Gandhi Nagar', pin='624001')
        work = self.partner._mart369_add_address({
            'name': 'x', 'street': '5 Gandhi Nagar', 'zip': '624001', 'mart369_label': 'Work'})
        self.assertFalse(self.partner._mart369_book_tidy())
        self.assertTrue(work.active)


@tagged('post_install', '-at_install')
class TestPhoneSigninHttp(Mart369BridgeFixtures, HttpCase):
    """The whole door: a WhatsApp-only customer signs in on the website."""

    def _post(self, path, payload):
        return self.url_open(path, data=json.dumps(payload), headers=HEADERS)

    def _code(self):
        for __, body in reversed(self.wa_sent):
            found = re.search(r'\*(\d{6})\*', body)
            if found:
                return found.group(1)
        return None

    def test_whatsapp_customer_signs_in_and_sees_their_orders(self):
        order = self._wa_order(phone=WA)
        order.partner_id.write({'street': '5 Old Road', 'zip': '624005'})
        r = self._post('/369mart/auth/phone/start', {'phone': WA, 'purpose': 'signin'})
        self.assertEqual(r.status_code, 200, r.text)
        r = self._post('/369mart/auth/phone/verify',
                       {'phone': WA, 'purpose': 'signin', 'code': self._code()})
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertTrue(body['created'])
        self.assertEqual(body['partner_id'], order.partner_id.id,
                         'the login is made on the record that holds the orders')
        self.assertGreaterEqual(body['joined']['orders'], 1)
        orders = self.url_open('/369mart/orders').json()['orders']
        mine = [o for o in orders if o['id'] == order.name]
        self.assertTrue(mine, 'the WhatsApp order is in My Orders')
        self.assertEqual(mine[0]['channel'], 'whatsapp')
        self.assertFalse(mine[0]['canCancel'])
        one = self.url_open('/369mart/orders/%s' % order.name)
        self.assertEqual(one.status_code, 200)
        addresses = self.url_open('/369mart/addresses').json()
        self.assertIn('5 Old Road', json.dumps(addresses))
