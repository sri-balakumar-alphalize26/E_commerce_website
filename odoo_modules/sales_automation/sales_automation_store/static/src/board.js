/** @odoo-module **/

// What the Orders and the Enquiries screens share (23 Nov 2026): the list on
// the left grouped by day, the details on the right, one meaning per colour.
import { _t } from "@web/core/l10n/translation";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";

export function dayKey(iso) {
    const d = iso ? new Date(iso) : null;
    return d && !isNaN(d) ? `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}` : "";
}

export function dayName(iso, now = new Date()) {
    const d = iso ? new Date(iso) : null;
    if (!d || isNaN(d)) {
        return _t("No date");
    }
    const date = d.toLocaleDateString([], { day: "numeric", month: "short" });
    if (dayKey(iso) === dayKey(now.toISOString())) {
        return _t("Today") + ", " + date;
    }
    const y = new Date(now);
    y.setDate(y.getDate() - 1);
    if (dayKey(iso) === dayKey(y.toISOString())) {
        return _t("Yesterday") + ", " + date;
    }
    return d.toLocaleDateString([], { weekday: "long" }) + ", " + date;
}

export function timeOf(iso) {
    const d = iso ? new Date(iso) : null;
    return d && !isNaN(d) ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
}

/** [{day, rows}] newest first; rows that need somebody now come first. */
export function byDay(rows, first) {
    const sorted = [...rows].sort((a, b) => (first(b) ? 1 : 0) - (first(a) ? 1 : 0)
        || String(b.at || "").localeCompare(String(a.at || "")) || (b.id || 0) - (a.id || 0));
    const out = [];
    for (const row of sorted) {
        const day = first(row) ? _t("Problems") : dayName(row.at);
        if (!out.length || out[out.length - 1].day !== day) {
            out.push({ day, rows: [] });
        }
        out[out.length - 1].rows.push(row);
    }
    return out;
}

/** [{day, rows, product}] one section per product, the newest first; problems on top. */
export function byProduct(rows, first, nameOf) {
    const out = [];
    const at = new Map();
    for (const group of byDay(rows, first)) {
        for (const row of group.rows) {
            const name = first(row) ? _t("Problems") : nameOf(row) || _t("No product");
            if (!at.has(name)) {
                at.set(name, { day: name, rows: [], product: !first(row) });
                out.push(at.get(name));
            }
            at.get(name).rows.push(row);
        }
    }
    return out;
}

export function orderProduct(row) {
    const names = [...new Set((row.lines || []).map((l) => l.name))];
    return names.length > 1 ? _t("Several products") : names[0] || "";
}

/** How many of the vendors asked gave a price, over the rows of a section. */
export function pricesIn(rows) {
    const cards = rows.flatMap((r) => r.cards || []);
    return cards.length ? _t("%(a)s of %(b)s gave a price", { a: cards.filter((c) => c.state === "price").length, b: cards.length }) : "";
}

