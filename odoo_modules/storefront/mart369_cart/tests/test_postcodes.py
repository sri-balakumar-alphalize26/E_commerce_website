"""Pincodes around a branch, for any country.

Where GeoNames has a list (India here) it is loaded once and read offline.
Anywhere else (Oman here) OpenStreetMap is asked point by point in the
background. Every answer carries a plain-words message for the screen. The
internet is never touched: downloads and OpenStreetMap are stood in for.
"""

import io
import zipfile
from unittest.mock import patch

import requests

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models.postcode import clean_pincode

DINDIGUL = (10.3673, 77.9803)
MUSCAT = (23.5880, 58.3829)

# GeoNames' columns: country, postcode, place, admin1 name, admin1 code,
# admin2 name, admin2 code, admin3 name, admin3 code, lat, lng, accuracy.
SAMPLE = '\n'.join('\t'.join(row) for row in (
    ('IN', '998401', 'Dindigul Fort', 'Tamil Nadu', '25', '', '', '', '', '10.3600', '77.9800', '4'),
    ('IN', '998401', 'Dindigul Bazaar', 'Tamil Nadu', '25', '', '', '', '', '10.3700', '77.9820', '4'),
    ('IN', '998402', 'Begambur', 'Tamil Nadu', '25', '', '', '', '', '10.3900', '77.9600', '4'),
    ('IN', '998410', 'Vedasandur', 'Tamil Nadu', '25', '', '', '', '', '10.5300', '77.9500', '4'),
    ('IN', 'bad', 'Nowhere', 'Tamil Nadu', '25', '', '', '', '', 'x', 'y', '4'),
))


def sample_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('IN.txt', SAMPLE)
    return buffer.getvalue()


