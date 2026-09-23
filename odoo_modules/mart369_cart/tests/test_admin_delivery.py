"""The staff side of fees, slots and service areas.

Four things are worth pinning here, and every one of them is a failure that
would look like nothing at all from the outside.

**Who may look.** These routes have no per-shopper fence - that is the point
of them - so the group check is the only thing between a shopper and the
shop's pricing. It is checked on every route, and a shopper is refused rather
than handed an empty list.

**A slot's key does not move.** It is what the app calls the slot and what
`sale.order.mart369_slot_key` stores when somebody books one. Rewriting it
would orphan every order already out for that window, and the capacity count,
which finds those orders by key, would quietly start reading zero - so a full
Saturday evening would go back on sale.

**The model's own rules still refuse.** A negative fee and a 25th hour are
refused by `@api.constrains` on the record, not by a second copy of those
rules in the controller. What is tested here is that the refusal arrives as a
sentence with a status, rather than as a stack trace after the handler has
already answered - which is what happens when nobody flushes.

**Nothing is deleted.** A rule, a slot and an area are all pointed at by
orders that have gone out. Switching one off is the only way to stop it.
"""

import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}

LIST = '/369mart/admin/delivery'
SLOTS = '/369mart/admin/delivery/slots'
AREAS = '/369mart/admin/delivery/areas'