export function matches(row, word) {
    const w = (word || "").trim().toLowerCase().replace(/^#/, "");
    if (!w) {
        return true;
    }
    const text = [row.ref, row.order_name, row.product, row.customer, row.phone, row.group, row.address]
        .concat((row.lines || []).map((l) => l.name), (row.cards || []).map((c) => c.vendor));
    return text.join(" ").toLowerCase().includes(w);
}

// ------------------------------------------------------------ orders
export const ORDER_TABS = [
    ["new", _t("New")], ["goods", _t("Waiting goods")], ["packing", _t("Packing")], ["payment", _t("Waiting payment")],
    ["rider", _t("Rider")], ["road", _t("On the way")], ["done", _t("Done")],
];

export function orderStep(row) {
    if (row.state === "delivered") {
        return "done";
    }
    if (row.supply_waiting) {
        return "goods";
    }
    if (row.state === "awaiting_shop") {
        return "new";
    }
    if (row.state === "preparing") {
        return "packing";
    }
    if (["ready", "to_assign"].includes(row.state)) {
        return !row.rider && (row.waiting_payment || row.unpaid_wait) ? "payment" : "rider";
    }
    if (["offered", "accepted"].includes(row.state)) {
        return "rider";
    }
    return "road";
}

export function orderProblem(row) {
    return !!(row.sos || row.issue);
}

/** [colour, words]: blue new, orange waiting, green good, grey going on, red problem. */
export function orderPills(row) {
    const step = orderStep(row);
    if (step === "done") {
        return [["good", _t("Delivered")]];
    }
    const out = [];
    if (row.sos) {
        out.push(["bad", _t("SOS")]);
    } else if (row.issue) {
        out.push(["bad", _t("Rider report")]);
    }
    if (step === "new") {
        out.push(["new", _t("New")]);
    }
    if (row.supply_waiting) {
        out.push(["warn", _t("Arranging")]);
    } else if (row.in_stock === true) {
        out.push(["good", _t("In stock")]);
    } else if (row.in_stock === false) {
        out.push(["warn", _t("No stock")]);
    }
    if (row.payment) {
        out.push([row.payment.colour, row.payment.words]);
    } else {
        out.push(row.paid ? ["good", _t("Paid")] : ["warn", _t("Payment pending")]);
    }
    if (row.self_delivery) {
        out.push(["", row.self_way === "collect" ? _t("Store pickup") : row.self_link ? row.self_who : _t("Our staff")]);
    }
    if (row.rider) {
        out.push(["", row.rider]);
    }
    return out;
}

/** The one button of the row: the next step, or nothing to press. */
export function orderMain(row) {
    if (row.self_link && !row.self_reached) {
        return null;            // the person with the link does the steps
    }
    if (row.self_delivery && orderStep(row) === "road") {
        return { key: "self_code", name: _t("Type the code"), cls: "btn-success" };
    }
    switch (orderStep(row)) {
        case "new":
            return { key: "accept", name: _t("Accept"), cls: "btn-primary" };
        case "goods":
            return { key: "supply_arrived", name: _t("Goods arrived"), cls: "btn-primary" };
        case "packing":
            return { key: "ready", name: _t("Packed"), cls: "btn-success" };
        case "payment":
            return row.can_send_pay_link && !row.pay_link ? { key: "pay_link", name: _t("Send payment link"), cls: "btn-primary" } : null;
        case "rider":
            if (!row.rider && ["ready", "to_assign"].includes(row.state)) {
                return { key: "call", name: _t("Call a rider"), cls: "btn-primary" };
            }
            return row.state === "accepted" ? { key: "dispatch", name: _t("Dispatch"), cls: "btn-primary" } : null;
        case "road":
            if (["picked", "dispatched"].includes(row.state)) {
                return row.state === "dispatched" ? { key: "near", name: _t("Near customer"), cls: "btn-primary" } : null;
            }
            return row.reached_on ? { key: "delivered", name: _t("Delivered"), cls: "btn-success" }
                : { key: "reached", name: _t("Reached"), cls: "btn-primary" };
    }
    return null;
}

/** Signed, goods, packed, paid, rider, delivered. */
export function orderPath(row) {
    const step = orderStep(row);
    const at = ["new", "goods", "packing", "payment", "rider", "road", "done"].indexOf(step);
    const done = [true, at >= 2, at >= 3, !!row.paid, at >= 5, at === 6];
    const now = done.indexOf(false);
    return [_t("Signed"), _t("Goods"), _t("Packed"), _t("Paid"), _t("Rider"), _t("Delivered")].map((name, i) => ({
        name, cls: done[i] ? "past" : i === now ? "now" : "" }));
}

// ------------------------------------------------------------ enquiries
export const ENQUIRY_TABS = [
    ["needs", _t("Needs you")], ["vendors", _t("With vendors")], ["sent", _t("Price sent")], ["ordered", _t("Ordered")], ["closed", _t("Closed")],
];

export function enquiryPill(row) {
    switch (row.kind) {
        case "pick":
            return ["new", _t("Choose the vendors")];
        case "choice":
            return ["new", _t("Two prices, approve one")];
        case "vendor":
            return ["new", _t("Choose the vendor")];
        case "price":
            return ["new", _t("Needs a price")];
        case "vendors":
            return ["", _t("%(a)s of %(b)s replied", { a: row.replied, b: row.asked })];
        case "sent":
            return row.better ? ["new", _t("Late, but cheaper")] : ["warn", _t("Customer to answer")];
        case "ordered":
            return ["good", _t("Ordered %s", row.order_name || "")];
    }
    return ["", row.reason || _t("Closed")];
}

// ------------------------------------------------------------ the colours
export class ColourKey extends Component {
    static template = "sales_automation_store.ColourKey";
    static props = {};
    setup() {
        this.root = useRef("root");
        this.state = useState({ open: false });
        this.away = (ev) => {
            if (this.state.open && (ev.key === "Escape" || (ev.type === "click" && this.root.el && !this.root.el.contains(ev.target)))) {
                this.state.open = false;
            }
        };
        onMounted(() => {
            document.addEventListener("click", this.away);
            document.addEventListener("keydown", this.away);
        });
        onWillUnmount(() => {
            document.removeEventListener("click", this.away);
            document.removeEventListener("keydown", this.away);
        });
    }
    toggle() {
        this.state.open = !this.state.open;
    }
}

export function remembered(key, fallback) {
    try {
        return localStorage.getItem(key) || fallback;
    } catch {
        return fallback;
    }
}
export function remember(key, value) {
    try {
        localStorage.setItem(key, value);
    } catch {
        /* a private window */
    }
}
