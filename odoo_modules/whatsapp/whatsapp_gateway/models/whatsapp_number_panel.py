"""What the panel does with a number, from Odoo (24 Nov 2026): restart, unlink the
phone, start over, the message footer, the activity, the name. Administrators
only, and only the number of the key: the panel decides by it."""
import logging

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

LINK = ('restart', 'unlink', 'reset')


class WhatsAppSessionPanel(models.Model):
    _inherit = 'whatsapp.session'

    def _panel_do(self, do, **more):
        """One thing about this number in the panel; its answer."""
        self.ensure_one()
        self._check_number_admin()
        try:
            return self.sudo()._gateway_call('POST', '/v1/self', dict(more, do=do), timeout=(5, 40)) or {}
        except UserError as err:
            raise UserError(_("Nothing was changed: %s", self.env['whatsapp.connect']._last_line(err))) from err

    def _panel_about(self, activity=False):
        self.ensure_one()
        self._check_number_admin()
        return self.sudo()._gateway_call('GET', '/v1/self%s' % ('?activity=1' if activity else ''), timeout=(5, 15)) or {}

    def action_restart_number(self):
        return self._ask_number('restart')

    def action_unlink_phone(self):
        return self._ask_number('unlink')

    def action_reset_number(self):
        return self._ask_number('reset')

    def _ask_number(self, do):
        if do not in LINK:
            return super()._ask_number(do)
        self.ensure_one()
        self._check_number_admin()
        wizard = self.env['whatsapp.number.off'].create({
            'session_id': self.id, 'do': do, 'shared': int(self._panel_about().get('shared_with') or 0)})
        names = {'restart': _("Restart"), 'unlink': _("Unlink phone"), 'reset': _("Full reset")}
        return {'type': 'ir.actions.act_window', 'res_model': wizard._name, 'res_id': wizard.id, 'view_mode': 'form',
                'target': 'new', 'name': names[do]}

    def _panel_dialog(self, what, name):
        about = self._panel_about(activity=what == 'activity')
        footer = about.get('footer') or {}
        wizard = self.env['whatsapp.number.panel'].create({
            'session_id': self.id, 'what': what, 'footer_on': bool(footer.get('on')), 'footer_name': footer.get('name') or '',
            'footer_phone': footer.get('phone') or '', 'used_text': _("%(used)s of %(may)s numbers", used=about.get('used') or 0,
                                                                      may=about.get('may_add') or 0),
            'activity': self.env['whatsapp.number.panel']._activity_table(about.get('activity') or [])})
        return {'type': 'ir.actions.act_window', 'res_model': wizard._name, 'res_id': wizard.id, 'view_mode': 'form',
                'target': 'new', 'name': name}

    def action_message_footer(self):
        self.ensure_one()
        return self._panel_dialog('footer', _("Message footer"))

    def action_panel_activity(self):
        self.ensure_one()
        return self._panel_dialog('activity', _("Activity"))

    def web_save(self, vals, specification, next_id=None):
        """A new name is the panel's as well; the panel not reached: only here."""
        result = super().web_save(vals, specification, next_id=next_id)
        if vals.get('name') and len(self) == 1 and self.active and self.sudo().gateway_api_key \
                and self.env.user.has_group('base.group_system'):
            try:
                self.sudo()._gateway_call('POST', '/v1/self', {'do': 'rename', 'label': self.name}, timeout=(3, 8))
            except UserError as err:
                _logger.info("WhatsApp: the panel keeps the old name of %s: %s", self.name, err)
        return result


class WhatsAppNumberDo(models.TransientModel):
    _inherit = 'whatsapp.number.off'

    do = fields.Selection(selection_add=[('restart', 'Restart'), ('unlink', 'Unlink phone'), ('reset', 'Full reset')],
                          ondelete={'restart': 'cascade', 'unlink': 'cascade', 'reset': 'cascade'})
    shared = fields.Integer(readonly=True)
    last_digits = fields.Char('Last 4 digits of the number', size=4)

    def action_do(self):
        self.ensure_one()
        if self.do not in LINK:
            return super().action_do()
        session = self.session_id
        number = ''.join(c for c in (session.sudo().authorized_number or '') if c.isdigit())
        if self.do != 'restart' and (len(number) < 4 or (self.last_digits or '').strip() != number[-4:]):
            raise UserError(_("Type the last 4 digits of %s first.", self.number))
        session._panel_do(self.do, sure=True)
        session.sudo()._refresh_state(force=True)
        if self.do == 'restart':
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'type': 'success', 'message': _("%s is connecting again.", self.number),
                'next': {'type': 'ir.actions.act_window_close'}}}
        return session.action_connect_screen()


class WhatsAppNumberPanel(models.TransientModel):
    _name = 'whatsapp.number.panel'
    _description = 'What the WhatsApp panel has about a number'

    session_id = fields.Many2one('whatsapp.session', required=True, readonly=True, ondelete='cascade')
    what = fields.Selection([('footer', 'Footer'), ('activity', 'Activity')], required=True, readonly=True)
    used_text = fields.Char(readonly=True)
    footer_on = fields.Boolean("Add it to messages")
    footer_name = fields.Char("Company name", size=60)
    footer_phone = fields.Char("Support number")
    activity = fields.Html(readonly=True)

    @api.model
    def _activity_table(self, rows):
        if not rows:
            return Markup('<p>%s</p>') % _("Nothing yet.")
        body = Markup()
        for row in rows:
            when = fields.Datetime.to_datetime(str(row.get('at') or '')[:19].replace('T', ' ') or False)
            when = fields.Datetime.context_timestamp(self, when).strftime('%d %b %H:%M:%S') if when else ''
            good = row.get('status') in ('sent', 'number on', 'number off', 'number added')
            body += Markup('<tr><td>%s</td><td>%s</td><td class="%s">%s</td><td>%s</td></tr>') % (
                when, escape(row.get('phone') or ''), 'text-success' if good else 'text-danger',
                escape(row.get('status') or ''), escape(row.get('detail') or ''))
        return Markup('<table class="table table-sm"><thead><tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr></thead>'
                      '<tbody>%s</tbody></table>') % (_("When"), _("To"), _("Result"), _("Why"), body)

    def action_save(self):
        self.ensure_one()
        phone = ''.join(c for c in (self.footer_phone or '') if c.isdigit())
        if phone and not 8 <= len(phone) <= 15:
            raise UserError(_("Support number: type it with the country code, 8 to 15 digits, or leave it empty."))
        self.session_id._panel_do('footer', on=self.footer_on, name=(self.footer_name or '').strip(), phone=phone)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': _("Saved for every number of this database."),
            'next': {'type': 'ir.actions.act_window_close'}}}
