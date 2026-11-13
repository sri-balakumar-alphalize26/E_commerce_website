"""The one-page Delivery settings (models/delivery_settings.py).

One Save writes everything or nothing; the hub rules are a grid of cells;
one area / many branches archives and brings back the routes; a person's
change stops the automatic setup from touching that branch.
"""

import json

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase

RUWI = (23.5880, 58.3829)
SOHAR = (24.3470, 56.7090)


@tagged('post_install', '-at_install')
class TestDeliverySettingsPage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Branch = env['stock.warehouse']
        Branch.search([]).write({'mart369_lat': 0.0, 'mart369_lng': 0.0, 'mart369_quick': False,
                                 'mart369_quick_km': 0.0, 'mart369_maybe_km': 0.0})
        env['mart369.hub.rule'].with_context(active_test=False).search([]).unlink()
        cls.ruwi = Branch.search([('company_id', '=', env['res.company'].create({'name': 'Zz Page Ruwi'}).id)], limit=1)
        cls.sohar = Branch.search([('company_id', '=', env['res.company'].create({'name': 'Zz Page Sohar'}).id)], limit=1)
        cls.ruwi.write({'mart369_lat': RUWI[0], 'mart369_lng': RUWI[1], 'mart369_auto': True})
        cls.sohar.write({'mart369_lat': SOHAR[0], 'mart369_lng': SOHAR[1]})
        cls.Rule = env['mart369.hub.rule'].with_context(active_test=False)
        cls.Page = env['mart369.delivery.settings.page']
        for mode, fee in (('quick', 30.0), ('all', 49.0)):
            rule = env['mart369.delivery.rule'].with_context(active_test=False).search([('mode', '=', mode)], limit=1)
            if not rule:
                env['mart369.delivery.rule'].create({'mode': mode, 'label': mode, 'eta': 'Soon', 'fee': fee})

    def _row(self, page, branch):
        return next(b for b in page['branches'] if b['id'] == branch.id)

    def test_the_page_has_every_section(self):
        page = self.Page.mart369_settings_get()
        for key in ('mode', 'branches', 'routes', 'fees', 'slots', 'whatsapp', 'areas', 'status', 'explain'):
            self.assertIn(key, page)
        self.assertEqual(page['mode'], 'one')
        self.assertIn('Not delivered', page['routes']['choices'])
        self.assertTrue(page['explain'])
        self.assertTrue(self._row(page, self.ruwi)['pin'])

    def test_save_all_writes_every_section_together(self):
        result = self.Page.mart369_settings_save({
            'mode': 'many',
            'branches': [{'id': self.ruwi.id, 'quick': True, 'quickKm': '6', 'maybeKm': '12'}],
            'fees': {'quick': {'fee': '25', 'freeAbove': '300'}},
            'slotsOn': False,
        })
        self.assertTrue(result['ok'], result)
        self.assertTrue(self.ruwi.mart369_quick)
        self.assertEqual(self.ruwi.mart369_quick_km, 6.0)
        self.assertFalse(self.ruwi.mart369_auto, "A person decided Quick: auto stops.")
        rule = self.env['mart369.delivery.rule'].with_context(active_test=False).search([('mode', '=', 'quick')], limit=1)
        self.assertEqual((rule.fee, rule.free_above), (25.0, 300.0))
        self.assertFalse(self.env.company.mart369_slots_on)
        # Many branches: the two pinned branches got their routes from the distance.
        rows = self.Rule.search([])
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(rows.mapped('auto')))
        self.assertEqual(result['page']['mode'], 'many')

    def test_one_wrong_value_saves_nothing_and_names_it(self):
        before = self.ruwi.mart369_quick_km
        result = self.Page.mart369_settings_save({
            'branches': [{'id': self.ruwi.id, 'quickKm': '9'}],
            'fees': {'quick': {'fee': '-5'}},
        })
        self.assertFalse(result['ok'])
        self.assertEqual(result['errors'][0]['section'], 'fees')
        self.assertEqual(result['errors'][0]['field'], 'fee')
        self.assertEqual(self.ruwi.mart369_quick_km, before, "Nothing was written.")

    def test_grid_cells_save_days_words_and_not_delivered(self):
        self.Page.mart369_settings_save({'mode': 'many'})
        result = self.Page.mart369_settings_save({'cells': [
            {'from': self.ruwi.id, 'to': self.sohar.id, 'arrives': 'Same day', 'cargo': False},
            {'from': self.sohar.id, 'to': self.ruwi.id, 'arrives': 'Not delivered'},
        ]})
        self.assertTrue(result['ok'], result)
        there = self.Rule.search([('from_hub_id', '=', self.ruwi.id), ('to_hub_id', '=', self.sohar.id)])
        self.assertEqual((there.arrives, there.days, there.auto), ('Same day', 0, False))
        back = self.Rule.search([('from_hub_id', '=', self.sohar.id), ('to_hub_id', '=', self.ruwi.id)])
        self.assertFalse(back.active)
        cells = {(c['from'], c['to']): c for c in result['page']['routes']['cells']}
        self.assertEqual(cells[(self.sohar.id, self.ruwi.id)]['arrives'], 'Not delivered')

    def test_words_not_on_the_list_are_kept(self):
        self.Rule.create({'from_hub_id': self.ruwi.id, 'to_hub_id': self.sohar.id,
                          'arrives': 'Tomorrow by noon', 'days': 1})
        result = self.Page.mart369_settings_save({'cells': [
            {'from': self.ruwi.id, 'to': self.sohar.id, 'arrives': 'Tomorrow by noon', 'cargo': True}]})
        self.assertTrue(result['ok'], result)
        row = self.Rule.search([('from_hub_id', '=', self.ruwi.id), ('to_hub_id', '=', self.sohar.id)])
        self.assertEqual((row.arrives, row.days, row.cargo), ('Tomorrow by noon', 1, True))

    def test_one_area_archives_the_routes_and_many_brings_them_back(self):
        typed = self.Rule.create({'from_hub_id': self.ruwi.id, 'to_hub_id': self.sohar.id,
                                  'arrives': 'Next day', 'days': 1})
        self.assertTrue(self.Page.mart369_settings_save({'mode': 'one'})['ok'])
        self.assertFalse(typed.active)
        self.assertEqual(self.Page.mart369_settings_get()['mode'], 'one')
        self.assertTrue(self.Page.mart369_settings_save({'mode': 'many'})['ok'])
        self.assertTrue(typed.active)
        self.assertEqual(typed.arrives, 'Next day')
        self.assertEqual(len(self.Rule.search([('active', '=', True)])), 2, "The missing way back is filled in.")

    def test_a_bad_pin_and_reach_are_refused(self):
        result = self.Page.mart369_settings_save({'branches': [
            {'id': self.ruwi.id, 'pin': 'not a place'},
            {'id': self.sohar.id, 'quickKm': '10', 'maybeKm': '5'}]})
        self.assertFalse(result['ok'])
        self.assertEqual({(e['row'], e['field']) for e in result['errors']},
                         {(self.ruwi.id, 'pin'), (self.sohar.id, 'maybeKm')})

    def test_saving_unchanged_values_changes_nothing(self):
        self.ruwi.write({'mart369_quick': True, 'mart369_quick_km': 5.0, 'mart369_maybe_km': 15.0})
        page = self.Page.mart369_settings_get()
        row = self._row(page, self.ruwi)
        result = self.Page.mart369_settings_save({'branches': [row]})
        self.assertTrue(result['ok'], result)
        self.assertTrue(self.ruwi.mart369_auto, "Nothing changed, so it is still the shop's to fill.")

    def test_only_delivery_editors(self):
        user = self.env['res.users'].create({
            'name': 'Zz Page Clerk', 'login': 'zz_page_clerk',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        with self.assertRaises(AccessError):
            self.Page.with_user(user).mart369_settings_get()
        with self.assertRaises(AccessError):
            self.Page.with_user(user).mart369_settings_save({'slotsOn': False})


@tagged('post_install', '-at_install')
class TestDeliverySettingsApi(HttpCase):

    def test_get_and_a_refused_save(self):
        self.authenticate('admin', 'admin')
        response = self.url_open('/369mart/admin/delivery/settings')
        self.assertEqual(response.status_code, 200)
        self.assertIn('branches', response.json())
        response = self.url_open('/369mart/admin/delivery/settings', data=json.dumps(
            {'fees': {'quick': {'fee': 'lots'}}}), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body['ok'])
        self.assertEqual(body['errors'][0]['field'], 'fee')
