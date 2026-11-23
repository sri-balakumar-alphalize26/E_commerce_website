/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";

export class NoticeBell extends Component {
    static template = "sales_automation_store.Bell";
    static props = {};

    setup() {
        this.notice = useService("sa_notice");
        this.data = useState(this.notice.state);
        this.state = useState({ open: false });
        this.root = useRef("root");
        this.away = (ev) => {
            const outside = ev.type === "click" && this.root.el && !this.root.el.contains(ev.target);
            if (this.state.open && (ev.key === "Escape" || outside)) {
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
        if (this.state.open) {
            this.notice.load();
        }
    }

    async go(row) {
        this.state.open = false;
        await this.notice.open(row.id);
    }

    when(iso) {
        const d = new Date(iso);
        return d.toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    }
}

registry.category("systray").add("sales_automation_store.bell", { Component: NoticeBell }, { sequence: 24 });
