"""One phone number, one customer."""

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

    def setUp(self):
        super().setUp()
        # A store account catches a chat only once it proved the number.
        self.partner.with_context(mart369_phone_proven=True).write({
            'phone': self.PHONE, 'mart369_phone_verified': True})

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

    # ---------------------------- the stack's lookup (res.partner._sa_phone_matches)

    def test_the_stacks_lookup_finds_the_proven_account(self):
        found = self.env['res.partner']._sa_phone_matches(self.PHONE.lstrip('+'))
        self.assertEqual(found[:1], self.partner)

    def test_the_stacks_lookup_answers_the_customer_not_the_doorstep(self):
        self.address.phone = self.PHONE
        found = self.env['res.partner']._sa_phone_matches(self.PHONE)
        self.assertIn(self.partner, found)
        self.assertFalse(found.filtered('parent_id'), 'never an address child')
        self.assertEqual(len(found.filtered(lambda p: p == self.partner)), 1)

    def test_a_proven_account_comes_before_a_plain_contact(self):
        contact = self.env['res.partner'].sudo().create(
            {'name': 'Older WhatsApp contact', 'phone': self.PHONE})
        found = self.env['res.partner']._sa_phone_matches(self.PHONE)
        self.assertEqual(found[:1], self.partner)
        self.assertIn(contact, found)

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
