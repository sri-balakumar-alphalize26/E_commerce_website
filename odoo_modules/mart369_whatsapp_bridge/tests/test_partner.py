"""One phone number, one customer."""

import json

from odoo.tests import tagged

from .common import Mart369BridgeCase


class FakeConv:
    def __init__(self, phone, name='Chat Customer'):
        self.phone = phone
        self.contact_name = name


@tagged('post_install', '-at_install')
class TestPartner(Mart369BridgeCase):

    # A number no seeded demo customer carries - the tests run on a copy of
    # the live database, which is full of +9198… people.
    PHONE = '+917009900011'

    def test_store_account_is_reused(self):
        self.partner.phone = self.PHONE
        found = self.env['wa.auto.reply']._mart369_bridge_partner(
            self.PHONE.lstrip('+'))
        self.assertEqual(found, self.partner)

    def test_address_child_never_wins(self):
        """The website keeps a phone on each delivery address; the chat must
        land on the customer, not on their doorstep."""
        self.partner.phone = self.PHONE
        self.address.phone = self.PHONE
        found = self.env['wa.auto.reply']._mart369_bridge_partner(self.PHONE)
        self.assertEqual(found, self.partner)
        self.assertFalse(found.parent_id)

    def test_unknown_number_falls_through(self):
        found = self.env['wa.auto.reply']._mart369_bridge_partner('+917009900099')
        self.assertFalse(found)

    # ------------------------------------------------- the address book

    def _request(self, **vals):
        return self.env['sa.group.request'].sudo().create(dict({
            'group_id': self.wa_group.id,
            'requester_phone': self.PHONE,
            'raw_text': 'address',
        }, **vals))

    def _second_address(self, label='Office', street='9 Market Road'):
        return self.partner._mart369_add_address({
            'name': self.partner.name, 'phone': self.PHONE,
            'street': street, 'city': 'Dindigul', 'zip': '624002',
            'mart369_label': label,
        })

    def _delivery_children(self):
        children = self.partner.with_context(active_test=False).child_ids
        return children.filtered(lambda c: c.active and c.type == 'delivery')

    def test_menu_address_change_adds_to_the_book(self):
        """A typed address joins the storefront book as the new default; the
        old one stays for tapping back to."""
        self.partner.phone = self.PHONE
        self.address.write({'type': 'delivery', 'mart369_default': True})
        request = self._request(
            sa_address_pending='confirm',
            sa_address_draft='12 New Colony, 4th Street, Dindigul 624001')
        self.assertTrue(request._sa_address_answer('YES, SAVE IT'))
        book = self.partner._mart369_book()
        self.assertEqual(len(book), 2)
        default = book.filtered('mart369_default')
        self.assertEqual(len(default), 1)
        self.assertIn('12 New Colony', default.street)
        self.assertEqual(default.mart369_label, 'WhatsApp')
        self.assertIn(self.address, book)
        self.assertFalse(self.address.mart369_default)
        # The one-delivery-child rule survived the change.
        self.assertEqual(len(self._delivery_children()), 1)

    def test_change_address_lists_the_book(self):
        self.partner.phone = self.PHONE
        self.address.write({'type': 'delivery', 'mart369_default': True})
        office = self._second_address()
        request = self._request()
        self.assertTrue(request._sa_ask_new_address())
        menu = json.loads(request.sa_menu_json)
        by_target = {v.get('target'): k for k, v in menu.items()
                     if v['kind'] == 'mart369_addr'}
        self.assertEqual(set(by_target), {self.address.id, office.id})
        self.assertTrue(by_target[self.address.id].startswith('✅'))
        self.assertIn('Office - 9 Market Road', by_target[office.id])
        kinds = [v['kind'] for v in menu.values()]
        self.assertIn('mart369_addr_new', kinds)
        self.assertIn(request.MENU_BACK, menu)
        self.assertIn(request.MENU_MAIN, menu)
        self.assertNotIn('MORE', ' '.join(menu))

    def test_change_address_without_a_book_asks_to_type(self):
        self.partner.phone = self.PHONE
        self.address.unlink()
        request = self._request()
        self.assertTrue(request._sa_ask_new_address())
        self.assertFalse(request.sa_menu_json)
        self.assertEqual(request.sa_address_pending, 'typing')

    def test_change_address_pages(self):
        self.partner.phone = self.PHONE
        for i in range(8):
            self._second_address('Spot %d' % i, '%d Long Lane' % i)
        request = self._request()
        request._sa_ask_new_address()
        first = json.loads(request.sa_menu_json)
        addrs = [v for v in first.values() if v['kind'] == 'mart369_addr']
        self.assertEqual(len(addrs), request.ADDR_PAGE)
        more = [v for v in first.values()
                if v['kind'] == 'menu' and v['level'] == 'mart369_addr:1']
        self.assertEqual(len(more), 1)
        request._sa_menu_show('mart369_addr:1')
        second = json.loads(request.sa_menu_json)
        rest = [v for v in second.values() if v['kind'] == 'mart369_addr']
        self.assertEqual(len(rest), 9 - request.ADDR_PAGE)
        self.assertEqual(second[request.MENU_BACK]['level'], 'mart369_addr')

    def test_tapping_an_address_makes_it_the_default(self):
        self.partner.phone = self.PHONE
        self.address.write({'type': 'delivery', 'mart369_default': True})
        office = self._second_address()
        request = self._request()
        request._sa_menu_tapped({'kind': 'mart369_addr', 'target': office.id,
                                 'parent': 'mart369_addr'})
        self.assertTrue(office.mart369_default)
        self.assertFalse(self.address.mart369_default)
        self.assertEqual(self._delivery_children(), office)
        self.assertTrue(any('Delivery address set' in body
                            for __, body in self.wa_sent))

    def test_tapping_someone_elses_address_is_refused(self):
        self.partner.phone = self.PHONE
        self.address.write({'type': 'delivery', 'mart369_default': True})
        stranger = self.env['res.partner'].sudo().create(
            {'name': 'Stranger', 'phone': '+917009900077'})
        theirs = stranger._mart369_add_address({
            'name': 'Stranger', 'phone': '+917009900077',
            'street': '1 Elsewhere', 'city': 'Madurai', 'zip': '625001'})
        request = self._request()
        request._sa_menu_tapped({'kind': 'mart369_addr', 'target': theirs.id,
                                 'parent': 'mart369_addr'})
        self.assertTrue(self.address.mart369_default)
        self.assertTrue(any('no longer available' in body
                            for __, body in self.wa_sent))

    def test_my_details_lists_the_book(self):
        self.partner.phone = self.PHONE
        self.address.write({'type': 'delivery', 'mart369_default': True})
        self._second_address()
        request = self._request()
        request._sa_say_my_details()
        body = self.wa_sent[-1][1]
        self.assertIn('Addresses:', body)
        self.assertIn('✅ Home - 3 Test Street', body)
        self.assertIn('• Office - 9 Market Road', body)

    # ------------------------------------------ the contact follows the book

    def test_tapping_an_address_syncs_the_contact(self):
        self.partner.phone = self.PHONE
        self.address.write({'type': 'delivery', 'mart369_default': True})
        office = self._second_address()
        request = self._request()
        request._sa_menu_tapped({'kind': 'mart369_addr', 'target': office.id,
                                 'parent': 'mart369_addr'})
        self.assertEqual(self.partner.street, '9 Market Road')
        self.assertEqual(self.partner.zip, '624002')
        self.assertEqual(self.partner.city, 'Dindigul')

    def test_website_default_change_syncs_the_contact(self):
        """The hook sits on the storefront's own helper, not on the chat."""
        self.partner.phone = self.PHONE
        self.address.write({'type': 'delivery', 'mart369_default': True})
        self.assertEqual(self.partner.street, '3 Test Street')
        office = self._second_address()
        office._mart369_set_default()
        self.assertEqual(self.partner.street, '9 Market Road')
        self.assertEqual(self.partner.zip, '624002')

    def test_editing_the_default_in_place_syncs_the_contact(self):
        self.partner.phone = self.PHONE
        self.address.write({'type': 'delivery', 'mart369_default': True})
        other = self._second_address()
        self.address.write({'street': '7 Renamed Road'})
        self.assertEqual(self.partner.street, '7 Renamed Road')
        other.write({'street': '1 Nowhere Lane'})
        self.assertEqual(self.partner.street, '7 Renamed Road')

    def test_sync_never_touches_name_or_phone(self):
        self.partner.phone = self.PHONE
        name = self.partner.name
        office = self._second_address(street='9 Market Road')
        office.write({'name': 'Office Reception', 'phone': '+917009900055'})
        office._mart369_set_default()
        self.assertEqual(self.partner.name, name)
        self.assertEqual(self.partner.phone, self.PHONE)
        found = self.env['wa.auto.reply']._mart369_bridge_partner(self.PHONE)
        self.assertEqual(found, self.partner)

    def test_sync_skips_a_parent_that_is_itself_a_child(self):
        self.partner.phone = self.PHONE
        nested = self.env['res.partner'].sudo().create({
            'name': 'Nested', 'parent_id': self.address.id, 'type': 'other',
            'street': '99 Deep Lane', 'city': 'Madurai', 'zip': '625001',
        })
        nested._mart369_sync_contact_address()
        self.assertEqual(self.address.street, '3 Test Street')
