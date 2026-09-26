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

    def test_menu_address_change_moves_the_storefront_default(self):
        self.partner.phone = self.PHONE
        # The customer already has a default delivery address from the book.
        self.address.write({'type': 'delivery', 'mart369_default': True})
        request = self.env['sa.group.request'].sudo().create({
            'group_id': self.wa_group.id,
            'requester_phone': self.PHONE,
            'raw_text': 'address change',
            'sa_address_pending': 'confirm',
            'sa_address_draft': '12 New Colony, 4th Street, Dindigul 624001',
        })
        handled = request._sa_address_answer('YES, SAVE IT')
        self.assertTrue(handled)
        book = self.partner._mart369_book()
        default = book.filtered('mart369_default')
        self.assertEqual(len(default), 1)
        self.assertIn('12 New Colony', default.street)
        # The one-delivery-child rule survived the change.
        children = self.partner.with_context(active_test=False).child_ids
        self.assertEqual(
            len(children.filtered(lambda c: c.active and c.type == 'delivery')), 1)
