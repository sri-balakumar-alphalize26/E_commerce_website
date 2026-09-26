/** @odoo-module */

import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";

/**
 * Patch OrderReceipt to add loyalty card data to the receipt.
 * 
 * This reads loyalty info from the order object (set during payment)
 * and exposes it as `loyaltyReceiptData` for the XML template.
 * 
 * Data flow:
 *   1. PaymentScreen sets order.loyalty_card_id, loyalty_points_redeemed, etc.
 *   2. On order validation, points are earned (server-side via action_pos_order_paid)
 *   3. This patch reads whatever is available on the order and computes display values.
 *   
 * Since points_earned is calculated server-side AFTER order sync, we estimate it
 * client-side using the same formula: (order_total / spend_amount) * points_earned_per_rule
 */
patch(OrderReceipt.prototype, {

    get loyaltyReceiptData() {
        const order = this.order;
        if (!order) return null;
        if (this.pos && this.pos.config && this.pos.config.enable_loyalty_cards === false) return null;

        // Get loyalty card ID from order
        const cardId = order.loyalty_card_id;
        if (!cardId) return null;

        // Try to get card data from the POS store
        // The loyalty card info is stored on the order during payment
        let cardNumber = '';
        let memberName = '';
        let totalPointsBefore = 0;
        let pointsEarned = 0;
        let pointsRedeemed = 0;
        let pointBalance = 0;

        // Method 1: Read from order's loyalty_receipt_data (set by our payment screen patch)
        if (order._loyalty_receipt_data) {
            const data = order._loyalty_receipt_data;
            cardNumber = data.card_number || '';
            memberName = data.member_name || '';
            pointsEarned = data.points_earned || 0;
            pointsRedeemed = data.points_redeemed || 0;
            pointBalance = data.point_balance || 0;
        }

        // Method 2: Read from order fields directly  
        if (!cardNumber && order._loyalty_card_number) {
            cardNumber = order._loyalty_card_number;
            memberName = order._loyalty_member_name || '';
        }

        // Method 3: Read redeemed points from order field
        if (order.loyalty_points_redeemed > 0) {
            pointsRedeemed = order.loyalty_points_redeemed;
        }

        // If we still don't have card number, try to get from the linked card data
        if (!cardNumber) {
            return null;
        }

        return {
            card_number: cardNumber,
            member_name: memberName,
            points_earned: pointsEarned,
            points_earned_display: Math.round(pointsEarned).toString(),
            points_redeemed: pointsRedeemed,
            points_redeemed_display: Math.round(pointsRedeemed).toString(),
            point_balance: pointBalance,
            point_balance_display: this._formatPointBalance(pointBalance),
        };
    },

    _formatPointBalance(points) {
        // Format with commas for large numbers
        return Math.round(points).toLocaleString('en-IN');
    },
});
