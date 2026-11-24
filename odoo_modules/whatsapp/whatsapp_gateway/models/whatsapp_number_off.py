"""Turn a number off, on, or take it out of this database (23 Nov 2026).

Off: the session is archived and the panel neither sends nor forwards for it;
the phone stays linked. Removed: its key goes as well. Nothing is ever deleted
with a number - its groups, orders, customers and messages stay."""
import logging
import uuid
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class WhatsAppSessionOff(models.Model):
    _inherit = 'whatsapp.session'

    removed = fields.Boolean('Removed', readonly=True, copy=False)
    shown_number = fields.Char('Number', compute='_compute_shown_number')

    # ------------------------------------------------------------ one number, once
    def _same_number_on(self):
        """Another entry that is on with this one's number."""
        self.ensure_one()
        number = ''.join(c for c in (self.authorized_number or '') if c.isdigit())
        return self.sudo().search([('active', '=', True), ('id', '!=', self.id), ('authorized_number', '=', number)],
                                  limit=1) if number else self.browse()

    @api.constrains('authorized_number', 'active')
    def _check_number_once(self):
        for rec in self:
            other = rec._same_number_on() if rec.active else rec.browse()
            if other:
                raise ValidationError(_("%(number)s is already connected as \"%(name)s\". One number can be connected only once.",
                                        number=self.env['whatsapp.connect']._pretty(rec.authorized_number), name=other.name))

    @api.depends('authorized_number', 'phone_number', 'active')
    def _compute_shown_number(self):
        """One that is off shows its own phone, not the number another one has now."""
        for rec in self:
            number = rec.authorized_number or ''
            if not rec.active and number and rec._same_number_on():
                own = ''.join(c for c in (rec.sudo().phone_number or '') if c.isdigit())
                number = own if own and own != number else ''
            rec.shown_number = (self.env['whatsapp.connect']._pretty(number) or number) if number else False

    def _check_number_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only an administrator can do this."))

    def _ask_number(self, do):
        self.ensure_one()
        self._check_number_admin()
        wizard = self.env['whatsapp.number.off'].create({'session_id': self.id, 'do': do})
        names = {'off': _("Turn off"), 'on': _("Turn on"), 'remove': _("Remove")}
        return {'type': 'ir.actions.act_window', 'res_model': wizard._name, 'res_id': wizard.id,
                'view_mode': 'form', 'target': 'new', 'name': names[do]}

    def action_turn_off(self):
        return self._ask_number('off')

    def action_turn_on(self):
        return self._ask_number('on')

    def action_remove_number(self):
        return self._ask_number('remove')

    # ------------------------------------------------------------ hooks
    def _off_summary(self):
        """What is open on this number, for the question. ["4 groups on"]"""
        return []

    def _number_off(self, removed=False):
        """What goes off with it."""

    def _number_on(self):
        """What comes back with it. Returns notes for the administrator."""
        return []

    # ------------------------------------------------------------ doing it
    def _panel_self(self, do):
        """The panel's side, last of all: refused or not reached undoes ours."""
        self.ensure_one()
        try:
            return self._gateway_call('POST', '/v1/self', {'do': do}, timeout=(5, 20))
        except UserError as err:
            text = str(err.args[0] if err.args else err).strip().split('\n')[-1]
            if do == 'remove' and 'not registered' in text:
                return {}                   # taken out in the panel already
            if do == 'off' and 'number is turned off' in text:
                return {}                   # off there already: an earlier try that was not kept here
            if isinstance(err.__cause__, requests.exceptions.RequestException):
                text = _("the WhatsApp panel cannot be reached now. Try again in a few minutes.")
            raise UserError(_("Nothing was changed: %s", text)) from err

    def _refresh_state(self, force=False):
        """A number that is off is not asked about: it stays disconnected."""
        on = self.filtered('active')
        return super(WhatsAppSessionOff, on)._refresh_state(force=force) if on else False

    def _waiting_messages(self, before=None):
        domain = [('session_id', '=', self.id), ('direction', '=', 'outgoing'), ('status', '=', 'pending')]
        if before:
            domain.append(('create_date', '<', before))
        return self.env['whatsapp.message'].sudo().search(domain)

    def _turn_off(self):
        self.ensure_one()
        session = self.sudo()
        session._number_off()
        session.write({'active': False, 'status': 'disconnected'})
        self.env.flush_all()
        session._panel_self('off')
        _logger.info("WhatsApp: number %s turned off by %s", session.name, self.env.user.login)

    def _key_of_another(self):
        """One that is on has the very same key: this one needs its own."""
        self.ensure_one()
        key = self.sudo().gateway_api_key or ''
        token = lambda text: self._decode_setup_key(text)[1] or text  # noqa: E731
        return bool(key) and any(token(s.gateway_api_key or '') == token(key) for s in self.sudo().search(
            [('active', '=', True), ('id', '!=', self.id), ('gateway_api_key', '!=', False)]))

    def _turn_on(self):
        self.ensure_one()
        session = self.sudo()
        if not session.removed and not session._same_number_on() and session._key_of_another():
            session._waiting_messages().write({'status': 'failed'})
            Connect = self.env['whatsapp.connect']
            number = ''.join(c for c in (session.authorized_number or '') if c.isdigit())
            Connect._new_key(session, number, session.company_id or self.env.company)
            return []
        if session.removed:
            raise UserError(_("It was removed. Use Connect a number to add it again."))
        other = session._same_number_on()
        if other:
            raise UserError(_("%(number)s is already connected as \"%(name)s\". One number can be connected only once.",
                              number=self.env['whatsapp.connect']._pretty(session.authorized_number), name=other.name))
        session.write({'active': True})
        # what waited longer than a day says nothing true any more
        session._waiting_messages(before=fields.Datetime.now() - timedelta(days=1)).write({'status': 'failed'})
        notes = session._number_on() or []
        self.env.flush_all()
        session._panel_self('on')
        session._refresh_state(force=True)
        _logger.info("WhatsApp: number %s turned on by %s", session.name, self.env.user.login)
        return notes

    def _remove_number(self):
        self.ensure_one()
        session = self.sudo()
        session._number_off(removed=True)
        session._waiting_messages().write({'status': 'failed'})
        session.write({'active': False, 'removed': True, 'status': 'disconnected'})
        self.env.flush_all()
        session._panel_self('remove')
        session.write({'gateway_api_key': 'removed-%s' % uuid.uuid4().hex})
        _logger.info("WhatsApp: number %s removed by %s", session.name, self.env.user.login)

    def unlink(self):
        for session in self:
            if session.sudo()._has_history():
                raise UserError(_(
                    "'%s' has groups or messages, which would be deleted with it. Turn it off or remove it instead.",
                    session.name))
        return super().unlink()

    def _has_history(self):
        self.ensure_one()
        return bool(self.env['whatsapp.message'].sudo().search_count([('session_id', '=', self.id)], limit=1))


