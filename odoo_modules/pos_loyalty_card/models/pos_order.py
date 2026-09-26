from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    loyalty_card_id = fields.Many2one('pos.loyalty.card', string='Loyalty Card', index=True, ondelete='set null')
    # These are computed server-side per order. copy=False so a backend refund
    # (created via order.copy()) does NOT inherit the original order's totals.
    loyalty_points_earned = fields.Float(string='Points Earned', default=0, copy=False)
    loyalty_points_redeemed = fields.Float(string='Points Redeemed', default=0, copy=False)
    loyalty_discount_amount = fields.Float(string='Loyalty Discount Amount', default=0, copy=False)
    loyalty_points_returned = fields.Float(string='Points Returned', default=0, copy=False)
    # Redeemed points credited back to the card when this refund order returns goods.
    loyalty_points_redeem_returned = fields.Float(string='Redeemed Points Refunded', default=0, copy=False)
    # On an ORIGINAL order: cumulative redeemed points already credited back across all its refunds.
    loyalty_points_redeem_credited = fields.Float(string='Redeemed Points Credited Back', default=0, copy=False)

    # ------------------------------------------------------------------
    # Override neonize's _send_whatsapp_notification to avoid duplicate
    # customer receipts — loyalty module sends its own detailed receipt
    # with points info via pos.loyalty.whatsapp.service
    # ------------------------------------------------------------------

    def _send_whatsapp_notification(self, order_id):
        """Override from whatsapp_neonize to skip customer receipt for loyalty orders.

        When an order has a loyalty card, the loyalty module already sends a
        detailed receipt (with points earned/redeemed/balance) from
        _earn_points_for_sale(). We only let the neonize module send
        owner notifications for loyalty orders, not customer notifications.
        """
        try:
            order = self.browse(order_id)
            if not order.exists():
                _logger.error("POS WA: Order %s not found", order_id)
                return

            if 'whatsapp.config' not in self.env:
                return
            config = self.env['whatsapp.config'].sudo().get_config(
                order.company_id.id
            )
            if not config.pos_notify_enabled:
                return

            # Determine if loyalty handles this order's customer receipt
            # Only skip if loyalty card is linked AND loyalty is enabled on this POS config
            has_loyalty_card = order.loyalty_card_id and order.loyalty_card_id.id
            loyalty_enabled = order.config_id and order.config_id.loyalty_active

            # Get WhatsApp session
            wa_session = config.pos_session_id
            if not wa_session:
                wa_session = self.env['whatsapp.session'].sudo().search([
                    '|',
                    ('company_id', '=', order.company_id.id),
                    ('company_id', '=', False),
                ], limit=1)

            if not wa_session:
                _logger.warning("POS WA: No WhatsApp session found")
                return

            # Format message for owner notification
            message = config.format_pos_message(order)

            # Send to owners (always — regardless of loyalty)
            if config.pos_notify_owners:
                for owner in config.owner_number_ids.filtered('active'):
                    try:
                        wa_session.send_message(owner.phone, message)
                        _logger.info("POS WA: SENT to owner %s (%s)", owner.name, owner.phone)
                    except Exception as e:
                        _logger.error("POS WA: FAILED to send to %s: %s", owner.phone, e)

            # Send to customer ONLY if NO loyalty card with loyalty ON (loyalty module sends its own receipt)
            if config.pos_notify_customer and order.partner_id and not (has_loyalty_card and loyalty_enabled):
                customer_phone = order.partner_id.phone
                if customer_phone:
                    customer_phone = customer_phone.replace('+', '').replace(' ', '').replace('-', '')
                    try:
                        wa_session.send_message(customer_phone, message)
                        _logger.info("POS WA: SENT to customer %s", customer_phone)
                    except Exception as e:
                        _logger.error("POS WA: FAILED to send to customer %s: %s", customer_phone, e)
            elif has_loyalty_card and loyalty_enabled:
                _logger.info(
                    "POS WA: Skipping customer receipt for order %s — "
                    "loyalty module handles receipt for card %s",
                    order.name, order.loyalty_card_id.card_number,
                )

        except Exception as e:
            _logger.error("POS WA notification error: %s", e, exc_info=True)

    def init(self):
        """Fix the foreign key constraint on loyalty_card_id to use SET NULL instead of RESTRICT.
        This prevents 'Another model is using the record' errors when loyalty cards are deleted."""
        try:
            self.env.cr.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'pos_order' 
                AND constraint_type = 'FOREIGN KEY'
                AND constraint_name LIKE '%loyalty_card_id%'
            """)
            constraints = self.env.cr.fetchall()
            for (constraint_name,) in constraints:
                _logger.info('LOYALTY: Fixing FK constraint %s to SET NULL', constraint_name)
                self.env.cr.execute("ALTER TABLE pos_order DROP CONSTRAINT IF EXISTS %s" % constraint_name)
            
            # Re-add the constraint with SET NULL
            self.env.cr.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'pos_order' AND column_name = 'loyalty_card_id'
                    ) THEN
                        ALTER TABLE pos_order 
                        ADD CONSTRAINT pos_order_loyalty_card_id_fkey 
                        FOREIGN KEY (loyalty_card_id) 
                        REFERENCES pos_loyalty_card(id) 
                        ON DELETE SET NULL;
                    END IF;
                EXCEPTION WHEN others THEN
                    NULL;
                END $$;
            """)
            _logger.info('LOYALTY: FK constraint fixed to SET NULL')
        except Exception as e:
            _logger.warning('LOYALTY: Could not fix FK constraint: %s', e)

    @api.model
    def _process_order(self, order, existing_order):
        """Override to capture loyalty_card_id from frontend before order is created"""
        loyalty_card_id = order.get('loyalty_card_id')

        # These fields are computed SERVER-SIDE only (in _process_loyalty_for_order).
        # The POS frontend copies them from the original order when creating a refund,
        # which makes a refund look "already processed" and skips the return handling.
        # Strip them so the server is the sole authority and refunds process correctly.
        order.pop('loyalty_points_earned', None)
        order.pop('loyalty_points_returned', None)

        # Validate loyalty_card_id exists before using it
        if loyalty_card_id:
            _logger.info('LOYALTY: _process_order received loyalty_card_id=%s', loyalty_card_id)
            try:
                card = self.env['pos.loyalty.card'].browse(loyalty_card_id)
                if not card.exists():
                    _logger.warning('LOYALTY: loyalty_card_id=%s does not exist, clearing it', loyalty_card_id)
                    loyalty_card_id = False
                    order.pop('loyalty_card_id', None)
                else:
                    if not order.get('partner_id') and card.partner_id:
                        order['partner_id'] = card.partner_id.id
                        _logger.info('LOYALTY: Set partner_id=%s from loyalty card', card.partner_id.id)
            except Exception as e:
                _logger.error('LOYALTY: Error validating loyalty card %s: %s', loyalty_card_id, e)
                loyalty_card_id = False
                order.pop('loyalty_card_id', None)
        
        result = super()._process_order(order, existing_order)
        
        if result:
            try:
                pos_order = self.env['pos.order'].browse(result)
                if pos_order.exists():
                    # Defensive: never let a newly created order inherit server-computed
                    # point totals from the frontend payload (esp. refund orders).
                    reset_vals = {}
                    if not existing_order:
                        if pos_order.loyalty_points_earned:
                            reset_vals['loyalty_points_earned'] = 0.0
                        if pos_order.loyalty_points_returned:
                            reset_vals['loyalty_points_returned'] = 0.0
                    if loyalty_card_id and not pos_order.loyalty_card_id:
                        reset_vals['loyalty_card_id'] = loyalty_card_id
                        _logger.info('LOYALTY: Linked loyalty_card_id=%s to order %s', loyalty_card_id, pos_order.name)
                    if reset_vals:
                        pos_order.write(reset_vals)
            except Exception as e:
                _logger.error('LOYALTY: Error linking loyalty card to order: %s (non-blocking)', e)

        return result

    def action_pos_order_paid(self):
        """Process loyalty points for all order types: sale, return, and exchange"""
        _logger.info('=== LOYALTY: action_pos_order_paid called for orders: %s ===', self.ids)
        result = super().action_pos_order_paid()
        
        for order in self:
            try:
                _logger.info('LOYALTY: Processing order %s (state: %s, amount: %s, partner: %s, card: %s)', 
                            order.name, order.state, order.amount_total, 
                            order.partner_id.id if order.partner_id else 'None',
                            order.loyalty_card_id.id if order.loyalty_card_id else 'None')
                order._process_loyalty_for_order()
            except Exception as e:
                _logger.error('LOYALTY: Error processing loyalty for order %s: %s (non-blocking)', 
                             order.name, str(e))
                # NEVER block payment due to loyalty errors
        
        return result

    # =========================================================================
    # === UNIFIED LOYALTY PROCESSING - Handles Sale, Return & Exchange ===
    # =========================================================================

    def _get_loyalty_discount_product_id(self):
        """Get the loyalty discount product ID to exclude from calculations"""
        try:
            product = self.env.ref('pos_loyalty_card.product_loyalty_redemption', raise_if_not_found=False)
            return product.id if product else False
        except Exception:
            return False

    def _is_loyalty_discount_line(self, line):
        """True if this order line is the loyalty-redemption discount line.
        Identified by MARKER, not just product id: the POS may apply the discount
        via a generic 'Discount' carrier product (not product_loyalty_redemption),
        so we match customer_note / full_product_name too. Without this, a refund
        of the discount line is mistaken for a real sale and earns bogus points."""
        disc_id = self._get_loyalty_discount_product_id()
        if disc_id and line.product_id.id == disc_id:
            return True
        note = (line.customer_note or '').strip().upper()
        if note == 'LOYALTY_DISCOUNT':
            return True
        fname = (line.full_product_name or '').lower()
        if 'loyalty' in fname and 'redemption' in fname:
            return True
        return False

    def _process_loyalty_for_order(self):
        """
        Process loyalty points by analyzing individual order lines.
        Handles ALL cases:
        - Pure sale: earn points on sale lines
        - Pure return: subtract points for return lines
        - Product exchange/change: earn on new products, subtract on returned products
        """
        self.ensure_one()

        # Skip if loyalty is disabled on this POS config
        # But still send WhatsApp receipt if customer is linked
        if self.config_id and not self.config_id.loyalty_active:
            _logger.info('LOYALTY: Loyalty cards disabled for POS config %s, skipping points for order %s',
                        self.config_id.name, self.name)
            # Still send WhatsApp receipt (without loyalty info)
            # Check loyalty card phone OR partner phone (customer-only mode has no loyalty card)
            has_phone = False
            if self.loyalty_card_id and self.loyalty_card_id.phone:
                has_phone = True
            elif self.partner_id and self.partner_id.phone:
                has_phone = True

            if has_phone:
                try:
                    self.env['pos.loyalty.whatsapp.service'].sudo().send_order_receipt_simple(self.id)
                except Exception as e:
                    _logger.error('LOYALTY WA: Error sending simple receipt for order %s: %s', self.name, e)
            else:
                _logger.info('LOYALTY WA: No phone found for order %s (no loyalty card and no partner phone)', self.name)
            return

        # NOTE: No blanket "already processed" guard here. It used to skip when
        # earned>0 AND returned>0, but backend refunds are created via order.copy()
        # and inherit those values, which made every backend refund skip. The
        # per-step helpers below are individually idempotent (earn only if
        # earned<=0, subtract only if returned<=0, credit-back only if no
        # redeem_returned row exists yet), so re-entry is safe without it.

        # Analyze order lines - separate sale lines from return lines
        sale_amount = 0.0
        return_amount = 0.0

        for line in self.lines:
            # Skip the loyalty redemption discount line (see _is_loyalty_discount_line).
            if self._is_loyalty_discount_line(line):
                _logger.info('LOYALTY: Skipping loyalty discount line: %s', line.product_id.name)
                continue

            if line.price_subtotal_incl >= 0:
                sale_amount += line.price_subtotal_incl
            else:
                return_amount += abs(line.price_subtotal_incl)

        _logger.info('LOYALTY: Order %s line analysis - sale_amount=%.2f, return_amount=%.2f',
                    self.name, sale_amount, return_amount)

        # Find loyalty card (needed for both earning and returning)
        card = self._find_loyalty_card_for_any_order()
        if not card:
            _logger.info('LOYALTY: No loyalty card found for order %s', self.name)
            return

        if card.state != 'active':
            _logger.info('LOYALTY: Card %s is not active (state: %s)', card.card_number, card.state)
            return

        # Get active rule
        rule = self.env['pos.loyalty.rule'].get_active_rule()
        if not rule or rule.spend_amount <= 0:
            _logger.warning('LOYALTY: No valid active loyalty rule found!')
            return

        # --- PROCESS RETURN/EXCHANGE LINES (subtract earned points) ---
        if return_amount > 0 and self.loyalty_points_returned <= 0:
            self._subtract_points_for_return(card, rule, return_amount)

        # --- CREDIT BACK REDEEMED POINTS on returns (proportional) ---
        if return_amount > 0:
            self._credit_back_redeemed_points_for_return(card, rule, return_amount)

        # --- PROCESS SALE LINES (earn points) ---
        if sale_amount > 0 and self.loyalty_points_earned <= 0:
            self._earn_points_for_sale(card, rule, sale_amount)

        # Link card to order if not yet linked
        if not self.loyalty_card_id:
            self.write({'loyalty_card_id': card.id})

        # Update last used date
        card.write({'last_used_date': fields.Datetime.now()})

    def _subtract_points_for_return(self, card, rule, return_amount):
        """Subtract loyalty points for returned/exchanged product lines"""
        self.ensure_one()

        points_to_subtract = (return_amount / rule.spend_amount) * rule.points_earned
        points_to_subtract = round(points_to_subtract, 2)

        if points_to_subtract <= 0:
            return

        # Cap at available points (don't go negative)
        if points_to_subtract > card.total_points:
            _logger.info('LOYALTY RETURN: Capping points from %s to %s (available balance)',
                        points_to_subtract, card.total_points)
            points_to_subtract = card.total_points

        if points_to_subtract <= 0:
            _logger.info('LOYALTY RETURN: Card %s has 0 points, nothing to subtract', card.card_number)
            return

        _logger.info('LOYALTY RETURN: Subtracting %s points from card %s for return of ₹%s',
                    points_to_subtract, card.card_number, return_amount)

        try:
            # Determine description based on order type
            if self.amount_total < 0:
                desc = 'POS Return: %s' % self.name
            else:
                desc = 'POS Product Change: %s' % self.name

            self.env['pos.loyalty.history'].create({
                'card_id': card.id,
                'points': points_to_subtract,
                'type': 'returned',
                'description': desc,
                'amount': return_amount,
                'order_id': self.id,
            })

            self.write({
                'loyalty_card_id': card.id,
                'loyalty_points_returned': points_to_subtract,
            })

            _logger.info('LOYALTY RETURN SUCCESS: Subtracted %.2f points from card %s for order %s',
                        points_to_subtract, card.card_number, self.name)

        except Exception as e:
            _logger.error('LOYALTY RETURN ERROR: Failed to subtract points for order %s: %s',
                         self.name, str(e))

    def _original_sale_base(self):
        """Gross product sale total of this order, excluding the loyalty discount line.
        Used as the denominator when apportioning redeemed points across returns."""
        self.ensure_one()
        base = 0.0
        for line in self.lines:
            if self._is_loyalty_discount_line(line):
                continue
            if line.price_subtotal_incl > 0:
                base += line.price_subtotal_incl
        return base

    def _credit_back_redeemed_points_for_return(self, card, rule, return_amount):
        """Credit redeemed points BACK to the card when goods are returned, in
        proportion to the amount returned vs the original order's gross sale.
        Capped so cumulative credit-back never exceeds what was redeemed."""
        self.ensure_one()

        # Don't double-process the same refund order.
        existing = self.env['pos.loyalty.history'].search([
            ('order_id', '=', self.id),
            ('type', '=', 'redeem_returned'),
        ], limit=1)
        if existing:
            return

        original = self._find_original_order()
        if not original:
            _logger.info('LOYALTY REDEEM-BACK: No original order for refund %s', self.name)
            return

        original_redeemed = original.loyalty_points_redeemed or 0.0
        if original_redeemed <= 0:
            return  # nothing was redeemed on the original order

        base = original._original_sale_base()
        if base <= 0:
            return

        proportion = min(1.0, return_amount / base)
        points_to_credit = round(original_redeemed * proportion, 2)

        # Cap by what's still un-credited across all returns of this original order.
        already = original.loyalty_points_redeem_credited or 0.0
        remaining = round(original_redeemed - already, 2)
        if points_to_credit > remaining:
            points_to_credit = remaining
        if points_to_credit <= 0:
            return

        _logger.info('LOYALTY REDEEM-BACK: Crediting %.2f pts to card %s for refund %s (orig %s redeemed=%.2f, base=%.2f, ret=%.2f)',
                     points_to_credit, card.card_number, self.name, original.name,
                     original_redeemed, base, return_amount)

        try:
            self.env['pos.loyalty.history'].create({
                'card_id': card.id,
                'points': points_to_credit,
                'type': 'redeem_returned',
                'description': 'Redeemed points refunded: %s' % self.name,
                'amount': return_amount,
                'order_id': self.id,
            })
            original.write({'loyalty_points_redeem_credited': already + points_to_credit})
            self.write({
                'loyalty_card_id': card.id,
                'loyalty_points_redeem_returned': points_to_credit,
            })
        except Exception as e:
            _logger.error('LOYALTY REDEEM-BACK ERROR for order %s: %s', self.name, str(e))

    @api.model
    def get_return_redeem_preview(self, original_order_id, return_amount):
        """POS helper: how many redeemed points would be credited back if
        `return_amount` of `original_order_id` is returned right now."""
        original = self.browse(original_order_id).exists()
        if not original:
            return {'points': 0.0, 'value': 0.0}
        original_redeemed = original.loyalty_points_redeemed or 0.0
        if original_redeemed <= 0:
            return {'points': 0.0, 'value': 0.0}
        base = original._original_sale_base()
        if base <= 0:
            return {'points': 0.0, 'value': 0.0}
        proportion = min(1.0, abs(return_amount) / base)
        pts = round(original_redeemed * proportion, 2)
        remaining = round(original_redeemed - (original.loyalty_points_redeem_credited or 0.0), 2)
        pts = max(0.0, min(pts, remaining))
        rule = self.env['pos.loyalty.rule'].get_active_rule()
        ppc = (rule.points_per_currency if rule else 10) or 10
        return {'points': pts, 'value': round(pts / ppc, 2)}

    def _earn_points_for_sale(self, card, rule, sale_amount):
        """Earn loyalty points for sale product lines"""
        self.ensure_one()

        points = (sale_amount / rule.spend_amount) * rule.points_earned
        points = round(points, 2)

        if points <= 0:
            return

        _logger.info('LOYALTY: Earning %s points for card %s on sale amount ₹%s',
                    points, card.card_number, sale_amount)

        try:
            self.env['pos.loyalty.history'].create({
                'card_id': card.id,
                'points': points,
                'type': 'earned',
                'description': 'POS Order: %s' % self.name,
                'amount': sale_amount,
                'order_id': self.id,
            })

            self.write({
                'loyalty_card_id': card.id,
                'loyalty_points_earned': points,
            })

            _logger.info('LOYALTY SUCCESS: Added %.2f points to card %s for order %s',
                        points, card.card_number, self.name)

            # Send WhatsApp receipt to customer
            try:
                self.env['pos.loyalty.whatsapp.service'].sudo().send_order_receipt(self.id)
            except Exception as e:
                _logger.error('LOYALTY WA: Error sending receipt for order %s: %s', self.name, e)

        except Exception as e:
            _logger.error('LOYALTY EARN ERROR: Failed to add points for order %s: %s',
                         self.name, str(e))

    # =========================================================================
    # === FIND LOYALTY CARD - Works for Sale, Return & Exchange ===
    # =========================================================================

    def _find_loyalty_card_for_any_order(self):
        """Find loyalty card using all available methods - works for any order type"""
        self.ensure_one()
        LoyaltyCard = self.env['pos.loyalty.card']

        _logger.info('LOYALTY: Finding card for order %s', self.name)

        # Method 1: Already linked via loyalty_card_id
        if self.loyalty_card_id and self.loyalty_card_id.state == 'active':
            _logger.info('LOYALTY: Found via loyalty_card_id: %s', self.loyalty_card_id.card_number)
            return self.loyalty_card_id

        # Method 2: Find original order's card (for returns/exchanges)
        original_order = self._find_original_order()
        if original_order and original_order.loyalty_card_id:
            _logger.info('LOYALTY: Found via original order %s -> card %s',
                        original_order.name, original_order.loyalty_card_id.card_number)
            return original_order.loyalty_card_id

        # Method 3: Find by partner_id
        if self.partner_id:
            card = LoyaltyCard.search([
                ('partner_id', '=', self.partner_id.id),
                ('state', '=', 'active'),
                ('is_deleted', '=', False),
            ], limit=1)
            if card:
                _logger.info('LOYALTY: Found by partner_id: %s', card.card_number)
                return card

            # Try by phone number
            phone = self.partner_id.phone or ''
            if phone:
                clean_phone = ''.join(filter(str.isdigit, str(phone)))
                if len(clean_phone) >= 10:
                    last_10 = clean_phone[-10:]
                    card = LoyaltyCard.search([
                        ('phone', 'ilike', last_10),
                        ('state', '=', 'active'),
                        ('is_deleted', '=', False),
                    ], limit=1)
                    if card:
                        _logger.info('LOYALTY: Found by phone %s: %s', last_10, card.card_number)
                        if not card.partner_id:
                            card.partner_id = self.partner_id.id
                        return card

        _logger.info('LOYALTY: No card found for order %s', self.name)
        return False

    def _find_original_order(self):
        """Find the original order that this refund/exchange is for"""
        self.ensure_one()

        # Method 1: Odoo 19 - check refunded_order_ids (reverse lookup)
        try:
            original = self.env['pos.order'].search([
                ('refunded_order_ids', 'in', self.ids),
            ], limit=1)
            if original:
                _logger.info('LOYALTY: Found original order %s via refunded_order_ids', original.name)
                return original
        except Exception:
            pass

        # Method 2: Check if pos_reference has RETURN pattern
        if self.pos_reference:
            ref = self.pos_reference.replace(' RETURN', '').replace(' Refund', '').strip()
            original = self.env['pos.order'].search([
                ('pos_reference', '=', ref),
                ('amount_total', '>', 0),
            ], limit=1)
            if original:
                _logger.info('LOYALTY: Found original order %s via pos_reference', original.name)
                return original

        # Method 3: Check name pattern
        if self.name:
            base_name = self.name.replace(' RETURN', '').replace(' Refund', '').strip()
            original = self.env['pos.order'].search([
                ('name', '=', base_name),
                ('amount_total', '>', 0),
            ], limit=1)
            if original:
                _logger.info('LOYALTY: Found original order %s via name', original.name)
                return original

        return False

    # Keep legacy methods as aliases for backward compatibility
    def _find_loyalty_card(self):
        return self._find_loyalty_card_for_any_order()

    def _find_loyalty_card_for_return(self):
        return self._find_loyalty_card_for_any_order()

    @api.model
    def sync_from_ui(self, orders):
        """Override to strip loyalty discount lines from refund/return orders
        before they are saved. The refund should only contain actual product lines.
        Also validates loyalty_card_id to prevent constraint violations."""
        _logger.info('LOYALTY: sync_from_ui called with %s orders', len(orders) if orders else 0)

        discount_product_id = self._get_loyalty_discount_product_id()

        for order_data in (orders or []):
            loyalty_card_id = order_data.get('loyalty_card_id')
            if loyalty_card_id:
                _logger.info('LOYALTY: sync_from_ui received order with loyalty_card_id=%s', loyalty_card_id)
                # Validate the loyalty card exists before syncing
                try:
                    card = self.env['pos.loyalty.card'].browse(loyalty_card_id)
                    if not card.exists():
                        _logger.warning('LOYALTY: loyalty_card_id=%s does not exist, removing from order data', loyalty_card_id)
                        order_data.pop('loyalty_card_id', None)
                except Exception as e:
                    _logger.error('LOYALTY: Error validating loyalty_card_id=%s: %s, removing it', loyalty_card_id, e)
                    order_data.pop('loyalty_card_id', None)

            # Detect refund order
            lines_data = order_data.get('lines') or []
            is_refund = False

            amount = order_data.get('amount_total', 0)
            if amount and amount < 0:
                is_refund = True
            elif lines_data:
                all_negative = all(
                    (l[2].get('qty', 0) if isinstance(l, (list, tuple)) and len(l) > 2 else 0) < 0
                    for l in lines_data
                    if isinstance(l, (list, tuple)) and len(l) > 2
                )
                if all_negative and len(lines_data) > 0:
                    is_refund = True

            if is_refund and discount_product_id and lines_data:
                cleaned_lines = []
                removed = 0
                for line_entry in lines_data:
                    if isinstance(line_entry, (list, tuple)) and len(line_entry) > 2:
                        vals = line_entry[2] if isinstance(line_entry[2], dict) else {}
                        pid = vals.get('product_id')
                        note = vals.get('customer_note', '')

                        if pid == discount_product_id or note == 'LOYALTY_DISCOUNT':
                            _logger.info(
                                'LOYALTY REFUND: Stripping loyalty discount line '
                                '(product_id=%s, note=%s) from refund order',
                                pid, note
                            )
                            removed += 1
                            continue
                    cleaned_lines.append(line_entry)

                if removed > 0:
                    order_data['lines'] = cleaned_lines
                    _logger.info('LOYALTY REFUND: Removed %s loyalty discount line(s) from refund', removed)

        return super().sync_from_ui(orders)
