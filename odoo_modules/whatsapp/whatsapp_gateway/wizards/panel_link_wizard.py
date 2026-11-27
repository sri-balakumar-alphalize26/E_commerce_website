"""Link this database to the WhatsApp panel with the vendor's link token (26 Nov 2026).

Each vendor has ONE link token in the panel (its page, "Odoo link token"); the
same token is pasted into every database of that vendor. It looks like
wl1_<base64url("<panel address>|<token>")>, so the panel's address comes with
it and nothing else is typed. The panel registers this database (or finds it)
and answers its link key. That key is kept in Odoo's system parameters - it is
not a number and not a session, so nothing is listed twice - and is only used
to ask the panel: add numbers, set their e-mail.

One link per database, shared by every module on top of whatsapp_gateway:
WhatsApp and Email, WA Tracker, Sales Automation. Linking again just reads the
same database's key; it never makes a second session.
"""

import base64

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

P_KEY = 'whatsapp_gateway.link_key'
P_VENDOR = 'whatsapp_gateway.link_vendor'
P_URL = 'whatsapp_gateway.link_url'


def decode_link_token(text):
    """(panel url, token) of a wl1_ link token, or (None, None)."""
    text = (text or '').strip()
    if not text.startswith('wl1_'):
        return None, None
    raw = text[4:]
    try:
        plain = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)).decode('utf-8')
    except (ValueError, UnicodeDecodeError):
        return None, None
    url, sep, token = plain.partition('|')
    if not sep or not url.startswith(('http://', 'https://')) or not token:
        return None, None
    return url.rstrip('/'), token


class WhatsappPanelLinkWizard(models.TransientModel):
    _name = 'whatsapp.panel.link.wizard'
    _description = 'Link this database to the WhatsApp panel'

    panel_url = fields.Char("WhatsApp panel address",
                            default=lambda self: self.env['ir.config_parameter'].sudo().get_param('whatsapp_gateway.link_url'))
    link_token = fields.Char("Link token", help="Copied from the WhatsApp panel: the vendor's page, Odoo link token. "
                                                "The same token for every database of the vendor.")
    linked = fields.Boolean(compute='_compute_linked')
    linked_text = fields.Char(compute='_compute_linked')
    this_odoo = fields.Char("This Odoo", compute='_compute_linked')

    @api.depends_context('uid')
    def _compute_linked(self):
        info = self.env['whatsapp.session'].sudo()._panel_link_info()
        for rec in self:
            rec.linked = info['linked']
            rec.linked_text = info['text']
            rec.this_odoo = '%s  /  %s' % (
                self.env['ir.config_parameter'].sudo().get_param('web.base.url', ''), self.env.cr.dbname)

    def _check_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_("Only an administrator can link this database."))

    def action_link(self):
        self.ensure_one()
        self._check_admin()
        body = self.env['whatsapp.session'].sudo()._panel_link(self.panel_url, self.link_token)
        self.link_token = False
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _("Linked to the WhatsApp panel"),
                'message': _("%(db)s is linked to %(vendor)s. Next: connect a number (scan its QR).",
                             db=self.env.cr.dbname, vendor=body.get('vendor') or ''),
                'type': 'success', 'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'whatsapp_gateway.connect', 'name': _("Connect a number")},
            },
        }

    def action_unlink(self):
        self.ensure_one()
        self._check_admin()
        params = self.env['ir.config_parameter'].sudo()
        for key in (P_KEY, P_VENDOR):
            params.set_param(key, False)
        return {'type': 'ir.actions.act_window_close'}

    def action_show_steps(self):
        return self.env['whatsapp.session']._wa_help_action(
            '/whatsapp_gateway/static/src/help/link_panel.html', _("Help - Link a new database"))

    def action_show_video(self):
        return self.env['whatsapp.session']._wa_help_action(
            '/whatsapp_gateway/static/src/help/link_panel.webm', _("Video - Link a new database"))
