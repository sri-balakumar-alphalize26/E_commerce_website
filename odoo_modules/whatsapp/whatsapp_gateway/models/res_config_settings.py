"""Settings > WhatsApp: which WhatsApp panel this database uses (26 Nov 2026).

There can be several WhatsApp panels, so the address is typed here, next to
the vendor's link token. Every module on top of whatsapp_gateway - WhatsApp and
Email, WA Tracker, Sales Automation - uses this one link; none has its own.

Pasting the token links at once (no button, no save first: a button on the
Settings page asks to save and reloads, which lost the token). Save links too,
when it has not been done. The token is kept (shown as *****), so a reload shows
the database linked rather than an empty field.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

P_URL = 'whatsapp_gateway.link_url'
P_TOKEN = 'whatsapp_gateway.link_token'
P_DONE = 'whatsapp_gateway.link_done'     # "url|token" that is linked


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    wa_panel_url = fields.Char(
        "WhatsApp panel address", config_parameter=P_URL,
        help="The address of the WhatsApp panel this database works with, as your vendor gave it, "
             "e.g. https://whatsapp.369ai.biz")
    wa_link_token = fields.Char(
        "Link token", config_parameter=P_TOKEN,
        help="Your vendor's link token from the WhatsApp panel. Paste it: the database links at once.")
    wa_linked = fields.Boolean(compute='_compute_wa_link')
    wa_link_text = fields.Char("Status", compute='_compute_wa_link')
    wa_number_count = fields.Integer("WhatsApp numbers", compute='_compute_wa_link')

    @api.depends('wa_panel_url', 'wa_link_token')
    def _compute_wa_link(self):
        Session = self.env['whatsapp.session'].sudo()
        info = Session._panel_link_info()
        count = Session.search_count([('active', '=', True)])
        for rec in self:
            rec.wa_linked = info['linked']
            rec.wa_link_text = info['text']
            rec.wa_number_count = count

    @staticmethod
    def _wa_norm(url):
        url = (url or '').strip().rstrip('/')
        return url if not url or '://' in url else 'https://' + url

    def _wa_needs_link(self):
        params = self.env['ir.config_parameter'].sudo()
        token = (self.wa_link_token or '').strip()
        if not token or not (self.wa_panel_url or '').strip():
            return False
        return params.get_param(P_DONE) != '%s|%s' % (self._wa_norm(self.wa_panel_url), token)

    def _wa_do_link(self):
        body = self.env['whatsapp.session'].sudo()._panel_link(self.wa_panel_url, self.wa_link_token)
        params = self.env['ir.config_parameter'].sudo()
        url = params.get_param(P_URL) or self._wa_norm(self.wa_panel_url)
        params.set_param(P_TOKEN, (self.wa_link_token or '').strip())
        params.set_param(P_DONE, '%s|%s' % (url, (self.wa_link_token or '').strip()))
        return body

    @api.onchange('wa_link_token', 'wa_panel_url')
    def _onchange_wa_link(self):
        """Paste the token (address filled): linked at once, status turns green."""
        if not self._wa_needs_link() or not self.env.user.has_group('base.group_system'):
            return None
        try:
            self._wa_do_link()
        except UserError as err:
            return {'warning': {'title': _("Not linked"), 'message': str(err.args[0] if err.args else err)}}
        self._compute_wa_link()
        return None

    def set_values(self):
        super().set_values()
        if self._wa_needs_link() and self.env.user.has_group('base.group_system'):
            self._wa_do_link()            # Save links too (a refusal stops the save and says why)

    def action_wa_link(self):
        """Link again (also after the vendor made a new token)."""
        self.ensure_one()
        body = self._wa_do_link()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _("Linked to the WhatsApp panel"),
                'message': _("%(db)s is linked to %(vendor)s. Next: connect a number.",
                             db=self.env.cr.dbname, vendor=body.get('vendor') or ''),
                'type': 'success', 'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'whatsapp_gateway.connect', 'name': _("Connect a number")},
            },
        }

    def action_wa_numbers(self):
        return self.env['ir.actions.actions']._for_xml_id('whatsapp_gateway.action_whatsapp_session')

    def action_wa_connect(self):
        return {'type': 'ir.actions.client', 'tag': 'whatsapp_gateway.connect', 'name': _("Connect a number")}

    def action_wa_help(self):
        return self.env['whatsapp.session']._wa_help_action(
            '/whatsapp_gateway/static/src/help/link_panel.html', _("Help - Link a new database"))
