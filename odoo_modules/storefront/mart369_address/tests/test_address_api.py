"""Delivery addresses over HTTP.

The test that matters most is test_a_customer_cannot_touch_another_s_address:
if that ever passes something it should not, one customer can read and edit
another's home address by guessing a number.
"""

import json
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}

NOMINATIM = {
    'address': {
        'road': 'Sandai Road',
        'suburb': 'Mettupatti',
        'city': 'Dindigul',
        'state': 'Tamil Nadu',
        'postcode': '624003',
        'country_code': 'in',
    },
}


@tagged('post_install', '-at_install')
class TestMart369AddressApi(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('auth_signup.invitation_scope', 'b2c')
        # The phone rule follows the company's country; pin it so the numbers
        # below mean what they say.
        self.env.company.partner_id.country_id = self.env.ref('base.in')
        # Real lookups are cached in the database; the pincode tests need the
        # stubbed India Post, not an answer left behind by a live one.
        self.env['ir.config_parameter'].sudo().search([('key', '=like', 'mart369.pin.%')]).unlink()

    # ------------------------------------------------------------- plumbing

    def _req(self, method, path, payload=None, follow=True):
        url = self.base_url() + path
        data = json.dumps(payload) if payload is not None else None
        return self.opener.request(method, url, data=data, headers=HEADERS,
                                   allow_redirects=follow)

    def _post(self, path, payload):
        return self._req('POST', path, payload)

    def _signup(self, name='Arun Kumar', email='arun@example.com', phone='9486020356'):
        return self._post('/369mart/auth/signup', {
            'name': name, 'email': email, 'password': 'secret123', 'phone': phone,
        })

    def _logout(self):
        self._post('/369mart/auth/logout', {})

    def _login(self, email):
        return self._post('/369mart/auth/login', {'login': email, 'password': 'secret123'})

    def _tn(self):
        return self.env['res.country.state'].search([
            ('country_id.code', '=', 'IN'), ('name', '=', 'Tamil Nadu')], limit=1)

    def _add(self, **over):
        payload = {
            'label': 'Home', 'name': 'Arun Kumar', 'phone': '9486020356',
            'line': '5/2 Sivamurugan Colony, 2nd Street', 'area': 'Sandai Road',
            'city': 'Dindigul 624003', 'state_id': self._tn().id,
        }
        payload.update(over)
        return self._post('/369mart/addresses', payload)

    # ---------------------------------------------------------------- basics

    def test_needs_an_account(self):
        """Signed out, the route sends you to the login page rather than
        answering. Redirects must not be followed here, or what comes back is
        the login page's own 200."""
        response = self._req('GET', '/369mart/addresses', follow=False)
        self.assertIn(response.status_code, (301, 302, 303, 401, 403))
        self.assertIn('/web/login', response.headers.get('Location', ''))

    def test_create_and_list(self):
        self._signup()
        created = self._add()
        self.assertEqual(created.status_code, 201, created.text)
        address = created.json()['address']
        self.assertEqual(address['label'], 'Home')
        self.assertEqual(address['city'], 'Dindigul 624003', 'city and pincode rejoined')
        self.assertEqual(address['phone'], '+919486020356', 'stored E.164')
        self.assertTrue(address['default'], 'the first address is the chosen one')

        listed = self._req('GET', '/369mart/addresses').json()
        self.assertEqual(len(listed['addresses']), 1)
        self.assertEqual(listed['selected'], address['id'])
        self.assertEqual(listed['phone']['dial'], '+91', 'the form is told what to show')
        self.assertEqual(listed['phone']['length'], 10)

    def test_city_and_pincode_are_stored_apart(self):
        """The app sends one string; Odoo keeps them separate so delivery and
        invoicing can use them."""
        self._signup()
        pid = self._add().json()['address']['id']
        record = self.env['res.partner'].browse(pid)
        self.assertEqual(record.city, 'Dindigul')
        self.assertEqual(record.zip, '624003')

    def test_update_and_archive(self):
        self._signup()
        pid = self._add().json()['address']['id']

        changed = self._req('PATCH', '/369mart/addresses/%s' % pid, {'line': 'New flat 9'})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()['address']['line'], 'New flat 9')

        gone = self._req('DELETE', '/369mart/addresses/%s' % pid)
        self.assertEqual(gone.status_code, 200)
        self.assertEqual(self._req('GET', '/369mart/addresses').json()['addresses'], [])
        self.assertFalse(self.env['res.partner'].browse(pid).active,
                         'archived, not deleted - past orders still point at it')

    def test_only_one_default(self):
        self._signup()
        first = self._add().json()['address']['id']
        second = self._add(label='Work', line='3rd Floor, Tech Park').json()['address']['id']

        listed = self._post('/369mart/addresses/%s/default' % second, {}).json()
        self.assertEqual(listed['selected'], second)
        flags = {a['id']: a['default'] for a in listed['addresses']}
        self.assertTrue(flags[second])
        self.assertFalse(flags[first], 'setting one default clears the other')

    # ------------------------------------------------- the Flipkart form

    def test_the_form_sends_every_line_apart(self):
        """The new form sends town and pincode apart, plus a landmark and a
        state; they come back apart too, and the one-line `city` still works
        for the screens that show it that way."""
        self._signup()
        created = self._add(city=None, town='Dindigul', pin='624003', landmark='Near the bus stand')
        self.assertEqual(created.status_code, 201, created.text)
        address = created.json()['address']
        self.assertEqual(address['town'], 'Dindigul')
        self.assertEqual(address['pin'], '624003')
        self.assertEqual(address['city'], 'Dindigul 624003')
        self.assertEqual(address['landmark'], 'Near the bus stand')
        self.assertEqual(address['state'], 'Tamil Nadu')
        self.assertEqual(address['state_id'], self._tn().id)
        record = self.env['res.partner'].browse(address['id'])
        self.assertEqual(record.country_id.code, 'IN', 'the shop country, so the phone rule follows it')

    def test_each_missing_line_names_its_field(self):
        self._signup()
        for key, field in (('name', 'name'), ('line', 'line'), ('area', 'area'),
                           ('state_id', 'state'), ('phone', 'phone')):
            refused = self._add(**{key: ''})
            self.assertEqual(refused.status_code, 400, key)
            self.assertEqual(refused.json()['field'], field, key)
        for over, field in (({'city': None, 'town': '', 'pin': '624003'}, 'town'),
                            ({'city': None, 'town': 'Dindigul', 'pin': ''}, 'pin'),
                            ({'city': None, 'town': 'Dindigul', 'pin': '62400'}, 'pin')):
            refused = self._add(**over)
            self.assertEqual(refused.status_code, 400, over)
            self.assertEqual(refused.json()['field'], field, over)
        self.assertEqual(self._req('GET', '/369mart/addresses').json()['addresses'], [])

    def test_a_state_from_another_country_is_refused(self):
        self._signup()
        elsewhere = self.env['res.country.state'].search([('country_id.code', '=', 'US')], limit=1)
        refused = self._add(state_id=elsewhere.id)
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()['field'], 'state')

    def test_edit_landmark_and_state(self):
        self._signup()
        pid = self._add().json()['address']['id']
        kerala = self.env['res.country.state'].search([
            ('country_id.code', '=', 'IN'), ('name', '=', 'Kerala')], limit=1)
        changed = self._req('PATCH', '/369mart/addresses/%s' % pid, {
            'landmark': 'Opposite the temple', 'state_id': kerala.id,
            'town': 'Kochi', 'pin': '682001'})
        self.assertEqual(changed.status_code, 200, changed.text)
        address = changed.json()['address']
        self.assertEqual((address['landmark'], address['state'], address['city']),
                         ('Opposite the temple', 'Kerala', 'Kochi 682001'))
        blanked = self._req('PATCH', '/369mart/addresses/%s' % pid, {'area': ''})
        self.assertEqual(blanked.json()['field'], 'area', 'an edit may not blank a required line')

    def test_form_meta_follows_the_shop_country(self):
        self._signup()
        meta = self._req('GET', '/369mart/addresses/form').json()
        self.assertEqual(meta['country']['code'], 'IN')
        self.assertEqual(meta['phone']['dial'], '+91')
        self.assertEqual(meta['pin_length'], 6)
        self.assertIn('Tamil Nadu', [s['name'] for s in meta['states']])

    def test_the_picked_country_sets_the_rules(self):
        """Amazon-style: the form's country decides the phone prefix, the
        states and the pincode length - not where the company sits."""
        self.env.company.partner_id.country_id = self.env.ref('base.om')
        # Signing up still follows the company's phone rule, so an Omani number.
        self.assertEqual(self._signup(phone='92123456').status_code, 201)
        india = self._req('GET', '/369mart/addresses/form').json()
        self.assertEqual(india['country']['code'], 'IN', 'a new address starts in India')
        self.assertEqual(india['phone']['dial'], '+91')
        self.assertIn('OM', [c['code'] for c in india['countries']])

        oman = self._req('GET', '/369mart/addresses/form?country=OM').json()
        self.assertEqual((oman['country']['code'], oman['phone']['dial'], oman['pin_length']),
                         ('OM', '+968', 0))

        # An Indian address with an Indian number, though the shop is in Oman.
        created = self._add()
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()['address']['phone'], '+919486020356')
        self.assertEqual(created.json()['address']['country_code'], 'IN')

        # Moving it to Oman: the number is now checked as Omani, and the
        # Indian state no longer fits.
        pid = created.json()['address']['id']
        refused = self._req('PATCH', '/369mart/addresses/%s' % pid, {
            'country_id': 'OM', 'phone': '9486020356', 'pin': '112', 'state_id': self._tn().id})
        self.assertEqual(refused.status_code, 400, refused.text)
        self.assertIn(refused.json()['field'], ('phone', 'state'))
        no_state = self._req('PATCH', '/369mart/addresses/%s' % pid, {
            'country_id': 'OM', 'phone': '92123456', 'pin': '112'})
        self.assertEqual(no_state.json()['field'], 'state', 'Oman has states; one must be picked')
        muscat = self.env['res.country.state'].search([('country_id.code', '=', 'OM')], limit=1)
        moved = self._req('PATCH', '/369mart/addresses/%s' % pid, {
            'country_id': 'OM', 'phone': '92123456', 'pin': '112', 'state_id': muscat.id})
        self.assertEqual(moved.status_code, 200, moved.text)
        address = moved.json()['address']
        self.assertEqual((address['country_code'], address['phone'], address['state_id']),
                         ('OM', '+96892123456', muscat.id))

    def test_pincode_fills_town_state_and_areas(self):
        class Reply:
            def raise_for_status(self):
                pass

            def json(self):
                return [{'Status': 'Success', 'PostOffice': [
                    {'Name': 'Begampur', 'District': 'Dindigul', 'State': 'Tamil Nadu'},
                    {'Name': 'Anna Nagar', 'District': 'Dindigul', 'State': 'Tamil Nadu'},
                ]}]

        target = 'odoo.addons.mart369_address.models.address_rules.requests.get'
        with patch(target, return_value=Reply()) as called:
            found = self._req('GET', '/369mart/pincode/624003').json()
            again = self._req('GET', '/369mart/pincode/624003').json()
        self.assertEqual(called.call_count, 1, 'the second answer comes from the cache')
        self.assertEqual(found, again)
        self.assertTrue(found['ok'])
        self.assertEqual(found['town'], 'Dindigul')
        self.assertEqual(found['state_id'], self._tn().id)
        self.assertEqual(found['areas'], ['Begampur', 'Anna Nagar'])

    def test_pincode_lookup_failing_leaves_the_form_manual(self):
        target = 'odoo.addons.mart369_address.models.address_rules.requests.get'
        with patch(target, side_effect=OSError('offline')):
            self.assertFalse(self._req('GET', '/369mart/pincode/600001').json()['ok'])
        self.assertFalse(self._req('GET', '/369mart/pincode/12').json()['ok'])

    # ------------------------------------------------------ the phone rule

    def test_a_landline_is_refused(self):
        self._signup()
        refused = self._add(phone='1234567890')
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()['field'], 'phone')

    def test_alternate_phone_is_optional_but_still_checked(self):
        self._signup()
        self.assertEqual(self._add(alt='').status_code, 201)
        bad = self._add(alt='12345')
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()['field'], 'alt')

    # ------------------------------------------------------------ ownership

    def test_a_customer_cannot_touch_another_s_address(self):
        """Two customers, one address each. Neither may read, change, delete or
        re-flag the other's by guessing its id."""
        self._signup(name='Arun Kumar', email='arun@example.com')
        arun_pid = self._add().json()['address']['id']
        self._logout()

        self._signup(name='Bala R', email='bala@example.com', phone='7092090133')
        bala_pid = self._add(name='Bala R', phone='7092090133').json()['address']['id']
        self.assertNotEqual(arun_pid, bala_pid)

        # Bala is signed in. Arun's address must be invisible to every route.
        self.assertNotIn(arun_pid, [a['id'] for a in
                                    self._req('GET', '/369mart/addresses').json()['addresses']])
        for method, path, payload in (
            ('PATCH', '/369mart/addresses/%s' % arun_pid, {'line': 'hijacked'}),
            ('DELETE', '/369mart/addresses/%s' % arun_pid, None),
            ('POST', '/369mart/addresses/%s/default' % arun_pid, {}),
        ):
            response = self._req(method, path, payload)
            self.assertEqual(response.status_code, 404,
                             '%s %s leaked another customer address' % (method, path))

        # And nothing actually changed.
        arun = self.env['res.partner'].browse(arun_pid)
        self.assertTrue(arun.active)
        self.assertNotEqual(arun.street, 'hijacked')

    # ------------------------------------------------------------ geocoding

    def test_reverse_geocode_maps_nominatim_onto_the_form(self):
        """Odoo blocks real OpenStreetMap calls in tests, so the reply is
        stubbed; what is checked is the mapping."""
        with patch(
            'odoo.addons.base_geolocalize.models.base_geocoder.BaseGeocoder'
            '._call_openstreetmap_reverse', return_value=NOMINATIM,
        ):
            response = self._post('/369mart/geocode/reverse', {'lat': 10.36, 'lng': 77.98})
        self.assertEqual(response.status_code, 200, response.text)
        found = response.json()
        self.assertEqual(found['city'], 'Dindigul')
        self.assertEqual(found['zip'], '624003')
        self.assertEqual(found['state'], 'Tamil Nadu')
        self.assertIn('Mettupatti', found['area'])

    def test_reverse_geocode_needs_coordinates(self):
        self.assertEqual(self._post('/369mart/geocode/reverse', {}).status_code, 400)
