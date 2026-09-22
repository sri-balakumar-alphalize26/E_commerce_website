/**
 * 369 Mart support, as a queue somebody works through.
 *
 * The twin of the app's console at /admin/support, and the sibling of the
 * orders, returns and reviews desks. It answers "who is waiting on me", oldest
 * first; the kanban it replaces answers "show me the tickets", and keeps what
 * this does not try to do: grouping, the form, and the chatter.
 *
 * Everything it reads is already on the model (models/ticket_admin.py) and
 * already tested, because the console screen needed exactly the same answers.
 * One list call brings the rows and the tile counts together.
 *
 * Opening one is a **dialog**, not a panel down the side - the same choice the
 * returns desk made, for the same reason. A conversation plus a reply box does
 * not fit in 380px, and most of that width went on wrapping.
 *
 * Three rules carried from the console, each load-bearing:
 *
 *  - **The next step is the server's.** `row.next.label` and `row.next.action`
 *    come from the model, so a button's words cannot drift from what pressing
 *    it does.
 *  - **The wait is the server's too.** `waiting_minutes` on the model is a
 *    stored compute that never moves while a ticket sits unanswered, so it
 *    reads nought for exactly the tickets this screen exists to surface. The
 *    payload works it out live and the desk only prints it - never recompute
 *    it here from `openedAt`, or the two screens will disagree.
 *  - **Reply is hidden, not disabled, on a closed ticket.** The model refuses
 *    it, and offering a box only to reject what somebody typed is a trap.
 *
 * `Pick` is imported from the orders desk rather than copied - mart369_support
 * depends on mart369_order, so it is already in the bundle.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

import { Pick } from "@mart369_order/desk/order_desk";

const MODEL = "mart369.ticket";

/* Each tile sets the tab, so the strip is the filter rather than a read-out
   above one. "Longest wait" is the exception - there is no tab for it, so it
   stays a plain figure and does not look pressable. */
const TILES = [
    { key: "needs", tab: "needs", label: _t("Needs a reply"), icon: "fa-inbox", warn: true },
    { key: "late", label: _t("Waiting over 30 min"), icon: "fa-exclamation-triangle", bad: true, flat: true },
    { key: "longest", label: _t("Longest wait"), icon: "fa-clock-o", minutes: true, flat: true },
    { key: "answeredToday", label: _t("Answered today"), icon: "fa-check", flat: true },
];

const TABS = [
    { key: "needs", label: _t("Needs a reply"), badge: "needs" },
    { key: "new", label: _t("Waiting"), badge: "new" },
    { key: "open", label: _t("Being handled"), badge: "open" },
    { key: "waiting", label: _t("On the customer"), badge: "waiting" },
    { key: "done", label: _t("Answered"), badge: "done" },
    { key: "all", label: _t("All"), badge: "all" },
];

const PAGE = 30;
const POLL_MS = 30000;
const MAX_REPLY = 500;

/** Odoo wraps a UserError a couple of ways; dig the sentence out of whichever
 *  one arrived. The same helper the other desks carry. */
function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

/** A wait, in words. Takes the server's minutes and only formats them. */
function waited(mins) {
    if (!mins) {
        return _t("just now");
    }
    if (mins < 60) {
        return _t("%s min", mins);
    }
    const hours = Math.round(mins / 60);
    return hours < 24 ? _t("%s h", hours) : _t("%s d", Math.round(hours / 24));
}

function ago(ms) {
    if (!ms) {
        return "";
    }
    return waited(Math.round((Date.now() - ms) / 60000));
}

/* ------------------------------------------------------------- one ticket */

/**
 * One ticket, opened to be read and answered.
 *
 * Loads its own detail rather than being handed one, so a reply redraws from
 * the server instead of from a guess - answering is also what claims the
 * ticket and stamps it answered, and this dialog must not have to work that
 * out. `onChanged` then tells the queue behind it to catch up.
 */
export class TicketDialog extends Component {
    static template = "mart369_support.TicketDialog";
    static components = { Dialog };
    static props = {
        ref: { type: String },
        staff: { type: Array },
        onChanged: { type: Function },
        close: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.state = useState({
            detail: null,
            text: "",
            loading: true,
            busy: false,
            error: "",
        });
        onWillStart(() => this.load());
    }

    async load() {
        try {
            const detail = await this.orm.call(MODEL, "mart369_admin_detail", [
                this.props.ref,
            ]);
            this.state.detail = detail && detail.ref ? detail : null;
            this.state.error = this.state.detail
                ? ""
                : _t("That ticket is no longer there.");
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    /** Never optimistic: a refusal means this dialog was out of date, so it
     *  re-reads either way, and the queue behind it does too. */
    async run(fn) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await fn();
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
        } finally {
            this.state.busy = false;
            await this.load();
            this.props.onChanged();
        }
    }

    send() {
        const said = (this.state.text || "").trim();
        if (!said) {
            return;
        }
        return this.run(async () => {
            await this.orm.call(MODEL, "mart369_admin_reply", [this.props.ref, said]);
            this.state.text = "";
        });
    }

    advance() {
        const next = this.state.detail?.next;
        if (!next) {
            return;
        }
        return this.run(() =>
            this.orm.call(MODEL, "mart369_admin_advance", [this.props.ref, next.action])
        );
    }

    park() {
        return this.run(() =>
            this.orm.call(MODEL, "mart369_admin_advance", [this.props.ref, "wait"])
        );
    }

