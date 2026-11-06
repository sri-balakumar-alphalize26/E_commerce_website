/** Our on/off toggle - the drawn pill, twin of the console's Switch
 *  (components/admin/AdminUI.jsx).
 *
 * A button carrying `role="switch"` rather than the console's hidden checkbox:
 * the two draw identically, and a button needs no label wrapped round it to be
 * reachable by keyboard, which suits the row of a list where most of these sit.
 *
 * `mart-switch` used to mean two different controls - this pill in three places
 * and a tinted native checkbox in five. It now means only this one.
 */
import { Component } from "@odoo/owl";

export class Switch extends Component {
    static template = "mart369.Switch";
    static props = {
        on: { type: Boolean },
        label: { type: String, optional: true },
        disabled: { type: Boolean, optional: true },
        onChange: { type: Function },
    };

    toggle() {
        if (!this.props.disabled) {
            this.props.onChange(!this.props.on);
        }
    }
}
