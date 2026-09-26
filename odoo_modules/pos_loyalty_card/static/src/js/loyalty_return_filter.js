/** @odoo-module */

/**
 * =========================================================================
 * LOYALTY RETURN FILTER - Remove loyalty discount from POS refund orders
 * =========================================================================
 * 
 * When Odoo creates a refund, it copies ALL lines from the original order
 * including the "Loyalty Points Redemption" discount line. This module
 * removes that line so the refund only contains actual product returns.
 * 
 * Strategy (3 layers):
 * 1. Pre-refund: Mark loyalty lines as fully refunded so Odoo skips them
 * 2. Post-refund: Delete any loyalty lines that slipped into the new order
 * 3. DOM fallback: Hide loyalty lines visually as safety net
 */

import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { onMounted, onPatched } from "@odoo/owl";

// ============================================
// Utility: Detect loyalty discount lines
// ============================================
function _isLoyaltyLine(line) {
    if (!line) return false;
    
    // Check customer_note marker
    const note = line.customer_note || line.customerNote || "";
    if (note === "LOYALTY_DISCOUNT") return true;
    
    // Check JS flag
    if (line.loyalty_discount_line) return true;
    
    // Check product name (multiple possible access paths)
    const name = (
        line.product_id?.display_name ||
        line.product_id?.name ||
        line.productName ||
        line.full_product_name ||
        ""
    ).toLowerCase();
    
    if (name.includes("loyalty points redemption")) return true;
    if (name.includes("loyalty") && name.includes("redemption")) return true;
    
    return false;
}

// ============================================
// Utility: Hide loyalty lines from DOM
// ============================================
function _hideLoyaltyLinesFromDOM() {
    try {
        const lineElements = document.querySelectorAll(
            ".ticket-screen .orderline, " +
            ".ticket-screen .order-line, " +
            ".ticket-screen .orderline-row, " +
            ".refund-orderlines .orderline, " +
            ".order-details .orderline"
        );
        
        for (const el of lineElements) {
            const text = (el.textContent || "").toLowerCase();
            if (text.includes("loyalty points redemption") ||
                text.includes("loyalty_discount")) {
                el.style.display = "none";
            }
        }
    } catch (e) {
        // Silent fail
    }
}

// ============================================
// Utility: Delete loyalty lines from an order
// ============================================
function _deleteLoyaltyLinesFromOrder(order) {
    if (!order || !order.lines) return 0;

    const toRemove = [];
    for (const line of order.lines) {
        if (_isLoyaltyLine(line)) {
            toRemove.push(line);
        }
    }

    let removed = 0;
    for (const line of toRemove) {
        try {
            if (typeof line.delete === "function") {
                line.delete();
                removed++;
            }
        } catch (e) {
            console.warn("LOYALTY_RETURN: Could not delete line:", e);
        }
    }

    if (removed > 0) {
        console.log("LOYALTY_RETURN: Deleted", removed, "loyalty discount line(s) from refund order");
    }
    return removed;
}

// ============================================
// Patch TicketScreen
// ============================================
patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        
        onMounted(() => _hideLoyaltyLinesFromDOM());
        onPatched(() => _hideLoyaltyLinesFromDOM());
    },

    /**
     * Override _onDoRefund to exclude loyalty discount lines from refund.
     * 
     * Layer 1: Before refund — mark loyalty lines as fully refunded
     *          so Odoo's core logic skips them.
     * Layer 2: After refund — delete any loyalty lines that still
     *          made it into the new refund order.
     */
    async _onDoRefund() {
        const order = this.getSelectedOrder ? this.getSelectedOrder() : null;
        
        if (order && order.lines) {
            const savedQtys = [];
            
            for (const line of order.lines) {
                if (_isLoyaltyLine(line)) {
                    savedQtys.push({
                        line: line,
                        origRefundedQty: line.refunded_qty || 0,
                    });
                    line.refunded_qty = Math.abs(line.qty || 1);
                    console.log("LOYALTY_RETURN: Pre-marking loyalty line as fully refunded");
                }
            }
            
            try {
                await super._onDoRefund(...arguments);
            } finally {
                for (const item of savedQtys) {
                    item.line.refunded_qty = item.origRefundedQty;
                }
            }
        } else {
            await super._onDoRefund(...arguments);
        }
        
        // Layer 2: Post-refund cleanup — delete loyalty lines from new order
        try {
            const pos = this.pos || this.env?.services?.pos;
            if (pos) {
                const newOrder = pos.getOrder ? pos.getOrder() : pos.get_order?.();
                if (newOrder) {
                    _deleteLoyaltyLinesFromOrder(newOrder);
                }
            }
        } catch (e) {
            console.warn("LOYALTY_RETURN: Post-refund cleanup error:", e);
        }

        setTimeout(() => _hideLoyaltyLinesFromDOM(), 300);
    },
});