    assign(userId) {
        return this.run(() =>
            this.orm.call(MODEL, "mart369_admin_assign", [
                this.props.ref,
                userId ? Number(userId) : false,
            ])
        );
    }

    askDrop() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Drop this ticket?"),
            body: _t(
                "It is closed without an answer, and the customer is not told."
            ),
            confirmLabel: _t("Drop it"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(() =>
                    this.orm.call(MODEL, "mart369_admin_advance", [
                        this.props.ref,
                        "drop",
                    ])
                ),
            cancel: () => {},
        });
    }

    get staffOptions() {
        return [
            ["", _t("Nobody yet")],
            ...this.props.staff.map((person) => [String(person.id), person.name]),
        ];
    }

    /** Who the <select> should show as chosen, as a string to compare against
     *  the option values. A getter rather than an expression in the template:
     *  an OWL template is evaluated without globals, so `String(...)` in there
     *  is a TypeError at render time rather than a mistake anybody sees. */
    get assignedValue() {
        const id = this.state.detail?.assigneeId;
        return id ? String(id) : "";
    }

    get left() {
        return MAX_REPLY - (this.state.text || "").length;
    }

    waited(mins) { return waited(mins); }
    ago(ms) { return ago(ms); }
}

/* --------------------------------------------------------------- the queue */

export class SupportDesk extends Component {
    static template = "mart369_support.SupportDesk";
    static components = { Layout, Pick };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.TILES = TILES;
        this.TABS = TABS;

        this.state = useState({
            tab: "needs",
            q: "",
            mine: "",
            assignee: "",
            sort: "old",
            limit: PAGE,
            rows: [],
            total: 0,
            counts: null,
            extra: {},
            staff: [],
            sel: null,
            loading: true,
            busy: false,
            error: "",
        });

        this.search = useDebounced((ev) => {
            this.state.q = ev.target.value.trim();
            this.state.limit = PAGE;
            this.load();
        }, 300);

        onWillStart(() => this.load());

        // A queue that goes stale while somebody stares at it is the failure
        // this screen exists to avoid. Skipped while a write is in flight, and
        // quiet so it never flashes the loading line.
        this.timer = setInterval(() => {
            if (!this.state.busy) {
                this.load({ quiet: true });
            }
        }, POLL_MS);
        onWillUnmount(() => clearInterval(this.timer));
    }

    // -------------------------------------------------------------- reading

    async load({ quiet = false } = {}) {
        if (!quiet) {
            this.state.loading = true;
        }
        try {
            const page = await this.orm.call(MODEL, "mart369_admin_list", [], {
                tab: this.state.tab,
                q: this.state.q || null,
                mine: this.state.mine === "1" ? true : null,
                assignee: this.state.assignee || null,
                sort: this.state.sort,
                limit: this.state.limit,
            });
            this.state.rows = page.tickets || [];
            this.state.total = page.total || 0;
            this.state.counts = page.counts || null;
            this.state.staff = page.staff || [];
            this.state.extra = {
                late: page.late || 0,
                longest: page.longest || 0,
                answeredToday: page.answeredToday || 0,
            };
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    select(row) {
        this.state.sel = row.ref;
        this.dialog.add(
            TicketDialog,
            {
                ref: row.ref,
                staff: this.state.staff,
                onChanged: () => this.load({ quiet: true }),
            },
            { onClose: () => (this.state.sel = null) }
        );
    }

    // ------------------------------------------------------------- filtering

    pick(tab) {
        if (!tab) {
            return; // a flat tile, which filters nothing
        }
        this.state.tab = tab;
        this.state.limit = PAGE;
        this.load();
    }

    setFilter(key, value) {
        this.state[key] = value;
        this.state.limit = PAGE;
        this.load();
    }

    showMore() {
        this.state.limit += PAGE;
        this.load();
    }

    tabCount(tab) {
        return tab.badge ? this.state.counts?.[tab.badge] ?? null : null;
    }

    /** Straight off the server's numbers, never `state.rows.length`: the tiles
     *  count every ticket, not the filtered ones. */
    tileValue(tile) {
        const raw =
            tile.key in this.state.extra
                ? this.state.extra[tile.key]
                : this.state.counts?.[tile.key] ?? 0;
        return tile.minutes ? waited(raw) : raw;
    }

    // -------------------------------------------------------------- writing

    async run(fn) {
        if (this.state.busy) {
            return false;
        }
        this.state.busy = true;
        try {
            await fn();
            return true;
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
            return false;
        } finally {
            this.state.busy = false;
            await this.load({ quiet: true });
        }
    }

    advance(row) {
        if (!row.next) {
            return;
        }
        return this.run(() =>
            this.orm.call(MODEL, "mart369_admin_advance", [row.ref, row.next.action])
        );
    }

    /** The kanban, for what this screen does not do: grouping, the form and
        the chatter. */
    moreViews() {
        this.action.doAction("mart369_support.action_mart369_tickets");
    }

    // --------------------------------------------------------------- drawing

    get mineOptions() {
        return [["", _t("Anyone's")], ["1", _t("Mine only")]];
    }

    get staffOptions() {
        return [
            ["", _t("Anybody")],
            ...this.state.staff.map((person) => [String(person.id), person.name]),
        ];
    }

    get sortOptions() {
        return [["old", _t("Longest wait first")], ["new", _t("Newest first")]];
    }

    waited(mins) { return waited(mins); }
    ago(ms) { return ago(ms); }
}

registry.category("actions").add("mart369_support.desk", SupportDesk);
