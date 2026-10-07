"""Sign in and sign up with a mobile number and a six-digit code.

The mobile number is a 369 Mart customer's identity: it is the only thing a
WhatsApp order and a website account share. So:

* **Sign in** asks only for the number. A number nobody has is told to sign
  up. A number with an account - or a customer who only ever ordered on
  WhatsApp (mart369_whatsapp_bridge finds those) - gets a code, and the right
  code signs them in with everything already there.
* **Sign up** asks a name and the number. A number that already has an
  account is sent to sign in; a WhatsApp-only customer gets their login
  attached to the record that already holds their orders.
* **Add a number** is for a signed-in account that has none proven yet -
  the older email accounts. They cannot carry on until they do.

A typed number proves nothing, so nothing here trusts one. The single
exception to "the code is enough": an account whose number was only ever
typed, never proven. The person holding the phone may not be the person who
made that account, so the account's password is asked once.

Same shape as auth_api.py: bare JSON, {ok, error, field} on failure, posted
by the storefront's own server or the app.
"""

import logging
import re

from odoo import _, http
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.addons.auth_signup.models.res_partner import SignupError

_logger = logging.getLogger(__name__)

_EMAIL = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]{2,}$')
_POST = {'type': 'http', 'auth': 'public', 'methods': ['POST'], 'csrf': False, 'sitemap': False}
_GET = {'type': 'http', 'auth': 'public', 'methods': ['GET'], 'csrf': False, 'sitemap': False}
_USER_POST = dict(_POST, auth='user')

# What each send outcome tells the customer. Never a blank failure.
SENT = {
    'sent': "We sent a 6-digit code to your WhatsApp.",
    'queued': "Code sent. It may take a minute to arrive.",
}
NOT_SENT = {
    'offline': "Codes are delayed. Try again in a few minutes.",
    'none': "We can't send codes right now. Sign in with email, or try again later.",
}
CODE_WRONG = {
    'none': "Send a code first.",
    'expired': "That code has expired. Send a new one.",
    'tries': "Too many tries. Send a new code.",
    'wrong': "That code is not right.",
}
NO_ACCOUNT = "You don't have an account with this number. Please sign up."
HAS_ACCOUNT = "You already have an account with this number. Sign in instead."
TAKEN = "This number belongs to another 369 Mart account."


