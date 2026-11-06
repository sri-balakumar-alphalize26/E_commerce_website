/** @odoo-module **/

import { Component } from "@odoo/owl";

/** Seven rows by twenty-four hours, five shades. No library needed. */
export class Heatmap extends Component {
    static template = "sales_automation_insights.Heatmap";
    static props = { heatmap: Object };

    get days() {
        return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    }

    get hours() {
        return Array.from({ length: 24 }, (_, i) => i);
    }

    shade(count) {
        const max = this.props.heatmap.max || 0;
        if (!count || !max) {
            return "";
        }
        const q = count / max;
        return q > 0.75 ? "h4" : q > 0.5 ? "h3" : q > 0.25 ? "h2" : "h1";
    }
}
