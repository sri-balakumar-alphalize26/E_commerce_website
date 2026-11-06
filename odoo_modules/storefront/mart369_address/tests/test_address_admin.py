"""The staff side of addresses, and two ways the default could go wrong.

**Who may look.** These routes have no per-shopper fence - that is the point of
them - so the group check is the only thing between a shopper and every
customer's home address.

**Read only.** There is no route that writes an address and there should never
be one, so the surface itself is asserted.

The two bug tests are the reason this file exists:

*Deleting an address used to archive it before choosing a successor*, against a
sibling search that could no longer see it - so a customer could be left with
nothing selected, while the archived record kept `type='delivery'` and Odoo's
own `address_get('delivery')` went on resolving to the address they had just
removed.

*The default flag could be set behind the helper's back.* Only
`_mart369_set_default` clears the sibling and moves the type; writing the flag
straight onto the record left two defaults and shipped to the older one.
"""

import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}
LIST = '/369mart/admin/addresses'


@tagged('post_install', '-at_install')
class TestAddressDefaults(HttpCase):
    """The model, without the HTTP layer in the way."""

    def setUp(self):
        super().setUp()
        self.customer = self.env['res.partner'].create({'name': 'Address Tester'})

    def _addr(self, name, **over):
        values = {'parent_id': self.customer.id, 'type': 'other',
                  'name': name, 'mart369_label': 'Home',
                  'street': '5/2 Sivamurugan Colony', 'city': 'Dindigul',
                  'zip': '624003', 'phone': '+919486020356'}
        values.update(over)
        return self.env['res.partner'].create(values)

    def _delivery_children(self):
        return self.env['res.partner'].with_context(active_test=False).search([
            ('parent_id', '=', self.customer.id), ('type', '=', 'delivery')])

    # ------------------------------------------------- the flag goes through

    def test_setting_the_flag_by_hand_still_moves_the_delivery_type(self):
        """Writing it straight on the record used to skip the helper."""
        first = self._addr('First')
        first._mart369_set_default()
        second = self._addr('Second')

        second.mart369_default = True

        self.assertTrue(second.mart369_default)
        self.assertFalse(first.mart369_default, 'only one default at a time')
        self.assertEqual(second.type, 'delivery')
        self.assertEqual(self._delivery_children(), second,
                         'and exactly one child is the delivery one')

    def test_turning_the_flag_off_is_left_alone(self):
        """A customer with no default is a state the delete route handles;
        clearing the flag must not be turned into setting it."""
        only = self._addr('Only')
        only._mart369_set_default()
        only.mart369_default = False
        self.assertFalse(only.mart369_default)

    # ------------------------------------------------------- deleting one

    def test_deleting_the_default_hands_over_before_it_goes(self):
        first = self._addr('First')
        first._mart369_set_default()
        second = self._addr('Second')

        self._archive(first)

        self.assertTrue(second.mart369_default, 'somebody took over')
        self.assertEqual(self._delivery_children(), second)
        self.assertNotEqual(
            self.customer.address_get(['delivery']).get('delivery'), first.id,
            'the shop must not still be shipping to the archived one')

    def test_deleting_the_only_address_leaves_nothing_typed_delivery(self):
        """The worst case: no successor exists, so the archived record must
        not keep the delivery type to itself."""
        only = self._addr('Only')
        only._mart369_set_default()

        self._archive(only)

        self.assertFalse(only.mart369_default)
        self.assertEqual(only.type, 'other', 'it gave the type back')
        self.assertFalse(self._delivery_children())

    def _archive(self, address):
        """What the delete route does, in the order it does it."""
        was_default = address.mart369_default
        successor = self.env['res.partner']
        if was_default:
            successor = self.env['res.partner'].search([
                ('parent_id', '=', address.parent_id.id),
                ('type', 'in', ('delivery', 'other')),
                ('id', '!=', address.id),
            ], order='mart369_default desc, id asc')[:1]
        address.write({'active': False, 'mart369_default': False, 'type': 'other'})
        if successor:
            successor._mart369_set_default()