class Mart369PhoneApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:
            data = None
        return data if isinstance(data, dict) else {}

    def _fail(self, error, field=None, status=400, **extra):
        payload = dict(extra, ok=False, error=error)
        if field:
            payload['field'] = field
        return self._json(payload, status=status)

    def _ip(self):
        """The caller: the storefront server forwards the browser's address."""
        forwarded = request.httprequest.headers.get('X-Forwarded-For', '')
        return (forwarded.split(',')[0].strip()
                or request.httprequest.remote_addr or '')

    def _phone(self, body):
        """(e164, None) or (None, failure response)."""
        ok, phone = request.env['res.partner'].sudo()._mart369_check_mobile(
            body.get('phone'), region=body.get('country'))
        if not ok:
            return None, self._fail(phone, 'phone')
        return phone, None

    def _send(self, phone, purpose, user=None):
        """Issue and deliver a code. A response either way."""
        Code = request.env['mart369.phone.code'].sudo()
        ip = self._ip()
        wait = Code._mart369_wait_minutes(phone, ip)
        if wait:
            return self._fail(_("Too many codes. Try again in %s minutes.", wait),
                              'phone', status=429, retryInMinutes=wait)
        record, code = Code._mart369_issue(phone, purpose, user=user, ip=ip)
        try:
            outcome = request.env['res.partner'].sudo()._mart369_send_login_code(phone, code)
        except Exception:  # noqa: BLE001 - say so, never a blank 500
            _logger.exception('mart369: sending a sign-in code to %s failed', phone)
            outcome = 'offline'
        if outcome not in SENT:
            record.unlink()     # a code nobody received does not count
            return self._fail(NOT_SENT.get(outcome, NOT_SENT['none']), 'phone',
                              status=503, delivery=outcome)
        return self._json({'ok': True, 'phone': phone, 'delivery': outcome,
                           'message': SENT[outcome], 'resendIn': 60})

    def _code_failure(self, why):
        return self._fail(CODE_WRONG.get(why, CODE_WRONG['wrong']), 'code',
                          expired=why in ('expired', 'tries', 'none'))

    def _sign_in_with(self, record, user):
        token = record._mart369_token_for(user)
        request.session.authenticate(request.env, {
            'type': 'mart369_wa', 'login': user.login, 'token': token,
        })
        return request.env.user

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/auth/phone-form', **_GET)
    def phone_form(self, **kwargs):
        """The country picker's data, before anyone is signed in."""
        return self._json(request.env['res.partner'].sudo()._mart369_phone_form(
            kwargs.get('country')))

    @http.route('/369mart/auth/phone/start', **_POST)
    def start(self, **kwargs):
        """Body: {phone, country, purpose: 'signin' | 'signup', name?}."""
        body = self._body()
        purpose = body.get('purpose') if body.get('purpose') in ('signin', 'signup') else 'signin'
        phone, failure = self._phone(body)
        if failure:
            return failure
        partner, user = request.env['res.partner'].sudo()._mart369_phone_owner(phone)
        if purpose == 'signin' and not partner:
            return self._fail(NO_ACCOUNT, 'phone', status=404, signup=True)
        if purpose == 'signup':
            if user:
                return self._fail(HAS_ACCOUNT, 'phone', status=409, signin=True)
            if not partner and len((body.get('name') or '').strip()) < 2:
                return self._fail(_('Enter your name as it should appear on deliveries.'), 'name')
        return self._send(phone, purpose)

    @http.route('/369mart/auth/phone/verify', **_POST)
    def verify(self, **kwargs):
        """Body: {phone, country, code, purpose, name?, email?, referral?, password?}.

        Ok: the profile, plus {created, joined: {orders, addresses}}.
        """
        body = self._body()
        purpose = body.get('purpose') if body.get('purpose') in ('signin', 'signup') else 'signin'
        phone, failure = self._phone(body)
        if failure:
            return failure
        env = request.env
        Code = env['mart369.phone.code'].sudo()
        partner, user = env['res.partner'].sudo()._mart369_phone_owner(phone)

        # An account whose number was only ever typed: the code proves the
        # phone, the password proves the account.
        needs_password = bool(user and not partner.mart369_phone_verified)
        record, why = Code._mart369_check(phone, purpose, body.get('code'),
                                          spend=not needs_password)
        if why:
            return self._code_failure(why)
        if needs_password:
            password = body.get('password') or ''
            if not password:
                return self._fail(
                    _('Enter your password once to confirm this is your account.'),
                    'password', needPassword=True)
            try:
                user.with_user(user).sudo()._check_credentials(
                    {'type': 'password', 'login': user.login, 'password': password},
                    {'interactive': True})
            except AccessDenied:
                record.attempts += 1
                return self._fail(_('That password is not right.'), 'password',
                                  needPassword=True)

        created = False
        if not user:
            if not partner and purpose == 'signin':
                return self._fail(NO_ACCOUNT, 'phone', status=404, signup=True)
            user, failure = self._create_login(phone, partner, body)
            if failure:
                return failure
            created = True

        joined = user.partner_id.sudo()._mart369_prove_phone(phone)
        user = self._sign_in_with(record, user)
        if created:
            self._credit_referral(user, body.get('referral') or body.get('code_ref'))
        profile = user._mart369_profile()
        profile.update(created=created, joined=joined)
        return self._json(profile, status=201 if created else 200)

    def _create_login(self, phone, partner, body):
        """A storefront login whose login is the mobile number - on the
        WhatsApp customer's own record when there is one, so every order and
        address is already theirs. (user, None) or (None, response)."""
        Users = request.env['res.users'].sudo()
        name = (body.get('name') or '').strip()
        if not partner and len(name) < 2:
            return None, self._fail(
                _('Enter your name as it should appear on deliveries.'), 'name')
        email = (body.get('email') or '').strip().lower()
        if email:
            if not _EMAIL.match(email):
                return None, self._fail(_('Enter a valid email address.'), 'email')
            if Users.with_context(active_test=False).search_count(
                    ['|', ('login', '=ilike', email), ('email', '=ilike', email)]):
                return None, self._fail(
                    _('An account already uses this email.'), 'email', status=409)
        if Users.with_context(active_test=False).search_count([('login', '=', phone)]):
            return None, self._fail(HAS_ACCOUNT, 'phone', status=409, signin=True)
        values = {'login': phone}
        if partner:
            values['partner_id'] = partner.id
            # The chat's name stays unless it is the stack's placeholder.
            if name and (not partner.name or partner.name.startswith('WhatsApp Customer')):
                partner.name = name
            values['name'] = partner.name
        else:
            values['name'] = name
        try:
            user = Users._create_user_from_template(values)
        except (SignupError, ValueError) as exc:
            return None, self._fail(str(exc) or _('Could not create the account.'), 'phone')
        if email:
            user.partner_id.email = email
        return user, None

    def _credit_referral(self, user, code):
        """The inviter's reward - never a reason to refuse an account."""
        code = (code or '').strip()
        if not code or 'mart369.referral' not in request.env:
            return False
        try:
            return bool(request.env['mart369.referral']._mart369_on_signup(
                user.partner_id, code))
        except Exception:  # noqa: BLE001
            _logger.exception('mart369: crediting referral code %s failed', code)
            return False

    # ------------------------------------------- a signed-in account's number

    @http.route('/369mart/auth/phone/add-start', **_USER_POST)
    def add_start(self, **kwargs):
        """Body: {phone, country}. For an account with no proven number."""
        body = self._body()
        phone, failure = self._phone(body)
        if failure:
            return failure
        me = request.env.user
        __, owner = request.env['res.partner'].sudo()._mart369_phone_owner(phone)
        if owner and owner != me and owner.partner_id.mart369_phone_verified:
            return self._fail(TAKEN, 'phone', status=409)
        return self._send(phone, 'link', user=me)

    @http.route('/369mart/auth/phone/add-verify', **_USER_POST)
    def add_verify(self, **kwargs):
        """Body: {phone, country, code}. Ok: profile + {joined}."""
        body = self._body()
        phone, failure = self._phone(body)
        if failure:
            return failure
        me = request.env.user
        __, owner = request.env['res.partner'].sudo()._mart369_phone_owner(phone)
        if owner and owner != me and owner.partner_id.mart369_phone_verified:
            return self._fail(TAKEN, 'phone', status=409)
        record, why = request.env['mart369.phone.code'].sudo()._mart369_check(
            phone, 'link', body.get('code'), user=me)
        if why:
            return self._code_failure(why)
        joined = me.partner_id.sudo()._mart369_prove_phone(phone)
        profile = me._mart369_profile()
        profile['joined'] = joined
        return self._json(profile)

    # ------------------------------------------------------------ staff sign-in

    # The group every /369mart/admin/* route checks: the console's staff.
    STAFF_GROUP = 'website.group_website_designer'

    def _staff_by_phone(self, phone):
        """The active staff user whose own number this is, or nothing.

        Only internal users in the console's staff group: a customer's
        number never opens the console, and the customer sign-in above never
        looks at staff (`_mart369_phone_owner` reads `share=True` only).
        """
        users = request.env['res.users'].sudo().search([
            ('share', '=', False),
            '|', ('partner_id.phone', '=', phone),
            ('partner_id.phone_sanitized', '=', phone),
        ])
        return users.filtered(lambda u: u.has_group(self.STAFF_GROUP))[:1]

    @http.route('/369mart/auth/staff/phone/start', **_POST)
    def staff_start(self, **kwargs):
        """Body: {phone, country}. A code on WhatsApp for a staff number.

        A number that is no staff member's gets the same answer as one that
        is, and no code - so the page cannot be used to find out who works
        here. A real one goes through the customer side's own limits.
        """
        body = self._body()
        phone, failure = self._phone(body)
        if failure:
            return failure
        user = self._staff_by_phone(phone)
        if not user:
            return self._json({'ok': True, 'phone': phone, 'delivery': 'sent',
                               'message': SENT['sent'], 'resendIn': 60})
        return self._send(phone, 'staff', user=user)

    @http.route('/369mart/auth/staff/phone/verify', **_POST)
    def staff_verify(self, **kwargs):
        """Body: {phone, country, code, password}. Two checks: the code proves
        the phone, the password proves the person - a staff account can change
        the whole shop. Without a password the code is checked but not spent,
        and the answer asks for it (needPassword)."""
        body = self._body()
        phone, failure = self._phone(body)
        if failure:
            return failure
        user = self._staff_by_phone(phone)
        Code = request.env['mart369.phone.code'].sudo()
        record, why = Code._mart369_check(phone, 'staff', body.get('code'),
                                          user=user or None, spend=False)
        if why or not user:
            return self._code_failure(why or 'wrong')
        password = body.get('password') or ''
        if not password:
            return self._fail(_('Enter your password to finish signing in.'),
                              'password', needPassword=True)
        try:
            user.with_user(user).sudo()._check_credentials(
                {'type': 'password', 'login': user.login, 'password': password},
                {'interactive': True})
        except AccessDenied:
            record.attempts += 1
            return self._fail(_('That password is not right.'), 'password',
                              needPassword=True)
        user = self._sign_in_with(record, user)
        try:
            # The Owner hears of it on WhatsApp (mart369_whatsapp_bridge).
            user.sudo()._mart369_on_staff_sign_in(
                'mobile code and password', self._ip(),
                request.httprequest.headers.get('X-Mart-Device', ''))
        except Exception:  # noqa: BLE001 - never stops the sign-in itself
            _logger.exception('mart369: staff sign-in alert for %s failed', user.login)
        return self._json(user._mart369_profile())
