/** @odoo-module */

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

/**
 * Extend PosOrder to handle loyalty data
 */
patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(...arguments);
        this.loyalty_card_id = vals.loyalty_card_id || false;
        this.loyalty_card_data = vals.loyalty_card_data || null;
        this.loyalty_points_redeemed = vals.loyalty_points_redeemed || 0;
        this.loyalty_discount_amount = vals.loyalty_discount_amount || 0;
    },

    /**
     * Serialize for sending to backend
     */
    serializeForORM(opts = {}) {
        const data = super.serializeForORM(...arguments);
        if (this.loyalty_card_id) {
            data.loyalty_card_id = this.loyalty_card_id;
        }
        if (this.loyalty_points_redeemed) {
            data.loyalty_points_redeemed = this.loyalty_points_redeemed;
        }
        if (this.loyalty_discount_amount) {
            data.loyalty_discount_amount = this.loyalty_discount_amount;
        }
        return data;
    },
});
