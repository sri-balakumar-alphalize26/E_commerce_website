/**
 * The order desk - 369 Mart > Orders.
 *
 * The twin of the app's console at /admin/orders, and deliberately the same
 * screen: staff who work in Odoo should not get a worse answer to the same
 * question than staff who work in the console.
 *
 * The question is "what do I pack next", not "show me the orders" - which is
 * what the kanban board next door answers, and why both exist. So:
 *
 *  - it opens on *Needs me*, oldest first, because the order that has waited
 *    longest is the one to act on and it belongs at the top;
 *  - every row carries its own next-step button, already labelled, so the
 *    common action costs one click and never opens anything;
 *  - the tiles along the top are the filter, not a read-out.
 *
 * Nothing here knows the order of the steps. A quick order is packed next and
 * an express one is shipped next; `row.next` arrives from the server already
 * saying which and what the button should read. A second copy of that ladder
 * in the browser is a second thing to get wrong, and `_check_mart369_state`
 * would refuse the write anyway.
 *
 * Every write re-reads. Nothing is patched locally to look like it worked: the
 * next state, the lateness and the tile numbers are all the server's, and
 * guessing them is how a screen starts lying. When a write is refused it is
 * almost always because this screen was stale, so a failure reloads too.
 *
 * No save queue and no save chip, unlike the two builders. There is nothing to
 * type here - every action is a command - so there is nothing to debounce.
 * They also live in mart369_home, which orders does not depend on and should
 * not: the home page has no business being a prerequisite of this.
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
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";

/* The shop's own words. Same six as `STATE_CHOICES` on sale.order and the same
   tones the console uses, so the two screens colour a state alike. */
export const STATUS = {
    placed: { label: _t("Placed"), tone: "blue" },
    packed: { label: _t("Packed"), tone: "amber" },
    shipped: { label: _t("Shipped"), tone: "violet" },
    out: { label: _t("Out for delivery"), tone: "orange" },
    delivered: { label: _t("Delivered"), tone: "green" },
    cancelled: { label: _t("Cancelled"), tone: "red" },
};

/* Tile -> which tab it switches to. The numbers come from
   `mart369_admin_counts`, the same counts the kanban's KPI strip shows. */
export const TILES = [
    { tab: "placed", label: _t("To pack"), icon: "fa-inbox" },
    { tab: "packing", label: _t("Packed & shipped"), icon: "fa-archive" },
    { tab: "out", label: _t("Out"), icon: "fa-truck" },
    { tab: "late", label: _t("Late"), icon: "fa-clock-o", warn: true },
    { tab: "cash", label: _t("Cash to collect"), icon: "fa-money", amount: true },
];

export const TABS = [
    { key: "needs", label: _t("Needs me"), badge: "needs" },
    { key: "all", label: _t("All") },
    { key: "delivered", label: _t("Delivered") },
    // The board's `has_return` filter, so the desk answers the same questions
    // its own search view does.
    { key: "returns", label: _t("Returns"), badge: "returns" },
    { key: "cancelled", label: _t("Cancelled") },
];

const PAGE = 20;
const POLL_MS = 30000;

/* Ours, not the browser's.
 *
 * A native <select> draws its menu with the operating system: a grey Windows
 * list here, a rounded sheet on a Mac, a full-screen roller on a phone. Three
 * looks the rest of this screen does not have, and none of them can show a
 * tick against the option that is currently on.
 *
 * Built on Odoo's own Dropdown rather than hand-rolled, so it gets the
 * positioning, the outside click, Escape and arrow-key navigation that the
 * rest of the backend's menus have - and the console's twin of this is the
 * same control drawn the same way.
 *
 * `options` are [value, label] pairs, the same shape the console's Select
 * takes, so the two stay easy to compare.
 */
export class Pick extends Component {
    static template = "mart369_order.Pick";
    static components = { Dropdown, DropdownItem };
    static props = {
        value: { type: String },
        options: { type: Array },
        label: { type: String },
        onChange: { type: Function },
    };

