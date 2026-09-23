/** Our dropdown.
 *
 * Ours, not the browser's.
 *
 * A native <select> draws its menu with the operating system: a grey Windows
 * list here, a rounded sheet on a Mac, a full-screen roller on a phone. Three
 * looks the rest of the screen does not have, and none of them can show a
 * tick against the option that is currently on.
 *
 * Built on Odoo's own Dropdown rather than hand-rolled, so it gets the
 * positioning, the outside click, Escape and arrow-key navigation that the
 * rest of the backend's menus have - and the console's twin of this is the
 * same control drawn the same way.
 *
 * `options` are [value, label] pairs, the same shape the console's Select
 * takes (components/admin/AdminUI.jsx), so the two stay easy to compare.
 *
 * It lives here, in the base module, because every screen needs it: the module
 * it used to live in (mart369_order) is a dependency of almost nothing, so
 * payments - which orders depends on - could not reach it at all, and catalog
 * drew three chips instead of borrowing it.
 */
import { Component } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { Icon } from "./icon";

export class Pick extends Component {
    static template = "mart369.Pick";
    static components = { Dropdown, DropdownItem, Icon };
    static props = {
        value: { type: String },
        options: { type: Array },
        label: { type: String },
        /* Optional, so the call sites that can never be mid-write say nothing.
           Passed on as `!!` because an absent optional prop arrives as
           undefined, which OWL's Boolean check refuses in dev mode. */
        disabled: { type: Boolean, optional: true },
        onChange: { type: Function },
    };

    get current() {
        const hit = this.props.options.find(([v]) => v === this.props.value);
        return hit ? hit[1] : "";
    }

    choose(value) {
        if (value !== this.props.value) {
            this.props.onChange(value);
        }
    }
}
