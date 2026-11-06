/** Our status pill - twin of the console's Pill (components/admin/AdminUI.jsx).
 *
 * `map` so a screen can bring its own vocabulary. Orders runs on the shop's own
 * states (placed / packed / shipped / ...), payments on its own; without this
 * the pill falls through to the raw key in grey, which is at least honest.
 */
import { Component } from "@odoo/owl";

export class Pill extends Component {
    static template = "mart369.Pill";
    static props = {
        s: { type: String },
        map: { type: Object, optional: true },
        /* When the words come from somewhere other than the map - the server
           already sent a label, or the screen computes one - say so here and
           the map is consulted for the tone only. */
        label: { type: String, optional: true },
    };

    get tone() {
        const hit = (this.props.map || {})[this.props.s];
        return hit ? hit.tone : "grey";
    }

    get label() {
        if (this.props.label) {
            return this.props.label;
        }
        const hit = (this.props.map || {})[this.props.s];
        return hit && hit.label ? hit.label : this.props.s;
    }
}