@tagged('post_install', '-at_install')
class TestPostcodes(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        env['mart369.postcode'].search([]).unlink()
        env['mart369.postcode.scan'].search([]).unlink()
        # The real database may already cover these pincodes; not in here.
        env['mart369.service.area'].with_context(active_test=False).search([]).unlink()
        env['stock.warehouse'].search([]).write({
            'mart369_quick': False, 'mart369_lat': 0.0, 'mart369_lng': 0.0,
            'mart369_country_code': False, 'mart369_country_pin': False,
            'mart369_pincodes_found': False})
        cls.branch = env['stock.warehouse'].search(
            [('company_id', '=', env.company.id)], limit=1)
        cls.branch.write({'mart369_quick': True, 'mart369_quick_km': 5.0,
                          'mart369_maybe_km': 15.0, 'mart369_lat': DINDIGUL[0],
                          'mart369_lng': DINDIGUL[1]})
        cls.Postcode = env.registry['mart369.postcode']

    def _find(self):
        return self.env['stock.warehouse'].mart369_admin_find_pincodes(self.branch.id)

    # ------------------------------------------------------------ the list

    def test_a_country_list_is_read_once_with_post_offices_averaged(self):
        count = self.env['mart369.postcode']._mart369_load_geonames('IN', data=sample_zip())
        self.assertEqual(count, 3, 'the bad row is skipped')
        rec = self.env['mart369.postcode'].search([('postcode', '=', '998401')])
        self.assertAlmostEqual(rec.lat, 10.365, places=4)
        self.assertEqual(rec.place, 'Dindigul Fort')
        self.assertEqual(rec.source, 'geonames')

    def test_a_branch_shows_the_map_pincodes_only_after_find(self):
        """The list is the whole country; only the branch someone pressed
        "Find" on offers its pincodes, one branch at a time."""
        self.env['mart369.postcode']._mart369_load_geonames('IN', data=sample_zip())
        Area = self.env['mart369.service.area']

        def offered():
            known = Area.mart369_admin_known_pincodes()
            return {r['pincode'] for g in known['groups'] for r in g['pincodes']}

        self.assertNotIn('998401', offered(), 'not pressed yet: hidden')
        with patch.object(self.Postcode, '_mart369_country_at', return_value='IN'):
            self._find()
        self.assertIn('998401', offered())

    def test_a_pincode_far_from_the_pin_is_flagged(self):
        """The address form warns when the typed pincode and the map pin are
        more than 30 km apart; it never blocks."""
        Postcode = self.env['mart369.postcode']
        Postcode._mart369_load_geonames('IN', data=sample_zip())
        near = Postcode._mart369_pin_check('998401', *DINDIGUL)
        self.assertEqual((near['known'], near['match']), (True, True))
        far = Postcode._mart369_pin_check('998401', *MUSCAT)
        self.assertEqual((far['known'], far['match']), (True, False))
        self.assertGreater(far['km'], 1000)
        self.assertEqual(far['place'], 'Dindigul Fort')
        self.assertEqual(Postcode._mart369_pin_check('112', *MUSCAT), {'known': False},
                         'not on the list: nothing to say')
        self.assertEqual(Postcode._mart369_pin_check('998401', 0.0, 0.0), {'known': False},
                         'no pin: nothing to compare')

    def test_pick_on_map_opens_on_the_pincodes_area(self):
        Postcode = self.env['mart369.postcode']
        Postcode._mart369_load_geonames('IN', data=sample_zip())
        spot = Postcode._mart369_spot('998 401')
        self.assertTrue(spot['known'])
        self.assertAlmostEqual(spot['lat'], 10.365, places=3)
        self.assertEqual(spot['place'], 'Dindigul Fort')
        self.assertEqual(Postcode._mart369_spot('000000'), {'known': False})

    def test_an_empty_name_gives_each_pincode_its_own_place(self):
        self.env['mart369.postcode']._mart369_load_geonames('IN', data=sample_zip())
        Area = self.env['mart369.service.area']
        Area.mart369_admin_add_many('998401, 998402', {'deliver': True, 'name': ''})
        names = dict((a.pincode, a.name) for a in Area.search(
            [('pincode', 'in', ['998401', '998402'])]))
        self.assertEqual(names, {'998401': 'Dindigul Fort', '998402': 'Begambur'})
        # A typed name still applies to all of them.
        Area.mart369_admin_add_many('998410', {'deliver': True, 'name': 'Zz Typed'})
        self.assertEqual(Area.search([('pincode', '=', '998410')]).name, 'Zz Typed')

    def test_in_a_listed_country_the_answer_is_ready_at_once(self):
        with patch.object(self.Postcode, '_mart369_country_at', return_value='IN'), \
                patch.object(self.Postcode, '_mart369_get') as get:
            get.return_value.content = sample_zip()
            status = self._find()
        self.assertEqual(status['state'], 'done')
        self.assertEqual(status['source'], 'geonames')
        self.assertEqual(status['found'], 2, '998410 is about 18 km away, past 15')
        self.assertIn('Found 2 pincodes within 15 km', status['message'])
        # The tick list: ticked, under the branch, "from the map".
        known = self.env['mart369.service.area'].mart369_admin_known_pincodes()
        group = next(g for g in known['groups'] if g['branch'] == self.branch.name)
        rows = {r['pincode']: r for r in group['pincodes']}
        self.assertTrue(rows['998401']['near'])
        self.assertEqual(rows['998401']['addresses'], 0)
        self.assertIn('OpenStreetMap', known['credit'])
        # Asked again: the list is not downloaded twice.
        with patch.object(self.Postcode, '_mart369_get') as get:
            self.assertEqual(self._find()['found'], 2)
            get.assert_not_called()

    # ------------------------------------------------------ OpenStreetMap

    def _answers(self, lat, lng, zoom=16):
        """Oman's postal codes: 112 north of the branch, 113 south of it."""
        return {'country': 'OM', 'postcode': '112' if lat >= MUSCAT[0] else '113',
                'place': 'Ruwi'}

    def test_elsewhere_openstreetmap_is_asked_in_the_background(self):
        self.branch.write({'mart369_lat': MUSCAT[0], 'mart369_lng': MUSCAT[1],
                           'mart369_maybe_km': 4.0, 'mart369_quick_km': 4.0})
        Scan = self.env['mart369.postcode.scan']
        with patch.object(self.Postcode, '_mart369_country_at', return_value='OM'), \
                patch.object(self.Postcode, '_mart369_reverse', side_effect=self._answers), \
                patch.object(self.Postcode, '_mart369_pause') as pause:
            status = self._find()
            self.assertEqual(status['state'], 'running')
            total = status['total']
            self.assertGreater(total, 5)
            self.assertIn('checked 0 of %s spots' % total, status['message'])
            Scan._cron_postcode_scan(batch=2)
            status = self.env['stock.warehouse'].mart369_admin_find_status(self.branch.id)
            self.assertEqual(status['done'], 2)
            self.assertIn('checked 2 of', status['message'])
            self.assertIn('You can close this window', status['message'])
            self.assertEqual(pause.call_args.args, (1.0,), 'one question a second')
            # Pressing the button again does not start over.
            self.assertEqual(self._find()['done'], 2)
            Scan._cron_postcode_scan(batch=500)
        status = self.env['stock.warehouse'].mart369_admin_find_status(self.branch.id)
        self.assertEqual(status['state'], 'done')
        self.assertEqual(status['found'], 2)
        self.assertIn('Finished: checked all', status['message'])
        codes = set(self.env['mart369.postcode'].search(
            [('country_code', '=', 'OM')]).mapped('postcode'))
        self.assertEqual(codes, {'112', '113'})

    def test_a_network_error_waits_then_carries_on(self):
        self.branch.write({'mart369_lat': MUSCAT[0], 'mart369_lng': MUSCAT[1],
                           'mart369_maybe_km': 2.0, 'mart369_quick_km': 2.0})
        Scan = self.env['mart369.postcode.scan']
        broken = requests.ConnectionError('no route')
        with patch.object(self.Postcode, '_mart369_country_at', return_value='OM'), \
                patch.object(self.Postcode, '_mart369_pause'):
            self._find()
            with patch.object(self.Postcode, '_mart369_reverse', side_effect=broken):
                for __ in range(5):
                    Scan._cron_postcode_scan()
            status = self.env['stock.warehouse'].mart369_admin_find_status(self.branch.id)
            self.assertEqual(status['state'], 'failed')
            self.assertIn('Press the button again', status['message'])
            # The button carries on from where it stopped.
            with patch.object(self.Postcode, '_mart369_reverse', side_effect=self._answers):
                self.assertEqual(self._find()['state'], 'running')
                Scan._cron_postcode_scan(batch=500)
        self.assertEqual(
            self.env['stock.warehouse'].mart369_admin_find_status(self.branch.id)['state'],
            'done')

    def test_a_country_without_postcodes_says_so_plainly(self):
        self.branch.write({'mart369_lat': MUSCAT[0], 'mart369_lng': MUSCAT[1],
                           'mart369_maybe_km': 2.0, 'mart369_quick_km': 2.0})
        empty = {'country': 'QA', 'postcode': '', 'place': 'Doha'}
        with patch.object(self.Postcode, '_mart369_country_at', return_value='QA'), \
                patch.object(self.Postcode, '_mart369_reverse', return_value=empty), \
                patch.object(self.Postcode, '_mart369_pause'):
            self._find()
            self.env['mart369.postcode.scan']._cron_postcode_scan(batch=500)
        status = self.env['stock.warehouse'].mart369_admin_find_status(self.branch.id)
        self.assertEqual((status['state'], status['found']), ('done', 0))
        self.assertIn("map pin and the distance decide", status['message'])

    def test_a_branch_without_a_location_is_asked_for_one(self):
        self.branch.write({'mart369_lat': 0.0, 'mart369_lng': 0.0})
        with self.assertRaisesRegex(Exception, 'location'):
            self._find()

    # ------------------------------------------- "Find from the address"

    def _address(self, **values):
        partner = self.branch.partner_id or self.branch.company_id.partner_id
        partner.write(dict({'street': False, 'street2': False, 'city': False,
                            'zip': False, 'state_id': False,
                            'country_id': self.env.ref('base.in').id}, **values))
        return partner

    def _locate(self):
        return self.env['stock.warehouse'].mart369_admin_locate(self.branch.id)

    def test_find_from_the_address_uses_the_street_first(self):
        self.branch.write({'mart369_lat': 0.0, 'mart369_lng': 0.0})
        self._address(street='Zz 12 Fort Road', city='Dindigul', zip='998401')
        with patch.object(self.Postcode, '_mart369_search', return_value=DINDIGUL) as search:
            found = self._locate()
        self.assertEqual((found['lat'], found['lng'], found['level']),
                         (DINDIGUL[0], DINDIGUL[1], 'street'))
        self.assertIn('Zz 12 Fort Road', search.call_args.args[0]['q'])
        self.assertIn('Pick on map', found['message'])
        self.assertEqual(self.branch.mart369_lat, 0.0, 'nothing is saved by looking')

    def test_an_unknown_street_falls_back_to_our_own_pincode_list(self):
        """The pincode on the list answers without asking the internet."""
        self.env['mart369.postcode']._mart369_load_geonames('IN', data=sample_zip())
        self._address(street='Zz Nowhere Lane', city='Dindigul', zip='998401')
        with patch.object(self.Postcode, '_mart369_search', return_value=None) as search, \
                patch.object(self.Postcode, '_mart369_pause'):
            found = self._locate()
        self.assertEqual(found['level'], 'pincode')
        self.assertAlmostEqual(found['lat'], 10.365, places=3)
        self.assertEqual(search.call_count, 1, 'only the street was asked')

    def test_a_town_alone_is_found_and_said_to_be_rough(self):
        self._address(city='Dindigul')
        with patch.object(self.Postcode, '_mart369_search', return_value=DINDIGUL) as search:
            found = self._locate()
        self.assertEqual(found['level'], 'town')
        self.assertEqual(search.call_args.args[0]['countrycodes'], 'in')
        self.assertIn('middle', found['message'])

    def test_no_address_and_not_found_say_what_to_do(self):
        self._address()
        answer = self._locate()
        self.assertFalse(answer['found'], 'no address: the screen asks for one')
        self.assertIn('Type it below', answer['message'])
        self._address(city='Zz Atlantis')
        with patch.object(self.Postcode, '_mart369_search', return_value=None):
            with self.assertRaisesRegex(Exception, "couldn't find"):
                self._locate()

    def test_an_address_typed_in_the_window_is_saved_then_found(self):
        partner = self._address()
        with patch.object(self.Postcode, '_mart369_search', return_value=DINDIGUL):
            found = self.env['stock.warehouse'].mart369_admin_locate(
                self.branch.id, {'street': ' Zz 12 Fort Road ', 'city': 'Dindigul', 'zip': ''})
        self.assertTrue(found['found'])
        self.assertEqual(found['level'], 'street')
        self.assertEqual((partner.street, partner.city, partner.zip),
                         ('Zz 12 Fort Road', 'Dindigul', False), 'kept on the contact')
        with self.assertRaisesRegex(Exception, 'Type the street'):
            self.env['stock.warehouse'].mart369_admin_locate(
                self.branch.id, {'street': ' ', 'city': '', 'zip': ''})

    def test_find_from_the_address_offline_says_so(self):
        self._address(city='Dindigul')
        with patch.object(self.Postcode, '_mart369_search',
                          side_effect=requests.ConnectionError('offline')):
            with self.assertRaisesRegex(Exception, "couldn't reach OpenStreetMap"):
                self._locate()

    def test_a_shopper_cannot_look(self):
        shopper = self.env['res.users'].create({
            'name': 'Zz Postcode Shopper', 'login': 'zz_postcode_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        with self.assertRaises(AccessError):
            self.env['stock.warehouse'].with_user(shopper).mart369_admin_find_pincodes(
                self.branch.id)
        with self.assertRaises(AccessError):
            self.env['stock.warehouse'].with_user(shopper).mart369_admin_locate(
                self.branch.id)

    # --------------------------------------------- postcodes with letters

    def test_postcodes_with_letters_work_everywhere(self):
        self.assertEqual(clean_pincode(' sw1a 1aa '), 'SW1A1AA')
        self.assertEqual(clean_pincode('100-0001'), '1000001')
        Area = self.env['mart369.service.area']
        done = Area.mart369_admin_add_many('sw1a 1aa, K1A 0B1', {'deliver': True})
        self.assertEqual(done['added'], ['SW1A1AA', 'K1A0B1'])
        self.assertTrue(Area._mart369_check('SW1A 1AA')['ok'])
        self.assertTrue(Area._mart369_check('k1a0b1')['ok'])
        Area.create({'pincode': 'ec1', 'name': 'Zz London EC1'})
        self.assertEqual(Area._mart369_match('EC1V 9HX').pincode, 'EC1', '"starts with" still works')
