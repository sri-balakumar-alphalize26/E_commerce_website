/** Our tab strip - twin of the console's Tabs (components/admin/AdminUI.jsx).
 *
 * `tabs` are [key, label, count] triples. A count of null or undefined draws no
 * badge at all, which is how a tab that never counts anything stays quiet.
 */
import { Component } from "@odoo/owl";

export class Tabs extends Component {
    static template = "mart369.Tabs";
    static props = {
        tabs: { type: Array },
        value: { type: String },
        onChange: { type: Function },
    };

    /* A badge is drawn for 0, but not for a tab that does not count. */
    shows(count) {
        return count !== null && count !== undefined;
    }
}
