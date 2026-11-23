/** @odoo-module **/

// The panel on the right: open after a load when there is something new,
// folded to "<" by its X, opened again by "<". Enquiries, orders and WhatsApp
// each have their own section.
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";

const ICON = { order: "fa-shopping-bag", price: "fa-tag", cheaper: "fa-arrow-down", paid: "fa-check", whatsapp: "fa-whatsapp",
    pick: "fa-users", stalled: "fa-clock-o", choice: "fa-balance-scale" };
const WORDS = { pick: _t("Choose the vendors"), stalled: _t("No vendor replied"), choice: _t("Approve a price") };
const SECTIONS = [
    ["enquiries", _t("Enquiries"), ["price", "cheaper"]],
    ["orders", _t("Orders"), ["order", "paid"]],
    ["whatsapp", _t("WhatsApp"), ["whatsapp"]],
];

export class NoticePanel extends Component {
    static template = "sales_automation_store.NoticePanel";
    static props = {};

    setup() {
        this.notice = useService("sa_notice");
        this.data = useState(this.notice.state);
        this.state = useState({ shut: {} });
    }

    get rows() {
        return this.data.rows.filter((row) => !row.seen);
    }

    get count() {
        return this.rows.length + this.data.waiting.length;
    }

    get sections() {
        return SECTIONS.map(([key, name, kinds]) => {
            const waiting = key === "enquiries" ? this.data.waiting : [];
            const rows = this.rows.filter((row) => kinds.includes(row.kind));
            return { key, name, waiting, rows, count: waiting.length + rows.length };
        }).filter((section) => section.count);
    }

    toggle(key) {
        this.state.shut[key] = !this.state.shut[key];
    }

    icon(row) {
        return ICON[row.kind] || "fa-bell";
    }

    words(row) {
        return WORDS[row.kind] || "";
    }

    readAll(section) {
        return this.notice.seen(section.rows.map((row) => row.id));
    }

    when(iso) {
        const d = new Date(iso);
        const today = d.toDateString() === new Date().toDateString();
        return d.toLocaleString([], today ? { hour: "2-digit", minute: "2-digit" }
            : { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    }
}

registry.category("main_components").add("sales_automation_store.notice_panel", { Component: NoticePanel });