@tagged('post_install', '-at_install')
class TestAddressAdminApi(HttpCase):

    def setUp(self):
        super().setUp()
        self.customer = self.env['res.partner'].create({'name': 'Console Tester'})
        self.address = self.env['res.partner'].create({
            'parent_id': self.customer.id, 'type': 'other',
            'name': 'Console Tester', 'mart369_label': 'Home',
            'street': '5/2 Sivamurugan Colony', 'city': 'Dindigul',
            'zip': '624003', 'phone': '+919486020356',
        })
        # One with holes in it, so the gap tiles have something to count.
        self.gappy = self.env['res.partner'].create({
            'parent_id': self.customer.id, 'type': 'other',
            'name': 'No pincode', 'mart369_label': 'Work',
            'street': 'Sandai Road', 'city': 'Dindigul',
        })
        self.shopper = self.env['res.users'].sudo().create({
            'name': 'A Shopper',
            'login': 'mart369_address_shopper',
            'password': 'mart369_address_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    # ------------------------------------------------------------- the lock

    def test_a_shopper_is_refused(self):
        """This is where customers live."""
        self.authenticate('mart369_address_shopper', 'mart369_address_shopper')
        self.assertEqual(self.url_open(LIST).status_code, 403)
        self.assertEqual(self.url_open(LIST + '/counts').status_code, 403)

    def test_signed_out_is_sent_to_the_sign_in_page(self):
        self.assertIn('/web/login', self.url_open(LIST).url)

    def test_there_is_no_way_to_write_an_address(self):
        """Read-only is the decision. Nothing should answer a write."""
        self.authenticate('admin', 'admin')
        for method in ('POST', 'PATCH', 'DELETE'):
            response = self.url_open(LIST, data=json.dumps({}),
                                     headers=HEADERS, method=method)
            self.assertNotEqual(response.status_code, 200,
                                '%s reached something it should not have' % method)

    # ------------------------------------------------------------ the list

    def test_staff_read_the_addresses(self):
        self.authenticate('admin', 'admin')
        payload = self.url_open(LIST + '?tab=all').json()
        self.assertTrue(payload['ok'])
        mine = [a for a in payload['addresses'] if a['id'] == self.address.id]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]['customer'], self.customer.display_name)
        self.assertEqual(mine[0]['zip'], '624003')

    def test_the_gap_tabs_find_what_is_missing(self):
        """`mart369_gap_label` is a non-stored compute and cannot be searched,
        so these count the raw fields instead."""
        Partner = self.env['res.partner']
        ids = [a['id'] for a
               in Partner.mart369_admin_list(tab='no_pincode')['addresses']]
        self.assertIn(self.gappy.id, ids)
        self.assertNotIn(self.address.id, ids)

    def test_the_tiles_count_everything_not_the_filtered_rows(self):
        Partner = self.env['res.partner']
        wide = Partner.mart369_admin_list(tab='all')
        narrow = Partner.mart369_admin_list(tab='all', q='No pincode')
        self.assertEqual(wide['counts'], narrow['counts'])
        self.assertLess(len(narrow['addresses']), len(wide['addresses']))

    def test_search_matches_the_customer_and_the_place(self):
        Partner = self.env['res.partner']
        ids = lambda **kw: [a['id'] for a in Partner.mart369_admin_list(**kw)['addresses']]
        self.assertIn(self.address.id, ids(tab='all', q='Console Tester'))
        self.assertIn(self.address.id, ids(tab='all', q='624003'))
        self.assertNotIn(self.address.id, ids(tab='all', q='nowhere at all'))

    def test_the_staff_shape_does_not_leak_into_the_shopper_one(self):
        """`_mart369_serialize` goes to the customer who owns the address.
        Whose it is, is not theirs to read."""
        shopper = self.address._mart369_serialize()
        self.assertNotIn('customer', shopper)
        self.assertNotIn('customerId', shopper)
        self.assertIn('label', shopper)
