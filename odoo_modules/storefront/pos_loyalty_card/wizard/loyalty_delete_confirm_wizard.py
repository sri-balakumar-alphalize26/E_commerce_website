from odoo import models, fields, api, _
from odoo.exceptions import UserError
import re
import logging

_logger = logging.getLogger(__name__)


# =========================================================================
# Shared phone normalization utility
# =========================================================================
def normalize_phone(phone, country_phone_code=91, local_length=10):
    """
    Normalize a phone number:
    - Strip spaces, hyphens, parentheses
    - Ensure starts with +<country_code>
    - Keep only digits after +
    Returns normalized phone string like +919876543210

    country_phone_code and local_length come from the global loyalty settings
    (Configuration > Loyalty > Loyalty Settings) so behaviour follows the
    configured country.
    """
    if not phone:
        return ''
    # Remove all non-digit characters except leading +
    cleaned = re.sub(r'[^\d+]', '', str(phone).strip())
    # Extract digits only
    digits = re.sub(r'\D', '', cleaned)

    if not digits:
        return phone  # Return original if no digits found

    # Country code -> digits only (accepts 91, '91', '+91')
    country_code = re.sub(r'\D', '', str(country_phone_code)) if country_phone_code else '91'
    country_code = country_code or '91'
    try:
        local_length = int(local_length) or 10
    except (TypeError, ValueError):
        local_length = 10

    # Already has country code prefix
    if digits.startswith(country_code) and len(digits) == len(country_code) + local_length:
        return '+' + digits
    # Starts with 0 (trunk prefix) - remove it and add country code
    if digits.startswith('0') and len(digits) == local_length + 1:
        return '+' + country_code + digits[1:]
    # Plain local-length number
    if len(digits) == local_length:
        return '+' + country_code + digits
    # Already looks international but different code — keep as is with +
    if len(digits) > local_length:
        return '+' + digits

    # Short number — just prefix country code
    return '+' + country_code + digits


def get_phone_digits(phone):
    """Extract last 10 digits from any phone format for matching."""
    if not phone:
        return ''
    digits = re.sub(r'\D', '', str(phone))
    return digits[-10:] if len(digits) >= 10 else digits


