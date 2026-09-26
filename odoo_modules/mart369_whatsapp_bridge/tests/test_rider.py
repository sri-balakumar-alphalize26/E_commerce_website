"""One person, one rider - on the console and in the rider app."""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import Mart369BridgeCase


@tagged('post_install', '-at_install')
class TestRider(Mart369BridgeCase):

    def test_console_assign_creates_the_stack_rider(self):
        order = self._web_order()
        order._mart369_set_rider(self.rider_user)
        job = self._job(order)
        rider = job.sa_delivery_partner_id
        self.assertTrue(rider)
        self.assertEqual(rider.user_id, self.rider_user)
        self.assertEqual(rider.phone, '+96890000002')
        # Assigning again finds the same record, never a twin.
        order2 = self._web_order(ref='369M-TESTR2')
        order2._mart369_set_rider(self.rider_user)
        self.assertEqual(self._job(order2).sa_delivery_partner_id, rider)
        self.assertEqual(self.env['sa.delivery.partner'].sudo().search_count(
            [('user_id', '=', self.rider_user.id)]), 1)

    def test_assign_offers_only_when_ready(self):
        order = self._web_order()
        job = self._job(order)
        order._mart369_set_rider(self.rider_user)
        # Still at the counter: the rider is pencilled in, not paged.
        self.assertEqual(job.sa_delivery_state, 'awaiting_shop')
        job.sa_shop_accept()
        job.sa_shop_ready()
        self.assertEqual(job.sa_delivery_state, 'offered')
        self.assertTrue([b for p, b in self.wa_sent if p == '+96890000002'])

    def test_too_late_to_reassign(self):
        order = self._web_order()
        job = self._job(order)
        order._mart369_set_rider(self.rider_user)
        job.sa_shop_accept()
        job.sa_shop_ready()
        job.sa_set_state('accepted')
        other = self.env['res.users'].sudo().create({
            'name': 'Second Rider',
            'login': 'second.rider@369mart.test',
            'group_ids': [(4, self.env.ref('mart369_roles.group_rider').id),
                          (4, self.env.ref('base.group_user').id)],
        })
        other.partner_id.phone = '+96890000003'
        with self.assertRaises(UserError):
            order._mart369_set_rider(other)

    def test_rider_without_a_phone_keeps_the_console_assignment(self):
        """The website assigned phone-less riders long before the bridge;
        they keep working - only the rider-app handover is skipped."""
        bare = self.env['res.users'].sudo().create({
            'name': 'No Phone',
            'login': 'no.phone@369mart.test',
            'group_ids': [(4, self.env.ref('mart369_roles.group_rider').id),
                          (4, self.env.ref('base.group_user').id)],
        })
        order = self._web_order()
        order._mart369_set_rider(bare)
        self.assertEqual(order.mart369_rider_id, bare)
        self.assertFalse(self._job(order).sa_delivery_partner_id)

    def test_app_assignment_mirrors_back(self):
        order = self._web_order()
        job = self._job(order)
        rider = self.env['sa.delivery.partner'].sudo()._mart369_bridge_for(
            self.rider_user)
        job.write({'sa_delivery_partner_id': rider.id})
        self.assertEqual(order.mart369_rider_id, self.rider_user)
