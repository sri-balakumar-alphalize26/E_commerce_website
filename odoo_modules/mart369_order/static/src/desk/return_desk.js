/**
 * 369 Mart returns, as a queue somebody works through.
 *
 * The twin of the app's console at /admin/returns, and the sibling of the
 * orders desk next door. It answers "what do I deal with next" - oldest first,
 * five tiles that are the filter, one next-step button per row. The kanban it
 * replaces answers "show me the returns", and keeps what this does not try to
 * do: grouping, the form, the photo widget.
 *
 * Everything it reads is already on the model (models/return_admin.py) and
 * already tested, because the console screen needed exactly the same answers.
 * One list call brings the rows and the tile counts together.
 *
 * Opening one is a **dialog**, not a panel down the side. A claim carries a
 * customer, their own words, the photos, the refund split and the ladder, and
 * 380px of side panel was not room to read any of it - most of that width went
 * on wrapping the order number onto two lines.
 *
 * Three rules carried from the console, each load-bearing:
 *
 *  - The browser never works out what happens next. `row.next.label` and the
 *    dialog's `flow` come from the server, so the button's words cannot drift
 *    from what pressing it does. They did once: keyed by the state being
 *    entered rather than the one being left, every button named the step after
 *    the one it took.
 *  - Refuse is hidden, not disabled, when the server says so. The model
 *    refuses a refusal once the refund has gone, and offering a button only to
 *    reject it is a trap.
 *  - It never says "Refunded" flatly. The refund puts back the wallet leg and
 *    leaves gateway money to the gateway, so the dialog shows the split. An
 *    operator who reads "refunded", closes the ticket and leaves the customer
 *    out of pocket is the bug this screen exists not to cause.
 *
 * `Pick` is imported from the orders desk rather than copied: same module,
 * same directory, already exported. What must NOT be reached for is anything
 * in mart369_home - the Icon component, useSaveQueue, the SaveChip - because
 * orders does not depend on it and should not. Icons here are Font Awesome,
 * as they are next door. There is no save queue to want: every action is a
 * command, not a field being typed.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Confirm } from "@mart369/ui/confirm";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Search } from "@mart369/ui/search";

import { Pick } from "@mart369/ui/pick";
import { Icon } from "@mart369/ui/icon";
import { Tabs } from "@mart369/ui/tabs";
import { Pill } from "@mart369/ui/pill";

const MODEL = "mart369.order.return";

/* The five states a return can be in. The label is the server's when it sends
   one; this is the fallback. Colour comes from `.rd-s-<state>`. */
export const STATUS = {
    requested: _t("Requested"),
    pickup: _t("Pickup scheduled"),
    picked: _t("Picked up"),
    done: _t("Refund issued"),
    refused: _t("Refused"),
};

/* Each tile sets the tab, so the strip is the filter rather than a read-out
   above one. Five, in the order a return really moves. */
const TILES = [
    { tab: "requested", label: _t("Requested"), icon: "box" },
    { tab: "pickup", label: _t("Pickup scheduled"), icon: "truck" },
    { tab: "picked", label: _t("Picked up"), icon: "check" },
    { tab: "done", label: _t("Refunded"), icon: "money" },
    { tab: "refused", label: _t("Refused"), icon: "x", warn: true },
];

const TABS = [
    { key: "needs", label: _t("Needs me"), badge: "needs" },
    { key: "all", label: _t("All") },
    { key: "done", label: _t("Refunded") },
    { key: "refused", label: _t("Refused") },
];

const PAGE = 20;

/* Which tone each state wears. The words come from `stateLabel`, which the
   server's vocabulary drives, so only the colour is decided here. */
const TONES = {
    requested: { tone: "blue" },
    pickup: { tone: "amber" },
    picked: { tone: "violet" },
    done: { tone: "green" },
    refused: { tone: "red" },
};
const POLL_MS = 30000;

/* ------------------------------------------------------------------ shared
   Used by the queue and by the dialog, so the two cannot format the same
   number or the same instant differently. */

/** Odoo wraps a UserError a couple of ways; dig the sentence out of whichever
 *  one arrived. */
function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

/**
 * Format what the shop sent, never glue on a symbol of our own. The amount and
 * its currency travel together, because a return carries the money the order
 * was charged in and a later pricelist must not rewrite an old refund. Same
 * rule as the orders desk and lib/money.js.
 */
