import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}


@tagged('post_install', '-at_install')
class TestMart369AuthApi(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('auth_signup.invitation_scope', 'b2c')

    def _post(self, path, payload):
        return self.url_open(path, data=json.dumps(payload), headers=HEADERS)

    def _signup(self, name='Arun Kumar', email='arun@example.com', password='secret123'):
        return self._post('/369mart/auth/signup', {'name': name, 'email': email, 'password': password})

    # ---------------------------------------------------------------- signup

    def test_signup_creates_a_portal_user(self):
        response = self._signup()
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['name'], 'Arun Kumar')
        self.assertEqual(body['email'], 'arun@example.com')

        user = self.env['res.users'].search([('login', '=', 'arun@example.com')])
        self.assertEqual(len(user), 1)
        self.assertTrue(user.share, 'A storefront account must be a portal user')
        self.assertFalse(user._is_internal(), 'A storefront account must not reach the backend')

    def test_signup_signs_the_new_user_in(self):
        self._signup()
        me = self.url_open('/369mart/auth/me')
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()['email'], 'arun@example.com')

    def test_signup_rejects_a_duplicate_email(self):
        self._signup()
        response = self._signup(name='Someone Else')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['field'], 'email')

    def test_signup_validates_like_the_storefront(self):
        for payload, field in (
            ({'name': 'A', 'email': 'a@example.com', 'password': 'secret123'}, 'name'),
            ({'name': 'Arun', 'email': 'not-an-email', 'password': 'secret123'}, 'email'),
            ({'name': 'Arun', 'email': 'a@example.com', 'password': 'short'}, 'password'),
        ):
            response = self._post('/369mart/auth/signup', payload)
            self.assertEqual(response.status_code, 400, payload)
            self.assertEqual(response.json()['field'], field)

    # ----------------------------------------------------------------- login

    def test_login_with_email_and_with_name(self):
        self._signup()
        self._post('/369mart/auth/logout', {})
        for identifier in ('arun@example.com', 'Arun Kumar', 'arun kumar'):
            response = self._post('/369mart/auth/login', {'login': identifier, 'password': 'secret123'})
            self.assertEqual(response.status_code, 200, identifier)
            self.assertEqual(response.json()['name'], 'Arun Kumar')
            self._post('/369mart/auth/logout', {})

    def test_login_rejects_a_wrong_password(self):
        self._signup()
        self._post('/369mart/auth/logout', {})
        response = self._post('/369mart/auth/login', {'login': 'arun@example.com', 'password': 'wrong-one'})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['ok'])

    def test_two_people_with_the_same_name(self):
        self._signup(email='arun1@example.com')
        self._post('/369mart/auth/logout', {})
        self.assertEqual(self._signup(email='arun2@example.com').status_code, 201)
        self._post('/369mart/auth/logout', {})

        by_name = self._post('/369mart/auth/login', {'login': 'Arun Kumar', 'password': 'secret123'})
        self.assertEqual(by_name.status_code, 409)
        self.assertIn('email', by_name.json()['error'].lower())

        by_email = self._post('/369mart/auth/login', {'login': 'arun2@example.com', 'password': 'secret123'})
        self.assertEqual(by_email.status_code, 200)

    # ------------------------------------------------------------ me / logout

    def test_me_is_401_when_signed_out(self):
        self.assertEqual(self.url_open('/369mart/auth/me').status_code, 401)

    def test_logout_ends_the_session(self):
        self._signup()
        self.assertEqual(self.url_open('/369mart/auth/me').status_code, 200)
        self.assertEqual(self._post('/369mart/auth/logout', {}).status_code, 200)
        self.assertEqual(self.url_open('/369mart/auth/me').status_code, 401)

    def test_forgot_never_reveals_accounts(self):
        for email in ('arun@example.com', 'nobody@example.com', ''):
            response = self._post('/369mart/auth/forgot', {'email': email})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['ok'])
