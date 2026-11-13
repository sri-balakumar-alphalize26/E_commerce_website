# -*- coding: utf-8 -*-
"""The optional delivery slot on the WhatsApp order page (13 Nov 2026):
the storefront's backend slots, per-company on/off, no fee, quotations only."""
from odoo.tests import TransactionCase, tagged

from ..models.qe_link import qe_on


@tagged('post_install', '-at_install')
class TestPortalSlots(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        if qe_on(env):
            return
        Slot = env['mart369.delivery.slot']
        Slot.search([]).write({'active': False})
        for mode, key in (('quick', 'zz_q_tomorrow'), ('all', 'zz_a_tomorrow')):
            Slot.create({'mode': mode, 'kind': 'days', 'key': key, 'top': 'Tomorrow',
                         'sub': '8 - 10 AM', 'label': 'Tomorrow, 8 - 10 AM',
                         'from_hour': 8, 'to_hour': 10, 'day_offset': 1, 'fee': 49})
        partner = env['res.partner'].create({'name': 'Zz Slot Customer', 'street': '1 Road', 'city': 'Muscat'})
        product = env['product.product'].create({'name': 'Zz Slot Cable', 'list_price': 5.0, 'type': 'consu'})
        cls.order = env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1, 'price_unit': 5.0,
                                   'tax_ids': [(6, 0, [])]})],
        })
        env.company.mart369_slots_on = True

    def setUp(self):
        super().setUp()
        if qe_on(self.env):
            self.skipTest("the WhatsApp Quick/Express slots decide here")

    def _keys(self):
        return [c['key'] for c in self.order._sa_portal_slots()['chips']]

    def test_the_backend_slots_are_offered_without_their_fee(self):
        data = self.order._sa_portal_slots()
        self.assertTrue(data['chips'])
        self.assertTrue(set(self._keys()) & {'zz_q_tomorrow', 'zz_a_tomorrow'})
        self.assertFalse(any('fee' in c for c in data['chips']))
        self.assertEqual(data['chosen'], '')

    def test_picking_a_slot_books_it_and_never_changes_the_total(self):
        total = self.order.amount_total
        key = self._keys()[0]
        self.assertEqual(self.order._sa_portal_set_slot(key), '')
        self.assertEqual(self.order.mart369_slot_key, key)
        self.assertTrue(self.order.mart369_slot_label)
        self.assertEqual(self.order.amount_total, total)
        self.assertEqual(self.order._sa_portal_slots()['chosen'], key)
        # no preference clears it
        self.assertEqual(self.order._sa_portal_set_slot(''), '')
        self.assertFalse(self.order.mart369_slot_key)

    def test_an_unknown_slot_is_refused(self):
        self.assertTrue(self.order._sa_portal_set_slot('nope'))
        self.assertFalse(self.order.mart369_slot_key)

    def test_slots_switched_off_for_the_company_offer_nothing(self):
        self.order.company_id.mart369_slots_on = False
        self.assertEqual(self._keys(), [])
        self.assertTrue(self.order._sa_portal_set_slot('zz_q_tomorrow'))

    def test_a_confirmed_order_can_no_longer_pick(self):
        self.order.write({'state': 'sale'})
        self.assertEqual(self._keys(), [])
