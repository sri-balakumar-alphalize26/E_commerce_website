/** @odoo-module **/

// Every vendor asked, one card each (24 Nov 2026). Sorting is only how it looks:
// the star and the automatic choice never follow it. No price: always last.
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";
import { dayKey, remember, remembered } from "./board";
import { ChatDialog } from "./chat_log";

const STATES = { waiting: _t("Waiting"), no: _t("Said no"), yes: _t("Has it, no price"), held: _t("Gave a price, to check") };

export function cardState(card) {
    return STATES[card.state] || "";
}

/** "Today 15:48:20", "23 Nov 15:48:20", or a dash. */
export function replyTime(iso, now = new Date()) {
    const d = iso ? new Date(iso) : null;
    if (!d || isNaN(d)) {
        return "—";
    }
    const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    return (dayKey(iso) === dayKey(now.toISOString()) ? _t("Today") : d.toLocaleDateString([], { day: "numeric", month: "short" })) + " " + time;
}

export function sortCards(cards, by, descending) {
    const sign = descending ? -1 : 1;
    const priced = cards.filter((c) => c.state === "price").sort((a, b) => by === "time"
        ? sign * (String(a.replied_at).localeCompare(String(b.replied_at)) || a.rank - b.rank)
        : sign * (a.price - b.price) || a.rank - b.rank);
    return priced.concat(cards.filter((c) => c.state !== "price"));
}

export class VendorCards extends Component {
    static template = "sales_automation_store.VendorCards";
    static props = { cards: Array, requestId: { type: Number, optional: true }, why: { type: String, optional: true }, onChoose: { type: Function, optional: true }, busy: { type: Boolean, optional: true } };

    setup() {
        this.dialog = useService("dialog");
        this.state = useState({ by: remembered("sa_cards_sort", "rate"), down: false, show: "all" });
    }
    get cards() {
        const show = this.state.show;
        return sortCards(this.props.cards.filter((c) => show === "all" || (c.state === "price") === (show === "replied")),
            this.state.by, this.state.down);
    }
    get counts() {
        const replied = this.props.cards.filter((c) => c.state === "price").length;
        return { all: this.props.cards.length, replied, waiting: this.props.cards.length - replied };
    }
    sort(by) {
        this.state.down = this.state.by === by ? !this.state.down : false;
        this.state.by = by;
        remember("sa_cards_sort", by);
    }
    show(which) {
        this.state.show = which;
    }
    arrow(by) {
        return this.state.by === by ? (this.state.down ? " ↓" : " ↑") : "";
    }
    chat(card) {
        this.dialog.add(ChatDialog, { requestId: this.props.requestId, vendorPhone: card.phone, name: card.vendor });
    }
    words(card) {
        return cardState(card);
    }
    time(card) {
        return replyTime(card.replied_at);
    }
    money(card) {
        return card.price === null ? "—" : `${card.price.toFixed(2)} ${card.currency || ""}`;
    }
}
