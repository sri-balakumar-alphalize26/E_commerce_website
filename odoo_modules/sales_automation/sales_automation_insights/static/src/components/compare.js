/** @odoo-module **/

import { Component } from "@odoo/owl";
import { Radar } from "./charts";
import { starGlyphs, money } from "./util";

/** Two to four rows, side by side, best value in each line marked. */
export class Compare extends Component {
    static template = "sales_automation_insights.Compare";
    static components = { Radar };
    static props = { kind: String, compare: Object, onBack: Function, onOpen: Function,
                     theme: { type: String, optional: true } };

    stars(col) {
        return starGlyphs(col.stars);
    }

    fmt(metric, value) {
        if (value === null || value === undefined) {
            return "—";
        }
        if (metric.unit === "0-1") {
            return Math.round(value * 100) + "%";
        }
        if (metric.unit === "money") {
            return money(value, "");
        }
        if (metric.code === "stars") {
            return Number(value).toFixed(1);
        }
        return String(value);
    }
}
