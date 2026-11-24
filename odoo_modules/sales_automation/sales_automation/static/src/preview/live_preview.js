/** @odoo-module **/

// The right side of a Sales Automation settings page: what happens with the
// options now, also before saving. A click on an option or on a heading only
// highlights its words (24 Nov 2026).
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, markup, onMounted, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { GROUPS, fullHtml, highlight, rulesOf } from "./preview_text";

/** How an enquiry goes with the saved settings: orange needs you. */
export class SaFlowDialog extends Component {
    static template = "sales_automation.SaFlowDialog";
    static components = { Dialog };
    static props = { steps: Array, open: Function, close: Function };

    go(xmlid) {
        this.props.close();
        this.props.open(xmlid);
    }
}

export class SaLivePreview extends Component {
    static template = "sales_automation.SaLivePreview";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.action = useService("action");
        this.root = useRef("root");
        this.body = useRef("body");
        this.state = useState({ names: [], taps: 0, cost: 100, page: 0, pick: 0 });
        // the folded list keeps its state when the preview is drawn again
        this.open = false;
        useEffect(() => {
            const all = this.body.el && this.body.el.querySelector(".sa_pv_all");
            if (all) {
                all.open = this.open;
            }
        });
        // each click: bring its first highlighted words into view, inside the preview
        useEffect(
            () => {
                const body = this.body.el;
                const word = body && body.querySelector("mark");
                if (!word) {
                    return;
                }
                // its words are only in the folded list: open it
                const all = word.closest(".sa_pv_all");
                if (all) {
                    this.open = true;
                    all.open = true;
                }
                const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
                const behavior = calm ? "auto" : "smooth";
                if (body.scrollHeight > body.clientHeight + 1) {
                    const top = word.getBoundingClientRect().top - body.getBoundingClientRect().top;
                    body.scrollTo({ top: body.scrollTop + top - body.clientHeight / 3, behavior });
                }
            },
            () => [this.state.taps]
        );
        const picked = (ev) => this.onPicked(ev);
        onMounted(() => {
            this.form = this.root.el.closest(".o_form_view") || this.root.el.closest(".o_form_renderer");
            if (this.form) {
                this.form.addEventListener("click", picked, true);
                this.form.addEventListener("focusin", picked);
            }
        });
        onWillUnmount(() => {
            if (this.form) {
                this.form.removeEventListener("click", picked, true);
                this.form.removeEventListener("focusin", picked);
            }
        });
    }

    get page() {
        return this.props.page;
    }

    /** Plain values: names for records, rows for tables. */
    get data() {
        const out = {};
        const { data, fields } = this.props.record;
        for (const name of Object.keys(data)) {
            const type = fields[name] && fields[name].type;
            const v = data[name];
            if (type === "one2many" || type === "many2many") {
                if (name === "margin_category_ids" || name === "margin_group_ids") {
                    out[name] = v.records.map((r) => {
                        const who = r.data.categ_id || r.data.group_id;
                        return { name: (who && who.display_name) || "New row", percent: r.data.percent };
                    });
                }
            } else if (type === "many2one") {
                out[name] = v ? v.display_name : "";
            } else {
                out[name] = v;
            }
        }
        return out;
    }

    get rules() {
        const d = this.data;
        return this.page === "margin" && d.margin_rules_enabled ? rulesOf(d) : [];
    }

    get html() {
        const d = this.data;
        const fields = {};
        for (const [name, field] of Object.entries(this.props.record.fields)) {
            fields[name] = this.props.words[name] ? { ...field, string: this.props.words[name] } : field;
        }
        const args = [this.page, d, this.state, fields];
        return markup(this.state.names.length ? highlight(...args, this.state.names) : fullHtml(...args));
    }

    /** The option or heading that was clicked; its value is never touched. */
    onPicked(ev) {
        if (!(ev.target instanceof Element) || this.root.el.contains(ev.target)) {
            return;
        }
        // a name only shows its preview: no dropdown opens, no switch turns.
        // The choices of a radio are not names, they stay clickable.
        if (ev.type === "click" && ev.target.closest(".sa_side_left label.o_form_label")) {
            ev.preventDefault();
        }
        const heading = ev.target.closest(".o_horizontal_separator");
        if (heading) {
            const text = heading.textContent.trim().toLowerCase();
            const group = (GROUPS[this.page] || []).find(([title]) => title.toLowerCase() === text);
            if (group) {
                this.state.names = group[1];
                this.state.taps += 1;
            }
            return;
        }
        const all = (GROUPS[this.page] || []).flatMap(([, list]) => list).concat(["margin_category_ids", "margin_group_ids"]);
        const label = ev.target.closest("label[for]");
        let name = label && all.find((f) => label.htmlFor === f || new RegExp(`^${f}_\\d+$`).test(label.htmlFor));
        for (let el = ev.target; !name && el && el !== this.form; el = el.parentElement) {
            const own = el.getAttribute("name");
            name = own && all.includes(own) ? own : undefined;
        }
        if (name) {
            this.state.names = [name];
            this.state.taps += 1;
        }
    }

    async onFlow() {
        const steps = await this.orm.call("sa.ai.settings", "sa_flow_steps", []);
        this.dialog.add(SaFlowDialog, { steps, open: (xmlid) => this.action.doAction(xmlid) });
    }

    onFold(ev) {
        if (ev.target.closest("summary")) {
            ev.preventDefault();
            const all = ev.target.closest(".sa_pv_all");
            this.open = !all.open;
            all.open = this.open;
        }
    }

    onNumber(key, ev) {
        this.state[key] = Math.max(0, parseFloat(ev.target.value) || 0);
    }

    onPick(ev) {
        this.state.pick = Number(ev.target.value);
    }
}

registry.category("view_widgets").add("sa_live_preview", {
    component: SaLivePreview,
    extractProps: ({ attrs }) => ({ page: attrs.page, words: JSON.parse(attrs.words || "{}") }),
});
