"""Give one WhatsApp number (one company) its own e-mail account.

The account lives on the WhatsApp panel next to the number's key, so the SMTP
password is handed over once and never stored in Odoo. The panel tests the mail
server before it saves anything.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

PRESETS = {
    'gmail': ('smtp.gmail.com', 587, False),
    'zoho': ('smtp.zoho.com', 587, False),
    'zoho_in': ('smtp.zoho.in', 587, False),
    'office365': ('smtp.office365.com', 587, False),
    'yahoo': ('smtp.mail.yahoo.com', 587, False),
    'custom': ('', 587, False),
}


class WhatsappSessionEmailWizard(models.TransientModel):
    _name = 'whatsapp.session.email.wizard'
    _description = 'E-mail account of a WhatsApp number'

    session_id = fields.Many2one('whatsapp.session', required=True, readonly=True, ondelete='cascade')
    company_id = fields.Many2one(related='session_id.company_id', readonly=True)
    current_email = fields.Char(related='session_id.authorized_email', readonly=True)
    provider = fields.Selection([
        ('gmail', 'Gmail / Google Workspace'),
        ('zoho', 'Zoho Mail (.com)'),
        ('zoho_in', 'Zoho Mail (.in)'),
        ('office365', 'Microsoft 365 / Outlook'),
        ('yahoo', 'Yahoo Mail'),
        ('custom', 'Other mail server'),
    ], default='gmail', required=True)
    # not required here: "View steps" saves the form first, before it is filled
    from_email = fields.Char("Send from (e-mail address)")
    from_name = fields.Char("Sender name", help="What the customer sees, e.g. the company name.")
    host = fields.Char("SMTP server", default='smtp.gmail.com')
    port = fields.Integer("Port", default=587)
    secure = fields.Boolean("SSL from the start (port 465)")
    username = fields.Char("SMTP username", help="Usually the same as the e-mail address.")
    password = fields.Char("App password",
                           help="For Gmail / Zoho / Microsoft use an app password. Leave empty to keep the saved one.")

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        session = self.env['whatsapp.session'].browse(vals.get('session_id')).exists()
        if session:
            vals.setdefault('from_name', (session.company_id or self.env.company).name)
            if session.authorized_email:
                vals.setdefault('from_email', session.authorized_email)
                try:
                    have = session._gateway_call('GET', '/v1/email', timeout=(3, 10)) or {}
                except UserError:
                    have = {}
                if have.get('configured'):
                    vals.update({
                        'from_name': have.get('from_name') or vals.get('from_name'),
                        'host': have.get('host') or '', 'port': have.get('port') or 587,
                        'secure': bool(have.get('secure')), 'username': have.get('username') or '',
                    })
                    known = [k for k, v in PRESETS.items() if v[0] and v[0] == vals['host']]
                    vals['provider'] = known[0] if known else 'custom'
        return vals

    @api.onchange('provider')
    def _onchange_provider(self):
        host, port, secure = PRESETS.get(self.provider or 'custom', PRESETS['custom'])
        if self.provider != 'custom':
            self.host, self.port, self.secure = host, port, secure

    @api.onchange('from_email')
    def _onchange_from_email(self):
        if self.from_email and not self.username:
            self.username = self.from_email.strip()

    def action_save(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_("Only an administrator can set a number's e-mail."))
        address = (self.from_email or '').strip()
        if '@' not in address:
            raise UserError(_("Type the e-mail address to send from."))
        if not (self.host or '').strip():
            raise UserError(_("Choose the mail provider or type the SMTP server."))
        if not self.password and not self.current_email:
            raise UserError(_("Type the app password of %s.", address))
        try:
            self.session_id.sudo()._panel_save_email({
                'from_email': address,
                'from_name': (self.from_name or '').strip(),
                'host': self.host.strip(), 'port': self.port or 587, 'secure': bool(self.secure),
                'username': (self.username or address).strip(),
                'password': self.password or '',
            })
        finally:
            self.password = False      # never kept in Odoo
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _("E-mail saved"),
                'message': _("%(number)s now sends e-mail from %(mail)s.",
                             number=self.session_id.name, mail=address),
                'type': 'success', 'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_show_steps(self):
        """The step-by-step guide (arrows, animated pointer) for the chosen
        provider, in the Help pop-up over this form (the form stays open)."""
        self.ensure_one()
        return self.env['whatsapp.session']._wa_help_action(
            '/whatsapp_gateway/static/src/help/email_password.html?p=%s' % (self.provider or 'gmail'),
            _("Help - Get the e-mail password"))

    def action_remove(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_("Only an administrator can remove a number's e-mail."))
        self.session_id.sudo()._panel_remove_email()
        return {'type': 'ir.actions.act_window_close'}
