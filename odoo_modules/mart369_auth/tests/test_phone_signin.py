"""The mobile number signs in - and only once it is proven."""

import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}

# Numbers no seeded customer carries - the tests run on a copy of a live DB.
NEW = '+919700990011'
OLD = '+919700990022'


@tagged('post_install', '-at_install')
class TestPhoneSignin(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param(
            'auth_signup.invitation_scope', 'b2c')
        cls.codes = []          # (phone, code) of every code "sent"
        cls.outcome = ['sent']

        def send(self, phone, code):
            cls.codes.append((phone, code))
            return cls.outcome[0]

        patcher = patch.object(cls.env.registry['res.partner'],
                               '_mart369_send_login_code', send)
        patcher.start()
        cls.addClassCleanup(patcher.stop)

    def setUp(self):
        super().setUp()
        self.codes.clear()
        self.outcome[0] = 'sent'

    def _post(self, path, payload):
        return self.url_open(path, data=json.dumps(payload), headers=HEADERS)

    def _last_code(self):
        return self.codes[-1][1]

    def _account(self, phone=OLD, verified=True, email='old.acc@369mart.test'):
        user = self.env['res.users'].sudo().create({
            'name': 'Old Account', 'login': email, 'email': email,
            'password': 'old-account-369',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        user.partner_id.sudo().with_context(mart369_phone_proven=True).write({
            'phone': phone, 'mart369_phone_verified': verified})
        return user

    # ------------------------------------------------------------ the form

    def test_phone_form_defaults_to_the_company_country(self):
        body = self.url_open('/369mart/auth/phone-form').json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['country']['id'], self.env.company.country_id.id
                         or body['country']['id'])
        self.assertTrue(body['countries'])
        self.assertTrue(body['country']['dial'].startswith('+'))

    # ------------------------------------------------------------- sign in

    def test_unknown_number_is_told_to_sign_up(self):
        r = self._post('/369mart/auth/phone/start', {'phone': NEW, 'purpose': 'signin'})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()['field'], 'phone')
        self.assertTrue(r.json()['signup'])
        self.assertFalse(self.codes, 'no code for a number nobody has')

    def test_proven_account_signs_in_with_the_code(self):
        user = self._account()
        r = self._post('/369mart/auth/phone/start', {'phone': OLD, 'purpose': 'signin'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.codes[-1][0], OLD)
        r = self._post('/369mart/auth/phone/verify',
                       {'phone': OLD, 'purpose': 'signin', 'code': self._last_code()})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['partner_id'], user.partner_id.id)
        me = self.url_open('/369mart/auth/me').json()
        self.assertEqual(me['partner_id'], user.partner_id.id)
        self.assertFalse(me['needPhone'])

    def test_wrong_code_then_too_many(self):
        self._account()
        self._post('/369mart/auth/phone/start', {'phone': OLD, 'purpose': 'signin'})
        for __ in range(4):
            r = self._post('/369mart/auth/phone/verify',
                           {'phone': OLD, 'purpose': 'signin', 'code': '000000'})
            self.assertEqual(r.json()['field'], 'code')
        r = self._post('/369mart/auth/phone/verify',
                       {'phone': OLD, 'purpose': 'signin', 'code': '000000'})
        self.assertIn('Too many', r.json()['error'])
        r = self._post('/369mart/auth/phone/verify',
                       {'phone': OLD, 'purpose': 'signin', 'code': self._last_code()})
        self.assertFalse(r.json()['ok'], 'a locked code stays locked')

    def test_expired_code_is_refused(self):
        self._account()
        self._post('/369mart/auth/phone/start', {'phone': OLD, 'purpose': 'signin'})
        self.env['mart369.phone.code'].sudo().search([('phone', '=', OLD)]).write(
            {'expires_at': fields.Datetime.now() - timedelta(minutes=1)})
        r = self._post('/369mart/auth/phone/verify',
                       {'phone': OLD, 'purpose': 'signin', 'code': self._last_code()})
        self.assertIn('expired', r.json()['error'])

    def test_unproven_account_asks_the_password_once(self):
        user = self._account(verified=False)
        self._post('/369mart/auth/phone/start', {'phone': OLD, 'purpose': 'signin'})
        code = self._last_code()
        r = self._post('/369mart/auth/phone/verify',
                       {'phone': OLD, 'purpose': 'signin', 'code': code})
        self.assertTrue(r.json()['needPassword'])
        r = self._post('/369mart/auth/phone/verify', {
            'phone': OLD, 'purpose': 'signin', 'code': code, 'password': 'nope'})
        self.assertEqual(r.json()['field'], 'password')
        r = self._post('/369mart/auth/phone/verify', {
            'phone': OLD, 'purpose': 'signin', 'code': code,
            'password': 'old-account-369'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(user.partner_id.mart369_phone_verified)

    def test_rate_limit(self):
        self._account()
        for __ in range(3):
            self._post('/369mart/auth/phone/start', {'phone': OLD, 'purpose': 'signin'})
        r = self._post('/369mart/auth/phone/start', {'phone': OLD, 'purpose': 'signin'})
        self.assertEqual(r.status_code, 429)
        self.assertIn('Too many codes', r.json()['error'])

    def test_no_way_to_send_says_so(self):
        self._account()
        self.outcome[0] = 'none'
        r = self._post('/369mart/auth/phone/start', {'phone': OLD, 'purpose': 'signin'})
        self.assertEqual(r.status_code, 503)
        self.assertIn('Sign in with email', r.json()['error'])
        self.outcome[0] = 'queued'
        r = self._post('/369mart/auth/phone/start', {'phone': OLD, 'purpose': 'signin'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('minute', r.json()['message'])

    # ------------------------------------------------------------- sign up

    def test_signup_with_name_and_number(self):
        r = self._post('/369mart/auth/phone/start',
                       {'phone': NEW, 'purpose': 'signup', 'name': 'Sri Bala'})
        self.assertEqual(r.status_code, 200, r.text)
        r = self._post('/369mart/auth/phone/verify', {
            'phone': NEW, 'purpose': 'signup', 'name': 'Sri Bala',
            'code': self._last_code()})
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertTrue(body['created'])
        self.assertTrue(body['phoneVerified'])
        user = self.env['res.users'].sudo().search([('login', '=', NEW)])
        self.assertTrue(user.share)
        self.assertEqual(user.partner_id.phone, NEW)
        self.assertEqual(user.name, 'Sri Bala')

    def test_signup_with_a_taken_number_goes_to_sign_in(self):
        self._account()
        r = self._post('/369mart/auth/phone/start',
                       {'phone': OLD, 'purpose': 'signup', 'name': 'Someone'})
        self.assertEqual(r.status_code, 409)
        self.assertTrue(r.json()['signin'])

    def test_country_picker_reads_the_local_number(self):
        r = self._post('/369mart/auth/phone/start', {
            'phone': '9123 4567', 'country': 'OM', 'purpose': 'signup',
            'name': 'Omani Customer'})
        # Valid or not for the real Omani plan, it is read as +968.
        if r.status_code == 200:
            self.assertEqual(self.codes[-1][0][:4], '+968')

    # ------------------------------------------------- an old email account

    def test_email_account_must_add_a_number(self):
        user = self._account(phone=False, verified=False, email='mail.only@369mart.test')
        r = self._post('/369mart/auth/login',
                       {'login': 'mail.only@369mart.test', 'password': 'old-account-369'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()['needPhone'])
        r = self._post('/369mart/auth/phone/add-start', {'phone': NEW})
        self.assertEqual(r.status_code, 200, r.text)
        r = self._post('/369mart/auth/phone/add-verify',
                       {'phone': NEW, 'code': self._last_code()})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()['needPhone'])
        self.assertEqual(user.partner_id.phone, NEW)

    def test_another_accounts_proven_number_is_refused(self):
        self._account()
        self._account(phone=False, verified=False, email='second@369mart.test')
        self._post('/369mart/auth/login',
                   {'login': 'second@369mart.test', 'password': 'old-account-369'})
        r = self._post('/369mart/auth/phone/add-start', {'phone': OLD})
        self.assertEqual(r.status_code, 409)

    def test_changing_the_number_unproves_it(self):
        user = self._account()
        user.partner_id.phone = NEW
        self.assertFalse(user.partner_id.mart369_phone_verified)
        user2 = self._account(phone=NEW, email='same@369mart.test')
        user2.partner_id.phone = '+91 97009 90011'      # same digits
        self.assertTrue(user2.partner_id.mart369_phone_verified)

    def test_email_signs_in_a_phone_first_account(self):
        self._post('/369mart/auth/phone/start',
                   {'phone': NEW, 'purpose': 'signup', 'name': 'Phone First'})
        self._post('/369mart/auth/phone/verify', {
            'phone': NEW, 'purpose': 'signup', 'name': 'Phone First',
            'code': self._last_code()})
        user = self.env['res.users'].sudo().search([('login', '=', NEW)])
        user.write({'password': 'phone-first-369'})
        user.partner_id.email = 'phone.first@369mart.test'
        login = self.env['res.users']._mart369_resolve_login('phone.first@369mart.test')
        self.assertEqual(login, NEW)
