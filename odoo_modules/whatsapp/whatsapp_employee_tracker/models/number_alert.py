"""A number that is not connected any more (25 Nov 2026).

The owner numbers are told twice: when it is down, and when it is back. It is
looked at every minute, and once more some seconds later before it is told. The number's own person gets the steps once: only its link to us is
gone, WhatsApp on the phone still receives. Another connected number of the
same company sends, any of them. Nothing for a number turned off on purpose."""
import logging
import random
import time
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import config

_logger = logging.getLogger(__name__)

# Closed at two looks is down; one that is still trying is told after a minute.
AGAIN_SECONDS = 6
TRYING_SECONDS = 60
ON_PURPOSE = ('turned off', 'switched off', 'no WhatsApp number assigned')


def _digits(text):
    return ''.join(c for c in (text or '') if c.isdigit())


class OwnerNumber(models.Model):
    _inherit = 'whatsapp.owner.number'

    @api.constrains('phone')
    def _check_phone(self):
        for rec in self:
            if not 8 <= len(_digits(rec.phone)) <= 15:
                raise ValidationError(_("The phone number needs 8 to 15 digits, with the country code."))


class WhatsAppConfigAlert(models.Model):
    _inherit = 'whatsapp.config'

    alert_minutes = fields.Integer('Send after (minutes)', default=0,
                                   help="0: at once, within about a minute. A number that comes back earlier is not told.")

    alert_down = fields.Boolean('Tell the owners when a number is disconnected', default=True)
    alert_up = fields.Boolean('Tell the owners when it is connected again', default=True)
    alert_steps = fields.Boolean('Send the steps to the disconnected number', default=True)

    @api.constrains('alert_minutes')
    def _check_alert_minutes(self):
        for rec in self:
            if not 0 <= rec.alert_minutes <= 1440:
                raise ValidationError(_("Choose 0 to 1440 minutes."))

    @api.model
    def action_wa_owner_numbers(self):
        """The one page of this company, with the numbers it has already."""
        config = self.sudo().get_config()
        self.env['whatsapp.owner.number'].sudo().with_context(active_test=False).search([
            ('config_id', '=', False), ('company_id', 'in', [False, config.company_id.id])]).write({'config_id': config.id})
        return {'type': 'ir.actions.act_window', 'name': _("Owner Numbers"), 'res_model': 'whatsapp.config', 'res_id': config.id,
                'view_mode': 'form', 'views': [(self.env.ref('whatsapp_employee_tracker.view_wa_owner_config_form').id, 'form')]}


