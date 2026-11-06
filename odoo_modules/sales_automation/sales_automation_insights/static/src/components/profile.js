/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ScoreRing } from "./charts";
import { Heatmap } from "./heatmap";
import { EnquiryThread } from "./enquiry_thread";
import { starGlyphs, money, when, clock } from "./util";

/** One row, everything about it, on one page. */
export class Profile extends Component {
    static template = "sales_automation_insights.Profile";
    static components = { ScoreRing, Heatmap, EnquiryThread };
    static props = { kind: String, profile: Object, onBack: Function,
                     theme: { type: String, optional: true } };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({ open: {}, chat: { day: "", rows: [], count: 0, loading: false, tz: "" } });
        onWillStart(() => this.loadChat());
    }

    /** The WhatsApp log of one day; today unless a day is given. */
    async loadChat(day) {
        this.state.chat.loading = true;
        try {
            const res = await this.orm.call("sa.insight.entity", "sa_insights_chat_log",
                                            [this.h.id, day || null]);
            Object.assign(this.state.chat, res, { loading: false });
        } catch (e) {
            this.state.chat.loading = false;
            throw e;
        }
    }

    onDayChange(ev) {
        if (ev.target.value) {
            this.loadChat(ev.target.value);
        }
    }

    /** YYYY-MM-DD of a Date in the browser's own timezone - toISOString()
     *  is UTC and moved a local midnight east of Greenwich back a day. */
    localDay(d) {
        const p = (n) => String(n).padStart(2, "0");
        return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    }

    shiftDay(delta) {
        const d = new Date((this.state.chat.day || this.localDay(new Date())) + "T00:00:00");
        d.setDate(d.getDate() + delta);
        this.loadChat(this.localDay(d));
    }

    get chatIsToday() {
        return this.state.chat.day === this.localDay(new Date());
    }

    get h() {
        return this.props.profile.header;
    }

    get initials() {
        const parts = (this.h.name || "?").trim().split(/\s+/);
        return parts.slice(0, 2).map((p) => p[0]).join("").toUpperCase();
    }

    get ltvPct() {
        const max = this.h.lifetime_max || 0;
        return max ? Math.round(100 * (this.h.lifetime_value || 0) / max) : 0;
    }

    get rows() {
        return this.props.kind === "vendor" ? this.props.profile.supplies : this.props.profile.orders;
    }

    get enquiries() {
        return this.props.kind === "vendor" ? this.props.profile.asks : this.props.profile.enquiries;
    }

    stars() {
        return starGlyphs(this.h.stars);
    }

    money(v) {
        return money(v, this.h.currency);
    }

    when(iso) {
        return when(iso);
    }

    clock(iso) {
        return clock(iso);
    }

    pct(score) {
        return score === null || score === undefined ? 0 : Math.round(score * 100);
    }

    segments(progress) {
        // Five bars, like the mockup's progress pills.
        const on = Math.round((progress || 0) / 20);
        return [1, 2, 3, 4, 5].map((i) => i <= on);
    }

    toggle(reqId) {
        this.state.open[reqId] = !this.state.open[reqId];
    }

    openRecord(model, id) {
        if (!id) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window", res_model: model, res_id: id,
            views: [[false, "form"]], target: "current",
        });
    }
}
