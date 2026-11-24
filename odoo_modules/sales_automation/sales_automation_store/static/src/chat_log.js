/** @odoo-module **/

// What was written, like in WhatsApp: received left, sent right, a line per day
// (24 Nov 2026). One tab for the customer, one for each vendor.
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillUpdateProps, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";
import { dayKey, dayName, timeOf } from "./board";

export class ChatLog extends Component {
    static template = "sales_automation_store.ChatLog";
    static props = { requestId: Number, vendorPhone: { type: String, optional: true }, plain: { type: Boolean, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ detail: null, tab: "all", failed: false });
        this.box = useRef("box");
        this.count = 0;
        onMounted(() => {
            this.load(this.props.requestId);
            this.timer = setInterval(() => this.load(this.props.requestId), 20000);
        });
        onWillUpdateProps((next) => {
            if (next.requestId !== this.props.requestId) {
                this.state.detail = null;
                this.state.tab = "all";
                this.count = 0;
                this.load(next.requestId);
            }
        });
        onPatched(() => {
            const n = this.lines.length;
            if (this.box.el && n !== this.count) {
                this.count = n;
                this.box.el.scrollTop = this.box.el.scrollHeight;
            }
        });
        onWillUnmount(() => clearInterval(this.timer));
    }
    async load(id) {
        try {
            const detail = await this.orm.silent.call("sa.group.request", "sa_enquiry_detail", [id]);
            this.state.detail = detail;
            this.state.failed = false;
        } catch {
            this.state.failed = !this.state.detail;
        }
    }
    /** Every message once, oldest first. */
    get messages() {
        const d = this.state.detail;
        if (!d) {
            return [];
        }
        const mine = d.messages.map((m) => ({ ...m, chat: "customer" }));
        const theirs = d.vendor_messages.map((m) => ({ ...m, chat: m.phone || m.name || "vendor" }));
        // one vendor's chat about this order, nothing else
        const tail = this.props.vendorPhone;
        if (tail) {
            return theirs.filter((m) => `${m.phone || ""}`.replace(/\D/g, "").slice(-9) === tail)
                .sort((a, b) => String(a.at).localeCompare(String(b.at)));
        }
        return mine.concat(theirs).sort((a, b) => String(a.at).localeCompare(String(b.at)));
    }
    get tabs() {
        const out = [{ key: "all", name: _t("All") }];
        const seen = new Set();
        for (const m of this.messages) {
            if (!seen.has(m.chat)) {
                seen.add(m.chat);
                out.push({ key: m.chat, name: m.chat === "customer" ? this.state.detail.customer || _t("Customer") : m.name || m.phone || _t("Vendor") });
            }
        }
        return out.length > 2 ? out : [];
    }
    get lines() {
        let day = "";
        const out = [];
        for (const [i, m] of this.messages.filter((x) => this.state.tab === "all" || x.chat === this.state.tab).entries()) {
            if (dayKey(m.at) !== day) {
                day = dayKey(m.at);
                out.push({ key: "d" + i, day: dayName(m.at) });
            }
            out.push({ key: "m" + i, ...m, sent: m.direction !== "incoming", time: timeOf(m.at) });
        }
        return out;
    }
    open(tab) {
        this.state.tab = tab;
    }
    who(m) {
        if (this.props.vendorPhone) {
            return "";
        }
        if (!m.sent) {
            return m.chat === "customer" ? this.state.detail.customer : m.name || m.phone;
        }
        return this.state.tab !== "all" ? "" : _t("To %s", m.chat === "customer" ? this.state.detail.customer || _t("customer") : m.name || m.phone);
    }
    tick(m) {
        return { sent: "\u2713", delivered: "\u2713\u2713", read: "\u2713\u2713", pending: "\u23F3", failed: "\u26A0", blocked: "\u26A0" }[m.status] || "";
    }
}

/** One vendor's chat about one order. */
export class ChatDialog extends Component {
    static template = "sales_automation_store.ChatDialog";
    static components = { Dialog, ChatLog };
    static props = { requestId: Number, vendorPhone: String, name: String, close: Function };
}
