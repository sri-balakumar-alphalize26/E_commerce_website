# -*- coding: utf-8 -*-
"""How a rider's phone proves who it is."""

import hashlib
import hmac
import logging
import secrets

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

_LOGIN_TTL_MINUTES = 10
# Long enough to stop a double-tap issuing two codes, short enough that a
# rider on a bad connection is not stranded. The app team picked the number.
_LOGIN_RESEND_SECONDS = 60
_TOKEN_DAYS = 30
_MAX_LOGIN_ATTEMPTS = 5


class SaDeliveryToken(models.Model):
    _name = 'sa.delivery.token'
    _description = 'Delivery App Session'
    _order = 'id desc'
    _rec_name = 'device'

    partner_id = fields.Many2one(
        'sa.delivery.partner', string='Rider', required=True,
        ondelete='cascade', index=True)
    token_hash = fields.Char('Token Hash', required=True, readonly=True,
                             index=True, groups='base.group_system')
    refresh_hash = fields.Char('Refresh Hash', readonly=True,
                               groups='base.group_system')
    device = fields.Char('Device')
    expires_on = fields.Datetime('Expires', required=True, readonly=True)
    last_seen = fields.Datetime('Last Seen', readonly=True)
    revoked = fields.Boolean('Revoked', default=False)
    push_platform = fields.Selection(
        [('android', 'Android'), ('ios', 'iOS'), ('web', 'Web')], 'Push Platform')
    push_token = fields.Char('Push Token', groups='base.group_system',
                             help="Device token registered by the rider app "
                                  "(/api/delivery/push/register). Nothing is "
                                  "sent to it yet.")

    # ------------------------------------------------------------------
    @api.model
    def _hash(self, value):
        secret = self.env['ir.config_parameter'].sudo().get_param(
            'database.secret') or 'sa-delivery'
        return hashlib.sha256(
            ('%s|%s' % (secret, value or '')).encode('utf-8')).hexdigest()

    @api.model
    def _issue(self, rider, device=''):
        """A new session. Returns the plain tokens, once."""
        token = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        self.sudo().create({
            'partner_id': rider.id,
            'token_hash': self._hash(token),
            'refresh_hash': self._hash(refresh),
            'device': (device or '')[:80],
            'expires_on': fields.Datetime.add(fields.Datetime.now(),
                                              days=_TOKEN_DAYS),
            'last_seen': fields.Datetime.now(),
        })
        _logger.info("Delivery API: %s logged in from %r", rider.name, device)
        return token, refresh

    @api.model
    def _rider_from_token(self, token):
        """The rider a bearer token belongs to, or an empty recordset.

        The single gate every endpoint goes through. Everything downstream is
        then filtered by the rider it returns - which is what keeps rider A out
        of rider B's jobs, and is tested by calling every endpoint with the
        wrong rider's token.
        """
        if not token:
            return self.env['sa.delivery.partner']
        row = self.sudo().search([
            ('token_hash', '=', self._hash(token)),
            ('revoked', '=', False),
            ('expires_on', '>', fields.Datetime.now()),
        ], limit=1)
        if not row:
            return self.env['sa.delivery.partner']
        # Cheap liveness, written at most once a minute so a busy app does not
        # write a row per request.
        if (not row.last_seen
                or (fields.Datetime.now() - row.last_seen).total_seconds() > 60):
            row.sudo().last_seen = fields.Datetime.now()
        rider = row.partner_id
        return rider if rider.active else self.env['sa.delivery.partner']

    @api.model
    def _refresh(self, refresh_token, device=''):
        row = self.sudo().search([
            ('refresh_hash', '=', self._hash(refresh_token)),
            ('revoked', '=', False),
        ], limit=1)
        if not row or not row.partner_id.active:
            return None
        # Rotated, not extended: a stolen refresh token is worth one use, and
        # the theft shows up as the real device being logged out.
        row.revoked = True
        return self._issue(row.partner_id, device or row.device)

    @api.model
    def _revoke(self, token):
        row = self.sudo().search(
            [('token_hash', '=', self._hash(token))], limit=1)
        if row:
            row.revoked = True
            return True
        return False


class SaDeliveryLoginCode(models.Model):
    _name = 'sa.delivery.login.code'
    _description = 'Delivery App Login Code'
    _order = 'id desc'
    _rec_name = 'phone'

    partner_id = fields.Many2one('sa.delivery.partner', string='Rider',
                                 required=True, ondelete='cascade')
    phone = fields.Char('Phone', required=True, index=True)
    code_hash = fields.Char('Code Hash', required=True, readonly=True,
                            groups='base.group_system')
    expires_on = fields.Datetime('Expires', required=True, readonly=True)
    attempts = fields.Integer(default=0, readonly=True)
    used_on = fields.Datetime('Used', readonly=True)
    active = fields.Boolean(default=True)

    @api.model
    @api.model
    def _cooldown_left(self, rider):
        """Seconds until this rider may be sent another code.

        Stops a double-tap issuing two codes and invalidating the first, which
        is how a rider ends up holding a code the server has already replaced.
        The code already sent stays valid for its full ten minutes, so nothing
        is lost by refusing to issue a second one.
        """
        last = self.sudo().search([('partner_id', '=', rider.id)],
                                  order='id desc', limit=1)
        if not last:
            return 0
        age = (fields.Datetime.now() - last.create_date).total_seconds()
        return max(0, int(_LOGIN_RESEND_SECONDS - age))

    def _issue(self, rider):
        """Send a six-digit code to the rider's own WhatsApp number."""
        self.sudo().search([('partner_id', '=', rider.id),
                            ('used_on', '=', False)]).write({'active': False})
        code = ''.join(str(secrets.randbelow(10)) for _n in range(6))
        self.sudo().create({
            'partner_id': rider.id,
            'phone': rider.phone,
            'code_hash': self.env['sa.delivery.token']._hash(
                '%s|%s' % (rider.id, code)),
            'expires_on': fields.Datetime.add(fields.Datetime.now(),
                                              minutes=_LOGIN_TTL_MINUTES),
        })
        return code

    @api.model
    def _verify(self, rider, code):
        row = self.sudo().search([('partner_id', '=', rider.id),
                                  ('active', '=', True)],
                                 order='id desc', limit=1)
        if not row or row.used_on:
            return False, _("Ask for a new code.")
        if row.attempts >= _MAX_LOGIN_ATTEMPTS:
            return False, _("Too many attempts. Ask for a new code.")
        if row.expires_on < fields.Datetime.now():
            return False, _("That code has expired.")
        expected = row.sudo().code_hash or ''
        got = self.env['sa.delivery.token']._hash(
            '%s|%s' % (rider.id, (code or '').strip()))
        if not hmac.compare_digest(expected, got):
            row.sudo().attempts += 1
            return False, _("Invalid or expired code.")
        row.sudo().write({'used_on': fields.Datetime.now(), 'active': False})
        return True, ''