# =========================================================================
# Delete Confirmation Wizard
# =========================================================================
class LoyaltyDeleteConfirmWizard(models.TransientModel):
    _name = 'loyalty.delete.confirm.wizard'
    _description = 'Delete Confirmation Wizard'

    # Source info
    source_model = fields.Selection([
        ('loyalty', 'Loyalty Cards'),
        ('customer', 'Customer Details'),
    ], string='Delete From', readonly=True)

    # Display fields (computed HTML summary)
    warning_message = fields.Html(string='Warning', readonly=True)

    # Hidden IDs to process
    loyalty_card_ids = fields.Many2many(
        'pos.loyalty.card', 'wizard_loyalty_card_rel',
        'wizard_id', 'card_id',
        string='Loyalty Cards to Delete',
    )
    partner_ids = fields.Many2many(
        'res.partner', 'wizard_partner_rel',
        'wizard_id', 'partner_id',
        string='Customers to Delete',
    )

    # Linked records found (for cross-delete)
    linked_loyalty_ids = fields.Many2many(
        'pos.loyalty.card', 'wizard_linked_loyalty_rel',
        'wizard_id', 'card_id',
        string='Linked Loyalty Cards',
    )
    linked_partner_ids = fields.Many2many(
        'res.partner', 'wizard_linked_partner_rel',
        'wizard_id', 'partner_id',
        string='Linked Customers',
    )

    @api.model
    def open_delete_wizard_loyalty(self, card_ids):
        """
        Called when deleting from Loyalty Cards.
        Finds linked customers by normalized phone and shows confirmation.
        """
        cards = self.env['pos.loyalty.card'].browse(card_ids)
        if not cards.exists():
            raise UserError(_('No loyalty cards selected.'))

        # Find matching partners by phone (try multiple matching strategies)
        linked_partners = self.env['res.partner']
        for card in cards:
            if not card.phone:
                continue
            digits = get_phone_digits(card.phone)
            if not digits or len(digits) < 10:
                continue

            # Strategy 1: Match by partner_id directly on the card
            if card.partner_id and not card.partner_id.is_customer_deleted:
                linked_partners |= card.partner_id

            # Strategy 2: Search by last 10 digits of phone
            partners = self.env['res.partner'].search([
                ('phone', 'ilike', digits[-10:]),
                ('is_customer_deleted', '=', False),
                ('is_company', '=', False),
            ])
            linked_partners |= partners

            # Strategy 3: Also try with country code prefix
            partners2 = self.env['res.partner'].search([
                '|',
                ('phone', 'ilike', '+91' + digits[-10:]),
                ('phone', 'ilike', digits[-10:]),
                ('is_customer_deleted', '=', False),
                ('is_company', '=', False),
            ])
            linked_partners |= partners2

        # Build warning HTML
        warning = self._build_loyalty_warning(cards, linked_partners)

        wizard = self.create({
            'source_model': 'loyalty',
            'warning_message': warning,
            'loyalty_card_ids': [(6, 0, cards.ids)],
            'linked_partner_ids': [(6, 0, linked_partners.ids)],
        })

        return {
            'name': _('Confirm Delete'),
            'type': 'ir.actions.act_window',
            'res_model': 'loyalty.delete.confirm.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
            'context': {'dialog_size': 'medium'},
        }

    @api.model
    def open_delete_wizard_customer(self, partner_ids):
        """
        Called when deleting from Customer Details.
        Finds linked loyalty cards by normalized phone and shows confirmation.
        """
        partners = self.env['res.partner'].browse(partner_ids)
        if not partners.exists():
            raise UserError(_('No customers selected.'))

        # Find matching loyalty cards by phone (try multiple matching strategies)
        linked_cards = self.env['pos.loyalty.card']
        for partner in partners:
            # Strategy 1: Search by partner_id link
            cards_by_partner = self.env['pos.loyalty.card'].search([
                ('partner_id', '=', partner.id),
                ('is_deleted', '=', False),
            ])
            linked_cards |= cards_by_partner

            # Strategy 2: Search by phone digits
            digits = get_phone_digits(partner.phone)
            if digits and len(digits) >= 10:
                cards_by_phone = self.env['pos.loyalty.card'].search([
                    '|',
                    ('phone', 'ilike', digits[-10:]),
                    ('phone', 'ilike', '+91' + digits[-10:]),
                    ('is_deleted', '=', False),
                ])
                linked_cards |= cards_by_phone

        # Build warning HTML
        warning = self._build_customer_warning(partners, linked_cards)

        wizard = self.create({
            'source_model': 'customer',
            'warning_message': warning,
            'partner_ids': [(6, 0, partners.ids)],
            'linked_loyalty_ids': [(6, 0, linked_cards.ids)],
        })

        return {
            'name': _('Confirm Delete'),
            'type': 'ir.actions.act_window',
            'res_model': 'loyalty.delete.confirm.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
            'context': {'dialog_size': 'medium'},
        }

    def _build_loyalty_warning(self, cards, linked_partners):
        """Build HTML warning for loyalty card deletion."""
        html = '<div style="font-size: 14px;">'
        html += '<h3 style="color: #d9534f;">⚠️ Delete Confirmation</h3>'

        # Cards being deleted
        html += '<p><strong>Loyalty Card(s) to be deleted:</strong></p>'
        html += '<table class="table table-sm table-bordered" style="margin-bottom: 12px;">'
        html += '<thead><tr><th>Card Number</th><th>Customer</th><th>Mobile</th><th>Points</th><th>Value (₹)</th></tr></thead><tbody>'
        for card in cards:
            html += '<tr><td>%s</td><td>%s</td><td>%s</td><td>%.2f</td><td>₹%.2f</td></tr>' % (
                card.card_number, card.name, card.phone, card.total_points, card.points_value
            )
        html += '</tbody></table>'

        # Linked customers
        if linked_partners:
            html += '<div class="alert alert-warning" style="margin-top: 8px;">'
            html += '<strong>⚠️ The following Customer(s) share the same mobile number and will ALSO be deleted:</strong>'
            html += '</div>'
            html += '<table class="table table-sm table-bordered">'
            html += '<thead><tr><th>Customer Name</th><th>Mobile</th><th>Email</th></tr></thead><tbody>'
            for partner in linked_partners:
                html += '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                    partner.name, partner.phone or '', partner.email or '-'
                )
            html += '</tbody></table>'
        else:
            html += '<div class="alert alert-info">No linked customers found for the selected mobile number(s).</div>'

        html += '</div>'
        return html

    def _build_customer_warning(self, partners, linked_cards):
        """Build HTML warning for customer deletion."""
        html = '<div style="font-size: 14px;">'
        html += '<h3 style="color: #d9534f;">⚠️ Delete Confirmation</h3>'

        # Customers being deleted
        html += '<p><strong>Customer(s) to be deleted:</strong></p>'
        html += '<table class="table table-sm table-bordered" style="margin-bottom: 12px;">'
        html += '<thead><tr><th>Customer Name</th><th>Mobile</th><th>Email</th></tr></thead><tbody>'
        for partner in partners:
            html += '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                partner.name, partner.phone or '', partner.email or '-'
            )
        html += '</tbody></table>'

        # Linked loyalty cards
        if linked_cards:
            html += '<div class="alert alert-warning" style="margin-top: 8px;">'
            html += '<strong>⚠️ The following Loyalty Card(s) share the same mobile number and will ALSO be deleted:</strong>'
            html += '</div>'
            html += '<table class="table table-sm table-bordered">'
            html += '<thead><tr><th>Card Number</th><th>Customer</th><th>Mobile</th><th>Points</th><th>Value (₹)</th></tr></thead><tbody>'
            for card in linked_cards:
                html += '<tr><td>%s</td><td>%s</td><td>%s</td><td style="color: #d9534f; font-weight: bold;">%.2f</td><td style="color: #d9534f; font-weight: bold;">₹%.2f</td></tr>' % (
                    card.card_number, card.name, card.phone, card.total_points, card.points_value
                )
            html += '</tbody></table>'
            total_pts = sum(linked_cards.mapped('total_points'))
            total_val = sum(linked_cards.mapped('points_value'))
            html += '<div class="alert alert-danger"><strong>Total Points to be lost: %.2f (₹%.2f)</strong></div>' % (total_pts, total_val)
        else:
            html += '<div class="alert alert-info">No linked loyalty cards found for the selected mobile number(s).</div>'

        html += '</div>'
        return html

    def action_confirm_delete(self):
        """Execute the confirmed deletion on both sides."""
        self.ensure_one()

        if self.source_model == 'loyalty':
            # Delete loyalty cards (soft delete)
            for card in self.loyalty_card_ids:
                _logger.info('WIZARD DELETE: Soft-deleting loyalty card %s', card.card_number)
                card.write({
                    'is_deleted': True,
                    'deleted_date': fields.Datetime.now(),
                    'state': 'suspended',
                })
            # Also soft-delete linked customers
            for partner in self.linked_partner_ids:
                _logger.info('WIZARD DELETE: Soft-deleting linked customer %s (ID: %s)', partner.name, partner.id)
                partner.write({
                    'is_customer_deleted': True,
                    'customer_deleted_date': fields.Datetime.now(),
                })

            # Return action to reload Loyalty Cards list
            return {
                'type': 'ir.actions.act_window',
                'name': _('Loyalty Cards'),
                'res_model': 'pos.loyalty.card',
                'view_mode': 'list,form',
                'domain': [('is_deleted', '=', False)],
                'target': 'main',
            }

        elif self.source_model == 'customer':
            # Soft-delete customers
            for partner in self.partner_ids:
                _logger.info('WIZARD DELETE: Soft-deleting customer %s (ID: %s)', partner.name, partner.id)
                partner.write({
                    'is_customer_deleted': True,
                    'customer_deleted_date': fields.Datetime.now(),
                })
            # Also soft-delete linked loyalty cards
            for card in self.linked_loyalty_ids:
                _logger.info('WIZARD DELETE: Soft-deleting linked loyalty card %s', card.card_number)
                card.write({
                    'is_deleted': True,
                    'deleted_date': fields.Datetime.now(),
                    'state': 'suspended',
                })

            # Return action to reload Customer Details list (with not_deleted filter)
            return {
                'type': 'ir.actions.act_window',
                'name': _('Customer Details'),
                'res_model': 'res.partner',
                'view_mode': 'list,form',
                'view_ids': [
                    (5, 0, 0),
                    (0, 0, {'view_mode': 'list', 'view_id': self.env.ref('pos_loyalty_card.view_customer_details_list').id}),
                    (0, 0, {'view_mode': 'form', 'view_id': self.env.ref('pos_loyalty_card.view_customer_details_form').id}),
                ],
                'search_view_id': [self.env.ref('pos_loyalty_card.view_customer_details_search').id],
                'domain': [('phone', '!=', False), ('is_company', '=', False), ('is_customer_deleted', '=', False)],
                'context': {
                    'search_default_has_phone': 1,
                    'customer_details_view': True,
                },
                'target': 'main',
            }

        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        """Cancel deletion."""
        return {'type': 'ir.actions.act_window_close'}
