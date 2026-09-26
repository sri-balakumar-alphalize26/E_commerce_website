import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


# Typical local mobile-number length (digits, excluding country dial code) by
# ISO country code. Used to auto-fill the length when a country is chosen.
COUNTRY_MOBILE_LENGTH = {
    'IN': 10, 'US': 10, 'CA': 10, 'GB': 10, 'IE': 9, 'AU': 9, 'NZ': 9,
    'AE': 9, 'SA': 9, 'QA': 8, 'KW': 8, 'OM': 8, 'BH': 8, 'JO': 9,
    'DE': 10, 'FR': 9, 'IT': 10, 'ES': 9, 'NL': 9, 'BE': 9, 'CH': 9,
    'SE': 9, 'NO': 8, 'DK': 8, 'FI': 9, 'PT': 9, 'AT': 10, 'PL': 9,
    'SG': 8, 'MY': 9, 'ID': 10, 'PH': 10, 'TH': 9, 'VN': 9, 'KR': 10,
    'JP': 10, 'CN': 11, 'HK': 8, 'TW': 9,
    'PK': 10, 'BD': 10, 'LK': 9, 'NP': 10,
    'ZA': 9, 'NG': 10, 'KE': 9, 'EG': 10, 'TR': 10, 'RU': 10, 'BR': 11,
    'MX': 10,
}

# Card-size / font clamp bounds (mm / pt).
MIN_W, MAX_W = 40.0, 120.0
MIN_H, MAX_H = 25.0, 90.0
MIN_FONT, MAX_FONT = 1.0, 44.0

# Per-field font-size cap (mm) = card_height * weight -> bigger card allows bigger fonts.
FONT_WEIGHTS = {
    'company_font_size': 0.30, 'title_font_size': 0.30, 'number_font_size': 0.30,
    'name_font_size': 0.22, 'status_font_size': 0.20, 'points_font_size': 0.20,
    'since_font_size': 0.15,
}

# Visiting-card default (ATM/business-card size) restored by "Reset to Default".
WELCOME_DEFAULT = (
    "\U0001F389 *Welcome to our Loyalty Program!*\n\n"
    "Dear *{name}*,\n\n"
    "Your loyalty card has been created successfully.\n\n"
    "\U0001FAAA *Card No:* {card_number}\n"
    "\U0001F4F1 *Mobile:* {phone}\n"
    "\u2B50 *Points:* {points}\n\n"
    "You will earn points on every purchase. "
    "Show your mobile number at the counter to collect & redeem points!\n\n"
    "Thank you for being a valued customer! \U0001F64F"
)

WELCOME_HEADER_DEFAULT = "\U0001F389 Welcome to our Loyalty Program!"
WELCOME_FOOTER_DEFAULT = "Thank you for being a valued customer! \U0001F64F"

WELCOME_INTRO_DEFAULT = "Your loyalty card has been created successfully."
WELCOME_INSTR_DEFAULT = ("You will earn points on every purchase. "
                         "Show your mobile number at the counter to collect & redeem points!")

DEFAULTS = {
    'enable_loyalty': True,
    'email_card_enabled': False,
    'welcome_message': WELCOME_DEFAULT,
    'welcome_mode': 'simple',
    'welcome_header': WELCOME_HEADER_DEFAULT,
    'welcome_intro': WELCOME_INTRO_DEFAULT,
    'welcome_instructions': WELCOME_INSTR_DEFAULT,
    'welcome_show_greeting': True,
    'welcome_show_intro': True,
    'welcome_show_card': True,
    'welcome_show_mobile': True,
    'welcome_show_points': True,
    'welcome_show_instructions': True,
    'welcome_footer': WELCOME_FOOTER_DEFAULT,
    'mail_smtp_host': 'smtp.gmail.com',
    'mail_smtp_port': 587,
    'mail_smtp_encryption': 'starttls',
    'card_prefix': 'LC',
    'card_use_mobile': True,
    'card_mobile_digits': 2,
    'card_counter_padding': 6,
    'card_width': 86.0,
    'card_height': 54.0,
    'font_family': 'Arial, sans-serif',
    'title_font_size': 4.0,
    'number_font_size': 6.0,
    'name_font_size': 4.0,
    'company_font_size': 5.0,
    'status_font_size': 3.5,
    'since_font_size': 2.5,
    'points_font_size': 3.5,
    'background_color': '#1a237e',
    'text_color': '#ffffff',
    'title_color': '#ffd700',
    'name_color': '#e0e0e0',
    'company_color': '#ffd700',
    'status_color': '#4caf50',
    'since_color': '#aaaaaa',
    'points_color': '#ffd700',
}

