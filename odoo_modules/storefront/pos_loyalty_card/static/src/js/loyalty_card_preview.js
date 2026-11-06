/** @odoo-module */

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

/** Live preview of the loyalty card on the Loyalty Settings form. Font sizes are
 *  in mm (same scale as the card size); rendered at scale px/mm on screen. */
export class LoyaltyCardPreview extends Component {
    static template = "pos_loyalty_card.LoyaltyCardPreview";
    static props = { "*": true };

    get d() { return this.props.record.data; }
    _num(v, fb) { const n = parseFloat(v); return !n || isNaN(n) ? fb : n; }
    get scale() { return 3.6; }              // px per mm on screen
    _fpx(v, fb) { return this._num(v, fb) * this.scale; }

    get cardNumber() {
        const d = this.d;
        const prefix = (d.card_prefix || "LC").trim() || "LC";
        let mobile = "";
        if (d.card_use_mobile) {
            const n = parseInt(d.card_mobile_digits, 10);
            if (n > 0) mobile = "9876543210".slice(-n);
        }
        const p = parseInt(d.card_counter_padding, 10);
        const pad = p >= 1 && p <= 12 ? p : 6;
        return prefix + mobile + "1".padStart(pad, "0");
    }

    get cardStyle() {
        const d = this.d;
        const w = (this._num(d.card_width, 86) - 4) * this.scale;
        const h = (this._num(d.card_height, 54) - 4) * this.scale;
        const bg = d.background_color || "#1a237e";
        const fg = d.text_color || "#ffffff";
        const font = d.font_family || "Arial, sans-serif";
        return `width:${w}px;height:${h}px;background:${bg};color:${fg};` +
            "border-radius:8px;padding:8px 12px;box-sizing:border-box;position:relative;" +
            `font-family:${font};overflow:hidden;display:flex;flex-direction:column;`;
    }

    get companyName() { return (this.d.card_company_name || "").trim(); }
    get companyStyle() { return `text-align:center;font-weight:bold;color:${this.d.company_color||"#ffd700"};font-size:${this._fpx(this.d.company_font_size,5)}px;`; }
    get titleStyle() { return `color:${this.d.title_color||"#ffd700"};font-weight:bold;font-size:${this._fpx(this.d.title_font_size,4)}px;`; }
    get numberStyle() { return `font-weight:bold;letter-spacing:1px;margin-top:2px;font-size:${this._fpx(this.d.number_font_size,6)}px;`; }
    get statusStyle() { return `font-weight:bold;color:${this.d.status_color||"#4caf50"};font-size:${this._fpx(this.d.status_font_size,3.5)}px;`; }
    get nameStyle() { return `text-transform:uppercase;letter-spacing:1px;color:${this.d.name_color||"#e0e0e0"};font-size:${this._fpx(this.d.name_font_size,4)}px;`; }
    get sinceStyle() { return `color:${this.d.since_color||"#aaaaaa"};font-size:${this._fpx(this.d.since_font_size,2.5)}px;`; }
    get pointsStyle() { return `font-weight:bold;color:${this.d.points_color||"#ffd700"};font-size:${this._fpx(this.d.points_font_size,3.5)}px;`; }
    get sinceText() { const dt = new Date(); return dt.toLocaleString("en", { month: "short", year: "numeric" }); }
    get barcodeSrc() { const v = encodeURIComponent(this.cardNumber); return `/report/barcode/?barcode_type=Code128&value=${v}&width=600&height=120&humanreadable=0`; }
}

registry.category("view_widgets").add("loyalty_card_preview", {
    component: LoyaltyCardPreview,
});
