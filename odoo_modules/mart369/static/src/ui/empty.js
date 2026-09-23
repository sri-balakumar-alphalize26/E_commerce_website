/** Our empty state - twin of the console's Empty (components/admin/AdminUI.jsx).
 *
 * The desks had a bare paragraph where the console has an icon, a heading, a
 * line of explanation and - where there is something useful to do about it - the
 * button that does it. An empty list is the moment a screen most needs to say
 * what it is for, so it is worth the four lines.
 */
import { Component } from "@odoo/owl";
import { Icon } from "./icon";

export class Empty extends Component {
    static template = "mart369.Empty";
    static components = { Icon };
    static props = {
        icon: { type: String, optional: true },
        title: { type: String },
        text: { type: String, optional: true },
        action: { type: String, optional: true },
        onAction: { type: Function, optional: true },
    };
    static defaultProps = { icon: "box", text: "" };
}
