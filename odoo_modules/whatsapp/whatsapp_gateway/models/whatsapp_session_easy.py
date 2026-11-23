"""A WhatsApp session that says what is missing, and refuses what would not work
(23 Nov 2026).

* The form lists the steps of the set-up, with one button for the next one.
  Other modules add theirs: whatsapp_employee_tracker the employee,
  sales_automation the groups.
* A key pasted in the form is checked with the panel when it is saved. Only
  there: a session made by code, or by "Connect a number", is as before.
* Archive and Unarchive of the gear menu are Turn off and Turn on. By itself the
  gear leaves the panel forwarding for a session nobody reads.
* What could not be sent for a day is not sent any more.
"""
import logging
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# A message that waited longer says nothing true any more. The rule of Turn on.
MAX_WAIT = timedelta(days=1)
NO_INSTANCE = ('', 'nexgenn-main')


class WhatsAppSessionEasy(models.Model):
    _inherit = 'whatsapp.session'

    setup_text = fields.Text(compute='_compute_setup', compute_sudo=True)
    setup_next = fields.Char(compute='_compute_setup', compute_sudo=True)
    waiting_count = fields.Integer(compute='_compute_waiting', compute_sudo=True)
    waiting_text = fields.Char(compute='_compute_waiting', compute_sudo=True)

    # ------------------------------------------------------------ what is missing
    def _setup_steps(self):
        """[(key, done, what it is, what to do)] in their order. Hook."""
        self.ensure_one()
        instance = self.instance_name or ''
        settings = bool(self.authorized_number or (instance not in NO_INSTANCE and not instance.startswith('pending-')))
        phone = _("Scan the QR with the right phone; another one was scanned.") if self.status == 'wrong_number' \
            else _("Scan the QR with the phone of this number.")
        return [
            ('key', bool(self.gateway_api_key), _("Key"), _("Paste the key from the WhatsApp panel in Setup Key and save.")),
            ('settings', settings, _("Number"), _("Press Load Settings.")),
            ('phone', self.status == 'connected', _("Phone connected"), phone),
        ]

    @api.depends('gateway_api_key', 'authorized_number', 'instance_name', 'status', 'active')
    def _compute_setup(self):
        for rec in self:
            steps = rec._setup_steps()
            todo = next((s for s in steps if not s[1]), None)
            rec.setup_next = todo[0] if todo else False
            lines = ['%s %s' % ('✓' if done else '○', label) for _key, done, label, _what in steps]
            rec.setup_text = '   '.join(lines) + ('\n' + _("Next: %s", todo[3]) if todo else '')

    @api.depends('status')
    def _compute_waiting(self):
        for rec in self:
            waiting = rec._waiting_messages() if isinstance(rec.id, int) else self.env['whatsapp.message']
            rec.waiting_count = len(waiting)
            oldest = min(waiting.mapped('create_date')) if waiting else False
            rec.waiting_text = _(
                "%(n)s message(s) wait to be sent, the oldest since %(when)s.", n=len(waiting),
                when=fields.Datetime.context_timestamp(self, oldest).strftime('%d %b %H:%M')) if waiting else ''

    # ------------------------------------------------------------ the form
    def onchange(self, values, field_names, fields_spec):
        if not self and not field_names:
            self = self.with_context(wa_new_form=True)
        return super().onchange(values, field_names, fields_spec)

    @api.model
    def default_get(self, fields):
        vals = super().default_get(fields)
        if self.env.context.get('wa_new_form'):
            # one mail account per database: the session that has it keeps it
            others = self.sudo().search([('active', '=', True), ('gateway_api_key', '!=', False)])
            for name in ('use_email', 'route_odoo_mail'):
                if vals.get(name) and any(others.mapped(name)):
                    vals[name] = False
        return vals

    def web_save(self, vals, specification, next_id=None):
        result = super().web_save(vals, specification, next_id=next_id)
        if not (vals.get('gateway_api_key') or '').strip():
            return result
        saved = self or self.browse(result[0]['id'])
        for session in saved:
            session._check_pasted_key()
        return (self.browse(next_id) if next_id else saved).web_read(specification)

    def _check_pasted_key(self):
        """The panel's word on a key somebody just pasted. Refused: nothing of
        it is kept. Not reached: kept, it is checked later."""
        self.ensure_one()
        try:
            config = self._fetch_panel_config()
        except UserError as err:
            if isinstance(err.__cause__, requests.exceptions.RequestException):
                self.env.user._bus_send('simple_notification', {
                    'type': 'warning', 'sticky': True,
                    'message': _("The key is saved but could not be checked: the WhatsApp panel cannot be reached now. "
                                 "Press Load Settings later.")})
                return
            raise UserError(_("The key was not saved: %s", self.env['whatsapp.connect']._last_line(err))) from err
        if self.use_email:
            self._sync_mail_from(config)
        if self.name == 'Default' and self.authorized_number:
            self.sudo().name = self.env['whatsapp.connect']._pretty(self.authorized_number)
        self._refresh_state(force=True)

    def _then_reload(self, action):
        """The form shows the answer, not what stood there before."""
        if isinstance(action, dict) and action.get('tag') == 'display_notification':
            action['params'].setdefault('next', {'type': 'ir.actions.client', 'tag': 'soft_reload'})
        return action

    def action_test_connection(self):
        return self._then_reload(super().action_test_connection())

    def action_fetch_config(self):
        return self._then_reload(super().action_fetch_config())

    # ------------------------------------------------------------ the gear menu
    def _unknown_to_panel(self, err):
        """The panel does not work with this key: nothing to tell it."""
        text = str(err)
        return not self.sudo().gateway_api_key or 'not registered' in text or 'wrong key' in text

    def action_archive(self):
        for session in self.filtered('active'):
            session._check_number_admin()
            try:
                with self.env.cr.savepoint():
                    session._turn_off()
            except UserError as err:
                if not session._unknown_to_panel(err):
                    raise
                session.sudo()._number_off()
                session.sudo().write({'active': False, 'status': 'disconnected'})

    def action_unarchive(self):
        for session in self.filtered(lambda s: not s.active):
            session._check_number_admin()
            session._turn_on()

    # ------------------------------------------------------------ what waits
    def _drop_waiting(self, before=None):
        self.ensure_one()
        waiting = self._waiting_messages(before=before)
        if waiting:
            waiting.write({'status': 'failed'})
            _logger.info("WhatsApp: %s waiting message(s) of %s are not sent any more", len(waiting), self.name)
        return len(waiting)

    def _flush_outbox(self, limit=50):
        self._drop_waiting(before=fields.Datetime.now() - MAX_WAIT)
        return super()._flush_outbox(limit=limit)

    def action_drop_waiting(self):
        self.ensure_one()
        self._check_number_admin()
        return self._then_reload({'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': _("%s message(s) will not be sent.", self._drop_waiting())}})
