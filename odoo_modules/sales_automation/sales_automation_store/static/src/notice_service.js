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

export const noticeService = {
    dependencies: ["orm", "bus_service", "notification", "action"],

    start(env, { orm, bus_service, notification, action }) {
        const state = reactive({ allowed: false, unread: 0, rows: [], waiting: [], panel: false });
        const shown = new Map(); // key -> close
        const tone = new Tone();
        let folded = false; // by its X, until the next load of the page

        function take(data) {
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

        function unfoldForNews() {
            if (state.allowed && !folded && (state.unread || state.waiting.length)) {
                state.panel = true;
            }
        }

        function fold() {
            folded = true;
            state.panel = false;
        }

        function unfold() {
            folded = false;
            state.panel = true;
            load();
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
            if (state.panel) {
                return; // it is in the panel, which is open
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
        onShared(() => {
            unfoldForNews();
            const now = `${shared.pick}-${shared.stalled}`;
            if (now !== counted) {          // another enquiry waits, or one less
                counted = now;
                if (state.allowed) {
                    load();
                }
            }
        });
        load();

        return { state, open, openEnquiry, seen, load, fold, unfold };
    },
};

registry.category("services").add("sa_notice", noticeService);
