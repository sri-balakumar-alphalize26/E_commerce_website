/** @odoo-module **/

// What is new on the right: one card each for enquiries, orders and WhatsApp.
// Its X moves a card to "< bell" at the edge (the bell shakes), which brings it
// back. "See the list" opens the panel with every note.
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { SECTIONS } from "./notice_service";
import { shared } from "./notice_shared";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";

const TOP = 60;
const OURS = ".sa_pop, .sa_side, .sa_side_tab, .sa_key, .o_main_navbar, .modal, .o_dialog, .o-overlay-container, .o_popover, .dropdown-menu";

/** Where our notes begin: below what other modules keep fixed at the right. */
function freeTop(box) {
    const w = window.innerWidth;
    const h = window.innerHeight;
    const left = w - Math.min(406, w);
    const found = new Set();
    for (const x of [w - 14, w - 40, w - 120, w - 240, w - 380]) {
        for (let y = 8; x > 0 && y < h; y += 20) {
            for (const el of document.elementsFromPoint(x, y)) {
                for (let n = el; n && n !== document.body; n = n.parentElement) {
                    if (n.matches(OURS)) {
                        break;
                    }
                    if (getComputedStyle(n).position === "fixed") {
                        found.add(n === el ? n : el);
                        break;
                    }
                }
            }
        }
    }
    const rects = [...found].map((n) => n.getBoundingClientRect())
        .filter((r) => r.right > left && r.height < h * 0.6 && r.width < w * 0.6)
        .sort((a, b) => a.top - b.top);
    let top = TOP;
    for (const r of rects) {
        if (r.top < top + box.height && r.bottom > top) {
            top = r.bottom + 10;
        }
    }
    return top + 120 > h ? TOP : Math.round(top);
}

const ICON = { order: "fa-shopping-bag", price: "fa-tag", cheaper: "fa-arrow-down", paid: "fa-check", whatsapp: "fa-whatsapp", supply: "fa-truck",
    pick: "fa-users", stalled: "fa-clock-o", choice: "fa-balance-scale", vendor: "fa-balance-scale" };
const WORDS = { pick: _t("Choose the vendors"), stalled: _t("No vendor replied"), choice: _t("Approve a price"), vendor: _t("Choose the vendor") };
const CARD = {
    enquiries: [_t("Enquiries"), _t("Open Enquiries"), (n) => (n === 1 ? _t("1 enquiry to look at") : _t("%s enquiries to look at", n))],
    orders: [_t("Orders"), _t("Open Orders"), (n) => (n === 1 ? _t("1 new order or payment") : _t("%s new orders or payments", n))],
    whatsapp: [_t("WhatsApp"), _t("See what is wrong"), (n) => (n === 1 ? _t("1 WhatsApp problem") : _t("%s WhatsApp problems", n))],
};

export class NoticePanel extends Component {
    static template = "sales_automation_store.NoticePanel";
    static props = {};

    setup() {
        this.notice = useService("sa_notice");
        this.data = useState(this.notice.state);
        this.shared = useState(shared);
        this.state = useState({ shut: {}, top: TOP });
        this.pop = useRef("pop");
        const place = () => {
            if (this.pop.el) {
                const top = freeTop(this.pop.el.getBoundingClientRect());
                if (top !== this.state.top) {
                    this.state.top = top;
                }
            }
        };
        let timer;
        onMounted(() => {
            timer = setInterval(place, 800);
            window.addEventListener("resize", place);
        });
        onWillUnmount(() => {
            clearInterval(timer);
            window.removeEventListener("resize", place);
        });
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

    /** 369 Mart's counter alarm says how many orders wait for Accept. */
    get accept() {
        const n = this.shared.counter;
        return n ? { key: "accept", title: _t("New orders"), go: _t("Open the Counter"), list: false,
                     text: n === 1 ? _t("1 order is waiting to be accepted") : _t("%s orders are waiting to be accepted", n) } : null;
    }

    get cards() {
        const first = this.accept && !this.data.tucked.accept ? [this.accept] : [];
        return first.concat(this.others);
    }

    get others() {
        return this.sections.filter((s) => !this.data.tucked[s.key]).map((s) => ({ ...s, title: CARD[s.key][0], go: CARD[s.key][1], list: true, text: CARD[s.key][2](s.count) }));
    }

    get aside() {
        return this.sections.filter((s) => this.data.tucked[s.key]).length + (this.accept && this.data.tucked.accept ? 1 : 0);
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
