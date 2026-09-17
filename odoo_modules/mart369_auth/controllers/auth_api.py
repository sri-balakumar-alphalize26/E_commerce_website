"""Sign up, sign in, sign out for the 369 Mart storefront.

Like home_api.py these are type='http' routes answering bare JSON. They are
POSTed to by the storefront's own server (app/api/auth/*), never straight
from a browser, so there is no cors='*' here: Odoo's session cookie stays
between the two servers.

Passwords are never handled by this module beyond passing them to Odoo:
auth_signup creates the user, res.users checks the password, and Odoo's own
login cooldown slows a guesser down.
"""

import re

from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.addons.auth_signup.models.res_partner import SignupError
from odoo.addons.mart369_auth.models.res_users import AMBIGUOUS

_EMAIL = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]{2,}$')

_POST = {'type': 'http', 'auth': 'public', 'methods': ['POST'], 'csrf': False, 'sitemap': False}
_GET = {'type': 'http', 'auth': 'public', 'methods': ['GET'], 'csrf': False, 'sitemap': False}

WRONG = 'Email or password is incorrect.'


class Mart369AuthApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:
            data = None
        return data if isinstance(data, dict) else {}

    def _fail(self, error, field=None, status=400):
        payload = {'ok': False, 'error': error}
        if field:
            payload['field'] = field
        return self._json(payload, status=status)

    def _sign_in(self, login, password):
        """Open the Odoo session. Raises AccessDenied on a bad password."""
        request.session.authenticate(request.env, {
            'type': 'password', 'login': login, 'password': password,
        })
        return request.env.user

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/auth/signup', **_POST)
    def signup(self, **kwargs):
        """Create a customer account, then sign it in.

        Body: {name, email, password, phone?}
        Ok:   {ok: true, name, email}
        Fail: {ok: false, error, field}  field is name | email | password
        """
        body = self._body()
        name = (body.get('name') or '').strip()
        email = (body.get('email') or '').strip().lower()
        password = body.get('password') or ''

        if len(name) < 2:
            return self._fail('Enter your name as it should appear on deliveries.', 'name')
        if not _EMAIL.match(email):
            return self._fail('Enter a valid email address.', 'email')
        if len(password) < 8:
            return self._fail('Use at least 8 characters.', 'password')
        # A mobile is optional at signup, but a wrong one is never accepted.
        ok, phone = request.env['res.partner']._mart369_check_mobile(
            body.get('phone'), required=False)
        if not ok:
            return self._fail(phone, 'phone')

        Users = request.env['res.users'].sudo()
        if Users.with_context(active_test=False).search_count([('login', '=ilike', email)]):
            return self._fail('An account already uses this email. Sign in instead.', 'email', status=409)

        try:
            Users.signup({'name': name, 'login': email, 'email': email, 'password': password})
        except (SignupError, ValueError) as exc:
            return self._fail(str(exc) or 'Could not create the account.', 'email')

        user = self._sign_in(email, password)
        if phone:
            user.partner_id.sudo().phone = phone
        return self._json(user._mart369_profile(), status=201)

    @http.route('/369mart/auth/login', **_POST)
    def login(self, **kwargs):
        """Body: {login, password}. login is the email or the full name."""
        body = self._body()
        password = body.get('password') or ''
        login = request.env['res.users']._mart369_resolve_login(body.get('login'))
        if login is None or not password:
            return self._fail(WRONG, status=400)
        if login is AMBIGUOUS:
            return self._fail('Several accounts use this name. Sign in with your email.', 'email', status=409)
        try:
            user = self._sign_in(login, password)
        except AccessDenied:
            return self._fail(WRONG, status=401)
        return self._json(user._mart369_profile())

    @http.route('/369mart/auth/logout', **_POST)
    def logout(self, **kwargs):
        request.session.logout(keep_db=True)
        return self._json({'ok': True})

    @http.route('/369mart/auth/me', **_GET)
    def me(self, **kwargs):
        user = request.env.user
        if not request.session.uid or user._is_public():
            return self._json({'ok': False}, status=401)
        return self._json(user._mart369_profile())

    @http.route('/369mart/auth/forgot', **_POST)
    def forgot(self, **kwargs):
        """Always answers ok, so the response never says whether an email
        has an account. Needs an outgoing mail server in Odoo to actually
        send anything."""
        email = (self._body().get('email') or '').strip()
        if email:
            try:
                request.env['res.users'].sudo().reset_password(email)
            except Exception:
                pass
        return self._json({'ok': True})
