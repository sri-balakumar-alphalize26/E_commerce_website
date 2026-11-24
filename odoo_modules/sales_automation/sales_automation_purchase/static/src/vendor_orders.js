/** @odoo-module **/

// Store > Vendor Orders: what paid orders still need from a vendor. To look at
// only: nothing on this screen orders, sends or changes anything.
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { byDay, dayName, matches, timeOf } from "@sales_automation_store/board";

const REFRESH_MS = 60000;

export const TABS = [
    ["review", _t("To review")], ["chosen", _t("Chosen")], ["draft", _t("Draft order")], ["ordered", _t("Ordered")], ["done", _t("Done")],
];

export function tabOf(row) {
    switch (row.state) {
        case "selected":
            return "chosen";
        case "po_draft":
            return "draft";
        case "ordered":
            return "ordered";
        case "received":
        case "cancelled":
            return "done";
    }
    return "review";
}

export function buyPills(row) {
    const out = [];
    if (row.better) {
        out.push(["bad", _t("Cheaper vendor")]);
    }
    if (row.loss) {
        out.push(["bad", _t("Loss")]);
    }
    switch (row.state) {
        case "waiting":
        case "review":
            out.push(row.replied ? ["new", _t("%(a)s of %(b)s replied", { a: row.replied, b: Math.max(row.asked, row.replied) })] : ["warn", _t("No price yet")]);
            break;
        case "no_vendor":
            out.push(["bad", _t("Nobody can supply")]);
            break;
        case "received":
            out.push(["good", _t("Received")]);
            break;
        case "cancelled":
            out.push(["", _t("Cancelled")]);
            break;
    }
    if (row.held.length) {
        out.push(["warn", _t("No exchange rate")]);
    }
    return out;
}

export class VendorOrders extends Component {
    static template = "sales_automation_purchase.VendorOrders";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            rows: [], totals: {}, warnings: [], more: false, tab: "review", search: "", sel: 0, detailOpen: false, loading: true, failed: false,
        });
        this.timeOf = timeOf;
        this.dayName = dayName;
        this.pills = buyPills;
        onWillStart(() => this.load());
        onMounted(() => {
            this.timer = setInterval(() => this.load(), REFRESH_MS);
        });
        onWillUnmount(() => clearInterval(this.timer));
    }

    async load() {
        try {
            const data = await this.orm.silent.call("sa.buy.line", "sa_vendor_orders", []);
            Object.assign(this.state, data, { loading: false, failed: false });
        } catch (error) {
            this.state.loading = false;
            this.state.failed = true;
            if (!this.state.rows.length) {
                throw error;
            }
        }
    }

    get tabs() {
        return TABS.map(([key, name]) => {
            const rows = this.state.rows.filter((r) => tabOf(r) === key);
            return { key, name, count: rows.length, bad: rows.some((r) => r.better || r.loss) };
        });
    }

    get shown() {
        return this.state.rows.filter((r) => (this.state.search ? matches(r, this.state.search) : tabOf(r) === this.state.tab));
    }

    get days() {
        return byDay(this.shown, () => false);
    }

    get selected() {
        return this.shown.find((r) => r.id === this.state.sel) || null;
    }

    openTab(key) {
        Object.assign(this.state, { tab: key, search: "", sel: 0, detailOpen: false });
    }

    select(row) {
        Object.assign(this.state, { sel: row.id, detailOpen: true });
    }

    closeDetail() {
        this.state.detailOpen = false;
    }

    onRowKey(ev, row) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.select(row);
        }
    }

    money(amount, currency) {
        return amount === null || amount === undefined || amount === false ? _t("no rate") : `${currency} ${Number(amount).toFixed(2)}`;
    }
}

registry.category("actions").add("sales_automation_purchase.vendor_orders", VendorOrders);