# Font family options -> value is the CSS font-family stack (single-quoted names
# so they embed safely in a style attribute; these fonts ship with Windows where
# wkhtmltopdf renders the PDF).
FONT_FAMILIES = [
    ('Arial, sans-serif', 'Arial'),
    ("'Times New Roman', serif", 'Times New Roman'),
    ('Georgia, serif', 'Georgia'),
    ("'Courier New', monospace", 'Courier New'),
    ('Verdana, sans-serif', 'Verdana'),
    ('Tahoma, sans-serif', 'Tahoma'),
    ("'Trebuchet MS', sans-serif", 'Trebuchet MS'),
    ('Helvetica, Arial, sans-serif', 'Helvetica'),
    ("'Comic Sans MS', cursive", 'Comic Sans MS'),
]


def _clamp(value, lo, hi):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return value


class LoyaltyCardSettings(models.Model):
    _name = 'pos.loyalty.card.settings'
    _description = 'Loyalty Card Print Settings'
    _order = 'is_active desc, id'

    name = fields.Char(string='Name', required=True, default='Loyalty Settings')
    is_active = fields.Boolean(
        string='Active', default=False,
        help='Only one settings record can be active. Turning this on turns the '
             'others off. The active record is used everywhere in loyalty.')

    # Loyalty system on/off: master switch + per-shop list
    enable_loyalty = fields.Boolean(
        string='Enable Loyalty (master)', default=True,
        help='Master switch — turns the loyalty system on/off for every shop. '
             'Use the per-shop list to run loyalty on specific shops only.')
    email_card_enabled = fields.Boolean(
        string='Auto-Email Card', default=False,
        help='Email the loyalty card (image + PDF) to the customer when a card is created, '
             'if the customer has an email address. Requires an outgoing mail server.')

    # === Email "From" account (writes through to a managed ir.mail_server) ===
    mail_from_name = fields.Char(
        string='From Name', help='Sender name customers see, e.g. "MyShop Loyalty".')
    mail_from_email = fields.Char(
        string='From Email',
        help='Address cards are sent from. For Gmail/Workspace this must be the same as the Username.')
    mail_smtp_host = fields.Char(string='SMTP Server', default='smtp.gmail.com')
    mail_smtp_port = fields.Integer(string='Port', default=587)
    mail_smtp_encryption = fields.Selection(
        [('none', 'None'), ('starttls', 'TLS (recommended)'), ('ssl', 'SSL')],
        string='Security', default='starttls')
    mail_smtp_user = fields.Char(string='Username')
    mail_smtp_pass = fields.Char(string='Password / App Password')
    mail_configured = fields.Boolean(
        string='Email Ready', compute='_compute_mail_configured')
    welcome_message = fields.Text(
        string='Welcome Message (advanced template)', default=WELCOME_DEFAULT,
        help='Advanced full template. Placeholders: {name}, {card_number}, {phone}, {points}. '
             'Use *stars* for bold.')
    welcome_mode = fields.Selection(
        [('simple', 'Simple (fill-in-the-blanks)'), ('advanced', 'Advanced (full template)')],
        string='Welcome Message Mode', default='simple')
    welcome_header = fields.Char('Header', default=WELCOME_HEADER_DEFAULT)
    welcome_show_greeting = fields.Boolean('Show greeting (Dear name)', default=True)
    welcome_show_intro = fields.Boolean('Show intro line', default=True)
    welcome_show_card = fields.Boolean('Show card number', default=True)
    welcome_show_mobile = fields.Boolean('Show mobile', default=True)
    welcome_show_points = fields.Boolean('Show points', default=True)
    welcome_show_instructions = fields.Boolean('Show instructions line', default=True)
    welcome_footer = fields.Text('Footer', default=WELCOME_FOOTER_DEFAULT)
    welcome_intro = fields.Text('Intro line', default=WELCOME_INTRO_DEFAULT)
    welcome_instructions = fields.Text('Instructions line', default=WELCOME_INSTR_DEFAULT)
    welcome_preview = fields.Text('Live Preview', compute='_compute_welcome_preview', readonly=True)

    # Mobile number rules (used everywhere in loyalty: POS validation + backend)
    country_id = fields.Many2one(
        'res.country', string='Country',
        default=lambda self: self.env.company.country_id,
        help='Country for loyalty mobile numbers. Its dial code and typical '
             'number length are applied everywhere in loyalty (POS validation, '
             'WhatsApp, normalization).')
    country_dial_code = fields.Char(
        string='Country Dial Code', compute='_compute_country_dial_code', store=True,
        help='Dial code derived from the selected country (e.g. 91 for India, 1 for US).')
    mobile_number_length = fields.Integer(
        string='Mobile Number Length', default=10,
        help='Number of digits a local mobile number must have (excluding the '
             'country dial code). Auto-filled from the country but editable.')

    # Card number format: <prefix> + [last N mobile digits] + 6-digit counter
    card_prefix = fields.Char(
        string='Card Prefix', default='LC',
        help="Leading letters of the card number (e.g. 'LC'). Editable.")
    card_use_mobile = fields.Boolean(
        string='Include Mobile Digits', default=True,
        help="If on, the last few digits of the customer's mobile are inserted "
             "into the card number (between the prefix and the counter).")
    card_mobile_digits = fields.Integer(
        string='Mobile Digits Used', default=2,
        help="How many digits from the end of the mobile number to include.")
    card_counter_padding = fields.Integer(
        string='Counter Digits', default=6,
        help="Length of the running counter, e.g. 6 -> 000001. Zero-padded.")

    # Physical card size (drives both the PDF paper format and the card box)
    card_width = fields.Float(string='Card Width (mm)', default=86.0, required=True)
    card_height = fields.Float(string='Card Height (mm)', default=54.0, required=True)

    # Typography
    font_family = fields.Selection(
        FONT_FAMILIES, string='Font Style', default='Arial, sans-serif', required=True,
        help='Font family used for the printed card and preview.')

    # Font sizes (pt)
    title_font_size = fields.Float(string='Title Size (mm)', default=4.0)
    number_font_size = fields.Float(string='Card Number Size (mm)', default=6.0)
    name_font_size = fields.Float(string='Customer Name Size (mm)', default=4.0)

    # Colors
    background_color = fields.Char(string='Background Color', default='#1a237e')
    text_color = fields.Char(string='Text / Number Color', default='#ffffff')
    title_color = fields.Char(string='Title Color', default='#ffd700',
                              help="Color of the 'LOYALTY CARD' title text.")
    name_color = fields.Char(string='Customer Name Color', default='#e0e0e0')

    # Extra per-field colours + sizes (sizes in mm, capped by card height)
    company_color = fields.Char(string='Company Color', default='#ffd700')
    status_color = fields.Char(string='Status Color', default='#4caf50')
    since_color = fields.Char(string='Since Color', default='#aaaaaa')
    points_color = fields.Char(string='Points Color', default='#ffd700')
    company_font_size = fields.Float(string='Company Size (mm)', default=5.0)
    status_font_size = fields.Float(string='Status Size (mm)', default=3.5)
    since_font_size = fields.Float(string='Since Size (mm)', default=2.5)
    points_font_size = fields.Float(string='Points Size (mm)', default=3.5)

    # Card image / WhatsApp
    card_company_name = fields.Char(
        string='Card Company Name',
        help='Business name shown (highlighted) on the loyalty card image. '
             'Leave blank to use the Odoo company name.')
    card_image_retention_months = fields.Integer(
        string='Card Image Retention (months)', default=6,
        help='Saved loyalty card image snapshots older than this are auto-deleted. '
             '0 = keep forever.')

    @api.depends('country_id')
    def _compute_country_dial_code(self):
        for rec in self:
            code = rec.country_id.phone_code if rec.country_id else False
            rec.country_dial_code = str(code) if code else '91'

    @api.onchange('country_id')
    def _onchange_country_id(self):
        """Auto-fill the mobile number length from the chosen country."""
        if self.country_id and self.country_id.code:
            self.mobile_number_length = COUNTRY_MOBILE_LENGTH.get(
                self.country_id.code, self.mobile_number_length or 10)

    @api.onchange('card_width', 'card_height',
                  'title_font_size', 'number_font_size', 'name_font_size',
                  'company_font_size', 'status_font_size', 'since_font_size',
                  'points_font_size')
    def _onchange_clamp_sizes(self):
        """Bring oversize values back down live; caps scale with card height."""
        if self.card_width:
            self.card_width = _clamp(self.card_width, MIN_W, MAX_W)
        if self.card_height:
            self.card_height = _clamp(self.card_height, MIN_H, MAX_H)
        h = self.card_height or 54.0
        for fname, w in FONT_WEIGHTS.items():
            if self[fname]:
                self[fname] = _clamp(self[fname], MIN_FONT, max(MIN_FONT, h * w))

    def _apply_clamp(self, vals):
        if vals.get('card_width'):
            vals['card_width'] = _clamp(vals['card_width'], MIN_W, MAX_W)
        if vals.get('card_height'):
            vals['card_height'] = _clamp(vals['card_height'], MIN_H, MAX_H)
        h = vals.get('card_height') or (self.card_height if len(self) == 1 else None) or 54.0
        for fname, w in FONT_WEIGHTS.items():
            if vals.get(fname):
                vals[fname] = _clamp(vals[fname], MIN_FONT, max(MIN_FONT, h * w))
        return vals

    def _deactivate_others(self, keep):
        """Ensure only `keep` records stay active."""
        if self.env.context.get('_skip_active_sync'):
            return
        others = self.search([('is_active', '=', True), ('id', 'not in', keep.ids)])
        if others:
            others.with_context(_skip_active_sync=True).write({'is_active': False})

    def action_activate(self):
        """Turn this settings record ON (write enforces single-active) and
        reload the view so the other rows show as OFF immediately."""
        self.ensure_one()
        self.write({'is_active': True})
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    def action_reset_defaults(self):
        """Restore visiting-card default size, fonts and colors."""
        self.ensure_one()
        vals = dict(DEFAULTS)
        if self.country_id and self.country_id.code:
            vals['mobile_number_length'] = COUNTRY_MOBILE_LENGTH.get(self.country_id.code, 10)
        else:
            vals['mobile_number_length'] = 10
        self.write(vals)
        return True

    @api.model
    def get_mobile_config(self):
        """Return {'dial', 'length'} from the active settings (for UI widgets)."""
        cfg = self.get_settings()
        return {
            'dial': ''.join(filter(str.isdigit, cfg.country_dial_code or '')) or '91',
            'length': cfg.mobile_number_length or 10,
        }

    @api.depends('mail_smtp_host', 'mail_smtp_user')
    def _compute_mail_configured(self):
        Param = self.env['ir.config_parameter'].sudo()
        srv_id = int(Param.get_param('pos_loyalty_card.mail_server_id') or 0)
        srv = self.env['ir.mail_server'].sudo().browse(srv_id).exists() if srv_id else False
        ready = bool(srv and srv.smtp_host)
        for rec in self:
            rec.mail_configured = ready

    def _get_mail_server(self, create=True):
        """Return the managed 'Loyalty Outgoing Mail' ir.mail_server (create if needed)."""
        Param = self.env['ir.config_parameter'].sudo()
        Server = self.env['ir.mail_server'].sudo()
        srv_id = int(Param.get_param('pos_loyalty_card.mail_server_id') or 0)
        srv = Server.browse(srv_id).exists() if srv_id else Server
        if not srv:
            srv = Server.search([('name', '=', 'Loyalty Outgoing Mail')], limit=1)
        if not srv and create:
            srv = Server.create({'name': 'Loyalty Outgoing Mail', 'smtp_host': 'smtp.gmail.com'})
        if srv:
            Param.set_param('pos_loyalty_card.mail_server_id', str(srv.id))
        return srv

    def _mail_notify(self, title, message, kind):
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': kind, 'sticky': kind != 'success'},
        }

    def action_save_email_settings(self):
        """Write the From-account fields through to the managed outgoing mail server."""
        self.ensure_one()
        if not self.mail_smtp_host or not self.mail_from_email:
            return self._mail_notify(_('Missing Info'),
                                     _('Please fill at least the From Email and SMTP Server.'),
                                     'warning')
        srv = self._get_mail_server()
        srv.write({
            'name': 'Loyalty Outgoing Mail',
            'smtp_host': (self.mail_smtp_host or '').strip(),
            'smtp_port': self.mail_smtp_port or 587,
            'smtp_encryption': self.mail_smtp_encryption or 'starttls',
            'smtp_authentication': 'login',
            'smtp_user': (self.mail_smtp_user or self.mail_from_email or '').strip(),
            'smtp_pass': self.mail_smtp_pass or '',
            'from_filter': (self.mail_from_email or '').strip(),
        })
        return self._mail_notify(_('Saved'),
                                 _('Email account saved. Use "Send Test Email" to confirm it works.'),
                                 'success')

    def action_send_test_email(self):
        """Send a test email from the configured account to the current user."""
        self.ensure_one()
        self.action_save_email_settings()
        srv = self._get_mail_server(create=False)
        if not srv or not srv.smtp_host:
            return self._mail_notify(_('Not Set Up'), _('Save the email account first.'), 'warning')
        to_addr = self.mail_from_email or self.env.user.email
        if not to_addr:
            return self._mail_notify(_('No Recipient'),
                                     _('Your user has no email address to receive the test.'),
                                     'warning')
        from_name = self.mail_from_name or self.card_company_name or self.env.company.name
        from_email = self.mail_from_email or self.mail_smtp_user
        email_from = ('%s <%s>' % (from_name, from_email)) if from_email else from_email
        mail = self.env['mail.mail'].sudo().create({
            'subject': _('Loyalty test email'),
            'email_from': email_from,
            'email_to': to_addr,
            'body_html': _('<p>This is a test email from your Loyalty email settings. '
                           'If you received this, sending loyalty cards by email will work.</p>'),
            'mail_server_id': srv.id,
        })
        try:
            mail.send(raise_exception=True)
            return self._mail_notify(_('Test Sent'),
                                     _('A test email was sent to %s. Please check the inbox.') % to_addr,
                                     'success')
        except Exception as e:
            _logger.error('LOYALTY EMAIL: test send failed: %s', e)
            return self._mail_notify(
                _('Test Failed'),
                _('Could not send: %s\n\nCheck the SMTP server, username and App Password.')
                % (str(e)[:200]), 'warning')

    def action_reset_welcome_default(self):
        """Reset the welcome message (all parts) back to the default text."""
        self.ensure_one()
        keys = ['welcome_mode', 'welcome_header', 'welcome_intro', 'welcome_instructions',
                'welcome_footer', 'welcome_message', 'welcome_show_greeting', 'welcome_show_intro',
                'welcome_show_card', 'welcome_show_mobile', 'welcome_show_points',
                'welcome_show_instructions']
        self.write({k: DEFAULTS[k] for k in keys})
        return True

    def _welcome_ctx(self, name, card_number, phone, points):
        return {'name': name or '', 'card_number': card_number or '',
                'phone': phone or '', 'points': str(0 if points is None else points)}

    @api.model
    def _assemble_welcome_for(self, src, ctx):
        """Render the welcome message from ANY record exposing welcome_* fields.
        Shared by real sending and the live preview (Email + WhatsApp settings)."""
        def fill(t):
            t = t or ''
            for k, v in ctx.items():
                t = t.replace('{%s}' % k, v)
            return t
        if src.welcome_mode == 'advanced':
            return fill(src.welcome_message or WELCOME_DEFAULT)
        parts = []
        if src.welcome_header:
            parts.append(fill(src.welcome_header))
        if src.welcome_show_greeting:
            parts.append('Dear *%s*,' % ctx['name'])
        if src.welcome_show_intro:
            parts.append(fill(src.welcome_intro or ''))
        detail = []
        if src.welcome_show_card:
            detail.append('\U0001FAAA *Card No:* %s' % ctx['card_number'])
        if src.welcome_show_mobile:
            detail.append('\U0001F4F1 *Mobile:* %s' % ctx['phone'])
        if src.welcome_show_points:
            detail.append('⭐ *Points:* %s' % ctx['points'])
        if detail:
            parts.append('\n'.join(detail))
        if src.welcome_show_instructions:
            parts.append(fill(src.welcome_instructions or ''))
        if src.welcome_footer:
            parts.append(fill(src.welcome_footer))
        return '\n\n'.join(p for p in parts if p)

    def render_welcome(self, name, card_number, phone, points):
        """Build the welcome message for a real card (simple builder or advanced template)."""
        return self._assemble_welcome_for(self, self._welcome_ctx(name, card_number, phone, points))

    @api.depends('welcome_mode', 'welcome_header', 'welcome_show_greeting', 'welcome_show_intro',
                 'welcome_show_card', 'welcome_show_mobile', 'welcome_show_points',
                 'welcome_show_instructions', 'welcome_footer', 'welcome_intro',
                 'welcome_instructions', 'welcome_message')
    def _compute_welcome_preview(self):
        ctx = self._welcome_ctx('Selva', 'LC60000003', '+917339022360', 0)
        for rec in self:
            rec.welcome_preview = self._assemble_welcome_for(rec, ctx)

    @api.model
    def action_open_email_settings(self):
        """Open the standalone Email Settings screen on the active settings record."""
        rec = self.get_settings()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Email Settings'),
            'res_model': 'pos.loyalty.card.settings',
            'res_id': rec.id,
            'view_mode': 'form',
            'views': [(self.env.ref('pos_loyalty_card.view_loyalty_email_settings_form').id, 'form')],
            'target': 'current',
        }

    @api.model
    def get_settings(self):
        """Return the active settings record (fallback to first / create if none)."""
        rec = self.sudo().search([('is_active', '=', True)], limit=1)
        if not rec:
            rec = self.sudo().search([], limit=1)
        if not rec:
            rec = self.sudo().create({'is_active': True})
        return rec

    def _sync_paperformat(self):
        """Keep the loyalty-card paper format in sync with the ACTIVE settings."""
        pf = self.env.ref('pos_loyalty_card.paperformat_loyalty_card', raise_if_not_found=False)
        if not pf:
            return
        rec = self.get_settings()
        if rec and rec.card_width and rec.card_height:
            # Make the PDF page exactly card-sized with no white waste. Keep
            # orientation Portrait so wkhtmltopdf uses page_width/page_height
            # literally (Landscape would rotate them); zero all margins.
            pf.sudo().write({
                'format': 'custom',
                'orientation': 'Portrait',
                'page_width': rec.card_width,
                'page_height': rec.card_height,
                'margin_top': 0,
                'margin_bottom': 0,
                'margin_left': 0,
                'margin_right': 0,
                'header_line': False,
                'header_spacing': 0,
            })

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._apply_clamp(dict(v)) for v in vals_list]
        recs = super().create(vals_list)
        active_new = recs.filtered('is_active')
        if active_new:
            self._deactivate_others(active_new)
        recs._sync_paperformat()
        return recs

    def write(self, vals):
        vals = self._apply_clamp(dict(vals))
        # Single on/off toggle: turning one ON turns the others OFF; turning the
        # only active one OFF is blocked (matches the AI Reply History pattern).
        if 'is_active' in vals and not self.env.context.get('_skip_active_sync'):
            if vals.get('is_active'):
                res = super().write(vals)
                self._deactivate_others(self.filtered('is_active'))
                self._sync_paperformat()
                return res
            off = self.filtered('is_active')
            if off and not self.search_count(
                    [('is_active', '=', True), ('id', 'not in', off.ids)]):
                raise UserError(_(
                    "At least one Loyalty Settings must stay ON. To switch, turn "
                    "ON another settings record instead — you can't turn off "
                    "the only active one."))
        res = super().write(vals)
        if 'card_width' in vals or 'card_height' in vals:
            self._sync_paperformat()
        return res


class ReportLoyaltyCard(models.AbstractModel):
    _name = 'report.pos_loyalty_card.report_loyalty_card_document'
    _description = 'Loyalty Card Report Values'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['pos.loyalty.card'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'pos.loyalty.card',
            'docs': docs,
            'cfg': self.env['pos.loyalty.card.settings'].get_settings(),
        }
