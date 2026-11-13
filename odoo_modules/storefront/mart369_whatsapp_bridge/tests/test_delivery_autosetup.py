# -*- coding: utf-8 -*-
"""The WhatsApp side of delivery setting itself up (13 Nov 2026): a delivery
shop per branch on the map, made once, with the branch's pin; a job leaves
from its warehouse's shop; nearest means the shop's own pin first."""
from odoo.tests import TransactionCase, tagged

RUWI = (23.5880, 58.3829)
SOHAR = (24.3470, 56.7090)


@tagged('post_install', '-at_install')
class TestDeliveryAutoShops(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.Branch = env['stock.warehouse']
        cls.Shop = env['sa.delivery.shop'].with_context(active_test=False)
        cls.Branch.search([]).write({'mart369_lat': 0.0, 'mart369_lng': 0.0,
                                     'mart369_quick': False})
        cls.ruwi_co = env['res.company'].create({'name': 'Zz Shop Ruwi'})
        cls.sohar_co = env['res.company'].create({'name': 'Zz Shop Sohar'})
        cls.ruwi = cls.Branch.search([('company_id', '=', cls.ruwi_co.id)], limit=1)
        cls.sohar = cls.Branch.search([('company_id', '=', cls.sohar_co.id)], limit=1)
        cls.ruwi.write({'mart369_lat': RUWI[0], 'mart369_lng': RUWI[1]})
        cls.sohar.write({'mart369_lat': SOHAR[0], 'mart369_lng': SOHAR[1]})

    def test_a_branch_on_the_map_gets_its_shop_once(self):
        self.Branch._mart369_auto_setup()
        shop = self.Shop.search([('warehouse_id', '=', self.ruwi.id)])
        self.assertEqual(len(shop), 1)
        self.assertTrue(shop.mart369_auto)
        self.assertAlmostEqual(shop.latitude, RUWI[0])
        self.Branch._mart369_auto_setup()
        self.assertEqual(len(self.Shop.search([('warehouse_id', '=', self.ruwi.id)])), 1)

        # Its pin follows the branch while nobody has set it by hand...
        self.ruwi.write({'mart369_lat': 23.6, 'mart369_lng': 58.4})
        self.Branch._mart369_auto_setup()
        self.assertAlmostEqual(shop.latitude, 23.6)
        # ...and stays where a person puts it.
        shop.write({'latitude': 23.7, 'longitude': 58.5})
        self.assertFalse(shop.mart369_auto)
        self.Branch._mart369_auto_setup()
        self.assertAlmostEqual(shop.latitude, 23.7)

    def test_a_shop_somebody_made_or_archived_is_kept(self):
        made = self.Shop.create({'name': 'Zz Hand Shop', 'warehouse_id': self.sohar.id})
        gone = self.Shop.create({'name': 'Zz Gone Shop', 'warehouse_id': self.ruwi.id,
                                 'active': False})
        self.Branch._mart369_auto_setup()
        self.assertEqual(self.Shop.search([('warehouse_id', '=', self.sohar.id)]), made)
        self.assertAlmostEqual(made.latitude, SOHAR[0], msg="An empty pin is filled.")
        self.assertEqual(made.name, 'Zz Hand Shop')
        self.assertEqual(self.Shop.search([('warehouse_id', '=', self.ruwi.id)]), gone)
        self.assertFalse(gone.active)
        checks = {c['key']: c['state'] for c in self.ruwi._mart369_setup_checks()}
        self.assertEqual(checks['shop'], 'off')

    def test_an_unpinned_branch_gets_no_shop(self):
        self.ruwi.write({'mart369_lat': 0.0, 'mart369_lng': 0.0})
        self.Branch._mart369_auto_setup()
        self.assertFalse(self.Shop.search([('warehouse_id', '=', self.ruwi.id)]))

    def test_a_job_leaves_from_its_warehouse_shop(self):
        self.Branch._mart369_auto_setup()
        ruwi_shop = self.Shop.search([('warehouse_id', '=', self.ruwi.id)])
        sohar_shop = self.Shop.search([('warehouse_id', '=', self.sohar.id)])
        # The customer is in Sohar, and Sohar's shop says it covers them...
        sohar_shop.service_areas = 'falaj'
        customer = self.env['res.partner'].create({
            'name': 'Zz Falaj', 'street': 'Falaj road', 'city': 'Sohar',
            'partner_latitude': SOHAR[0], 'partner_longitude': SOHAR[1]})
        # ...but the stock leaves Ruwi: Ruwi's shop takes the job.
        self.assertEqual(self.Shop._sa_pick_for(customer, warehouse=self.ruwi), ruwi_shop)
        # No warehouse: the delivery stack's own steps, unchanged.
        self.assertEqual(self.Shop._sa_pick_for(customer), sohar_shop)

    def test_nearest_measures_from_the_shop_pin(self):
        self.Branch._mart369_auto_setup()
        ruwi_shop = self.Shop.search([('warehouse_id', '=', self.ruwi.id)])
        sohar_shop = self.Shop.search([('warehouse_id', '=', self.sohar.id)])
        near_sohar = self.env['res.partner'].create({
            'name': 'Zz Near Sohar', 'partner_latitude': SOHAR[0] + 0.01,
            'partner_longitude': SOHAR[1]})
        self.assertEqual(self.Shop._sa_nearest(near_sohar, ruwi_shop | sohar_shop), sohar_shop)

    def test_the_checklist_asks_for_a_rider(self):
        self.Branch._mart369_auto_setup()
        Rider = self.env['sa.delivery.partner'].with_context(active_test=False)
        Rider.search([]).write({'active': False})
        checks = {c['key']: c['state'] for c in self.ruwi._mart369_setup_checks()}
        self.assertEqual(checks['shop'], 'ok')
        self.assertEqual(checks['riders'], 'todo')
        Rider.create({'name': 'Zz Rider', 'phone': '96890000001'})
        checks = {c['key']: c['state'] for c in self.ruwi._mart369_setup_checks()}
        self.assertEqual(checks['riders'], 'ok')
