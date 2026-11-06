"""The senior's "Mirror" list: what both sides keep, kept in step.

The updates switch and the delivery note mirror into fields the stack added
in its 7 Oct 2026 release; on an older stack (this machine's copy) those
tests skip - they run for real on DUBAI_TEST. The rider role mirrors into
`sa.delivery.partner`, which every stack version has.
"""

from odoo.tests import tagged

from .common import Mart369BridgeCase


@tagged('post_install', '-at_install')
class TestMirrors(Mart369BridgeCase):

    # --------------------------------------------------------- updates switch

    def test_the_website_switch_writes_the_stacks(self):
        if 'sa_wa_updates_off' not in self.env['res.partner']._fields:
            self.skipTest('the stack here has no STOP / START UPDATES field yet')
        self.partner._mart369_write_prefs({'whatsapp': False})
        self.assertTrue(self.partner.sa_wa_updates_off)
        self.partner._mart369_write_prefs({'whatsapp': True})
        self.assertFalse(self.partner.sa_wa_updates_off)

    def test_other_switches_leave_the_stacks_alone(self):
        if 'sa_wa_updates_off' not in self.env['res.partner']._fields:
            self.skipTest('the stack here has no STOP / START UPDATES field yet')
        self.partner.sudo().sa_wa_updates_off = True
        self.partner._mart369_write_prefs({'offers': False})
        self.assertTrue(self.partner.sa_wa_updates_off)

    # ------------------------------------------------------------ the note

    def test_the_checkout_note_is_the_stacks_note(self):
        if 'sa_delivery_note' not in self.env['sale.order']._fields:
            self.skipTest('the stack here has no note for one delivery yet')
        order = self._web_order()
        order.sudo().mart369_instructions = 'Ring the bell twice'
        self.assertEqual(order.sa_delivery_note, 'Ring the bell twice')

    def test_a_whatsapp_note_shows_on_the_order_page(self):
        if 'sa_delivery_note' not in self.env['sale.order']._fields:
            self.skipTest('the stack here has no note for one delivery yet')
        order = self._web_order()
        order.sudo().write({'mart369_instructions': False, 'sa_delivery_note': 'Gate 3'})
        self.assertEqual(order._mart369_serialize()['instructions'], 'Gate 3')

    # ---------------------------------------------------------- the rider

    def _rider_of(self, user):
        return self.env['sa.delivery.partner'].sudo().with_context(
            active_test=False).search([('user_id', '=', user.id)])

    def _staff(self, login, phone=None):
        user = self.env['res.users'].sudo().create({
            'name': 'Mirror %s' % login, 'login': '%s@369mart.test' % login,
            'group_ids': [(4, self.env.ref('base.group_user').id)],
        })
        if phone:
            user.partner_id.phone = phone
        return user

    def test_the_rider_role_makes_a_rider_record(self):
        user = self._staff('mirror.rider', '+96890000071')
        rider_group = self.env.ref('mart369_roles.group_rider')
        user.write({'group_ids': [(4, rider_group.id)]})
        rider = self._rider_of(user)
        self.assertEqual(len(rider), 1)
        self.assertTrue(rider.active)
        self.assertFalse(rider.on_duty, 'a role is not a shift')

        user.write({'group_ids': [(3, rider_group.id)]})
        self.assertFalse(rider.active, 'losing the role switches it off')

        user.write({'group_ids': [(4, rider_group.id)]})
        self.assertEqual(self._rider_of(user), rider, 'the same record comes back')
        self.assertTrue(rider.active)

    def test_no_phone_no_rider_record(self):
        user = self._staff('mirror.nophone')
        user.write({'group_ids': [(4, self.env.ref('mart369_roles.group_rider').id)]})
        self.assertFalse(self._rider_of(user))
