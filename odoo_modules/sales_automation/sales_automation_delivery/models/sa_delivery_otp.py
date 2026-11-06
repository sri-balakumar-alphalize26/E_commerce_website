# -*- coding: utf-8 -*-
"""One-time codes for the two moments that need proof."""

import hashlib
import hmac
import logging
import secrets

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Long enough that guessing inside the attempt limit is hopeless, short enough
# to read out over a counter.
_DIGITS = 6
_TTL_MINUTES = 15
_MAX_ATTEMPTS = 5


class SaDeliveryOtp(models.Model):
    _name = 'sa.delivery.otp'
    _description = 'Delivery One-Time Code'
    _order = 'id desc'
    _rec_name = 'kind'

    picking_id = fields.Many2one(
        'stock.picking', string='Delivery', required=True,
        ondelete='cascade', index=True)
    kind = fields.Selection([
        ('pickup', 'Pickup'),
        ('delivery', 'Delivery'),
    ], required=True, index=True)

    # Never the digits themselves. An OTP is a password for one action, and a
    # database dump, a log line or a screenshot of a list view should not hand
    # somebody else's parcel over.
    code_hash = fields.Char('Code Hash', required=True, readonly=True,
                            groups='base.group_system')
    sent_to = fields.Char('Sent To', readonly=True)
    expires_on = fields.Datetime('Expires', required=True, readonly=True)
    attempts = fields.Integer('Failed Attempts', default=0, readonly=True)
    used_on = fields.Datetime('Used', readonly=True)
    active = fields.Boolean(default=True)

    state = fields.Selection([
        ('open', 'Waiting'),
        ('used', 'Used'),
        ('expired', 'Expired'),
        ('locked', 'Locked'),
    ], compute='_compute_state', store=False)

    def _compute_state(self):
        now = fields.Datetime.now()
        for otp in self:
            if otp.used_on:
                otp.state = 'used'
            elif otp.attempts >= _MAX_ATTEMPTS:
                otp.state = 'locked'
            elif otp.expires_on and otp.expires_on < now:
                otp.state = 'expired'
            else:
                otp.state = 'open'

    # ------------------------------------------------------------------
    # Making one
    # ------------------------------------------------------------------
    @api.model
    def _hash(self, picking_id, kind, code):
        """Salted with the job and the kind, so one hash is useless elsewhere."""
        secret = self.env['ir.config_parameter'].sudo().get_param(
            'database.secret') or 'sa-delivery'
        payload = '%s|%s|%s' % (picking_id, kind, (code or '').strip())
        return hashlib.sha256(
            ('%s|%s' % (secret, payload)).encode('utf-8')).hexdigest()

    @api.model
    def _issue(self, picking, kind):
        """A fresh code, voiding whatever was live before.

        Returns the plain digits - the *only* moment they exist outside the
        message - so the caller can send them and forget them.
        """
        self.sudo().search([('picking_id', '=', picking.id),
                            ('kind', '=', kind),
                            ('used_on', '=', False)]).write({'active': False})
        code = ''.join(str(secrets.randbelow(10)) for _n in range(_DIGITS))
        self.sudo().create({
            'picking_id': picking.id,
            'kind': kind,
            'code_hash': self._hash(picking.id, kind, code),
            'expires_on': fields.Datetime.add(fields.Datetime.now(),
                                              minutes=_TTL_MINUTES),
        })
        _logger.info("Delivery: issued a %s code for job %s", kind,
                     picking.sa_ref_code)
        return code

    # ------------------------------------------------------------------
    # Checking one
    # ------------------------------------------------------------------
    @api.model
    def _verify(self, picking, kind, code):
        """(ok, message). Never says which part was wrong."""
        code = (code or '').strip()
        otp = self.sudo().search([('picking_id', '=', picking.id),
                                  ('kind', '=', kind),
                                  ('active', '=', True)],
                                 order='id desc', limit=1)
        if not otp:
            return False, _("No code has been sent for this delivery yet.")
        if otp.used_on:
            return False, _("That code has already been used.")
        if otp.attempts >= _MAX_ATTEMPTS:
            return False, _("Too many wrong attempts. Ask for a new code.")
        if otp.expires_on and otp.expires_on < fields.Datetime.now():
            return False, _("That code has expired. Ask for a new one.")
        if not code.isdigit() or len(code) != _DIGITS:
            otp.sudo().attempts += 1
            return False, _("Invalid or expired code.")

        expected = otp.sudo().code_hash or ''
        if not hmac.compare_digest(expected,
                                   self._hash(picking.id, kind, code)):
            otp.sudo().attempts += 1
            _logger.info("Delivery: wrong %s code for job %s (%d/%d)", kind,
                         picking.sa_ref_code, otp.attempts, _MAX_ATTEMPTS)
            return False, _("Invalid or expired code.")

        otp.sudo().write({'used_on': fields.Datetime.now(), 'active': False})
        return True, _("Code verified.")
