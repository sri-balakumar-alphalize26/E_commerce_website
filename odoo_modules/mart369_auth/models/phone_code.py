"""The six-digit code that proves a mobile number belongs to whoever typed it.

The mobile number is a 369 Mart customer's identity - it is the only thing a
WhatsApp order and a website account have in common. So a number is never
trusted because someone typed it: a code goes to that number, and only the
person holding the phone can read it back.

How the code travels is not decided here. This module knows nothing about
WhatsApp; `res.partner._mart369_send_login_code` is the postman, and on its
own it answers "no way to send" (mart369_whatsapp_bridge plugs WhatsApp in).

Stored as an HMAC, never as the code: whoever can read this table still cannot
sign in as anyone. After the code is right, a one-time *token* is minted for
the sign-in itself (`res.users._check_credentials`), valid for a minute.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import api, fields, models

KEY_PARAM = 'mart369_auth.phone_code_key'
CODE_MINUTES = 10
TOKEN_SECONDS = 60
MAX_TRIES = 5
SENDS_PER_HOUR = 3          # per number
IP_SENDS_PER_HOUR = 10      # per caller


class Mart369PhoneCode(models.Model):
    _name = 'mart369.phone.code'
    _description = '369 Mart mobile number code'
    _order = 'id desc'

    phone = fields.Char(required=True, index=True, help="E.164, e.g. +96891234567.")
    purpose = fields.Selection([
        ('signin', 'Sign in'),
        ('signup', 'Sign up'),
        ('link', 'Add a number to an account'),
        ('staff', 'Staff sign in'),
    ], required=True, index=True)
    user_id = fields.Many2one(
        'res.users', ondelete='cascade',
        help="Who asked, for a signed-in customer adding a number.")
    ip = fields.Char(index=True)
    code_hash = fields.Char(required=True)
    expires_at = fields.Datetime(required=True)
    attempts = fields.Integer(default=0)
    used_at = fields.Datetime()
    token_hash = fields.Char(index=True)
    token_user_id = fields.Many2one('res.users', ondelete='cascade')
    token_expires_at = fields.Datetime()

    # ------------------------------------------------------------- hashing

    @api.model
    def _mart369_key(self):
        params = self.env['ir.config_parameter'].sudo()
        key = params.get_param(KEY_PARAM)
        if not key:
            key = secrets.token_hex(32)
            params.set_param(KEY_PARAM, key)
        return key.encode()

    @api.model
    def _mart369_digest(self, phone, secret):
        return hmac.new(self._mart369_key(), ('%s:%s' % (phone, secret)).encode(),
                        hashlib.sha256).hexdigest()

    # ------------------------------------------------------------ issuing

    @api.model
    def _mart369_wait_minutes(self, phone, ip=None):
        """Minutes until another code may go to this number (or from this
        caller), or 0."""
        now = fields.Datetime.now()
        hour_ago = now - timedelta(hours=1)
        Code = self.sudo()
        for domain, limit in (
                ([('phone', '=', phone)], SENDS_PER_HOUR),
                ([('ip', '=', ip)] if ip else None, IP_SENDS_PER_HOUR)):
            if domain is None:
                continue
            recent = Code.search(domain + [('create_date', '>=', hour_ago)],
                                 order='create_date asc')
            if len(recent) >= limit:
                oldest = recent[len(recent) - limit].create_date
                return max(1, int((oldest + timedelta(hours=1) - now)
                                  .total_seconds() // 60) + 1)
        return 0

    @api.model
    def _mart369_issue(self, phone, purpose, user=None, ip=None):
        """A fresh code for this number: (record, code). Earlier unused codes
        for the same number and purpose stop working."""
        Code = self.sudo()
        Code.search([('phone', '=', phone), ('purpose', '=', purpose),
                     ('used_at', '=', False)]).write({'used_at': fields.Datetime.now()})
        code = '%06d' % secrets.randbelow(1000000)
        record = Code.create({
            'phone': phone,
            'purpose': purpose,
            'user_id': user.id if user else False,
            'ip': ip or False,
            'code_hash': self._mart369_digest(phone, code),
            'expires_at': fields.Datetime.now() + timedelta(minutes=CODE_MINUTES),
        })
        return record, code

    # ----------------------------------------------------------- checking

    @api.model
    def _mart369_check(self, phone, purpose, code, user=None, spend=True):
        """(record, None) for the right code, else (record_or_empty, why).

        `spend=False` checks without using the code up - for the one case
        where a password must follow before the sign-in can finish.
        """
        domain = [('phone', '=', phone), ('purpose', '=', purpose),
                  ('used_at', '=', False)]
        if user:
            domain.append(('user_id', '=', user.id))
        record = self.sudo().search(domain, limit=1)
        if not record:
            return record, 'none'
        if record.expires_at < fields.Datetime.now():
            return record, 'expired'
        if record.attempts >= MAX_TRIES:
            return record, 'tries'
        code = ''.join(c for c in (code or '') if c.isdigit())
        if not hmac.compare_digest(record.code_hash,
                                   self._mart369_digest(phone, code)):
            record.attempts += 1
            return record, 'tries' if record.attempts >= MAX_TRIES else 'wrong'
        if spend:
            record.used_at = fields.Datetime.now()
        return record, None

    # ------------------------------------------------------- sign-in token

    def _mart369_token_for(self, user):
        """A one-minute, one-use token that signs `user` in."""
        self.ensure_one()
        token = secrets.token_urlsafe(32)
        self.sudo().write({
            'token_hash': self._mart369_digest('token', token),
            'token_user_id': user.id,
            'token_expires_at': fields.Datetime.now() + timedelta(seconds=TOKEN_SECONDS),
            'used_at': self.used_at or fields.Datetime.now(),
        })
        return token

    @api.model
    def _mart369_spend_token(self, user, token):
        if not token or not user:
            return False
        record = self.sudo().search([
            ('token_hash', '=', self._mart369_digest('token', token)),
            ('token_user_id', '=', user.id),
            ('token_expires_at', '>=', fields.Datetime.now()),
        ], limit=1)
        if not record:
            return False
        record.write({'token_hash': False, 'token_expires_at': False})
        return True

    # ------------------------------------------------------------ the vacuum

    @api.model
    def _cron_mart369_vacuum(self):
        self.sudo().search([
            ('create_date', '<', fields.Datetime.now() - timedelta(days=1)),
        ]).unlink()