function money(amount, currency) {
    const value = Number(amount) || 0;
    const decimals = currency?.decimals ?? 2;
    const shown = value.toLocaleString(currency?.locale, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
    if (!currency?.symbol) {
        return shown;
    }
    return currency.position === "after"
        ? `${shown} ${currency.symbol}`
        : `${currency.symbol}${shown}`;
}

function when(ms) {
    if (!ms) {
        return "";
    }
    return new Date(ms).toLocaleString(undefined, {
        day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
    });
}

function ago(ms) {
    if (!ms) {
        return "";
    }
    const mins = Math.floor((Date.now() - ms) / 60000);
    if (mins < 1) {
        return _t("just now");
    }
    if (mins < 60) {
        return _t("%s min ago", mins);
    }
    const hours = Math.floor(mins / 60);
    if (hours < 24) {
        return _t("%s h ago", hours);
    }
    return _t("%s d ago", Math.floor(hours / 24));
}

function kindLabel(kind) {
    return kind === "replace" ? _t("Replacement") : _t("Refund");
}

function stateLabel(row) {
    return row.stateLabel || STATUS[row.state] || row.state;
}

/* -------------------------------------------------------------- one return */

/**
 * One return, opened.
 *
 * It loads its own detail rather than being handed one, so a write here
 * redraws from the server instead of from a guess; `onChanged` then tells the
 * queue behind it to catch up.
 *
 * Opened through the dialog service, which is how the rest of the suite does
 * it - see NamePrompt in mart369_home's pages.js.
 */
export class ReturnDialog extends Component {
    static template = "mart369_order.ReturnDialog";
    static components = { Dialog, Icon, Pill };
    static props = {
        id: { type: String },
        onChanged: { type: Function },
        close: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.state = useState({ detail: null, loading: true, busy: false, error: "" });
        onWillStart(() => this.load());
    }

    async load() {
        try {
            const detail = await this.orm.call(MODEL, "mart369_returns_detail", [
                this.props.id,
            ]);
            this.state.detail = detail && detail.id ? detail : null;
            this.state.error = this.state.detail
                ? ""
                : _t("That return is no longer there.");
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

    advance() {
        return this.run(() =>
            this.orm.call(MODEL, "mart369_returns_advance", [this.props.id])
        );
    }

    askRefuse() {
        this.dialog.add(Confirm, {
            title: _t("Refuse this return?"),
            body: _t(
                "The customer is told it was refused on their own tracking " +
                    "screen, and it stops here. Nothing is refunded."
            ),
            confirmLabel: _t("Refuse it"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(() =>
                    this.orm.call(MODEL, "mart369_returns_refuse", [this.props.id])
                ),
            cancel: () => {},
        });
    }

    /** The ladder, off the server's own `flow`. A refused return left the
     *  ladder, so the template says so rather than drawing a half-finished
     *  one. */
    get steps() {
        const d = this.state.detail;
        if (!d || !d.flow) {
            return [];
        }
        const at = d.flow.findIndex((s) => s.state === d.state);
        return d.flow.map((s, i) => ({
            key: s.state, label: s.label, done: i < at, now: i === at,
        }));
    }

    /** The console's own route, which works unchanged in here: same session,
     *  same group check, and the photo has to belong to this return. */
    photoUrl(photoId) {
        return `/369mart/admin/returns/${this.props.id}/photo/${photoId}`;
    }

    kindLabel(kind) { return kindLabel(kind); }
    stateLabel(row) { return stateLabel(row); }
    money(amount, currency) { return money(amount, currency); }
    when(ms) { return when(ms); }
    ago(ms) { return ago(ms); }
}

/* --------------------------------------------------------------- the queue */

export class ReturnDesk extends Component {
    static template = "mart369_order.ReturnDesk";
    static components = { Layout, Pick, Search, Icon, Tabs, Pill };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.TILES = TILES;
        this.TABS = TABS;
        this.TONES = TONES;

        this.state = useState({
            tab: "needs",
            kind: "",
            sort: "old",
            q: "",
            limit: PAGE,
            rows: [],
            total: 0,
            counts: null,
            sel: null, // the id of the return whose dialog is open
            loading: true,
            busy: false,
            error: "",
        });

        /* The box writes to state at once, so typing is never swallowed by
           the wait; only the reload is debounced, which is all the 300ms
           was ever for. The text is kept raw and trimmed when it is sent -
           trimming it here would eat the space between two words. */
        this.reload = useDebounced(() => this.load(), 300);
        this.onSearch = (q) => {
            this.state.q = q;
            this.state.limit = PAGE;
            this.reload();
        };

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
            // One call: the list already carries the tile counts, because the
            // console screen needed both in one go too.
            const page = await this.orm.call(MODEL, "mart369_returns_list", [], {
                tab: this.state.tab,
                kind: this.state.kind || null,
                q: this.state.q.trim() || null,
                sort: this.state.sort,
                limit: this.state.limit,
            });
            this.state.rows = page.returns || [];
            this.state.total = page.total || 0;
            this.state.counts = page.counts || null;
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    /** Opening one is a dialog, not a panel down the side. `sel` stays only to
     *  mark which row is open behind it. */
    select(id) {
        this.state.sel = id;
        this.dialog.add(
            ReturnDialog,
            { id, onChanged: () => this.load({ quiet: true }) },
            { onClose: () => (this.state.sel = null) }
        );
    }

    message(err) { return message(err); }

    // ------------------------------------------------------------- filtering

    pick(tab) {
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


    /** The tabs as the kit's strip takes them: [key, label, count] triples.
     *  `tabCount` returns null for a tab that counts nothing, and the strip
     *  draws no badge for null - which is how a tab stays quiet. */
    get tabItems() {
        return this.TABS.map((tab) => [tab.key, tab.label, this.tabCount(tab)]);
    }

    tabCount(tab) {
        return tab.badge ? this.state.counts?.[tab.badge] ?? null : null;
    }

    tileValue(tile) {
        return this.state.counts?.[tile.tab] ?? 0;
    }

    // -------------------------------------------------------------- writing

    /** Never optimistic. A refusal means the screen was stale, so it reloads
     *  either way rather than arguing with the model. */
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
        return this.run(() =>
            this.orm.call(MODEL, "mart369_returns_advance", [row.id])
        );
    }

    /** The kanban, for what this screen does not do: grouping, the form, and
        adding or removing photos. */
    moreViews() {
        this.action.doAction("mart369_order.action_mart369_returns");
    }

    // --------------------------------------------------------------- drawing

    get kindOptions() {
        return [
            ["", _t("Refund or replacement")],
            ["refund", _t("Refund")],
            ["replace", _t("Replacement")],
        ];
    }

    get sortOptions() {
        return [["old", _t("Longest wait first")], ["new", _t("Newest first")]];
    }

    kindLabel(kind) { return kindLabel(kind); }
    stateLabel(row) { return stateLabel(row); }
    money(amount, currency) { return money(amount, currency); }
    ago(ms) { return ago(ms); }
}

registry.category("actions").add("mart369_order.returns", ReturnDesk);
