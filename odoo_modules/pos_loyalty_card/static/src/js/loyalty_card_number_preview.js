/** @odoo-module */

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

/**
 * Live flow-diagram of the card-number format, shown in a yellow banner on the
 * Loyalty Settings form. Updates as prefix / mobile toggle / digit count change.
 */
export class LoyaltyCardNumberPreview extends Component {
    static template = "pos_loyalty_card.LoyaltyCardNumberPreview";
    static props = { "*": true };

    get d() {
        return this.props.record.data;
    }
    get prefix() {
        return (this.d.card_prefix || "LC").trim() || "LC";
    }
    get useMobile() {
        return !!this.d.card_use_mobile;
    }
    get mobileDigits() {
        const n = parseInt(this.d.card_mobile_digits, 10);
        return n > 0 ? n : 0;
    }
    get sampleMobile() {
        if (!this.useMobile || !this.mobileDigits) {
            return "";
        }
        return "9876543210".slice(-this.mobileDigits);
    }
    get counterPadding() {
        const n = parseInt(this.d.card_counter_padding, 10);
        return n >= 1 && n <= 12 ? n : 6;
    }
    get counter() {
        return "1".padStart(this.counterPadding, "0");
    }
    get example() {
        return this.prefix + this.sampleMobile + this.counter;
    }
}

registry.category("view_widgets").add("loyalty_card_number_preview", {
    component: LoyaltyCardNumberPreview,
});
