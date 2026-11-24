/** @odoo-module **/

// Side notifications: a service, so they come on every menu. A note only
// opens something; it accepts and orders nothing.
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { reactive } from "@odoo/owl";
import { onShared, shared, sharedChanged } from "./notice_shared";

const AT_ONCE = 3;
const CLOSE_MS = 8000;
const TYPE = { blue: "info", green: "success", red: "danger" };
const SOUND = ["order", "cheaper", "whatsapp"];

/** One short tone. A browser allows it only after the first click or key. */
class Tone {
    constructor() {
        const arm = () => {
            try {
                this.audio = this.audio || new (window.AudioContext || window.webkitAudioContext)();
                this.audio.resume();
            } catch {
                /* no sound on this browser */
            }
        };
        document.addEventListener("pointerdown", arm, { capture: true, once: true });
        document.addEventListener("keydown", arm, { capture: true, once: true });
    }
    play() {
        if (!this.audio || this.audio.state !== "running") {
            return;
        }
        const osc = this.audio.createOscillator();
        const gain = this.audio.createGain();
        const now = this.audio.currentTime;
        osc.frequency.value = 660;
        gain.gain.setValueAtTime(0.12, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
        osc.connect(gain).connect(this.audio.destination);
        osc.start(now);
        osc.stop(now + 0.36);
    }
}

export const SECTIONS = [
    ["enquiries", _t("Enquiries"), ["price", "cheaper"]],
    ["orders", _t("Orders"), ["order", "paid", "supply"]],
    ["whatsapp", _t("WhatsApp"), ["whatsapp"]],
];
const CARD_KINDS = new Set(SECTIONS.flatMap((s) => s[2]));
const SCREENS = { accept: "sales_automation_store.action_sa_store_screen", enquiries: "sales_automation_store.action_sa_enquiry_screen", orders: "sales_automation_store.action_sa_store_screen" };
const MENUS = { accept: "sales_automation_store.menu_sa_store_screen", enquiries: "sales_automation_store.menu_sa_store_enquiries", orders: "sales_automation_store.menu_sa_store_screen" };

function sectionCounts(data) {
    const counts = {};
    for (const [key, , kinds] of SECTIONS) {
        counts[key] = (data.rows || []).filter((r) => !r.seen && kinds.includes(r.kind)).length
            + (key === "enquiries" ? (data.waiting || []).length : 0);
    }
    return counts;
}

export const noticeService = {
    dependencies: ["orm", "bus_service", "notification", "action", "menu"],

    start(env, { orm, bus_service, notification, action, menu }) {
        const state = reactive({ allowed: false, unread: 0, rows: [], waiting: [], panel: false, tucked: {} });
        const shown = new Map(); // key -> close
        const tone = new Tone();
        let before = {};

        function take(data) {
            // a section with something more comes out again
            const counts = sectionCounts(data);
            for (const key of Object.keys(counts)) {
                if (counts[key] > (before[key] || 0)) {
                    state.tucked[key] = false;
                }
            }
            before = counts;
            for (const w of data.waiting || []) {
                w.until = w.seconds >= 0 ? Date.now() + w.seconds * 1000 : 0;
            }
            Object.assign(state, data);
            shared.on = !!data.allowed;
            shared.known = true;
            sharedChanged();
        }

        async function load() {
            try {
                take(await orm.silent.call("sa.notice", "sa_notices", []));
            } catch {
                // no answer: the alarm's own note, as always
                if (!shared.known) {
                    take({ allowed: false, unread: 0, rows: [], waiting: [] });
                }
            }
        }

        function fold() {
            state.panel = false;
            for (const [key] of SECTIONS) {
                state.tucked[key] = true;
            }
            state.tucked.accept = true;
        }

        function unfold() {
            state.panel = true;
            load();
        }

        function tuck(key) {
            state.tucked[key] = true;
        }

        function untuck() {
            state.tucked = {};
            load();
        }

        async function openSection(section) {
            tuck(section.key);
            const target = menu.getAll().find((m) => m.xmlid && m.xmlid === MENUS[section.key]);
            if (target) {
                await menu.selectMenu(target);      // the Store app and its menu, not only the screen
            } else if (SCREENS[section.key]) {
                await action.doAction(SCREENS[section.key], { clearBreadcrumbs: true });
            } else {
                unfold();
            }
        }

        async function open(id) {
            const target = await orm.call("sa.notice", "sa_notice_open", [id]);
            if (target) {
                await action.doAction(target);
            }
            await load();
        }

        async function openEnquiry(id) {
            await action.doAction(await orm.call("sa.notice", "sa_notice_enquiry", [id]));
        }

        async function seen(ids) {
            take(await orm.call("sa.notice", "sa_notice_seen", ids ? [ids] : []));
        }

        function show(note) {
            if (!state.allowed) {
                return;
            }
            if (SOUND.includes(note.kind)) {
                tone.play();
            }
            if (state.panel || CARD_KINDS.has(note.kind)) {
                return; // it is in the panel or on a card
            }
            const before = shown.get(note.key);
            if (before) {
                before();
            } else if (shown.size >= AT_ONCE) {
                return; // it is in the bell
            }
            const close = notification.add(note.body, {
                title: note.title,
                type: TYPE[note.level] || "info",
                sticky: note.level === "red",
                autocloseDelay: CLOSE_MS,
                buttons: [{
                    name: _t("Open"),
                    primary: true,
                    onClick: () => {
                        close();
                        open(note.id);
                    },
                }],
                onClose: () => {
                    if (shown.get(note.key) === close) {
                        shown.delete(note.key);
                    }
                },
            });
            shown.set(note.key, close);
        }

        bus_service.subscribe("sa_notice/new", (note) => {
            show(note);
            load();
        });
        let counted = "";
        let waitingOrders = 0;
        onShared(() => {
            if (shared.counter > waitingOrders) {
                state.tucked.accept = false;        // one more: the card comes out again
            }
            waitingOrders = shared.counter;
            const now = `${shared.pick}-${shared.stalled}`;
            if (now !== counted) {          // another enquiry waits, or one less
                counted = now;
                if (state.allowed) {
                    load();
                }
            }
        });
        load();

        return { state, open, openEnquiry, openSection, seen, load, fold, unfold, tuck, untuck };
    },
};

registry.category("services").add("sa_notice", noticeService);