@tagged('post_install', '-at_install')
class TestAdminDelivery(HttpCase):

    def setUp(self):
        super().setUp()
        self.Rule = self.env['mart369.delivery.rule'].with_context(active_test=False)
        self.Slot = self.env['mart369.delivery.slot'].with_context(active_test=False)
        self.Area = self.env['mart369.service.area'].with_context(active_test=False)

        self.rule = self.Rule.search([('mode', '=', 'quick')], limit=1)
        if not self.rule:
            self.rule = self.Rule.create({'mode': 'quick', 'label': 'Quick',
                                          'eta': 'Delivery in 13 mins', 'fee': 30.0})
        self.slot = self.Slot.create({
            'mode': 'quick', 'kind': 'window', 'key': 'admintest',
            'top': 'Today', 'from_hour': 18.0, 'to_hour': 20.0,
        })
        self.area = self.Area.create({'pincode': '600001', 'name': 'Test area'})

        self.shopper = self.env['res.users'].sudo().create({
            'name': 'A Shopper',
            'login': 'mart369_delivery_shopper',
            'password': 'mart369_delivery_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    # -------------------------------------------------------------- acting

    def _send(self, method, path, payload=None):
        return self.url_open(
            path, data=json.dumps(payload or {}), headers=HEADERS, method=method)

    def _staff(self):
        self.authenticate('admin', 'admin')

    def _rule_path(self, rule=None):
        return '/369mart/admin/delivery/rules/%s' % (rule or self.rule).id

    # ------------------------------------------------------------ the lock

    def test_a_shopper_is_refused_every_admin_route(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        self.authenticate('mart369_delivery_shopper', 'mart369_delivery_shopper')
        for response in (
            self.url_open(LIST),
            self._send('PATCH', self._rule_path(), {'fee': 0.0}),
            self._send('POST', SLOTS, {'key': 'sneak', 'top': 'Mine'}),
            self._send('PATCH', '%s/%s' % (SLOTS, self.slot.id), {'active': False}),
            self._send('POST', AREAS, {'pincode': '999999'}),
            self._send('PATCH', '%s/%s' % (AREAS, self.area.id), {'active': False}),
        ):
            self.assertEqual(response.status_code, 403)
            self.assertFalse(response.json()['ok'])

        # And nothing moved while they were trying.
        self.assertTrue(self.slot.active)
        self.assertTrue(self.area.active)

    # ------------------------------------------------------------ the list

    def test_the_list_carries_all_three_and_its_own_vocabulary(self):
        """One GET feeds three tabs, and the words for the choice rows.

        The labels travel with the list so that neither side keeps its own
        copy of what a storefront is called.
        """
        self._staff()
        payload = self.url_open(LIST).json()
        self.assertTrue(payload['ok'])
        for key in ('rules', 'slots', 'areas', 'modes', 'kinds'):
            self.assertIn(key, payload)
        self.assertIn(self.slot.id, [s['id'] for s in payload['slots']])
        self.assertIn('quick', [m['key'] for m in payload['modes']])
        self.assertIn('window', [k['key'] for k in payload['kinds']])

        row = next(s for s in payload['slots'] if s['id'] == self.slot.id)
        # The hours go out as numbers, not as '6 PM'. The screen prints the
        # time; what it edits and sends back is the float.
        self.assertEqual(row['fromHour'], 18.0)
        self.assertEqual(row['modeLabel'], 'Quick')

    def test_a_switched_off_slot_is_still_listed(self):
        """Off is a state the screen shows, not a reason to hide a row."""
        self.slot.active = False
        self._staff()
        rows = self.url_open(LIST).json()['slots']
        row = next((s for s in rows if s['id'] == self.slot.id), None)
        self.assertIsNotNone(row)
        self.assertFalse(row['active'])

    # ------------------------------------------------------------ the fees

    def test_staff_can_change_what_delivery_costs(self):
        self._staff()
        response = self._send('PATCH', self._rule_path(),
                              {'fee': 45.0, 'free_above': 599.0, 'eta': 'In 15 mins'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['rule']['fee'], 45.0)
        self.rule.invalidate_recordset()
        self.assertEqual(self.rule.fee, 45.0)
        self.assertEqual(self.rule.eta, 'In 15 mins')

    def test_a_negative_fee_is_refused_in_the_models_own_words(self):
        """The constraint lives on the record. This checks it arrives."""
        self._staff()
        response = self._send('PATCH', self._rule_path(), {'fee': -5.0})
        self.assertEqual(response.status_code, 400)
        self.assertIn('negative', response.json()['error'])
        self.rule.invalidate_recordset()
        self.assertNotEqual(self.rule.fee, -5.0)

    def test_a_storefront_cannot_be_left_without_a_name(self):
        self._staff()
        response = self._send('PATCH', self._rule_path(), {'label': '   '})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'label')

    def test_the_mode_is_not_writable(self):
        """One rule per storefront, so a form that could move one between
        them would collide with the other rather than edit anything."""
        self._staff()
        self._send('PATCH', self._rule_path(), {'mode': 'all', 'fee': 12.0})
        self.rule.invalidate_recordset()
        self.assertEqual(self.rule.mode, 'quick')
        self.assertEqual(self.rule.fee, 12.0)

    # ----------------------------------------------------------- the slots

    def test_staff_can_add_a_slot(self):
        self._staff()
        response = self._send('POST', SLOTS, {
            'mode': 'quick', 'kind': 'window', 'key': 'newtest', 'top': 'Tonight',
            'from_hour': 20.0, 'to_hour': 22.0, 'capacity': 40,
        })
        self.assertEqual(response.status_code, 201)
        made = self.Slot.search([('key', '=', 'newtest')])
        self.assertEqual(len(made), 1)
        self.assertEqual(made.capacity, 40)

    def test_a_duplicate_key_in_one_storefront_is_a_conflict(self):
        self._staff()
        response = self._send('POST', SLOTS, {
            'mode': 'quick', 'kind': 'window', 'key': 'admintest', 'top': 'Again',
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['field'], 'key')

    def test_the_same_key_in_the_other_storefront_is_fine(self):
        """The index is on the pair, and Quick and Express are separate
        lists to the app - 'std' in one is not 'std' in the other."""
        self._staff()
        response = self._send('POST', SLOTS, {
            'mode': 'all', 'kind': 'days', 'key': 'admintest', 'top': 'Standard',
        })
        self.assertEqual(response.status_code, 201)

    def test_a_slot_needs_a_key_and_a_heading(self):
        self._staff()
        self.assertEqual(
            self._send('POST', SLOTS, {'top': 'Nameless'}).json()['field'], 'key')
        self.assertEqual(
            self._send('POST', SLOTS, {'key': 'headless', 'top': ''}).json()['field'],
            'top')

    def test_a_slots_key_cannot_be_rewritten(self):
        """Orders already booked into it are found by this key."""
        self._staff()
        response = self._send('PATCH', '%s/%s' % (SLOTS, self.slot.id),
                              {'key': 'renamed', 'top': 'Evening'})
        self.assertEqual(response.status_code, 200)
        self.slot.invalidate_recordset()
        self.assertEqual(self.slot.key, 'admintest')
        self.assertEqual(self.slot.top, 'Evening')

    def test_an_hour_outside_the_day_is_refused(self):
        self._staff()
        response = self._send('PATCH', '%s/%s' % (SLOTS, self.slot.id),
                              {'from_hour': 25.0})
        self.assertEqual(response.status_code, 400)
        self.slot.invalidate_recordset()
        self.assertEqual(self.slot.from_hour, 18.0)

    def test_an_hour_that_is_not_a_number_names_its_own_field(self):
        self._staff()
        response = self._send('PATCH', '%s/%s' % (SLOTS, self.slot.id),
                              {'from_hour': 'six'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'from_hour')

    def test_switching_a_slot_off_stops_the_checkout_offering_it(self):
        """The whole point of the screen: the shopper feed follows."""
        self._staff()
        self._send('PATCH', '%s/%s' % (SLOTS, self.slot.id), {'active': False})
        self.slot.invalidate_recordset()
        self.assertFalse(self.slot.active)
        offered = self.env['mart369.delivery.slot']._mart369_slots()
        self.assertNotIn('admintest', [c['key'] for c in offered['quick']])

    # ----------------------------------------------------------- the areas

    def test_staff_can_open_a_new_area(self):
        self._staff()
        response = self._send('POST', AREAS, {
            'pincode': '641001', 'name': 'Coimbatore', 'quick': False, 'eta': '2 days'})
        self.assertEqual(response.status_code, 201)
        made = self.Area.search([('pincode', '=', '641001')])
        self.assertEqual(len(made), 1)
        self.assertFalse(made.quick)
        self.assertTrue(made.express)

    def test_a_pincode_with_a_space_in_it_is_accepted(self):
        """Pasted from a spreadsheet. Refusing that teaches nobody anything."""
        self._staff()
        response = self._send('POST', AREAS, {'pincode': '641 002'})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.Area.search([('pincode', '=', '641002')]))

    def test_a_pincode_that_is_not_digits_is_refused(self):
        self._staff()
        response = self._send('POST', AREAS, {'pincode': 'KOCHI1'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.Area.search([('pincode', '=', 'KOCHI1')]))

    def test_a_pincode_already_covered_is_a_conflict(self):
        self._staff()
        response = self._send('POST', AREAS, {'pincode': '600001'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['field'], 'pincode')

    def test_switching_an_area_off_tells_the_customer_we_do_not_go_there(self):
        self._staff()
        self._send('PATCH', '%s/%s' % (AREAS, self.area.id),
                   {'quick': False, 'express': False})
        answer = self.env['mart369.service.area']._mart369_check('600001')
        self.assertFalse(answer['ok'])

    def test_an_edit_to_a_missing_record_is_a_404(self):
        self._staff()
        for path in ('/369mart/admin/delivery/rules/0',
                     '%s/0' % SLOTS, '%s/0' % AREAS):
            self.assertEqual(self._send('PATCH', path, {'active': False}).status_code, 404)
