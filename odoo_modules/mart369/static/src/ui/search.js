/** Our search box - twin of the console's Search (components/admin/AdminUI.jsx).
 *
 * The thirteen desks each wrote their own `<input type="search">` with their own
 * two-letter class, which left every one of them without the magnifying glass
 * and with the browser's own clear cross instead of ours. This is that box,
 * once.
 */
import { Component } from "@odoo/owl";
import { Icon } from "./icon";

export class Search extends Component {
    static template = "mart369.Search";
    static components = { Icon };
    static props = {
        value: { type: String },
        placeholder: { type: String, optional: true },
        /* What the box is for, for a screen reader. The placeholder says the
           same thing, but it disappears the moment somebody types. */
        label: { type: String, optional: true },
        wide: { type: Boolean, optional: true },
        onChange: { type: Function },
    };
    static defaultProps = { placeholder: "Search" };
}