    get current() {
        const hit = this.props.options.find(([v]) => v === this.props.value);
        return hit ? hit[1] : "";
    }

    choose(value) {
        if (value !== this.props.value) {
            this.props.onChange(value);
        }
    }
}

export class OrderDesk extends Component {
    static template = "mart369_order.OrderDesk";
    static components = { Layout, Pick };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.STATUS = STATUS;
        this.TILES = TILES;
        this.TABS = TABS;

        this.state = useState({
            tab: "needs",
            mode: "",
            when: "all",
            sort: "old",
            q: "",
            limit: PAGE,
            rows: [],
            total: 0,
            reasons: [],
            counts: null,
            cashDue: "",
            sel: null,        // the ref of the order the panel is showing
            detail: null,
            reason: "",       // what a cancellation would be recorded as
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

        /* A queue that goes stale while somebody stares at it is the failure
           this screen exists to avoid, so it refreshes itself. Same 30s as the
           console. */
        this.timer = setInterval(() => {
            if (!this.state.busy) {
                this.load({ quiet: true });
            }
        }, POLL_MS);
        onWillUnmount(() => clearInterval(this.timer));
    }

    // ------------------------------------------------------------- reading

    async load({ quiet = false } = {}) {
        if (!quiet) {
            this.state.loading = true;
        }
        try {
            const [page, counts] = await Promise.all([
                this.orm.call("sale.order", "mart369_admin_list", [], {
                    tab: this.state.tab,
                    mode: this.state.mode || null,
                    when: this.state.when === "all" ? null : this.state.when,
                    q: this.state.q || null,
                    sort: this.state.sort,
                    limit: this.state.limit,
                }),
                this.orm.call("sale.order", "mart369_admin_counts", []),
            ]);
            this.state.rows = page.orders;
            this.state.total = page.total;
            this.state.reasons = page.reasons || [];
            if (!this.state.reason) {
                this.state.reason = this.state.reasons[0] || "";
            }
            this.state.counts = counts.counts;
            this.state.cashDue = counts.cashDue;
            this.state.error = "";
            /* An order that has left the tab the panel was opened from is
               still worth showing - it was just moved on, most likely by the
               button that is being watched. Only drop it if it is gone. */
            if (this.state.sel) {
                await this.loadDetail(this.state.sel);
            }
        } catch (err) {
            this.state.error = this.message(err);
        } finally {
            this.state.loading = false;
        }
    }

    async loadDetail(ref) {
        const detail = await this.orm.call("sale.order", "mart369_admin_detail", [ref]);
        this.state.detail = detail && detail.ref ? detail : null;
        if (!this.state.detail) {
            this.state.sel = null;
        }
    }

    /**
     * Opening an order is a dialog, not the column beside the list.
     *
     * The panel had 380px for a customer, an address, a basket, a bill and a
     * timeline, and spent most of it wrapping the order number onto two lines.
     * The dialog is handed this component rather than a copy of the detail, so
     * there is still exactly one `state.detail` and every existing write,
     * helper and reload keeps working untouched.
     */
    async select(ref) {
        this.state.sel = ref;
        this.state.detail = null;
        this.dialog.add(
            OrderDialog,
            { desk: this },
            { onClose: () => { this.state.sel = null; this.state.detail = null; } }
        );
        try {
            await this.loadDetail(ref);
        } catch (err) {
            this.notification.add(this.message(err), { type: "danger" });
            this.state.sel = null;
        }
    }

    message(err) {
        return (
            err?.data?.message ||
            err?.message?.data?.message ||
            err?.message ||
            _t("We could not reach the shop.")
        );
    }

    // ------------------------------------------------------------- filters

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

    tabCount(tab) {
        if (!tab.badge) {
            return null;
        }
        return this.state.counts?.[tab.badge] ?? null;
    }

    tileValue(tile) {
        if (tile.amount) {
            return this.state.cashDue || "-";
        }
        return this.state.counts?.[tile.tab] ?? 0;
    }

    // ------------------------------------------------------------- writing

    /* Not optimistic, and a refusal reloads. `mart369_action_advance` raises
       when the order has already moved, which means what is on screen is out
       of date - so showing the message without refreshing would leave the
       operator looking at the same wrong row. */
    async run(fn) {
        if (this.state.busy) {
            return false;
        }
        this.state.busy = true;
        try {
            await fn();
            return true;
        } catch (err) {
            this.notification.add(this.message(err), { type: "danger" });
            return false;
        } finally {
            this.state.busy = false;
            await this.load({ quiet: true });
        }
    }

    advance(row) {
        return this.run(() =>
            this.orm.call("sale.order", "mart369_admin_advance", [row.ref])
        );
    }

    /* The reason is picked before the dialog opens, so the dialog can say what
       it is about to write. It lands on the customer's own tracking screen. */
    askCancel(order) {
        const reason = this.state.reason || this.state.reasons[0] || "";
        this.dialog.add(ConfirmationDialog, {
            title: _t("Cancel order %s?", order.ref),
            body: _t(
                'The money goes back the way it was paid, and the customer is ' +
                    'told "%s" on their own tracking screen.',
                reason
            ),
            confirmLabel: _t("Cancel the order"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(() =>
                    this.orm.call("sale.order", "mart369_admin_cancel", [order.ref, reason])
                ),
            cancel: () => {},
        });
    }

    setReason(ev) {
        this.state.reason = ev.target.value;
    }

    /* What is on screen, not what is in the shop - hence "these" on the
       button. An operator who mails a "full export" that turns out to be one
       page of it has been misled by the label, not by the data.

       Written here rather than handed to Odoo's own exporter because the rows
       are already in the browser: this is the list as the desk drew it, with
       the storefront and the status in the words the desk uses. The board next
       door still has the real export, with every field on the model. */
    exportCsv() {
        const head = [
            _t("Order"), _t("Placed"), _t("Storefront"), _t("Customer"),
            _t("Phone"), _t("Area"), _t("Items"), _t("Total"), _t("Currency"),
            _t("Payment"), _t("Status"), _t("Late"),
        ];
        const body = this.state.rows.map((o) => [
            o.ref,
            o.at ? new Date(o.at).toISOString() : "",
            this.modeLabel(o.mode),
            o.customer.name,
            o.customer.phone,
            o.customer.area,
            o.itemCount,
            o.total,
            o.currency?.code || "",
            o.payNote || o.method,
            STATUS[o.state]?.label || o.state,
            o.late ? _t("yes") : "",
        ]);
        const csv = [head, ...body]
            .map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(","))
            .join("\n");
        try {
            /* A BOM, because the obvious thing to do with this file is open it
               in Excel, and without one Excel reads UTF-8 as the system
               codepage and mangles every non-ASCII name and currency. */
            const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `369mart-orders-${new Date().toISOString().slice(0, 10)}.csv`;
            a.click();
            URL.revokeObjectURL(url);
            this.notification.add(
                _t("%s orders exported", this.state.rows.length),
                { type: "success" }
            );
        } catch (err) {
            this.notification.add(_t("That export did not work."), { type: "danger" });
        }
    }

    /* Grouping, the form and the saved search filters all live on the board.
       This screen does one job; that one does the rest. */
    moreViews() {
        this.action.doAction("mart369_order.action_mart369_orders");
    }

    // ------------------------------------------------------------ printing

    /* The order carries the currency it was charged in, because a later
       pricelist change must not rewrite the money on an old receipt. Same
       rule as lib/money.js in the app: format what the shop sent, never glue
       on a symbol of our own. */
    money(amount, currency) {
        const n = Number(amount) || 0;
        const decimals = currency ? currency.decimals : 2;
        const shown = n.toLocaleString(currency?.locale || undefined, {
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

    modeLabel(mode) {
        return mode === "quick" ? _t("Quick") : _t("Express");
    }

    /* The server sends epoch milliseconds so the two screens agree on the
       instant; the browser turns it into the reader's own clock. */
    clock(ms) {
        if (!ms) {
            return "";
        }
        return new Date(ms).toLocaleTimeString(undefined, {
            hour: "numeric",
            minute: "2-digit",
        });
    }

    when(ms) {
        if (!ms) {
            return "";
        }
        return new Date(ms).toLocaleString(undefined, {
            day: "numeric",
            month: "short",
            hour: "numeric",
            minute: "2-digit",
        });
    }

    ago(ms) {
        const mins = Math.max(0, Math.round((Date.now() - ms) / 60000));
        if (mins < 1) {
            return _t("just now");
        }
        if (mins < 60) {
            return _t("%s min ago", mins);
        }
        if (mins < 1440) {
            return _t("%s h ago", Math.floor(mins / 60));
        }
        return _t("%s d ago", Math.floor(mins / 1440));
    }

    /* Counts up rather than back: somebody looking at an overdue order is
       asking how late it is, not when it was placed. */
    overdue(ms) {
        const mins = Math.max(0, Math.round((Date.now() - ms) / 60000));
        if (mins < 60) {
            return _t("%s min late", mins);
        }
        if (mins < 1440) {
            return _t("%s h late", Math.floor(mins / 60));
        }
        return _t("%s d late", Math.floor(mins / 1440));
    }

    /* The panel draws the ladder this order is really on - `flow` is the
       server's, so a quick order shows Packed where an express one shows
       Shipped, instead of the screen working it out from `mode`. */
    get modeOptions() {
        return [["", _t("All types")], ["quick", _t("Quick")], ["all", _t("Express")]];
    }

    get whenOptions() {
        return [["all", _t("All time")], ["today", _t("Today")], ["7d", _t("Last 7 days")]];
    }

    get sortOptions() {
        return [
            ["old", _t("Longest wait first")],
            ["new", _t("Newest first")],
            ["value", _t("Highest value")],
        ];
    }

    get steps() {
        const o = this.state.detail;
        if (!o) {
            return [];
        }
        const stamped = {};
        for (const stamp of o.timeline || []) {
            stamped[stamp.state] = stamp;
        }
        const reached = o.flow.filter((k) => stamped[k]).length;
        const steps = o.flow.map((key, i) => ({
            key,
            label: STATUS[key].label,
            at: stamped[key] ? this.clock(stamped[key].at) : "",
            done: !!stamped[key],
            now: i === reached - 1 && o.state !== "delivered" && o.state !== "cancelled",
        }));
        if (stamped.cancelled) {
            steps.push({
                key: "cancelled",
                label: STATUS.cancelled.label,
                at: stamped.cancelled.note || this.clock(stamped.cancelled.at),
                done: true,
                cancelled: true,
            });
        }
        return steps;
    }

    get address() {
        const a = this.state.detail?.address;
        if (!a) {
            return "";
        }
        return [a.line, a.area, a.city].filter(Boolean).join(", ");
    }

    /* What the panel says about the delivery code. Never the code itself and
       never the hash it is checked against - a manager needs to know the
       customer has one, not to be able to open their own door with it. */
    get doorstep() {
        const otp = this.state.detail?.otp;
        if (!otp?.issuedAt) {
            return _t("No code has been issued for this order yet.");
        }
        if (otp.usedAt) {
            return _t("Used at %s.", this.clock(otp.usedAt));
        }
        return _t(
            "Issued %s, not used yet. The customer has it in their app.",
            this.clock(otp.issuedAt)
        );
    }
}

/**
 * One order, opened.
 *
 * Deliberately thin: it holds no state and no logic of its own, and reads the
 * desk's. `useState` over the desk's own reactive object is what subscribes
 * this component to it, so a write on the desk redraws in here without the two
 * ever holding separate copies of the same order.
 */
export class OrderDialog extends Component {
    static template = "mart369_order.OrderDialog";
    static components = { Dialog };
    static props = {
        desk: { type: Object },
        close: { type: Function },
    };

    setup() {
        this.desk = this.props.desk;
        this.state = useState(this.props.desk.state);
    }
}

registry.category("actions").add("mart369_order.desk", OrderDesk);
