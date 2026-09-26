from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta, datetime, time
import pytz
import logging
import base64
import re
import html
from io import BytesIO

_logger = logging.getLogger(__name__)


def _wa_text_to_html(text):
    """Convert WhatsApp-style text (*bold*, newlines) into safe HTML for email."""
    esc = html.escape(text or '')
    esc = re.sub(r'\*(.+?)\*', r'<b>\1</b>', esc)
    return esc.replace('\n', '<br/>')

# === BARCODE SUPPORT (integrated from File 2 for Print Card UI) ===
try:
    from barcode import Code128
    from barcode.writer import ImageWriter
    BARCODE_AVAILABLE = True
except ImportError:
    BARCODE_AVAILABLE = False


class LoyaltyCard(models.Model):
    _name = 'pos.loyalty.card'
    _description = 'Loyalty Card'
    _rec_name = 'card_number'

    card_number = fields.Char(string='Card Number', readonly=True, default='New', copy=False)
    name = fields.Char(string='Customer Name', required=True)
    phone = fields.Char(string='Mobile Number', required=True, index=True)
    email = fields.Char(string='Email')
    partner_id = fields.Many2one('res.partner', string='Partner', index=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
    ], default='draft', string='Status', index=True)
    
    # Points fields
    total_points = fields.Float(string='Total Points', compute='_compute_total_points', store=True)
    points_value = fields.Float(string='Points Value (₹)', compute='_compute_points_value')
    
    # Date fields - including registration_date for backwards compatibility
    registration_date = fields.Datetime(string='Registration Date', default=fields.Datetime.now, readonly=True)
    expiry_date = fields.Date(string='Expiry Date')
    last_used_date = fields.Datetime(string='Last Used')
    
    # Relations
    history_ids = fields.One2many('pos.loyalty.history', 'card_id', string='History')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    
    # Soft Delete fields
    is_deleted = fields.Boolean(string='Deleted', default=False, index=True)
    deleted_date = fields.Datetime(string='Deleted Date')

    # Additional useful fields
    notes = fields.Text(string='Notes')
    barcode = fields.Char(string='Barcode', copy=False)
    
    # === NEW: Barcode image field (integrated from File 2 for Print Card UI) ===
    barcode_image = fields.Binary(
        string='Barcode Image',
        compute='_compute_barcode_image',
        store=True,
    )

    _sql_constraints = [
        ('card_number_unique', 'unique(card_number)', 'Card number must be unique!'),
    ]

    def init(self):
        """Fix NULL is_deleted values and set DB-level NOT NULL constraint.
        Runs on every module install/upgrade to ensure data integrity."""
        self.env.cr.execute("""
            UPDATE pos_loyalty_card SET is_deleted = False WHERE is_deleted IS NULL;
            ALTER TABLE pos_loyalty_card ALTER COLUMN is_deleted SET DEFAULT False;
            ALTER TABLE pos_loyalty_card ALTER COLUMN is_deleted SET NOT NULL;
        """)

    @api.constrains('phone', 'company_id', 'is_deleted')
    def _check_phone_unique(self):
        """Ensure phone is unique among non-deleted cards per company"""
        for record in self:
            if record.is_deleted:
                continue
            duplicate = self.search([
                ('phone', '=', record.phone),
                ('company_id', '=', record.company_id.id),
                ('is_deleted', '=', False),
                ('id', '!=', record.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_('Phone number must be unique per company! Card %s already has this number.') % duplicate.card_number)

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=None, order=None):
        """
        Override to search by card_number, customer name, and phone number.
        This enables the global search bar to find cards by any of these fields.
        """
        domain = domain or []
        if name:
            # Search across card_number, name (customer name), and phone
            domain = ['|', '|',
                      ('card_number', operator, name),
                      ('name', operator, name),
                      ('phone', operator, name),
                      ] + domain
        return self._search(domain, limit=limit, order=order)

    @api.model
    def _get_loyalty_mobile_cfg(self):
        """Return (dial_code_digits, local_length) from the global Loyalty Settings."""
        cfg = self.env['pos.loyalty.card.settings'].get_settings()
        dial = ''.join(filter(str.isdigit, cfg.country_dial_code or '')) or (
            str(self.env.company.country_id.phone_code) if self.env.company.country_id else '91')
        length = cfg.mobile_number_length or 10
        return dial, length

    @api.model
    def _build_card_number(self, phone):
        """Build a card number from the configurable format in Loyalty Settings:
        <prefix> + [last N mobile digits] + <6-digit counter>, e.g. LC90000001."""
        cfg = self.env['pos.loyalty.card.settings'].get_settings()
        prefix = (cfg.card_prefix or 'LC').strip()
        pad = cfg.card_counter_padding if 1 <= (cfg.card_counter_padding or 0) <= 12 else 6
        raw = self.env['ir.sequence'].next_by_code('pos.loyalty.card') or 'LC1'
        counter = ('%0' + str(pad) + 'd') % int(''.join(filter(str.isdigit, raw)) or '1')
        mobile_part = ''
        if cfg.card_use_mobile:
            digits = ''.join(filter(str.isdigit, phone or ''))
            n = cfg.card_mobile_digits or 0
            if n > 0 and digits:
                mobile_part = digits[-n:]
        return '%s%s%s' % (prefix, mobile_part, counter)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # === Auto-normalize phone with configured country code + length ===
            if vals.get('phone'):
                from ..wizard.loyalty_delete_confirm_wizard import normalize_phone
                dial, length = self._get_loyalty_mobile_cfg()
                vals['phone'] = normalize_phone(vals['phone'], dial, length)

            # === Build card number from the configurable format (prefix + mobile + counter) ===
            if vals.get('card_number', 'New') == 'New':
                vals['card_number'] = self._build_card_number(vals.get('phone'))

            # === NEW: Auto-generate barcode (integrated from File 2) ===
            if not vals.get('barcode'):
                card_num = vals.get('card_number', '')
                prefix = (self.env['pos.loyalty.card.settings'].get_settings().card_prefix or 'LC').strip()
                vals['barcode'] = card_num.replace(prefix, '', 1) if card_num else ''
            
            # Auto-create partner if not provided
            if not vals.get('partner_id') and vals.get('name') and vals.get('phone'):
                partner = self._create_or_get_partner(vals.get('name'), vals.get('phone'), vals.get('email'))
                if partner:
                    vals['partner_id'] = partner.id
                    # === NEW: Set barcode on partner (integrated from File 2) ===
                    if vals.get('barcode'):
                        partner.write({'barcode': vals['barcode']})
                    
        records = super().create(vals_list)

        # Queue the WhatsApp welcome (text + image + PDF) and email for newly
        # created active cards. Deferred to the send queue so POS card creation
        # returns immediately instead of blocking on network sends.
        for card in records:
            if card.state == 'active':
                try:
                    self.env['whatsapp.send.queue'].sudo()._enqueue('welcome', card, delay_seconds=30)
                except Exception as e:
                    _logger.error('LOYALTY WA: Error queueing welcome for card %s: %s', card.card_number, e)

        return records

    def write(self, vals):
        """Override write to normalize phone on edit."""
        if vals.get('phone'):
            from ..wizard.loyalty_delete_confirm_wizard import normalize_phone
            dial, length = self._get_loyalty_mobile_cfg()
            vals['phone'] = normalize_phone(vals['phone'], dial, length)
        return super().write(vals)

    def action_open_delete_wizard(self):
        """Open delete confirmation wizard for selected loyalty cards."""
        return self.env['loyalty.delete.confirm.wizard'].open_delete_wizard_loyalty(self.ids)

    def _create_or_get_partner(self, name, phone, email=False):
        """Create or find a partner for this loyalty card"""
        Partner = self.env['res.partner']
        
        # Clean phone number
        clean_phone = ''.join(filter(str.isdigit, str(phone))) if phone else ''
        
        # Search for existing partner by phone only (no mobile field in Odoo 19)
        if clean_phone:
            _dial, _n = self._get_loyalty_mobile_cfg()
            search_pattern = clean_phone[-_n:] if len(clean_phone) >= _n else clean_phone
            partner = Partner.search([
                ('phone', 'ilike', search_pattern),
            ], limit=1)
            if partner:
                _logger.info('LOYALTY: Found existing partner %s for phone %s', partner.name, phone)
                return partner
        
        # Create new partner with only standard fields
        partner_vals = {
            'name': name,
            'phone': phone,
            'email': email or False,
            'customer_rank': 1,
        }
        
        # Create partner
        try:
            partner = Partner.create(partner_vals)
        except Exception as e:
            _logger.error('LOYALTY: Error creating partner: %s', e)
            return False
            
        _logger.info('LOYALTY: Created new partner %s (ID: %s) for phone %s', partner.name, partner.id, phone)
        return partner

    # === NEW: Barcode image computation (integrated from File 2 for Print Card UI) ===
    @api.depends('barcode')
    def _compute_barcode_image(self):
        """Generate barcode image for printing"""
        for record in self:
            if record.barcode and BARCODE_AVAILABLE:
                try:
                    barcode_io = BytesIO()
                    Code128(record.barcode, writer=ImageWriter()).write(barcode_io)
                    record.barcode_image = base64.b64encode(barcode_io.getvalue())
                except Exception:
                    record.barcode_image = False
            else:
                record.barcode_image = False

    @api.depends('history_ids.points', 'history_ids.type')
    def _compute_total_points(self):
        for card in self:
            earned = sum(card.history_ids.filtered(lambda h: h.type == 'earned').mapped('points'))
            redeemed = sum(card.history_ids.filtered(lambda h: h.type == 'redeemed').mapped('points'))
            returned = sum(card.history_ids.filtered(lambda h: h.type == 'returned').mapped('points'))
            # Redeemed points credited back on a return ADD to the balance.
            redeem_returned = sum(card.history_ids.filtered(lambda h: h.type == 'redeem_returned').mapped('points'))
            card.total_points = earned - redeemed - returned + redeem_returned

    def _compute_points_value(self):
        """Calculate monetary value of points"""
        rule = self.env['pos.loyalty.rule'].get_active_rule()
        points_per_currency = rule.points_per_currency if rule else 10
        for card in self:
            if points_per_currency > 0:
                card.points_value = card.total_points / points_per_currency
            else:
                card.points_value = 0

    def _maybe_email_card(self):
        """Auto-email the card if enabled in settings and the customer has an email."""
        self.ensure_one()
        try:
            if self.email and self.env['pos.loyalty.card.settings'].get_settings().email_card_enabled:
                self._email_card()
        except Exception as e:
            _logger.error('LOYALTY EMAIL: auto-email failed for card %s: %s', self.card_number, e)

    def _notify(self, title, message, kind):
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': kind, 'sticky': False},
        }

    def action_email_card(self):
        """Button: email the loyalty card (image + PDF) to this customer."""
        self.ensure_one()
        if not self.email:
            return self._notify(_('No Email'),
                                _('This card has no email address. Add one to email the card.'),
                                'warning')
        ok = self._email_card()
        if ok:
            return self._notify(_('Card Emailed'),
                                _('The loyalty card was emailed to %s.') % self.email, 'success')
        return self._notify(_('Not Sent'),
                            _('Could not send the email. Check that an outgoing mail server is '
                              'configured (Settings > Technical > Outgoing Mail Servers).'),
                            'warning')

    def _email_card(self):
        """Generate the card image + PDF and email them to self.email. Returns True on success."""
        self.ensure_one()
        if not self.email:
            _logger.info('LOYALTY EMAIL: no email on card %s, skipping.', self.card_number)
            return False
        Attachment = self.env['ir.attachment'].sudo()
        attachments = self.env['ir.attachment']
        # Card image (pure Pillow -- works with no WhatsApp connection)
        img_b64 = False
        try:
            img_b64 = self.env['pos.loyalty.whatsapp.service'].sudo()._generate_loyalty_card_image(self)
        except Exception as e:
            _logger.warning('LOYALTY EMAIL: image generation failed for %s: %s', self.card_number, e)
        if img_b64:
            attachments |= Attachment.create({
                'name': 'LoyaltyCard_%s.png' % (self.card_number or self.id),
                'datas': img_b64, 'mimetype': 'image/png',
                'res_model': 'pos.loyalty.card', 'res_id': self.id,
            })
        # PDF version of the card
        try:
            pdf, _ct = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                'pos_loyalty_card.action_report_loyalty_card', self.ids)
            if pdf:
                attachments |= Attachment.create({
                    'name': 'LoyaltyCard_%s.pdf' % (self.card_number or self.id),
                    'datas': base64.b64encode(pdf), 'mimetype': 'application/pdf',
                    'res_model': 'pos.loyalty.card', 'res_id': self.id,
                })
        except Exception as e:
            _logger.warning('LOYALTY EMAIL: PDF generation failed for %s: %s', self.card_number, e)
        # Shop / company name for the subject + greeting
        try:
            cfg = self.env['pos.loyalty.card.settings'].get_settings()
        except Exception:
            cfg = False
        shop = (cfg.card_company_name if cfg else False) or self.env.company.name
        from_name = (cfg.mail_from_name if cfg else False) or shop
        from_email = (cfg.mail_from_email if cfg else False) or self.env.company.email or self.env.user.email
        email_from = ('%s <%s>' % (from_name, from_email)) if from_email else False
        srv_id = int(self.env['ir.config_parameter'].sudo().get_param(
            'pos_loyalty_card.mail_server_id') or 0)
        points = int(round(self.total_points or 0))
        inline = ('<p><img src="data:image/png;base64,%s" style="max-width:360px;width:100%%;'
                  'border-radius:8px;"/></p>' % img_b64) if img_b64 else ''
        welcome = cfg.render_welcome(self.name, self.card_number, self.phone, points) if cfg else ''
        body = (
            '<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;">%s%s</div>'
            % (_wa_text_to_html(welcome), inline)
        )
        mail = self.env['mail.mail'].sudo().create({
            'subject': _('Your %s Loyalty Card - %s') % (shop, self.card_number or ''),
            'email_from': email_from,
            'email_to': self.email,
            'body_html': body,
            'attachment_ids': [(6, 0, attachments.ids)],
            'mail_server_id': srv_id or False,
        })
        try:
            mail.send(raise_exception=True)
            _logger.info('LOYALTY EMAIL: sent card %s to %s', self.card_number, self.email)
            return True
        except Exception as e:
            _logger.error('LOYALTY EMAIL: send failed for card %s: %s', self.card_number, e)
            return False

    def action_activate(self):
        for card in self:
            was_draft = card.state == 'draft'
            card.state = 'active'
            # Queue WhatsApp welcome + PDF + email when first activated (deferred).
            if was_draft:
                try:
                    self.env['whatsapp.send.queue'].sudo()._enqueue('welcome', card, delay_seconds=30)
                except Exception as e:
                    _logger.error('LOYALTY WA: Error queueing welcome on activate for card %s: %s',
                                  card.card_number, e)

    def action_suspend(self):
        self.state = 'suspended'
    
    # === NEW: Reactivate action (integrated from File 2) ===
    def action_reactivate(self):
        """Reactivate a suspended card"""
        for record in self:
            if record.state == 'suspended':
                record.state = 'active'
        return True

    # =========================================================================
    # === SOFT DELETE / RECYCLE BIN METHODS ===
    # =========================================================================

    def unlink(self):
        """Override unlink to soft-delete instead of permanent delete"""
        for record in self:
            record.write({
                'is_deleted': True,
                'deleted_date': fields.Datetime.now(),
                'state': 'suspended',
            })
        return True

    def action_soft_delete(self):
        """Manually soft-delete selected loyalty cards"""
        for record in self:
            record.write({
                'is_deleted': True,
                'deleted_date': fields.Datetime.now(),
                'state': 'suspended',
            })
        return True

    def action_restore(self):
        """Restore soft-deleted loyalty cards back to active"""
        for record in self:
            record.write({
                'is_deleted': False,
                'deleted_date': False,
                'state': 'active',
            })
        # Reload deleted cards popup so restored card disappears
        return self.action_view_deleted_cards()

    def _hard_unlink(self):
        """Really remove the card rows, bypassing the soft-delete unlink() override.
        Shared by the card- and customer-side permanent-delete actions."""
        return super(LoyaltyCard, self).unlink()

    def action_permanent_delete(self):
        """Permanently delete loyalty cards (bypass soft-delete) AND release the
        phone number: the auto-created partner that is left with no other card is
        marked deleted, so the number is no longer detected as an existing customer
        in POS (fixes one-sided delete)."""
        model = self.env['pos.loyalty.card']
        partners = self.mapped('partner_id')
        self._hard_unlink()
        # Any partner now orphaned (no remaining loyalty card) is soft-deleted so
        # the customer lookup (search_customer_by_phone) won't match its phone.
        for partner in partners:
            if not partner.exists() or partner.is_company:
                continue
            if model.sudo().search_count([('partner_id', '=', partner.id)]):
                continue
            partner.sudo().write({
                'is_customer_deleted': True,
                'customer_deleted_date': fields.Datetime.now(),
            })
        # Reload deleted cards popup so deleted card disappears
        return model.action_view_deleted_cards()

    @api.model
    def action_view_deleted_cards(self):
        """Open deleted loyalty cards in a popup window - called from JS button"""
        return {
            'name': _('Deleted Loyalty Cards'),
            'type': 'ir.actions.act_window',
            'res_model': 'pos.loyalty.card',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('pos_loyalty_card.view_deleted_loyalty_card_list').id, 'list'),
                (self.env.ref('pos_loyalty_card.view_deleted_loyalty_card_form').id, 'form'),
            ],
            'search_view_id': [self.env.ref('pos_loyalty_card.view_deleted_loyalty_card_search').id],
            'domain': [('is_deleted', '=', True)],
            'context': {
                'show_deleted': True,
                'create': False,
            },
            'target': 'new',
        }

    def action_add_test_points(self):
        """Add 500 test points"""
        for card in self:
            if card.state == 'active':
                self.env['pos.loyalty.history'].create({
                    'card_id': card.id,
                    'points': 500,
                    'type': 'earned',
                    'description': 'Test Points',
                })

    # =========================================================================
    # === PRINT CARD UI (integrated from File 2) ===
    # =========================================================================
    def action_print_card(self):
        """Print loyalty card in ATM card format (PDF)"""
        self.ensure_one()
        return self.env.ref('pos_loyalty_card.action_report_loyalty_card').report_action(self)

    def action_view_card(self):
        """Open a centered on-screen view of the card (with a Print button)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/loyalty_card/view/%s' % self.id,
            'target': 'new',
        }

    # =========================================================================
    # === WHATSAPP UI (integrated from File 2) ===
    # =========================================================================
    def action_send_whatsapp(self):
        """Send loyalty card details via WhatsApp"""
        self.ensure_one()
        if not self.phone:
            raise ValidationError(_('Phone number is required to send WhatsApp message.'))
        
        # Format phone for WhatsApp (needs country code)
        dial, _length = self._get_loyalty_mobile_cfg()
        phone = self.phone.replace(' ', '').replace('-', '').replace('+', '')
        if not phone.startswith(dial):
            phone = dial + phone
        
        # Compose WhatsApp message
        message = (
            "Dear %s,\n\n"
            "Welcome to our Loyalty Program!\n\n"
            "Your Loyalty Card Details:\n"
            "Card Number: %s\n"
            "Current Points: %.2f\n"
            "Points Value: ₹%.2f\n\n"
            "Show this card number at checkout to earn and redeem points!\n\n"
            "Thank you for being a valued customer!"
        ) % (self.name, self.card_number, self.total_points, self.points_value)
        
        # URL encode the message
        import urllib.parse
        encoded_message = urllib.parse.quote(message)
        whatsapp_url = "https://wa.me/%s?text=%s" % (phone, encoded_message)
        
        return {
            'type': 'ir.actions.act_url',
            'url': whatsapp_url,
            'target': 'new',
        }

    # =========================================================================
    # === POS INTEGRATION METHODS ===
    # =========================================================================
    
    @api.model
    def search_by_phone_or_card(self, search_term):
        """Search card by phone or card number - called from POS"""
        _logger.info('LOYALTY: search_by_phone_or_card called with: %s', search_term)
        
        if not search_term:
            return {'error': 'Please enter phone or card number'}
        
        # Clean the search term
        clean_term = str(search_term).strip()
        
        # First try exact match on phone or card number with active state
        card = self.search([
            ('state', '=', 'active'),
            ('is_deleted', '=', False),
            '|',
            ('phone', '=', clean_term),
            ('card_number', '=', clean_term),
        ], limit=1)
        
        if not card:
            # Phone match — EXACT on the normalized local number (last N digits).
            # We must NOT substring-match: typing "12345678" should never match a
            # stored "+11234567890" just because it contains those digits. So we
            # pull candidates that end with the typed digits, then keep only the
            # one whose normalized last-N digits EQUAL exactly what was typed.
            clean_digits = ''.join(filter(str.isdigit, clean_term))
            _dial, _n = self._get_loyalty_mobile_cfg()
            if len(clean_digits) >= _n:
                target = clean_digits[-_n:]
                candidates = self.search([
                    ('state', '=', 'active'),
                    ('is_deleted', '=', False),
                    ('phone', 'ilike', target),
                ], limit=50)
                for cand in candidates:
                    cand_digits = ''.join(filter(str.isdigit, cand.phone or ''))
                    if cand_digits and cand_digits[-_n:] == target:
                        card = cand
                        break

        if not card:
            # Card-number match — EXACT (case-insensitive), never a substring.
            card = self.search([
                ('state', '=', 'active'),
                ('is_deleted', '=', False),
                ('card_number', '=ilike', clean_term),
            ], limit=1)
        
        if not card:
            _logger.info('LOYALTY: No card found for search term: %s', search_term)
            return {'error': 'No card found'}
        
        _logger.info('LOYALTY: Found card %s (ID: %s) for search term: %s', 
                    card.card_number, card.id, search_term)
        
        rule = self.env['pos.loyalty.rule'].get_active_rule()
        min_points = rule.min_redeem_points if rule else 100
        points_per_currency = rule.points_per_currency if rule else 10
        
        return {
            'id': card.id,
            'card_number': card.card_number,
            'name': card.name,
            'phone': card.phone,
            'partner_id': card.partner_id.id if card.partner_id else False,
            'total_points': card.total_points,
            'points_value': card.total_points / points_per_currency if points_per_currency else 0,
            'can_redeem': card.total_points >= min_points,
            'min_redeem_points': min_points,
            'points_per_currency': points_per_currency,
            'max_redeem_percent': rule.max_redeem_percent if rule else 100,
        }

    @api.model
    def get_card_pos_data(self, card_id):
        """Return the same POS card dict for a given card id (used to restore
        the loyalty card on the payment screen after a browser refresh)."""
        card = self.browse(card_id).exists()
        if not card or card.is_deleted or card.state != 'active':
            return {'error': 'Card not found'}
        rule = self.env['pos.loyalty.rule'].get_active_rule()
        min_points = rule.min_redeem_points if rule else 100
        points_per_currency = rule.points_per_currency if rule else 10
        return {
            'id': card.id,
            'card_number': card.card_number,
            'name': card.name,
            'phone': card.phone,
            'partner_id': card.partner_id.id if card.partner_id else False,
            'total_points': card.total_points,
            'points_value': card.total_points / points_per_currency if points_per_currency else 0,
            'can_redeem': card.total_points >= min_points,
            'min_redeem_points': min_points,
            'points_per_currency': points_per_currency,
            'max_redeem_percent': rule.max_redeem_percent if rule else 100,
        }

    # === Customer-only search (for when loyalty is OFF) ===
    @api.model
    def search_customer_by_phone(self, phone):
        """
        Search customer by phone number — used when loyalty is OFF.
        Always searches res.partner first by phone, then falls back to loyalty cards.
        Returns minimal data: name, phone, partner_id (no points info).
        """
        if not phone:
            return {'error': 'Please enter a mobile number'}

        clean_phone = str(phone).strip()
        clean_digits = ''.join(filter(str.isdigit, clean_phone))
        _dial, _n = self._get_loyalty_mobile_cfg()
        # Strip a leading country dial code if present.
        if _dial and len(clean_digits) > _n and clean_digits.startswith(_dial):
            clean_digits = clean_digits[len(_dial):]
        target = clean_digits[-_n:] if len(clean_digits) >= _n else clean_digits

        # 1. Search res.partner by phone FIRST — EXACT on normalized last-N digits,
        #    never a substring (so "12345678" won't match "+11234567890").
        Partner = self.env['res.partner']
        partner = False
        if target:
            for cand in Partner.search([('phone', 'ilike', target), ('is_customer_deleted', '=', False)], limit=50):
                cand_digits = ''.join(filter(str.isdigit, cand.phone or ''))
                if cand_digits and cand_digits[-_n:] == target:
                    partner = cand
                    break

        if partner:
            # Check if this partner also has a loyalty card
            card = self.search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'active'),
                ('is_deleted', '=', False),
            ], limit=1)
            return {
                'id': card.id if card else False,
                'card_number': card.card_number if card else '',
                'name': partner.name,
                'phone': partner.phone or clean_phone,
                'partner_id': partner.id,
                'total_points': 0,  # Don't show points when loyalty OFF
                'has_loyalty_card': bool(card),
            }

        # 2. Fallback: Try loyalty card (may exist from before) — EXACT normalized match.
        card = False
        if target:
            for cand in self.search([
                ('state', '=', 'active'),
                ('is_deleted', '=', False),
                ('phone', 'ilike', target),
            ], limit=50):
                cand_digits = ''.join(filter(str.isdigit, cand.phone or ''))
                if cand_digits and cand_digits[-_n:] == target:
                    card = cand
                    break

        if card:
            return {
                'id': card.id,
                'card_number': card.card_number,
                'name': card.name,
                'phone': card.phone,
                'partner_id': card.partner_id.id if card.partner_id else False,
                'total_points': 0,  # Don't show points when loyalty OFF
                'has_loyalty_card': True,
            }

        return {'error': 'No customer found'}

    @api.model
    def create_customer_only(self, name, phone, email=False):
        """
        Create a new res.partner customer WITHOUT creating a loyalty card.
        Used when loyalty is OFF but we still need customer details for the order.
        Returns: dict with partner_id, name, phone.
        """
        _logger.info('LOYALTY: create_customer_only called: name=%s, phone=%s', name, phone)

        if not name or not name.strip():
            return {'error': 'Customer name is required'}
        if not phone or not phone.strip():
            return {'error': 'Mobile number is required'}

        # Clean phone
        clean_digits = ''.join(filter(str.isdigit, str(phone).strip()))
        if len(clean_digits) > 10 and clean_digits.startswith('91'):
            clean_digits = clean_digits[2:]

        if len(clean_digits) != 10:
            return {'error': 'Please enter a valid 10-digit mobile number'}

        search_pattern = clean_digits[-10:]

        # Check for existing partner by phone
        Partner = self.env['res.partner']
        existing = Partner.search([
            ('phone', 'ilike', search_pattern),
        ], limit=1)

        if existing:
            return {
                'error': 'Customer already exists: %s (%s)' % (existing.name, existing.phone),
            }

        # Create new partner
        try:
            partner = Partner.create({
                'name': name.strip(),
                'phone': phone.strip(),
                'email': email.strip() if email else False,
                'customer_rank': 1,
            })
            _logger.info('LOYALTY: Created customer-only partner %s (ID: %s)', partner.name, partner.id)

            return {
                'success': True,
                'id': False,  # No loyalty card ID
                'card_number': '',
                'name': partner.name,
                'phone': partner.phone,
                'partner_id': partner.id,
                'total_points': 0,
                'has_loyalty_card': False,
            }
        except Exception as e:
            _logger.error('LOYALTY: Error creating customer: %s', e)
            return {'error': 'Failed to create customer: %s' % str(e)}

    # === NEW: search_card_for_pos method (integrated from File 2 for Payment section popup) ===
    @api.model
    def search_card_for_pos(self, search_term):
        """
        Search for loyalty card by barcode, card number, or phone.
        Returns card data for POS display.
        Supports searching by mobile number or loyalty card number.
        """
        if not search_term:
            return {'error': 'Please enter a mobile number or card number.'}
        
        search_term = str(search_term).strip()
        
        # Normalize phone if it looks like a phone number
        normalized_phone = None
        cleaned = re.sub(r'\D', '', search_term)
        if len(cleaned) >= 10:
            if cleaned.startswith('91') and len(cleaned) == 12:
                normalized_phone = cleaned[2:]
            elif cleaned.startswith('0') and len(cleaned) == 11:
                normalized_phone = cleaned[1:]
            elif len(cleaned) == 10:
                normalized_phone = cleaned
        
        # Build search domain (exclude deleted cards)
        domain = [
            ('is_deleted', '=', False),
            '|', '|', '|',
            ('barcode', '=', search_term),
            ('card_number', 'ilike', search_term),
            ('phone', 'ilike', search_term),
            ('phone', 'ilike', normalized_phone) if normalized_phone else ('id', '=', False),
        ]
        card = self.search(domain, limit=1)
        
        if not card:
            return {'error': 'No loyalty card found for: %s' % search_term}
        
        if card.state != 'active':
            return {'error': 'Loyalty card is not active. Status: %s' % card.state}
        
        # Get redemption rule
        rule = self.env['pos.loyalty.rule'].get_active_rule()
        
        min_points = rule.min_redeem_points if rule else 100
        points_per_unit = rule.points_per_currency if rule else 10
        max_redemption_percent = 100  # Default to 100%
        allow_partial = True  # Default to allow partial
        
        can_redeem = card.total_points >= min_points
        redeemable_value = card.total_points / points_per_unit if points_per_unit > 0 else 0
        
        return {
            'id': card.id,
            'card_number': card.card_number,
            'name': card.name,
            'phone': card.phone,
            'email': card.email or '',
            'total_points': card.total_points,
            'points_value': round(redeemable_value, 2),
            'state': card.state,
            'can_redeem': can_redeem,
            'min_redemption_points': min_points,
            'points_per_unit': points_per_unit,
            'max_redemption_percent': max_redemption_percent,
            'allow_partial': allow_partial,
            'partner_id': card.partner_id.id if card.partner_id else False,
        }

    @api.model
    def create_new_card(self, name, phone, email=False):
        """Create new card from POS"""
        _logger.info('LOYALTY: create_new_card called: name=%s, phone=%s', name, phone)
        
        if not name or not phone:
            return {'error': 'Name and phone are required'}
        
        # Clean phone
        clean_phone = ''.join(filter(str.isdigit, str(phone)))
        
        # Check for existing card (exclude deleted)
        existing = self.search([
            ('is_deleted', '=', False),
            '|',
            ('phone', '=', phone),
            ('phone', '=', clean_phone),
        ], limit=1)
        
        if existing:
            _logger.info('LOYALTY: Card already exists: %s', existing.card_number)
            return {'error': 'Card already exists: ' + existing.card_number}
        
        # Create card (partner will be auto-created via create method)
        card = self.create({
            'name': name,
            'phone': phone,
            'email': email,
            'state': 'active',
        })
        
        _logger.info('LOYALTY: Created new card %s (ID: %s), partner_id: %s', 
                    card.card_number, card.id, card.partner_id.id if card.partner_id else 'None')
        
        return {
            'success': True,
            'id': card.id,
            'card_number': card.card_number,
            'name': card.name,
            'phone': card.phone,
            'partner_id': card.partner_id.id if card.partner_id else False,
            'total_points': 0,
        }

    # === NEW: create_from_pos method (integrated from File 2 for Payment section popup) ===
    @api.model
    def create_from_pos(self, vals):
        """
        Create a new loyalty card from POS.
        Used when a new customer needs to be registered during checkout.
        Validates mobile number and card number formats.
        """
        if not vals.get('name') or not vals.get('name').strip():
            return {'error': 'Customer name is required.'}
        
        if not vals.get('phone') or not vals.get('phone').strip():
            return {'error': 'Phone number is required.'}
        
        # Validate phone format
        phone = vals['phone'].strip()
        cleaned = re.sub(r'\D', '', phone)
        valid_patterns = [
            r'^[6-9]\d{9}$',
            r'^91[6-9]\d{9}$',
            r'^0[6-9]\d{9}$',
        ]
        if not any(re.match(pattern, cleaned) for pattern in valid_patterns):
            return {'error': 'Please enter a valid 10-digit mobile number.'}
        
        # Normalize phone number
        if cleaned.startswith('91') and len(cleaned) == 12:
            phone = cleaned[2:]
        elif cleaned.startswith('0') and len(cleaned) == 11:
            phone = cleaned[1:]
        elif len(cleaned) == 10:
            phone = cleaned
        
        # Check if phone already exists (exclude deleted)
        existing = self.search([('phone', 'ilike', phone), ('is_deleted', '=', False)], limit=1)
        if existing:
            return {'error': 'A loyalty card with this phone number already exists: %s' % existing.card_number}
        
        try:
            card = self.create({
                'name': vals['name'].strip(),
                'phone': phone,
                'email': vals.get('email').strip() if vals.get('email') else False,
                'state': 'active',  # Auto-activate for POS registrations
            })
            
            return {
                'success': True,
                'id': card.id,
                'card_number': card.card_number,
                'barcode': card.barcode,
                'name': card.name,
                'phone': card.phone,
                'total_points': 0,
                'can_redeem': False,
            }
        except Exception as e:
            return {'error': str(e)}

    # =========================================================================
    # === DAILY MIDNIGHT REDEMPTION LIMIT CHECK ===
    # =========================================================================
    def _check_redemption_cooldown(self):
        """
        Check if redemption is allowed based on daily midnight reset rule.
        Customer can redeem only ONCE per calendar day (resets at midnight local time).
        Returns: dict with 'allowed' (bool), 'error' (str if not allowed), 
                 'next_allowed_time' (datetime if not allowed)
        """
        self.ensure_one()
        
        # Get user/company timezone
        user_tz_name = self.env.user.tz or self.env.company.partner_id.tz or 'UTC'
        try:
            user_tz = pytz.timezone(user_tz_name)
        except Exception:
            user_tz = pytz.UTC
            user_tz_name = 'UTC'
        
        _logger.info('LOYALTY COOLDOWN: Using timezone %s for card %s', user_tz_name, self.card_number)
        
        # Get current time in local timezone
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local = now_utc.astimezone(user_tz)
        
        # Calculate today's start (midnight) and tomorrow's start in local timezone
        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start_local = today_start_local + timedelta(days=1)
        
        # Convert to UTC for database query
        today_start_utc = today_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        tomorrow_start_utc = tomorrow_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        
        _logger.info('LOYALTY COOLDOWN: Today range (UTC): %s to %s', today_start_utc, tomorrow_start_utc)
        
        # Check if there's any redemption TODAY (in local timezone)
        todays_redemption = self.env['pos.loyalty.history'].search([
            ('card_id', '=', self.id),
            ('type', '=', 'redeemed'),
            ('create_date', '>=', today_start_utc),
            ('create_date', '<', tomorrow_start_utc),
        ], limit=1)
        
        if not todays_redemption:
            # No redemption today - allow
            _logger.info('LOYALTY COOLDOWN: Card %s has no redemption today, allowing', self.card_number)
            return {'allowed': True}
        
        # Already redeemed today - block until midnight
        next_allowed_local_str = tomorrow_start_local.strftime('%d-%b-%Y %I:%M %p')
        last_redeem_local = todays_redemption.create_date.replace(tzinfo=pytz.UTC).astimezone(user_tz)
        last_redeem_str = last_redeem_local.strftime('%d-%b-%Y %I:%M %p')
        
        # Calculate hours until midnight
        time_until_midnight = tomorrow_start_local - now_local
        hours_remaining = time_until_midnight.total_seconds() / 3600
        
        error_msg = _(
            "Redemption allowed only once per day.\n"
            "Already redeemed today at: %s\n"
            "Try again after: %s (midnight)\n"
            "(%.1f hours remaining)"
        ) % (
            last_redeem_str,
            next_allowed_local_str,
            hours_remaining
        )
        
        _logger.warning('LOYALTY COOLDOWN: Card %s blocked - already redeemed today at %s, next allowed at %s (%.1f hrs)', 
                       self.card_number, last_redeem_str, next_allowed_local_str, hours_remaining)
        
        # Return next_allowed_time as UTC datetime for storage/comparison
        tomorrow_start_utc_dt = tomorrow_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        
        return {
            'allowed': False,
            'error': error_msg,
            'next_allowed_time': tomorrow_start_utc_dt,
            'next_allowed_local': next_allowed_local_str,
            'hours_remaining': hours_remaining,
        }

    @api.model
    def check_redemption_eligibility(self, card_id):
        """
        Public API method to check if a card is eligible for redemption.
        Called from POS before opening Redeem Points popup.
        Uses daily midnight reset rule (local timezone).
        Returns: dict with 'eligible' (bool), 'reason' (str), 'next_allowed' (str datetime)
        """
        _logger.info('LOYALTY: check_redemption_eligibility called for card_id=%s', card_id)
        
        if not card_id:
            return {
                'eligible': False,
                'reason': 'No loyalty card selected.',
                'next_allowed': None,
            }
        
        card = self.browse(card_id)
        if not card.exists():
            return {
                'eligible': False,
                'reason': 'Loyalty card not found.',
                'next_allowed': None,
            }
        
        if card.state != 'active':
            return {
                'eligible': False,
                'reason': 'Loyalty card is not active.',
                'next_allowed': None,
            }
        
        # Check daily redemption limit (midnight reset)
        cooldown_check = card._check_redemption_cooldown()
        
        if cooldown_check.get('allowed'):
            return {
                'eligible': True,
                'reason': 'Redemption allowed.',
                'next_allowed': None,
            }
        else:
            next_allowed = cooldown_check.get('next_allowed_time')
            next_allowed_local = cooldown_check.get('next_allowed_local', '')
            return {
                'eligible': False,
                'reason': cooldown_check.get('error', 'Already redeemed today. Try again after midnight.'),
                'next_allowed': next_allowed.strftime('%Y-%m-%d %H:%M:%S') if next_allowed else None,
                'next_allowed_local': next_allowed_local,
            }

    @api.model
    def redeem_points(self, card_id, points, order_total):
        """
        CALCULATE redemption only - called from POS when clicking Redeem button
        This does NOT deduct points - just validates and returns discount value
        Actual deduction happens in confirm_redemption after payment
        """
        _logger.info('LOYALTY: redeem_points (calculate only) called: card_id=%s, points=%s, order_total=%s', 
                    card_id, points, order_total)
        
        card = self.browse(card_id)
        if not card.exists():
            return {'error': 'Card not found'}
        
        if card.state != 'active':
            return {'error': 'Card is not active'}
        
        # === 24-HOUR COOLDOWN CHECK ===
        cooldown_check = card._check_redemption_cooldown()
        if not cooldown_check.get('allowed'):
            _logger.warning('LOYALTY: Redemption blocked by 24-hour cooldown for card %s', card.card_number)
            return {'error': cooldown_check.get('error', 'Redemption not allowed yet. Try again later.')}
        
        if points > card.total_points:
            return {'error': 'Not enough points'}
        
        rule = self.env['pos.loyalty.rule'].get_active_rule()
        if not rule:
            return {'error': 'No active rule'}
        
        if points < rule.min_redeem_points:
            return {'error': 'Minimum %s points required' % rule.min_redeem_points}
        
        discount = points / rule.points_per_currency
        
        # DO NOT create history or deduct points here!
        # Just return calculation for display
        
        _logger.info('LOYALTY: Calculated redemption: %s points = %s discount (NOT deducted yet)', 
                    points, discount)
        
        return {
            'success': True,
            'points_redeemed': points,
            'discount_value': discount,
            'remaining_points': card.total_points,  # Points NOT deducted yet
            'card_id': card.id,
        }

    # === NEW: process_pos_redemption method (integrated from File 2 for Payment section popup) ===
    @api.model
    def process_pos_redemption(self, card_id, points_to_redeem, order_total, pos_order_id=None):
        """
        Process points redemption from POS.
        Returns discount amount and updated card info.
        """
        _logger.info('=== LOYALTY REDEMPTION: process_pos_redemption called ===')
        _logger.info('REDEMPTION: card_id=%s, points=%s, order_total=%s, pos_order_id=%s',
                    card_id, points_to_redeem, order_total, pos_order_id)
        
        card = self.browse(card_id)
        if not card.exists():
            _logger.error('REDEMPTION ERROR: Card ID %s not found', card_id)
            return {'error': 'Loyalty card not found.'}
        
        _logger.info('REDEMPTION: Card found - %s (%s), current points: %s', 
                    card.card_number, card.name, card.total_points)
        
        if card.state != 'active':
            _logger.error('REDEMPTION ERROR: Card %s is not active (state: %s)', card.card_number, card.state)
            return {'error': 'Loyalty card is not active.'}
        
        # === 24-HOUR COOLDOWN CHECK ===
        cooldown_check = card._check_redemption_cooldown()
        if not cooldown_check.get('allowed'):
            _logger.warning('REDEMPTION: Blocked by 24-hour cooldown for card %s', card.card_number)
            return {'error': cooldown_check.get('error', 'Redemption not allowed yet. Try again later.')}
        
        rule = self.env['pos.loyalty.rule'].get_active_rule()
        
        if not rule:
            _logger.error('REDEMPTION ERROR: No active loyalty rule found')
            return {'error': 'No active redemption rule found.'}
        
        _logger.info('REDEMPTION: Using rule - min_redeem=%s, points_per_currency=%s',
                    rule.min_redeem_points, rule.points_per_currency)
        
        # Validate minimum points
        if points_to_redeem < rule.min_redeem_points:
            _logger.warning('REDEMPTION: Points %s below minimum %s', points_to_redeem, rule.min_redeem_points)
            return {'error': 'Minimum redemption is %.0f points.' % rule.min_redeem_points}
        
        # Validate available points
        if points_to_redeem > card.total_points:
            _logger.warning('REDEMPTION: Insufficient points - requested %s, available %s', 
                          points_to_redeem, card.total_points)
            return {'error': 'Insufficient points. Available: %.2f' % card.total_points}
        
        # Calculate discount value
        discount_value = points_to_redeem / rule.points_per_currency
        
        # Check max redemption percentage (default 100%)
        max_redemption_percent = 100
        max_discount = order_total * (max_redemption_percent / 100)
        if discount_value > max_discount:
            discount_value = max_discount
            points_to_redeem = discount_value * rule.points_per_currency
        
        _logger.info('REDEMPTION: Creating history record - points=%s, type=redeemed', points_to_redeem)
        
        # Create redemption history with explicit commit
        try:
            history = self.env['pos.loyalty.history'].create({
                'card_id': card.id,
                'points': points_to_redeem,
                'type': 'redeemed',
                'description': 'POS Redemption - Order Total: %.2f' % order_total,
                'amount': order_total,
            })
            _logger.info('REDEMPTION SUCCESS: Created history record ID=%s for card %s', 
                        history.id, card.card_number)
            
            # Force flush to database
            self.env.cr.flush()
            
        except Exception as e:
            _logger.error('REDEMPTION ERROR: Failed to create history record: %s', str(e))
            return {'error': 'Failed to record redemption: %s' % str(e)}
        
        # Refresh card to get updated points
        card.invalidate_recordset(['total_points', 'points_value'])
        
        _logger.info('REDEMPTION COMPLETE: Card %s now has %s points (was %s)', 
                    card.card_number, card.total_points, card.total_points + points_to_redeem)
        
        return {
            'success': True,
            'points_redeemed': points_to_redeem,
            'discount_value': round(discount_value, 2),
            'remaining_points': card.total_points,
            'card_number': card.card_number,
            'customer_name': card.name,
            'history_id': history.id,
        }

    @api.model
    def confirm_redemption(self, card_id, points, order_name):
        """
        ACTUALLY deduct points - called from POS after payment is validated
        This creates the history record and deducts points
        """
        _logger.info('=== LOYALTY: confirm_redemption called ===')
        _logger.info('LOYALTY: card_id=%s, points=%s, order=%s', card_id, points, order_name)
        
        card = self.browse(card_id)
        if not card.exists():
            _logger.error('LOYALTY: Card not found for redemption confirmation')
            return {'error': 'Card not found'}
        
        _logger.info('LOYALTY: Card found - %s, current points: %s', card.card_number, card.total_points)
        
        if card.state != 'active':
            _logger.error('LOYALTY: Card %s is not active', card.card_number)
            return {'error': 'Card is not active'}
        
        # === 24-HOUR COOLDOWN CHECK (Final server-side validation) ===
        cooldown_check = card._check_redemption_cooldown()
        if not cooldown_check.get('allowed'):
            _logger.warning('LOYALTY: confirm_redemption blocked by 24-hour cooldown for card %s', card.card_number)
            return {'error': cooldown_check.get('error', 'Redemption not allowed yet. Try again later.')}
        
        if points > card.total_points:
            _logger.error('LOYALTY: Not enough points on card %s (has %s, needs %s)', 
                         card.card_number, card.total_points, points)
            return {'error': 'Not enough points'}
        
        rule = self.env['pos.loyalty.rule'].get_active_rule()
        if not rule:
            _logger.error('LOYALTY: No active loyalty rule found')
            return {'error': 'No active rule'}
        
        discount = points / rule.points_per_currency
        
        # Try to find the POS order by name for linking
        pos_order = None
        if order_name:
            pos_order = self.env['pos.order'].search([
                '|',
                ('name', '=', order_name),
                ('pos_reference', '=', order_name),
            ], limit=1)
        
        # NOW create redemption history with full details
        try:
            history_vals = {
                'card_id': card.id,
                'points': points,
                'type': 'redeemed',
                'description': 'POS Redemption: %s' % (order_name or 'Order'),
                'amount': discount,  # Store the discount amount
            }
            
            if pos_order:
                history_vals['order_id'] = pos_order.id
                _logger.info('LOYALTY: Linked to POS order ID %s', pos_order.id)
            
            history = self.env['pos.loyalty.history'].create(history_vals)
            _logger.info('LOYALTY: Created redemption history record ID=%s', history.id)
            
            # Force flush to ensure it's written to database
            self.env.cr.flush()
            
        except Exception as e:
            _logger.error('LOYALTY: Error creating redemption history: %s', str(e))
            return {'error': 'Failed to create redemption history: %s' % str(e)}
        
        # Refresh card to get updated points
        card.invalidate_recordset(['total_points', 'points_value'])
        
        _logger.info('LOYALTY SUCCESS: Deducted %s points from card %s for order %s', 
                    points, card.card_number, order_name)
        _logger.info('LOYALTY: Card now has %s points, discount was %s', card.total_points, discount)
        
        return {
            'success': True,
            'points_redeemed': points,
            'discount_value': discount,
            'remaining_points': card.total_points,
            'history_id': history.id,
        }

    @api.model
    def get_receipt_data(self, card_id, order_total, points_redeemed):
        """
        Calculate loyalty receipt data for POS receipt display.
        Called from JS before receipt is rendered.
        Returns: card_number, member_name, points_earned, points_redeemed, point_balance
        """
        _logger.info('LOYALTY RECEIPT: get_receipt_data called - card_id=%s, order_total=%s, points_redeemed=%s',
                     card_id, order_total, points_redeemed)

        if not card_id:
            return {'error': 'No card ID provided'}

        card = self.browse(card_id)
        if not card.exists():
            return {'error': 'Card not found'}

        # Get active rule for points calculation
        rule = self.env['pos.loyalty.rule'].get_active_rule()

        # Calculate estimated points to be earned
        points_earned = 0
        if rule and rule.spend_amount > 0 and order_total > 0:
            # Use the actual order total (before loyalty discount) for earning
            # If there was a redemption, the discount line reduces total,
            # but points should be earned on the actual product total
            effective_total = order_total
            if points_redeemed > 0 and rule.points_per_currency > 0:
                # Add back the discount amount to get the real product total
                discount_amount = points_redeemed / rule.points_per_currency
                effective_total = order_total + discount_amount

            points_earned = (effective_total / rule.spend_amount) * rule.points_earned
            points_earned = round(points_earned, 2)

        # Current balance (before this transaction)
        current_points = card.total_points

        # Projected balance after this transaction
        # Note: points_redeemed may have already been deducted via confirm_redemption
        # or may be pending - we calculate the projected final balance
        point_balance = current_points + points_earned
        # If redemption hasn't been confirmed yet, subtract it
        # (it will be confirmed after validateOrder)
        if points_redeemed > 0:
            point_balance = current_points - points_redeemed + points_earned

        _logger.info('LOYALTY RECEIPT: card=%s, earned=%s, redeemed=%s, balance=%s',
                     card.card_number, points_earned, points_redeemed, point_balance)

        return {
            'card_number': card.card_number,
            'member_name': card.name,
            'points_earned': points_earned,
            'points_redeemed': points_redeemed,
            'point_balance': max(0, round(point_balance, 2)),
        }

    @api.model  
    def get_or_create_partner(self, card_id):
        """Ensure card has a partner and return partner_id - called from POS"""
        card = self.browse(card_id)
        if not card.exists():
            return False
        
        if card.partner_id:
            _logger.info('LOYALTY: Card %s already has partner %s', card.card_number, card.partner_id.id)
            return card.partner_id.id
        
        # Create partner
        partner = card._create_or_get_partner(card.name, card.phone, card.email)
        if partner:
            card.partner_id = partner.id
            _logger.info('LOYALTY: Created/linked partner %s to card %s', partner.id, card.card_number)
            return partner.id
        
        return False
