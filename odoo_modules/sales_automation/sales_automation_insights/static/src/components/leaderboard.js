/** @odoo-module **/

import { Component } from "@odoo/owl";
import { starGlyphs, money, when } from "./util";

/** The ranked table. Tick rows to compare, click a row to open it. */
export class Leaderboard extends Component {
    static template = "sales_automation_insights.Leaderboard";
    static props = {
        kind: String, board: { type: Object, optional: true },
        selected: Object, search: String, busy: Boolean,
        tier: { type: String, optional: true }, onTier: { type: Function, optional: true },
        aspect: { type: String, optional: true }, onAspect: { type: Function, optional: true },
        onSearch: Function, onOpen: Function, onToggle: Function,
        onCompare: Function, onRecompute: Function,
    };

    // The chips above the list: a verdict each, plus the flagged ones.
    static CHIPS = [
        ["all", "All"], ["best", "⭐ Best"], ["better", "Better"],
        ["normal", "Normal"], ["poor", "Poor"], ["new", "New"], ["flagged", "⚑ Flagged"],
    ];
    static TIER_LABEL = { best: "BEST", better: "BETTER", normal: "NORMAL", poor: "POOR", new: "NEW" };

    // The angle chips. Each one is a component score (or the order count),
    // a threshold and a direction: "fast" keeps rows scoring at least 0.7 on
    // reply speed and sorts the fastest first; "slow" keeps rows under 0.4.
    static ASPECTS = {
        customer: [
            ["all", "All"],
            ["reply_fast", "\u26a1 Fast reply", "reply", ">=", 0.7],
            ["reply_slow", "\ud83d\udc22 Slow reply", "reply", "<", 0.4],
            ["buyers", "\ud83d\uded2 Buyers", "order_count", ">=", 1],
            ["no_orders", "No orders", "order_count", "<", 1],
            ["pays_well", "\ud83d\udcb0 Pays well", "payment", ">=", 0.8],
            ["pay_issues", "\u26a0 Payment issues", "payment", "<", 0.5],
        ],
        vendor: [
            ["all", "All"],
            ["reply_fast", "\u26a1 Fast reply", "reply_speed", ">=", 0.7],
            ["reply_slow", "\ud83d\udc22 Slow reply", "reply_speed", "<", 0.4],
            ["wins", "\ud83c\udfc6 Wins quotes", "win", ">=", 0.5],
            ["no_wins", "Never cheapest", "win", "<", 0.5],
            ["cheapest", "\ud83d\udcb0 Cheapest", "price", ">=", 0.9],
            ["pricey", "\u26a0 Pricey", "price", "<", 0.7],
        ],
    };

    _aspectValue(row, code) {
        if (code === "order_count") {
            return row.order_count || 0;
        }
        const v = row.scores && row.scores[code];
        return (v === null || v === undefined) ? null : v;
    }

    _aspectDef() {
        const defs = Leaderboard.ASPECTS[this.props.kind === "vendor" ? "vendor" : "customer"];
        return defs.find((d) => d[0] === (this.props.aspect || "all")) || defs[0];
    }

    _passesAspect(row, def) {
        if (def[0] === "all") {
            return true;
        }
        const v = this._aspectValue(row, def[2]);
        if (v === null) {
            return false;        // no sample on that angle
        }
        return def[3] === ">=" ? v >= def[4] : v < def[4];
    }

    get aspects() {
        const defs = Leaderboard.ASPECTS[this.props.kind === "vendor" ? "vendor" : "customer"];
        const base = this.tierRows;
        return defs.map((d) => ({
            code: d[0], label: d[1], on: (this.props.aspect || "all") === d[0],
            count: base.filter((r) => this._passesAspect(r, d)).length,
        }));
    }

    onAspectChip(code) {
        if (this.props.onAspect) {
            this.props.onAspect(code);
        }
    }

    get allRows() {
        return (this.props.board && this.props.board.rows) || [];
    }

    /** The rows the verdict chip lets through. */
    get tierRows() {
        const tier = this.props.tier || "all";
        if (tier === "all") {
            return this.allRows;
        }
        if (tier === "flagged") {
            return this.allRows.filter((r) => r.remarks_count > 0);
        }
        return this.allRows.filter((r) => (r.tier || "new") === tier);
    }

    /** Verdict chip, then the angle chip; an angle also orders the list by it. */
    get rows() {
        const def = this._aspectDef();
        const rows = this.tierRows.filter((r) => this._passesAspect(r, def));
        if (def[0] === "all") {
            return rows;
        }
        const sign = def[3] === ">=" ? -1 : 1;
        return rows.slice().sort((a, b) => sign * ((this._aspectValue(a, def[2]) || 0) - (this._aspectValue(b, def[2]) || 0)));
    }

    get chips() {
        const counts = (this.props.board && this.props.board.tier_counts) || {};
        return Leaderboard.CHIPS.map(([code, label]) => ({
            code, label, count: counts[code] || 0, on: (this.props.tier || "all") === code,
        }));
    }

    tierLabel(row) {
        return Leaderboard.TIER_LABEL[row.tier] || "NEW";
    }

    onChip(code) {
        if (this.props.onTier) {
            this.props.onTier(code);
        }
    }

    get selectedCount() {
        return Object.values(this.props.selected).filter(Boolean).length;
    }

    stars(row) {
        return starGlyphs(row.stars);
    }

    money(v) {
        return money(v, this.props.board ? this.props.board.currency : "");
    }

    when(iso) {
        return when(iso);
    }

    onSearchInput(ev) {
        if (ev.key === "Enter") {
            this.props.onSearch(ev.target.value);
        }
    }

    onTick(ev, row) {
        ev.stopPropagation();
        this.props.onToggle(row.id);
    }
}