class WhatsAppSessionAlert(models.Model):
    _inherit = 'whatsapp.session'

    wa_was_connected = fields.Boolean(readonly=True, copy=False)
    wa_down_since = fields.Datetime('Not connected since', readonly=True, copy=False)
    wa_down_told = fields.Boolean(readonly=True, copy=False)

    @api.model
    def _cron_watch_numbers(self):
        """Every minute, only when somebody is to be told."""
        if not self.env['whatsapp.owner.number'].sudo().search_count([], limit=1):
            return
        sessions = self.sudo().search([('active', '=', True), ('authorized_number', '!=', False)])
        sessions._refresh_state(force=True)
        self._tell_about_numbers()
        if not config['test_enable']:
            self.env.cr.commit()
        if sessions.filtered(lambda s: s.wa_was_connected and s.status != 'connected' and not s.wa_down_told):
            time.sleep(0 if config['test_enable'] else AGAIN_SECONDS)
            sessions._refresh_state(force=True)
            self._tell_about_numbers()

    def _number_off(self, removed=False):
        super()._number_off(removed=removed)
        self.sudo().write({'wa_was_connected': False, 'wa_down_since': False, 'wa_down_told': False})

    @api.model
    def _tell_about_numbers(self):
        now = fields.Datetime.now()
        for session in self.sudo().search([('active', '=', True), ('authorized_number', '!=', False)]):
            if session.status == 'connected':
                told, down = session.wa_down_told, session.wa_down_since
                values = {'wa_was_connected': True, 'wa_down_since': False, 'wa_down_told': False}
                if any(session[name] != value for name, value in values.items()):
                    session._alert_write(values)
                if told and session._alert_on('alert_up'):
                    session._tell_owners(_(
                        "✅ *WhatsApp connected again*\n%(who)s\nConnected: %(at)s\nWas disconnected: %(long)s, since %(since)s",
                        who=session._alert_who(), at=session._alert_time(now), long=session._alert_long(now - down) if down else '-',
                        since=session._alert_time(down) if down else '-'))
                continue
            if not session.wa_was_connected:
                continue
            if any(text in (session.error_message or '') for text in ON_PURPOSE):
                if session.wa_down_since:
                    session._alert_write({'wa_down_since': False, 'wa_down_told': False})
                continue
            if not session.wa_down_since:
                session._alert_write({'wa_down_since': now})
            elif session._alert_owners() and not session.wa_down_told and now - session.wa_down_since >= session._alert_wait():
                if not session._alert_senders():
                    continue                # nobody can send now; the next round looks again
                session._alert_write({'wa_down_told': True})
                since = _("Since: %s", session._alert_time(session.wa_down_since))
                if session._alert_on('alert_down'):
                    session._tell_owners(_("⚠️ *WhatsApp disconnected*\n%(who)s\n%(since)s", who=session._alert_who(), since=since))
                if session._alert_on('alert_steps'):
                    session._tell_itself(since)

    def _alert_wait(self):
        """As long as the settings say; one that is still trying, a minute at least."""
        self.ensure_one()
        trying = TRYING_SECONDS if self.status == 'connecting' else 0
        return timedelta(seconds=max(trying, (self._alert_config().alert_minutes or 0) * 60))

    def _alert_config(self):
        self.ensure_one()
        return self.env['whatsapp.config'].sudo().search([('company_id', '=', (self.company_id or self.env.company).id)], limit=1)

    def _alert_on(self, name):
        """On as long as nobody has opened the page."""
        settings = self._alert_config()
        return settings[name] if settings else True

    def _alert_write(self, values):
        """Kept at once: what was sent is not sent again by a round that fails later."""
        self.write(values)
        self.env.flush_all()
        if not config['test_enable']:
            self.env.cr.commit()

    def _alert_who(self):
        self.ensure_one()
        card = self.env['wa.employee.session'].sudo().search([('session_id', '=', self.id), ('active', '=', True)], limit=1)
        number = self.env['whatsapp.connect'].sudo()._pretty(self.authorized_number) or self.name
        return (_("Employee: *%s*\n", card.employee_id.name) if card else '') + _("Number: *%s*", number)

    def _alert_time(self, when):
        zone = self._alert_zone()
        return pytz.utc.localize(when).astimezone(zone).strftime('%d %b %Y, %I:%M %p') + (' UTC' if zone is pytz.utc else '')

    def _alert_zone(self):
        """This database's own time: the company's, the administrator's, or that
        of the company's country when it has only one."""
        company = self.company_id or self.env.company
        admin = self.env.ref('base.user_admin', raise_if_not_found=False)
        country = pytz.country_timezones.get(company.country_id.code or '') or []
        for name in (company.partner_id.tz, admin and admin.tz, country[0] if len(country) == 1 else ''):
            if name in pytz.all_timezones_set:
                return pytz.timezone(name)
        return pytz.utc

    @api.model
    def _alert_long(self, time):
        minutes = int(time.total_seconds() // 60)
        if minutes < 60:
            return _("%s min", minutes)
        hours = _("%(h)s h %(m)s min", h=minutes // 60 % 24, m=minutes % 60)
        return _("%(d)s day(s) %(rest)s", d=minutes // 1440, rest=hours) if minutes >= 1440 else hours

    def _alert_owners(self):
        """Without one nothing is sent at all."""
        self.ensure_one()
        owners = self.env['whatsapp.owner.number'].sudo().search([('company_id', 'in', [False, self.company_id.id])])
        return [p for p in dict.fromkeys(_digits(o.phone) for o in owners) if p]

    def _alert_senders(self):
        """The other connected numbers of the company, in any order."""
        self.ensure_one()
        found = self.sudo().search([('active', '=', True), ('status', '=', 'connected'), ('use_whatsapp', '=', True),
                                    ('id', '!=', self.id), ('company_id', 'in', [False, self.company_id.id])])
        return self.browse(random.sample(found.ids, len(found)))

    def _alert_send(self, phone, text, senders):
        """From the first that can."""
        for sender in senders:
            if sender._policy_block(phone, text):
                continue
            try:
                with self.env.cr.savepoint():
                    sender._send_payload('sendText', {'number': phone, 'text': text, 'delay': 0, 'plain': True},
                                         phone, text, queue_on_failure=False)
                return True
            except UserError as err:
                _logger.info("WA Tracker: alert not sent from %s: %s", sender.name, str(err).split('\n')[0])
        _logger.warning("WA Tracker: alert about %s could not be sent", self.name)
        return False

    def _tell_owners(self, text):
        self.ensure_one()
        senders = self._alert_senders()
        if self.status == 'connected':
            senders |= self                 # the only one: it is back, it can say so
        for phone in self._alert_owners():
            # a number does not write to itself
            self._alert_send(phone, text, senders.filtered(lambda s: _digits(s.authorized_number) != phone))

    def _tell_itself(self, since):
        self.ensure_one()
        text = _("⚠️ *Your WhatsApp is disconnected from the %(company)s software*\n%(since)s\n\n*To connect again:*\n"
                 "1. Ask your manager to open WhatsApp Numbers in our software and press Scan again.\n"
                 "2. On this phone open WhatsApp > Linked devices.\n"
                 "3. Press Link a device and scan the QR code.", company=self.company_id.name or _("company"), since=since)
        self._alert_send(_digits(self.authorized_number), text, self._alert_senders())
