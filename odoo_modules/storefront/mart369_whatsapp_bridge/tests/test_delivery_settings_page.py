# -*- coding: utf-8 -*-
"""The WhatsApp side of the one-page Delivery settings (13 Nov 2026)."""
from odoo.tests import TransactionCase, tagged

from ..models.qe_link import THEIRS, qe_on

RUWI = (23.5880, 58.3829)


@tagged('post_install', '-at_install')
class TestDeliverySettingsWhatsapp(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.Page = env['mart369.delivery.settings.page']
        co = env['res.company'].create({'name': 'Zz Page WA'})
        cls.branch = env['stock.warehouse'].search([('company_id', '=', co.id)], limit=1)
        cls.branch.write({'mart369_lat': RUWI[0], 'mart369_lng': RUWI[1]})
        cls.shop = env['sa.delivery.shop'].create({'name': 'Zz Page Shop', 'warehouse_id': cls.branch.id,
                                                   'latitude': RUWI[0], 'longitude': RUWI[1]})

    def test_the_whatsapp_section_is_shown_and_saved(self):
        page = self.Page.mart369_settings_get()
        self.assertTrue(page['whatsapp'])
        row = next(b for b in page['branches'] if b['id'] == self.branch.id)
        self.assertEqual(row['shop'], 'yours')
        result = self.Page.mart369_settings_save({'whatsapp': {
            'quickHours': '6', 'cutoffHour': '18', 'expressDays': '2', 'autoCallRider': True, 'askReview': False}})
        self.assertTrue(result['ok'], result)
        s = self.env['sa.delivery.settings'].get_settings()
        self.assertEqual((s.quick_hours, s.cutoff_hour, s.express_days), (6, 18, 2))
        self.assertTrue(s.auto_call_rider_on_packed)
        self.assertFalse(s.ask_review)

    def test_a_wrong_cut_off_saves_nothing(self):
        before = self.env['sa.delivery.settings'].get_settings().quick_hours
        result = self.Page.mart369_settings_save({'whatsapp': {'quickHours': '9', 'cutoffHour': '30'}})
        self.assertFalse(result['ok'])
        self.assertEqual(result['errors'][0]['field'], 'cutoffHour')
        self.assertEqual(self.env['sa.delivery.settings'].get_settings().quick_hours, before)

    def test_the_branch_pin_lands_on_its_shop(self):
        result = self.Page.mart369_settings_save({'branches': [
            {'id': self.branch.id, 'pin': '25.2697, 55.3095', 'quick': True, 'quickKm': '4'}]})
        self.assertTrue(result['ok'], result)
        self.assertAlmostEqual(self.shop.latitude, 25.2697)
        self.assertAlmostEqual(self.shop.longitude, 55.3095)
        if 'qe_quick' in self.shop._fields:
            self.assertTrue(self.shop.qe_quick)
            self.assertEqual(self.shop.qe_quick_km, 4.0)

    def test_fees_reach_the_quick_express_rules_too(self):
        if not qe_on(self.env):
            self.skipTest('Quick / Express is not installed here')
        result = self.Page.mart369_settings_save({'fees': {'quick': {'fee': '21'}}})
        self.assertTrue(result['ok'], result)
        rule = self.env['sa.qe.delivery.rule'].with_context(active_test=False).search(
            [('mode', '=', THEIRS['quick'])], order='active desc, id', limit=1)
        self.assertEqual(rule.fee, 21.0)
        self.assertEqual(self.Page.mart369_settings_get()['fees']['quick']['fee'], 21.0)

    def test_the_slot_table_is_the_quick_express_list(self):
        """With Quick / Express, the checkout and the WhatsApp order page offer
        its slots: the page's slot table shows and saves those (17 Nov 2026)."""
        if not qe_on(self.env):
            self.skipTest('Quick / Express is not installed here')
        Slot = self.env['sa.qe.delivery.slot'].with_context(active_test=False)
        page = self.Page.mart369_settings_get()['slots']
        self.assertFalse(page['detail'], 'his slot has one name')
        self.assertEqual({r['id'] for r in page['rows']}, set(Slot.search([]).ids))
        rows = page['rows'] + [{'id': None, 'key': 'new-1', 'mode': 'all', 'kind': 'days',
                                'heading': 'Zz In 3 days', 'dayOffset': '3', 'fromHour': '0',
                                'toHour': '0', 'orderBefore': '24', 'fee': '5', 'capacity': '0',
                                'active': True}]
        result = self.Page.mart369_settings_save({'slots': rows})
        self.assertTrue(result['ok'], result)
        made = Slot.search([('name', '=', 'Zz In 3 days')])
        self.assertEqual((made.mode, made.kind, made.day_offset, made.fee),
                         (THEIRS['all'], 'days', 3, 5.0))
