/** @odoo-module **/

/**
 * The Insights console: one screen, two doors.
 *
 * The same component serves the Customer Dashboard and the Vendor Dashboard;
 * the action's context says which. Three views live inside it - the ranked
 * board, one row's full profile, and a side-by-side of two to four rows -
 * and nothing here makes a sound: it imports nothing from the store screens
 * and never touches their `presence` or `Alarm`.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { Leaderboard } from "./components/leaderboard";
import { Profile } from "./components/profile";
import { Compare } from "./components/compare";

export class InsightsScreen extends Component {
    static template = "sales_automation_insights.Screen";
    static components = { Leaderboard, Profile, Compare };
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const ctx = (this.props.action && this.props.action.context) || {};
        this.kind = ctx.kind
            || ((this.props.action && this.props.action.tag || "").endsWith("vendors")
                ? "vendor" : "customer");

        this.state = useState({
            view: "board",
            search: "",
            board: null,
            profile: null,
            compare: null,
            selected: {},
            loading: true,
            busy: false,
            // Night is the console's native look; day is a token swap. The
            // choice is per browser - a counter screen and a manager's laptop
            // have no reason to agree.
            theme: this._loadTheme(),
            // Which verdict the board is narrowed to. Remembered per browser
            // and per dashboard, like the theme.
            tier: this._loadTier(),
            // Second row of chips: reply / orders / payment angle.
            aspect: this._loadAspect(),
        });

        onWillStart(() => this.loadBoard());
    }

    _tierKey() {
        return "sai_tier_" + (this.kind || "customer");
    }

    _loadTier() {
        try {
            const v = window.localStorage.getItem("sai_tier_" + (this.kind || "customer"));
            return ["best", "better", "normal", "poor", "new", "flagged"].includes(v) ? v : "all";
        } catch (_err) {
            return "all";
        }
    }

    _loadAspect() {
        try {
            return window.localStorage.getItem("sai_aspect_" + (this.kind || "customer")) || "all";
        } catch (_err) {
            return "all";
        }
    }

    onAspect(aspect) {
        this.state.aspect = aspect || "all";
        try {
            window.localStorage.setItem("sai_aspect_" + (this.kind || "customer"), this.state.aspect);
        } catch (_err) {
            // Not remembered, still applied.
        }
    }

    onTier(tier) {
        this.state.tier = tier || "all";
        try {
            window.localStorage.setItem(this._tierKey(), this.state.tier);
        } catch (_err) {
            // Not remembered, still applied.
        }
    }

    _loadTheme() {
        try {
            const v = window.localStorage.getItem("sai_theme");
            return v === "day" ? "day" : "night";
        } catch (_err) {
            return "night";      // private windows, blocked storage
        }
    }

    toggleTheme() {
        this.state.theme = this.state.theme === "day" ? "night" : "day";
        try {
            window.localStorage.setItem("sai_theme", this.state.theme);
        } catch (_err) {
            // Not remembered, still switched.
        }
    }

    get title() {
        return this.kind === "vendor" ? "Vendor Dashboard" : "Customer Dashboard";
    }

    get selectedIds() {
        return Object.keys(this.state.selected)
            .filter((id) => this.state.selected[id])
            .map((id) => parseInt(id, 10));
    }

    async loadBoard() {
        this.state.loading = true;
        try {
            this.state.board = await this.orm.call(
                "sa.insight.entity", "sa_insights_board",
                [this.kind, this.state.search, 200]);
        } finally {
            this.state.loading = false;
        }
    }

    async onSearch(value) {
        this.state.search = value || "";
        await this.loadBoard();
    }

    onToggle(id) {
        const on = !this.state.selected[id];
        if (on && this.selectedIds.length >= 4) {
            this.notification.add("Compare up to four at a time.", { type: "warning" });
            return;
        }
        this.state.selected[id] = on;
    }

    async onOpen(id) {
        this.state.busy = true;
        try {
            this.state.profile = await this.orm.call(
                "sa.insight.entity", "sa_insights_profile", [this.kind, id]);
            this.state.view = "profile";
        } finally {
            this.state.busy = false;
        }
    }

    async onCompare() {
        const ids = this.selectedIds;
        if (ids.length < 2) {
            this.notification.add("Tick at least two rows to compare.", { type: "warning" });
            return;
        }
        this.state.busy = true;
        try {
            this.state.compare = await this.orm.call(
                "sa.insight.entity", "sa_insights_compare", [this.kind, ids]);
            this.state.view = "compare";
        } finally {
            this.state.busy = false;
        }
    }

    async onRecompute() {
        this.state.busy = true;
        try {
            await this.orm.call("sa.insight.entity", "action_recompute", [[]]);
            await this.loadBoard();
            this.notification.add("Ratings recomputed.", { type: "success" });
        } finally {
            this.state.busy = false;
        }
    }

    onBack() {
        this.state.view = "board";
        this.state.profile = null;
        this.state.compare = null;
    }

    /** Open one of the compared rows straight from the compare view. */
    onOpenFromCompare(id) {
        return this.onOpen(id);
    }
}

registry.category("actions").add("sales_automation_insights.customers", InsightsScreen);
registry.category("actions").add("sales_automation_insights.vendors", InsightsScreen);
