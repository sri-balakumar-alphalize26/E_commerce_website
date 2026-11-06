/** Our avatar - twin of the console's Avatar (components/admin/AdminUI.jsx).
 *
 * Initials, not a photograph: staff, customers and reviewers all appear in these
 * lists and almost none of them have uploaded a picture, so a drawn circle is
 * what the screen would fall back to anyway. `initials` was copy-pasted into
 * two desks before this existed.
 */
import { Component } from "@odoo/owl";

export class Avatar extends Component {
    static template = "mart369.Avatar";
    static props = {
        name: { type: String },
        tone: { type: String, optional: true },
        size: { type: Number, optional: true },
    };
    static defaultProps = { tone: "", size: 38 };

    get initials() {
        return (this.props.name || "")
            .split(/\s+/)
            .filter((w) => w)
            .map((w) => w[0])
            .join("")
            .slice(0, 2)
            .toUpperCase();
    }

    /* The font rides the box, as the console's does, so one component covers
       the 26px one in a row and the 46px one at the top of a dialog. */
    get style() {
        const s = this.props.size;
        return `width:${s}px;height:${s}px;font-size:${Math.round(s * 0.36)}px`;
    }
}
