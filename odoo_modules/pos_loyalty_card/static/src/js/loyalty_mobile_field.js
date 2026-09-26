/** @odoo-module */

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Backend field widget for a mobile number that follows the global Loyalty
 * Settings: a fixed "+<dial code>" prefix (read-only here, changeable only in
 * Loyalty Settings) and a digit-only input capped to the configured length.
 */
export class LoyaltyMobileField extends Component {
    static template = "pos_loyalty_card.LoyaltyMobileField";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.cfg = useState({ dial: "91", length: 10 });
        onWillStart(async () => {
            const r = await this.orm.call("pos.loyalty.card.settings", "get_mobile_config", []);
            if (r) {
                this.cfg.dial = String(r.dial || "91");
                this.cfg.length = r.length || 10;
            }
        });
    }

    // The stored value may be normalised ("+919876543210"); show just the local part.
    get localValue() {
        let v = String(this.props.record.data[this.props.name] || "").replace(/[^0-9]/g, "");
        if (this.cfg.dial && v.length > this.cfg.length && v.startsWith(this.cfg.dial)) {
            v = v.slice(this.cfg.dial.length);
        }
        return v.slice(0, this.cfg.length);
    }

    get placeholder() {
        return `${this.cfg.length}-digit mobile`;
    }

    get isReadonly() {
        return this.props.readonly;
    }

    onInput(ev) {
        const v = ev.target.value.replace(/[^0-9]/g, "").slice(0, this.cfg.length);
        if (ev.target.value !== v) {
            ev.target.value = v;
        }
        this.props.record.update({ [this.props.name]: v });
    }
}

registry.category("fields").add("loyalty_mobile", {
    component: LoyaltyMobileField,
    supportedTypes: ["char"],
});
