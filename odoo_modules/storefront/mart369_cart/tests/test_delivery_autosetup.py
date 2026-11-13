"""Delivery setting itself up (models/delivery_autosetup.py).

The one rule under test everywhere: it fills what is empty or missing and
never changes what a person set. The map is never asked for real - the
lookup is replaced, so these run without the internet.
"""

import json
from unittest.mock import patch

import requests

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase

from ..models.delivery_autosetup import route_for_km

RUWI = (23.5880, 58.3829)
SOHAR = (24.3470, 56.7090)        # about 190 km from Ruwi
SALALAH = (17.0151, 54.0924)      # about 850 km from Ruwi
SEEB = (23.6700, 58.1890)         # about 22 km from Ruwi


def spot(lat, lng):
    return {'found': True, 'lat': lat, 'lng': lng, 'level': 'street',
            'message': 'Found it.', 'name': '', 'country': ''}


@tagged('post_install', '-at_install')
class TestDeliveryAutoSetup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        # Whatever the database has must not answer for these tests.
        cls.old = env['stock.warehouse'].search([])
        cls.old.write({'mart369_quick': False, 'mart369_lat': 0.0, 'mart369_lng': 0.0,
                       'mart369_maybe_km': 0.0, 'mart369_quick_km': 0.0})
        env['mart369.hub.rule'].with_context(active_test=False).search([]).unlink()
        cls.Branch = env['stock.warehouse']
        cls.Rule = env['mart369.hub.rule'].with_context(active_test=False)
        cls.locate = type(env['mart369.postcode'])

    def _company(self, name, street='Way 3201', city='Muscat'):
        company = self.env['res.company'].create({'name': name})
        company.partner_id.write({'street': street, 'city': city})
        return company, self.Branch.search([('company_id', '=', company.id)], limit=1)

    def _run(self, answer):
        with patch.object(self.locate, '_mart369_locate', side_effect=answer) as asked:
            done = self.Branch._mart369_auto_setup()
        return done, asked

    # ------------------------------------------------------------ new branch

    def test_a_new_branch_finds_its_pin_and_switches_quick_on(self):
        _co, branch = self._company('Zz Auto Ruwi')
        self.assertTrue(branch.mart369_auto, "A new warehouse sets itself up.")
        done, asked = self._run(lambda partner: spot(*RUWI))
        self.assertEqual(asked.call_count, 1)
        self.assertAlmostEqual(branch.mart369_lat, RUWI[0])
        self.assertTrue(branch.mart369_quick)
        self.assertEqual(branch.mart369_quick_km, 5.0)
        self.assertEqual(branch.mart369_maybe_km, 15.0)
        self.assertTrue(branch._mart369_ready())
        self.assertTrue(any('Zz Auto Ruwi' in line for line in done))

        # Twice changes nothing, and the map is not asked again.
        done, asked = self._run(lambda partner: spot(*SOHAR))
        self.assertEqual(asked.call_count, 0)
        self.assertAlmostEqual(branch.mart369_lat, RUWI[0])
        self.assertFalse([line for line in done if 'Zz Auto Ruwi' in line])

    def test_a_branch_from_before_is_never_touched(self):
        branch = self.old[:1]
        self.assertFalse(branch.mart369_auto)
        _done, asked = self._run(lambda partner: spot(*RUWI))
        self.assertFalse(branch.mart369_lat or branch.mart369_lng)
        self.assertFalse(branch.mart369_quick)
        for call in asked.call_args_list:
            self.assertNotEqual(call.args[0], branch.partner_id)

    def test_a_person_deciding_quick_stops_the_automatic_setup(self):
        _co, branch = self._company('Zz Auto Hand')
        self.Branch.mart369_admin_save(branch.id, {'pin': '%s, %s' % RUWI})
        self.assertTrue(branch.mart369_auto, "A pin alone: Quick still comes on by itself.")
        self.Branch.mart369_admin_save(branch.id, {'quick': False, 'quickKm': 0})
        self.assertFalse(branch.mart369_auto)
        self._run(lambda partner: spot(*RUWI))
        self.assertFalse(branch.mart369_quick, "The person said no Quick.")

    def test_an_address_the_map_cannot_find_is_not_asked_again(self):
        _co, branch = self._company('Zz Auto Lost')

        def lost(partner):
            raise UserError("OpenStreetMap couldn't find it.")
        _done, asked = self._run(lost)
        self.assertEqual(asked.call_count, 1)
        self.assertIn("couldn't find", branch.mart369_auto_note)
        _done, asked = self._run(lost)
        self.assertEqual(asked.call_count, 0)
        checks = {c['key']: c for c in branch._mart369_setup_checks()}
        self.assertEqual(checks['pin']['state'], 'todo')

        # A new address is looked up again.
        branch.company_id.partner_id.street = 'Way 3202'
        _done, asked = self._run(lambda partner: spot(*RUWI))
        self.assertEqual(asked.call_count, 1)
        self.assertTrue(branch.mart369_quick)

    def test_no_internet_asks_again_next_time(self):
        _co, branch = self._company('Zz Auto Offline')

        def offline(partner):
            try:
                raise requests.ConnectionError('down')
            except requests.ConnectionError as exc:
                raise UserError("We couldn't reach OpenStreetMap.") from exc
        self._run(offline)
        self.assertFalse(branch.mart369_auto_tried)
        _done, asked = self._run(lambda partner: spot(*RUWI))
        self.assertEqual(asked.call_count, 1)
        self.assertTrue(branch.mart369_quick)

    def test_no_address_is_a_to_do_not_a_lookup(self):
        _co, branch = self._company('Zz Auto Bare', street='', city='')
        branch.partner_id.write({'street': False, 'city': False, 'zip': False})
        _done, asked = self._run(lambda partner: spot(*RUWI))
        self.assertEqual(asked.call_count, 0)
        checks = {c['key']: c for c in branch._mart369_setup_checks()}
        self.assertEqual(checks['address']['state'], 'todo')

    # ---------------------------------------------------------------- routes

    def test_route_bands(self):
        self.assertEqual(route_for_km(20), (1, 'Next day', False))
        self.assertEqual(route_for_km(190), (2, 'In 2-3 days', False))
        self.assertEqual(route_for_km(850), (3, 'In 3-4 days', True))

    def test_routes_are_not_added_while_the_hub_rules_are_off(self):
        _co, ruwi = self._company('Zz Route Ruwi')
        _co, sohar = self._company('Zz Route Sohar')
        self._run(lambda partner: spot(*(RUWI if 'Ruwi' in partner.display_name else SOHAR)))
        self.assertFalse(self.Rule.search([]), "A shop not using hubs is never switched over.")

    def test_missing_routes_are_added_and_existing_ones_kept(self):
        _co, ruwi = self._company('Zz Route Ruwi')
        _co, sohar = self._company('Zz Route Sohar')
        _co, salalah = self._company('Zz Route Salalah')
        _co, seeb = self._company('Zz Route Seeb')
        where = {'Ruwi': RUWI, 'Sohar': SOHAR, 'Salalah': SALALAH, 'Seeb': SEEB}
        for branch in (ruwi, sohar, salalah, seeb):
            branch.write({'mart369_lat': where[branch.company_id.name.split()[-1]][0],
                          'mart369_lng': where[branch.company_id.name.split()[-1]][1]})
        # Hub rules on, with one row somebody typed and one they archived.
        typed = self.Rule.create({'from_hub_id': sohar.id, 'to_hub_id': ruwi.id, 'days': 1,
                                  'arrives': 'Tomorrow'})
        said_no = self.Rule.create({'from_hub_id': salalah.id, 'to_hub_id': ruwi.id,
                                    'days': 5, 'active': False})
        self._run(lambda partner: spot(*RUWI))

        def row(a, b):
            return self.Rule.search([('from_hub_id', '=', a.id), ('to_hub_id', '=', b.id)])
        self.assertEqual(row(sohar, ruwi), typed)
        self.assertEqual(typed.arrives, 'Tomorrow')
        self.assertFalse(typed.auto)
        self.assertEqual(row(salalah, ruwi), said_no)
        self.assertFalse(said_no.active, "An archived route is somebody's no.")
        self.assertEqual(row(ruwi, sohar).arrives, 'In 2-3 days')
        self.assertTrue(row(ruwi, sohar).auto)
        self.assertEqual(row(ruwi, seeb).arrives, 'Next day')
        self.assertTrue(row(ruwi, salalah).cargo)
        self.assertEqual(len(self.Rule.search([])), 12, "Every pair of the four hubs.")

        # Changing a worked-out row makes it the person's.
        row(ruwi, sohar).days = 1
        self.assertFalse(row(ruwi, sohar).auto)
        checks = {c['key']: c for c in ruwi._mart369_setup_checks()}
        self.assertEqual(checks['routes']['state'], 'ok')

    # ------------------------------------------------------------- checklist

    def test_the_checklist(self):
        _co, branch = self._company('Zz Check Ruwi')
        status = self.Branch.mart369_setup_status()
        row = next(b for b in status['branches'] if b['id'] == branch.id)
        self.assertFalse(row['ready'])
        states = {c['key']: c['state'] for c in row['checks']}
        self.assertEqual(states['pin'], 'wait')
        self.assertEqual(states['quick'], 'wait')
        self.assertTrue({'fee_quick', 'fee_all', 'slots', 'hubs'} <= {c['key'] for c in status['shop']})

        with patch.object(self.locate, '_mart369_locate', side_effect=lambda p: spot(*RUWI)):
            status = self.Branch.mart369_setup_run()
        row = next(b for b in status['branches'] if b['id'] == branch.id)
        states = {c['key']: c['state'] for c in row['checks']}
        self.assertEqual(states['pin'], 'ok')
        self.assertEqual(states['quick'], 'ok')
        self.assertTrue(status['done'])

    def test_the_button_names_what_is_left_and_goes_there(self):
        """13 Nov 2026: "1 thing(s) still need you: see To do" led nowhere."""
        _co, branch = self._company('Zz Fix Ruwi')
        branch.write({'mart369_auto': False, 'mart369_quick': True, 'mart369_quick_km': 0.0,
                      'mart369_lat': RUWI[0], 'mart369_lng': RUWI[1]})
        with patch.object(self.locate, '_mart369_locate', side_effect=lambda p: spot(*RUWI)):
            action = branch.action_mart369_auto_setup()
        params = action['params']
        self.assertIn('Zz Fix Ruwi', params['message'])
        self.assertIn('reaches nobody', params['message'])
        after = params['next']
        if after.get('res_id'):
            self.assertEqual(after['res_id'], branch.id)
        else:
            self.assertIn(branch.id, after['domain'][0][2])

        # Fix it opens the screen that sets the reach: the Delivery desk.
        fix = branch.action_mart369_fix()
        self.assertEqual(fix.get('tag'), 'mart369_cart.delivery')

    def test_fix_it_for_a_missing_address_opens_the_address(self):
        _co, branch = self._company('Zz Fix Bare', street='', city='')
        branch.partner_id.write({'street': False, 'city': False, 'zip': False})
        fix = branch.action_mart369_fix()
        self.assertEqual(fix['res_model'], 'res.partner')
        self.assertEqual(fix['res_id'], branch.partner_id.id)

    def test_nothing_left_says_so_and_stays(self):
        _co, branch = self._company('Zz Fix Done')
        with patch.object(self.locate, '_mart369_locate', side_effect=lambda p: spot(*RUWI)):
            branch.action_mart369_auto_setup()
            action = branch.action_mart369_auto_setup()
        self.assertNotIn('Zz Fix Done:', action['params']['message'])

    def test_only_delivery_editors_see_the_checklist(self):
        user = self.env['res.users'].create({
            'name': 'Zz Clerk', 'login': 'zz_setup_clerk',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        with self.assertRaises(AccessError):
            self.Branch.with_user(user).mart369_setup_status()
        with self.assertRaises(AccessError):
            self.Branch.with_user(user).mart369_setup_run()


@tagged('post_install', '-at_install')
class TestDeliverySetupApi(HttpCase):

    def test_staff_get_the_checklist_and_a_shopper_is_refused(self):
        self.env['res.users'].create({
            'name': 'Zz Setup Shopper', 'login': 'zz_setup_shopper',
            'password': 'zz_setup_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        self.authenticate('zz_setup_shopper', 'zz_setup_shopper')
        for method, path in (('GET', '/369mart/admin/delivery/setup'),
                             ('POST', '/369mart/admin/delivery/setup/run')):
            response = self.url_open(path, data=None if method == 'GET' else '{}',
                                     headers={'Content-Type': 'application/json'},
                                     method=method)
            self.assertEqual(response.status_code, 403, path)

        self.authenticate('admin', 'admin')
        response = self.url_open('/369mart/admin/delivery/setup')
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.text)
        self.assertTrue(body['ok'])
        self.assertIn('branches', body)
        self.assertIn('shop', body)
