/** @odoo-module */

import { useService } from "@web/core/utils/hooks";
import { useState, onMounted } from "@odoo/owl";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { LoyaltyCardPopup, RedeemPopup } from "./loyalty_popups";


/**
 * Patch PaymentScreen to add loyalty functionality
 * 
 * KEY FEATURE: Redemption appears as a payment line (like Cash)
 * so the flow is:
 * 1. Original total shown
 * 2. "Loyalty Points" payment shows redeemed amount
 * 3. Remaining balance shows what needs Cash/Card
 */
patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        
        // State for loyalty card
        this.loyaltyCard = useState({ data: null });
        
        // State for redemption
        this.loyaltyRedemption = useState({ 
            active: false,
            points_redeemed: 0,
            discount_value: 0,
            payment_line_id: null,
        });
        
        this._popupShown = false;
        this.loyaltyOrm = useService("orm");
        this.loyaltyNotification = useService("notification");

        // Show loyalty popup on mount
        onMounted(() => {
            setTimeout(() => this._showLoyaltyPopup(), 300);
        });
    },

    /**
     * Auto-show loyalty card popup when entering payment screen
     */
    _showLoyaltyPopup() {
        if (this._popupShown) return;
        this._popupShown = true;

        const self = this;
        this.dialog.add(LoyaltyCardPopup, {
            getPayload: function (card) {
                if (card) {
                    self.loyaltyCard.data = card;
                    self._linkCardToOrder(card);
                }
            },
        });
    },

    /**
     * Link loyalty card to current order
     */
    _linkCardToOrder(card) {
        if (!card || !this.currentOrder) return;
        
        this.currentOrder.loyalty_card_id = card.id;
        this.currentOrder.loyalty_card_data = card;
        
        // Also set partner if available
        if (card.partner_id) {
            try {
                const partner = this.pos.models["res.partner"].get(card.partner_id);
                if (partner) {
                    this.currentOrder.setPartner(partner);
                }
            } catch (e) {
                console.log("LOYALTY: Could not set partner:", e);
            }
        }
    },

    /**
     * Get the original order total (before any loyalty payment)
     */
    _getOriginalOrderTotal() {
        try {
            const order = this.currentOrder;
            if (!order) return 0;
            
            // Get total with tax from order lines (not including payments)
            if (typeof order.get_total_with_tax === "function") {
                return order.get_total_with_tax();
            }
            if (typeof order.getTotalDue === "function") {
                return order.getTotalDue() + this._getLoyaltyPaidAmount();
            }
            return 0;
        } catch (e) {
            console.error("LOYALTY: Error getting total:", e);
            return 0;
        }
    },

    /**
     * Get amount already paid via loyalty points
     */
    _getLoyaltyPaidAmount() {
        if (!this.loyaltyRedemption.active) return 0;
        return this.loyaltyRedemption.discount_value || 0;
    },

    /**
     * Get the loyalty payment method
     */
    _getLoyaltyPaymentMethod() {
        try {
            // Get all payment methods available in the POS config
            const paymentMethods = this.pos.config.payment_method_ids;
            
            for (const pm of paymentMethods) {
                if (pm.is_loyalty_payment) {
                    return pm;
                }
            }
            
            // Fallback: try to find by name
            for (const pm of paymentMethods) {
                if (pm.name && pm.name.toLowerCase().includes('loyalty')) {
                    return pm;
                }
            }
            
            return null;
        } catch (e) {
            console.error("LOYALTY: Error finding payment method:", e);
            return null;
        }
    },

    /**
     * Add loyalty payment line to order
     */
    async _addLoyaltyPayment(discountValue, pointsRedeemed) {
        if (!discountValue || discountValue <= 0) return false;
        
        const order = this.currentOrder;
        if (!order) return false;

        // First remove any existing loyalty payment
        this._removeLoyaltyPayment();

        // Find loyalty payment method
        const loyaltyPM = this._getLoyaltyPaymentMethod();
        
        if (!loyaltyPM) {
            this.loyaltyNotification.add(
                "Loyalty Points payment method not found. Please add it to POS config.", 
                { type: "danger" }
            );
            return false;
        }

        try {
            // Add payment line using the loyalty payment method
            const paymentLine = order.add_paymentline(loyaltyPM);
            
            if (paymentLine) {
                paymentLine.set_amount(discountValue);
                paymentLine.loyalty_points_used = pointsRedeemed;
                paymentLine.is_loyalty_payment = true;
                
                // Store reference
                this.loyaltyRedemption.active = true;
                this.loyaltyRedemption.points_redeemed = pointsRedeemed;
                this.loyaltyRedemption.discount_value = discountValue;
                this.loyaltyRedemption.payment_line_id = paymentLine.uuid || paymentLine.cid;
                
                // Update order
                this.currentOrder.loyalty_points_redeemed = pointsRedeemed;
                this.currentOrder.loyalty_discount_amount = discountValue;
                
                console.log("LOYALTY: Added payment line:", discountValue);
                return true;
            }
        } catch (e) {
            console.error("LOYALTY: Error adding payment:", e);
            this.loyaltyNotification.add("Failed to add loyalty payment: " + e.message, { type: "danger" });
        }
        
        return false;
    },

    /**
     * Remove loyalty payment line
     */
    _removeLoyaltyPayment() {
        const order = this.currentOrder;
        if (!order) return;

        try {
            const paymentlines = order.payment_ids || order.paymentlines || [];
            
            for (const line of [...paymentlines]) {
                if (line.is_loyalty_payment || 
                    (line.payment_method_id && line.payment_method_id.is_loyalty_payment)) {
                    order.remove_paymentline(line);
                }
            }
            
            this.loyaltyRedemption.active = false;
            this.loyaltyRedemption.points_redeemed = 0;
            this.loyaltyRedemption.discount_value = 0;
            this.loyaltyRedemption.payment_line_id = null;
            
            this.currentOrder.loyalty_points_redeemed = 0;
            this.currentOrder.loyalty_discount_amount = 0;
            
            console.log("LOYALTY: Removed payment line");
        } catch (e) {
            console.error("LOYALTY: Error removing payment:", e);
        }
    },

    // ==== GETTERS FOR TEMPLATE ====
    
    get loyaltyCardInfo() { 
        return this.loyaltyCard.data; 
    },
    
    get hasLoyaltyRedemption() { 
        return this.loyaltyRedemption.active && this.loyaltyRedemption.discount_value > 0; 
    },
    
    get loyaltyRedemptionInfo() {
        return {
            points: this.loyaltyRedemption.points_redeemed,
            amount: this.loyaltyRedemption.discount_value,
        };
    },

    /**
     * Original order total (items only)
     */
    get originalOrderTotal() {
        return this._getOriginalOrderTotal();
    },

    /**
     * Amount paid with loyalty points
     */
    get loyaltyPaidAmount() {
        return this._getLoyaltyPaidAmount();
    },

    /**
     * Remaining amount to pay with Cash/Card
     */
    get remainingToPay() {
        return Math.max(0, this.originalOrderTotal - this.loyaltyPaidAmount);
    },

    // ==== ACTIONS ====

    /**
     * Open loyalty card search popup
     */
    openLoyaltyPopup() {
        const self = this;
        this.dialog.add(LoyaltyCardPopup, {
            getPayload: function (card) {
                if (card) {
                    self.loyaltyCard.data = card;
                    self._linkCardToOrder(card);
                }
            },
        });
    },

    /**
     * Open redeem points popup
     */
    openRedeemPopup() {
        const self = this;
        const orderTotal = this._getOriginalOrderTotal();
        
        console.log("LOYALTY: Opening redeem popup, total:", orderTotal);
        
        this.dialog.add(RedeemPopup, {
            orderTotal: orderTotal,
            cardData: this.loyaltyCard.data,
            getPayload: function (res) {
                if (res && res.discount_value > 0) {
                    // Add loyalty payment line
                    self._addLoyaltyPayment(res.discount_value, res.points_redeemed);
                    
                    // Update card data with new points balance
                    if (self.loyaltyCard.data) {
                        self.loyaltyCard.data.total_points = res.remaining_points;
                    }
                }
            },
        });
    },

    /**
     * Remove redemption
     */
    removeRedemption() {
        this._removeLoyaltyPayment();
        this.loyaltyNotification.add("Loyalty redemption removed", { type: "info" });
    },
});
