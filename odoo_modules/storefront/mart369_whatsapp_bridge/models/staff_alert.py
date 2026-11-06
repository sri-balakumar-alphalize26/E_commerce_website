"""Every staff sign-in, told to the Owner on WhatsApp.

The console can change the whole shop - prices, refunds, staff - so a
sign-in nobody expected should be noticed the moment it happens, not found
in a log weeks later. mart369_auth calls `_mart369_on_staff_sign_in` after
any staff sign-in (email + password, or mobile code + password); this sends
each active Owner who has a mobile the who, when, where and which device.

Sent through the same WhatsApp session as the sign-in codes. Never stops the
sign-in: a gateway that is down is logged and the staff member is let in.
"""

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


def _digits(phone):
    return ''.join(c for c in (phone or '') if c.isdigit())


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _mart369_on_staff_sign_in(self, how='password', ip='', agent=''):
        result = super()._mart369_on_staff_sign_in(how, ip, agent)
        if 'whatsapp.session' not in self.env:
            return result
        group = self.env.ref('mart369_roles.group_owner', raise_if_not_found=False)
        session = self.env['mart369.whatsapp'].sudo()._mart369_session()
        if not group or not session:
            return result
        owners = group.sudo().all_user_ids.filtered(
            lambda u: u.active and not u.share and _digits(u.partner_id.phone))
        if not owners:
            return result
        when = fields.Datetime.context_timestamp(
            self.with_context(tz=self.env.company.partner_id.tz or self.tz or 'Asia/Dubai'),
            fields.Datetime.now()).strftime('%d %b %Y, %I:%M %p')
        device = self._mart369_device(agent)
        body = _("\U0001F510 *369 Mart console sign-in*\n\n"
                 "%(name)s (%(login)s) signed in with %(how)s.\n"
                 "When: %(when)s\nWhere: %(ip)s%(device)s\n\n"
                 "Not expected? Change their password and the console address.",
                 name=self.name, login=self.login, how=how, when=when,
                 ip=ip or 'unknown address', device=(', ' + device) if device else '')
        for owner in owners:
            try:
                session.send_message(_digits(owner.partner_id.phone), body)
            except Exception:  # noqa: BLE001 - queued, offline: never block a sign-in
                _logger.info('bridge: staff sign-in alert to %s not sent', owner.login)
        return result
