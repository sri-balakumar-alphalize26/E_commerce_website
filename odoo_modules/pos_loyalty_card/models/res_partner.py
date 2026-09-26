from odoo import models, fields, _, api
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    pos_order_ids = fields.One2many(
        'pos.order', 'partner_id',
        string='POS Orders',
    )
    pos_order_count = fields.Integer(
        string='POS Order Count',
        compute='_compute_pos_order_count',
    )
    loyalty_card_ids = fields.One2many(
        'pos.loyalty.card', 'partner_id',
        string='Loyalty Cards',
    )

    # Soft Delete fields for Customer Details trash feature
    is_customer_deleted = fields.Boolean(string='Deleted', default=False, index=True)
    customer_deleted_date = fields.Datetime(string='Deleted Date')

    def init(self):
        """Ensure is_customer_deleted column exists and has proper defaults.
        Runs on every module install/upgrade to prevent registry crash."""
        self.env.cr.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'res_partner' AND column_name = 'is_customer_deleted'
                ) THEN
                    ALTER TABLE res_partner ADD COLUMN is_customer_deleted BOOLEAN DEFAULT FALSE;
                END IF;
                UPDATE res_partner SET is_customer_deleted = FALSE WHERE is_customer_deleted IS NULL;
                ALTER TABLE res_partner ALTER COLUMN is_customer_deleted SET DEFAULT FALSE;
                ALTER TABLE res_partner ALTER COLUMN is_customer_deleted SET NOT NULL;
            END $$;
        """)

    def _compute_pos_order_count(self):
        for partner in self:
            partner.pos_order_count = len(partner.pos_order_ids)

    @api.model
    def _loyalty_mobile_cfg(self):
        """(dial_code_digits, local_length) from the global Loyalty Settings."""
        cfg = self.env['pos.loyalty.card.settings'].get_settings()
        dial = ''.join(filter(str.isdigit, cfg.country_dial_code or '')) or (
            str(self.env.company.country_id.phone_code) if self.env.company.country_id else '91')
        return dial, (cfg.mobile_number_length or 10)

    @api.model_create_multi
    def create(self, vals_list):
        """Override to normalize phone using the loyalty country config."""
        from ..wizard.loyalty_delete_confirm_wizard import normalize_phone
        dial, length = self._loyalty_mobile_cfg()
        for vals in vals_list:
            if vals.get('phone'):
                vals['phone'] = normalize_phone(vals['phone'], dial, length)
        return super().create(vals_list)

    def write(self, vals):
        """Override to normalize phone using the loyalty country config."""
        if vals.get('phone'):
            from ..wizard.loyalty_delete_confirm_wizard import normalize_phone
            dial, length = self._loyalty_mobile_cfg()
            vals['phone'] = normalize_phone(vals['phone'], dial, length)
        return super().write(vals)

    def action_open_delete_wizard(self):
        """Open delete confirmation wizard for selected customers."""
        return self.env['loyalty.delete.confirm.wizard'].open_delete_wizard_customer(self.ids)

    def _generate_loyalty_cards(self):
        """Make sure every customer in self that has a mobile ends up with an
        ACTIVE loyalty card: create one if missing, or activate an existing
        draft/suspended card. Returns (created, activated, skipped)."""
        Card = self.env['pos.loyalty.card']
        created = 0
        activated = 0
        skipped = 0
        for partner in self:
            if partner.is_customer_deleted or not partner.phone:
                skipped += 1
                continue
            cards = Card.search([('partner_id', '=', partner.id), ('is_deleted', '=', False)])
            if cards:
                drafts = cards.filtered(lambda c: c.state != 'active')
                if drafts:
                    drafts.write({'state': 'active'})
                    activated += 1
                else:
                    skipped += 1
                continue
            Card.create({
                'name': partner.name or partner.phone,
                'phone': partner.phone,
                'partner_id': partner.id,
                'state': 'active',
            })
            created += 1
        return created, activated, skipped

    def _generate_cards_notification(self, created, activated, skipped):
        message = _(
            "%(created)s created, %(activated)s activated, %(skipped)s skipped "
            "(already active or no mobile number)."
        ) % {'created': created, 'activated': activated, 'skipped': skipped}
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Generate Loyalty Cards'),
                'message': message,
                'type': 'success' if (created or activated) else 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_generate_loyalty_card(self):
        """Ensure the selected customers have an active loyalty card."""
        created, activated, skipped = self._generate_loyalty_cards()
        return self._generate_cards_notification(created, activated, skipped)

    @api.model
    def action_generate_all_loyalty_cards(self):
        """Ensure ALL customers with a mobile have an active card (control panel)."""
        partners = self.search([
            ('phone', '!=', False),
            ('is_company', '=', False),
            ('is_customer_deleted', '=', False),
        ])
        created, activated, skipped = partners._generate_loyalty_cards()
        return self._generate_cards_notification(created, activated, skipped)

    def action_view_pos_orders(self):
        """Open POS orders for this customer"""
        self.ensure_one()
        return {
            'name': _('POS Orders - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'pos.order',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'create': False},
        }

    def action_soft_delete_customer(self):
        """Soft-delete customers (move to trash)"""
        for partner in self:
            _logger.info('LOYALTY: Soft deleting customer %s (ID: %s)', partner.name, partner.id)
            partner.write({
                'is_customer_deleted': True,
                'customer_deleted_date': fields.Datetime.now(),
            })
        return True

    def action_restore_customer(self):
        """Restore soft-deleted customers back from trash"""
        for partner in self:
            _logger.info('LOYALTY: Restoring customer %s (ID: %s)', partner.name, partner.id)
            partner.write({
                'is_customer_deleted': False,
                'customer_deleted_date': False,
            })
        # Reload deleted customers popup so restored customer disappears
        return self.action_view_deleted_customers()

    def action_permanent_delete_customer(self):
        """Permanently delete customers (from trash - bypass soft-delete)"""
        model = self.env['res.partner']
        for partner in self:
            _logger.info('LOYALTY: Permanently deleting customer %s (ID: %s)', partner.name, partner.id)

            # Unlink partner from POS orders (set partner_id = False, don't delete orders)
            pos_orders = self.env['pos.order'].sudo().search([('partner_id', '=', partner.id)])
            if pos_orders:
                _logger.info('LOYALTY: Unlinking %d POS orders from partner %s', len(pos_orders), partner.name)
                pos_orders.write({'partner_id': False})

            # Permanently remove the partner's loyalty cards too (bypass the
            # soft-delete unlink) so no active card keeps the phone alive as an
            # "existing customer" after the customer is permanently deleted.
            loyalty_cards = self.env['pos.loyalty.card'].sudo().search([('partner_id', '=', partner.id)])
            if loyalty_cards:
                _logger.info('LOYALTY: Permanently deleting %d loyalty cards of partner %s', len(loyalty_cards), partner.name)
                loyalty_cards._hard_unlink()

        # Now permanently delete the partners
        self.sudo().unlink()

        # Reload deleted customers popup
        return model.action_view_deleted_customers()

    def action_force_delete_customer(self):
        """Soft delete customers (moved to trash instead of permanent delete)"""
        return self.action_soft_delete_customer()

    @api.model
    def action_view_deleted_customers(self):
        """Open deleted customers in a popup window - called from JS button"""
        return {
            'name': _('Deleted Customers'),
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('pos_loyalty_card.view_deleted_customer_details_list').id, 'list'),
                (self.env.ref('pos_loyalty_card.view_deleted_customer_details_form').id, 'form'),
            ],
            'search_view_id': [self.env.ref('pos_loyalty_card.view_deleted_customer_details_search').id],
            'domain': [('is_customer_deleted', '=', True)],
            'context': {
                'show_deleted': True,
                'create': False,
            },
            'target': 'new',
        }
