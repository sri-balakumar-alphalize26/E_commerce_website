from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import base64
import re
import logging
from io import BytesIO

_logger = logging.getLogger(__name__)

try:
    from barcode import Code128
    from barcode.writer import ImageWriter
    BARCODE_AVAILABLE = True
except ImportError:
    BARCODE_AVAILABLE = False


class PosLoyaltyCard(models.Model):
    _name = 'pos.loyalty.card'
    _description = 'POS Loyalty Card'
    _rec_name = 'card_number'
    _order = 'registration_date desc'

    name = fields.Char(
        string='Customer Name',
        required=True,
    )
    phone = fields.Char(
        string='Phone Number',
        required=True,
    )
    email = fields.Char(
        string='Email',
    )
    card_number = fields.Char(
        string='Card Number',
        readonly=True,
        copy=False,
        default='New',
    )
    barcode = fields.Char(
        string='Barcode',
        readonly=True,
        copy=False,
    )
    barcode_image = fields.Binary(
        string='Barcode Image',
        compute='_compute_barcode_image',
        store=True,
    )
    total_points = fields.Float(
        string='Total Points',
        compute='_compute_total_points',
        store=True,
        digits=(16, 2),
    )
    points_value = fields.Float(
        string='Points Value',
        compute='_compute_points_value',
        digits=(16, 2),
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
    ], string='Status', default='draft')
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        ondelete='restrict',
    )
    points_history_ids = fields.One2many(
        'pos.loyalty.points.history',
        'card_id',
        string='Points History',
    )
    registration_date = fields.Datetime(
        string='Registration Date',
        default=fields.Datetime.now,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        ('card_number_unique', 'unique(card_number)', 'Card number must be unique!'),
        ('barcode_unique', 'unique(barcode)', 'Barcode must be unique!'),
        ('phone_unique', 'unique(phone)', 'Phone number must be unique!'),
    ]

    @api.constrains('phone')
    def _check_phone_format(self):
        for record in self:
            if record.phone:
                cleaned = re.sub(r'[\s\-\(\)\+]', '', record.phone)
                valid_patterns = [
                    r'^[6-9]\d{9}$',
                    r'^91[6-9]\d{9}$',
                    r'^0[6-9]\d{9}$',
                ]
                if not any(re.match(pattern, cleaned) for pattern in valid_patterns):
                    raise ValidationError(_(
                        'Invalid phone number format. Please enter a valid 10-digit mobile number.'
                    ))

    def _normalize_phone(self, phone):
        if not phone:
            return phone
        cleaned = re.sub(r'\D', '', phone)
        if cleaned.startswith('91') and len(cleaned) == 12:
            cleaned = cleaned[2:]
        elif cleaned.startswith('0') and len(cleaned) == 11:
            cleaned = cleaned[1:]
        return cleaned if len(cleaned) == 10 else phone

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('card_number', 'New') == 'New':
                vals['card_number'] = self.env['ir.sequence'].next_by_code(
                    'pos.loyalty.card') or 'LC000001'
            
            if not vals.get('barcode'):
                card_num = vals['card_number']
                vals['barcode'] = card_num.replace('LC', '') if card_num else ''
            
            if not vals.get('partner_id'):
                existing_partner = self.env['res.partner'].search([
                    ('phone', '=', vals.get('phone'))
                ], limit=1)
                
                if existing_partner:
                    vals['partner_id'] = existing_partner.id
                    existing_partner.write({'barcode': vals['barcode']})
                else:
                    partner = self.env['res.partner'].create({
                        'name': vals.get('name'),
                        'phone': vals.get('phone'),
                        'email': vals.get('email'),
                        'barcode': vals['barcode'],
                        'customer_rank': 1,
                    })
                    vals['partner_id'] = partner.id
        
        return super().create(vals_list)

    @api.depends('barcode')
    def _compute_barcode_image(self):
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

    @api.depends('points_history_ids.points', 'points_history_ids.transaction_type')
    def _compute_total_points(self):
        for record in self:
            earned = sum(record.points_history_ids.filtered(
                lambda h: h.transaction_type == 'earned'
            ).mapped('points'))
            redeemed = sum(record.points_history_ids.filtered(
                lambda h: h.transaction_type == 'redeemed'
            ).mapped('points'))
            record.total_points = earned - redeemed

    @api.depends('total_points')
    def _compute_points_value(self):
        for record in self:
            rule = self.env['pos.loyalty.points.rule'].search([
                ('is_active', '=', True),
            ], limit=1)
            if rule and rule.redemption_points_per_unit > 0:
                record.points_value = record.total_points / rule.redemption_points_per_unit
            else:
                record.points_value = 0.0

    def action_activate(self):
        for record in self:
            if record.state == 'draft':
                record.state = 'active'
        return True

    def action_suspend(self):
        for record in self:
            if record.state == 'active':
                record.state = 'suspended'
        return True

    def action_reactivate(self):
        for record in self:
            if record.state == 'suspended':
                record.state = 'active'
        return True

    def action_print_card(self):
        self.ensure_one()
        return self.env.ref('pos_loyalty_card.action_report_loyalty_card').report_action(self)

    def action_send_whatsapp(self):
        self.ensure_one()
        if not self.phone:
            raise ValidationError(_('Phone number is required to send WhatsApp message.'))
        
        phone = self.phone.replace(' ', '').replace('-', '').replace('+', '')
        if not phone.startswith('91'):
            phone = '91' + phone
        
        message = (
            "Dear %s,\n\n"
            "Welcome to our Loyalty Program!\n\n"
            "Your Loyalty Card Number: %s\n"
            "Current Points: %.0f\n"
            "Points Value: ₹%.2f\n\n"
            "Thank you for being a valued customer!"
        ) % (self.name, self.card_number, self.total_points, self.points_value)
        
        encoded_message = message.replace('\n', '%0A').replace(' ', '%20')
        whatsapp_url = f'https://wa.me/{phone}?text={encoded_message}'
        
        return {
            'type': 'ir.actions.act_url',
            'url': whatsapp_url,
            'target': 'new',
        }

    def action_add_test_points(self):
        """Add 500 test points for testing"""
        for card in self:
            if card.state == 'active':
                self.env['pos.loyalty.points.history'].create({
                    'card_id': card.id,
                    'points': 500,
                    'transaction_type': 'earned',
                    'description': 'Test Points Added',
                })

    # ==================== POS Integration Methods ====================

    @api.model
    def search_by_phone_or_card(self, search_term):
        """Search card by phone or card number - called from POS UI"""
        _logger.info('LOYALTY: search_by_phone_or_card called with: %s', search_term)
        
        if not search_term:
            return {'error': 'Please enter phone or card number'}
        
        clean_term = str(search_term).strip()
        
        card = self.search([
            ('state', '=', 'active'),
            '|',
            ('phone', '=', clean_term),
            ('card_number', '=', clean_term),
        ], limit=1)
        
        if not card:
            clean_digits = ''.join(filter(str.isdigit, clean_term))
            if len(clean_digits) >= 10:
                search_pattern = clean_digits[-10:]
                card = self.search([
                    ('state', '=', 'active'),
                    ('phone', 'ilike', search_pattern),
                ], limit=1)
        
        if not card:
            card = self.search([
                ('state', '=', 'active'),
                ('card_number', 'ilike', clean_term),
            ], limit=1)
        
        if not card:
            _logger.info('LOYALTY: No card found for: %s', search_term)
            return {'error': 'No card found'}
        
        _logger.info('LOYALTY: Found card %s (ID: %s)', card.card_number, card.id)
        
        rule = self.env['pos.loyalty.points.rule'].search([('is_active', '=', True)], limit=1)
        min_points = rule.min_redemption_points if rule else 5000
        points_per_currency = rule.redemption_points_per_unit if rule else 10
        
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
        }

    @api.model
    def create_new_card(self, name, phone, email=False):
        """Create new card from POS"""
        _logger.info('LOYALTY: create_new_card: name=%s, phone=%s', name, phone)
        
        if not name or not phone:
            return {'error': 'Name and phone are required'}
        
        clean_phone = ''.join(filter(str.isdigit, str(phone)))
        
        existing = self.search([
            '|',
            ('phone', '=', phone),
            ('phone', '=', clean_phone),
        ], limit=1)
        
        if existing:
            return {'error': 'Card already exists: ' + existing.card_number}
        
        card = self.create({
            'name': name,
            'phone': phone,
            'email': email,
            'state': 'active',
        })
        
        _logger.info('LOYALTY: Created card %s (ID: %s)', card.card_number, card.id)
        
        return {
            'success': True,
            'id': card.id,
            'card_number': card.card_number,
            'name': card.name,
            'phone': card.phone,
            'partner_id': card.partner_id.id if card.partner_id else False,
            'total_points': 0,
        }

    @api.model
    def redeem_points(self, card_id, points, order_total):
        """Calculate redemption - does NOT deduct points"""
        _logger.info('LOYALTY: redeem_points (calculate): card_id=%s, points=%s', card_id, points)
        
        card = self.browse(card_id)
        if not card.exists():
            return {'error': 'Card not found'}
        
        if card.state != 'active':
            return {'error': 'Card is not active'}
        
        if points > card.total_points:
            return {'error': 'Not enough points'}
        
        rule = self.env['pos.loyalty.points.rule'].search([('is_active', '=', True)], limit=1)
        if not rule:
            return {'error': 'No active rule'}
        
        if points < rule.min_redemption_points:
            return {'error': 'Minimum %s points required' % int(rule.min_redemption_points)}
        
        discount = points / rule.redemption_points_per_unit
        
        max_discount = order_total * (rule.max_redemption_percent / 100)
        if discount > max_discount:
            discount = max_discount
            points = discount * rule.redemption_points_per_unit
        
        _logger.info('LOYALTY: Calculated: %s points = %s discount', points, discount)
        
        return {
            'success': True,
            'points_redeemed': points,
            'discount_value': discount,
            'remaining_points': card.total_points,
            'card_id': card.id,
        }

    @api.model
    def confirm_redemption(self, card_id, points, order_name):
        """Actually deduct points - called after payment"""
        _logger.info('LOYALTY: confirm_redemption: card_id=%s, points=%s, order=%s', 
                    card_id, points, order_name)
        
        card = self.browse(card_id)
        if not card.exists():
            return {'error': 'Card not found'}
        
        if card.state != 'active':
            return {'error': 'Card is not active'}
        
        if points > card.total_points:
            return {'error': 'Not enough points'}
        
        rule = self.env['pos.loyalty.points.rule'].search([('is_active', '=', True)], limit=1)
        if not rule:
            return {'error': 'No active rule'}
        
        discount = points / rule.redemption_points_per_unit
        
        self.env['pos.loyalty.points.history'].create({
            'card_id': card.id,
            'points': points,
            'transaction_type': 'redeemed',
            'description': 'POS Redemption: %s' % (order_name or 'Order'),
            'amount': discount,
        })
        
        _logger.info('LOYALTY SUCCESS: Deducted %s points from card %s', points, card.card_number)
        
        return {
            'success': True,
            'points_redeemed': points,
            'discount_value': discount,
            'remaining_points': card.total_points,
        }