class WhatsAppNumberOff(models.TransientModel):
    _name = 'whatsapp.number.off'
    _description = 'Turn a WhatsApp number off, on or remove it'

    session_id = fields.Many2one('whatsapp.session', required=True, readonly=True, ondelete='cascade')
    do = fields.Selection([('off', 'Turn off'), ('on', 'Turn on'), ('remove', 'Remove')], required=True, readonly=True)
    number = fields.Char(compute='_compute_text')
    open_text = fields.Text(compute='_compute_text')

    @api.depends('session_id', 'do')
    def _compute_text(self):
        for rec in self:
            session = rec.session_id.sudo()
            rec.number = self.env['whatsapp.connect']._pretty(session.authorized_number) or session.name
            rec.open_text = ', '.join(session._off_summary()) if rec.do != 'on' else ''

    def action_do(self):
        self.ensure_one()
        session = self.session_id
        session._check_number_admin()
        notes = []
        if self.do == 'off':
            session._turn_off()
            text = _("%s is off. Its phone stays linked.", self.number)
        elif self.do == 'on':
            notes = session._turn_on() or []
            text = _("%s is on.", self.number)
        else:
            session._remove_number()
            text = _("%s was removed. Its groups, orders and messages stay.", self.number)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'warning' if notes else 'success', 'sticky': bool(notes), 'message': '\n'.join([text] + notes),
            'next': {'type': 'ir.actions.act_window_close'}}}
