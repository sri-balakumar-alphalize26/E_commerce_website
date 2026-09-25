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
import { Confirm } from "@mart369/ui/confirm";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Search } from "@mart369/ui/search";
import { Pick } from "@mart369/ui/pick";
import { Icon } from "@mart369/ui/icon";
import { Tabs } from "@mart369/ui/tabs";
import { Pill } from "@mart369/ui/pill";

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
    { tab: "placed", label: _t("To pack"), icon: "box" },
    { tab: "packing", label: _t("Ready to send"), icon: "archive" },
    { tab: "out", label: _t("Out for delivery"), icon: "truck" },
    { tab: "late", label: _t("Late"), icon: "clock", warn: true },
    { tab: "cash", label: _t("Cash to collect"), icon: "money", amount: true },
];

/* "Needs me", grouped by what you do next - the state says which group. */
const NEXT_GROUPS = [
    { key: "pack", label: _t("To pack"), states: ["placed"] },
    { key: "send", label: _t("Ready to send"), states: ["packed", "shipped"] },
    { key: "out", label: _t("Out for delivery"), states: ["out"] },
];
const PAID_BY = { upi: "UPI", card: _t("card"), netbanking: _t("net banking"), wallet: _t("369 Wallet") };

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

/* The doorstep code, asked for.
 *
 * `delivered` is the one step the ladder will not take on its own: the server
 * refuses an advance into it and asks for the code the customer reads off their
 * phone at the door. So this is not politeness, it is the only way through.
 *
 * It stays open on a refusal and clears the box. The server answers the same
 * sentence for a wrong code and for one already spent - deliberately, so nobody
 * can tell by guessing whether a code is live - which means the operator's only
 * move is to ask again, and closing the dialog would lose their place.
 */
export class DeliverDialog extends Component {
    static template = "mart369_order.DeliverDialog";
    static components = { Dialog };
    static props = {
        order: { type: Object },
        onDelivered: { type: Function },
        close: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ code: "", busy: false, error: "" });
    }

    onInput(ev) {
        // Digits only, and never longer than the code the server issues.
        this.state.code = (ev.target.value || "").replace(/\D/g, "").slice(0, 6);
        this.state.error = "";
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && this.canSend) {
            this.send();
        }
    }

    get canSend() {
        return this.state.code.length === 6 && !this.state.busy;
    }

    async send() {
        if (!this.canSend) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("sale.order", "mart369_admin_deliver", [
                this.props.order.ref,
                this.state.code,
            ]);
            this.props.onDelivered();
            this.props.close();
        } catch (err) {
            this.state.error =
                err?.data?.message || err?.message?.data?.message || err?.message ||
                _t("That delivery code is not right.");
            this.state.code = "";
        } finally {
            this.state.busy = false;
        }
    }
}

export class OrderDesk extends Component {
    static template = "mart369_order.OrderDesk";
    static components = { Layout, Pick, Search, Icon, Tabs, Pill };
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
            pay: "",
            sort: "due",
            q: "",
            limit: PAGE,
            rows: [],
            total: 0,
            reasons: [],
            counts: null,
            cashDue: "",
            sel: null,        // the ref of the order the panel is showing
            picked: [],       // the refs ticked for a bulk action
            detail: null,
            addrPick: null, // the address being chosen while "Change" is open
            reason: "",       // what a cancellation would be recorded as
            failReason: "",   // what went wrong at the door
            sound: soundWanted(), // chime for a new order
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
                    pay: this.state.pay || null,
                    q: this.state.q.trim() || null,
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
            this.announce(counts.latest || []);
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
        // Each order starts from the first reason, not whatever was picked
        // on the last one opened.
        this.state.reason = this.state.reasons[0] || "";
        this.state.failReason = "";
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
        this.state.picked = [];
        this.load();
    }

    // ------------------------------------------------------------ ticking

    isPicked(row) {
        return this.state.picked.includes(row.ref);
    }

    togglePick(row) {
        const picked = this.state.picked;
        this.state.picked = picked.includes(row.ref)
            ? picked.filter((r) => r !== row.ref)
            : [...picked, row.ref];
    }

    get allPicked() {
        return this.state.rows.length > 0 && this.state.rows.every((r) => this.isPicked(r));
    }

    toggleAll() {
        this.state.picked = this.allPicked ? [] : this.state.rows.map((r) => r.ref);
    }

    get pickedRows() {
        return this.state.rows.filter((r) => this.isPicked(r));
    }

    get canMoveAll() {
        return this.pickedRows.some((r) => r.next && !this.needsCode(r));
    }

    /** Move every ticked order one step on, one at a time, the way pressing
     *  each row's button would. Orders at the door are skipped - they need the
     *  customer's code - and so is anything the shop refuses; the count says
     *  how many went. */
    async moveAll() {
        const chosen = this.pickedRows.filter((r) => r.next && !this.needsCode(r));
        if (!chosen.length || this.state.busy) {
            return;
        }
        this.state.busy = true;
        let moved = 0;
        const refused = [];
        try {
            for (const row of chosen) {
                try {
                    await this.orm.call("sale.order", "mart369_admin_advance", [row.ref]);
                    moved += 1;
                } catch {
                    refused.push(row.ref);
                }
            }
        } finally {
            this.state.busy = false;
            this.state.picked = [];
            await this.load({ quiet: true });
        }
        this.notification.add(
            refused.length
                ? _t("Moved %s of %s. Not moved: #%s", moved, chosen.length, refused.join(", #"))
                : _t("Moved %s order(s) on", moved),
            { type: refused.length ? "warning" : "success" });
    }

    /** Packing slips or the picklist for the ticked orders, as a PDF in a new
     *  tab (controllers/admin_api.py, print_orders). */
    printPicked(kind) {
        const refs = encodeURIComponent(this.state.picked.join(","));
        window.open(`/369mart/admin/orders/print?kind=${kind}&refs=${refs}`, "_blank");
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

    /** The last step is not ours to take. Everything up to `out` is one call;
     *  `delivered` needs the code from the door, so it opens the dialog. */
    needsCode(row) {
        return row.next?.state === "delivered";
    }

    advance(row) {
        if (this.needsCode(row)) {
            this.dialog.add(DeliverDialog, {
                order: row,
                onDelivered: () => {
                    this.notification.add(
                        _t("#%s delivered", row.ref), { type: "success" });
                    this.load({ quiet: true });
                },
            });
            return;
        }
        return this.run(() =>
            this.orm.call("sale.order", "mart369_admin_advance", [row.ref])
        );
    }

    /* The reason is picked before the dialog opens, so the dialog can say what
       it is about to write. It lands on the customer's own tracking screen. */
    askCancel(order) {
        const reason = this.state.reason || this.state.reasons[0] || "";
        this.dialog.add(Confirm, {
            title: _t("Cancel order %s?", order.ref),
            // Says how much, like the console does: cash orders owe nothing,
            // paid ones get their money back.
            body: order.method === "cod"
                ? _t('It was cash on delivery, so there is nothing to refund. The customer is told "%s" on their own tracking screen.', reason)
                : _t("%s goes to the customer's 369 Wallet straight away, and they are told \"%s\" on their own tracking screen.",
                    this.money(order.paid || order.bill?.total || order.total, order.currency), reason),
            confirmLabel: _t("Cancel the order"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(() =>
                    this.orm.call("sale.order", "mart369_admin_cancel", [order.ref, reason])
                ),
            cancel: () => {},
        });
    }

    /** Take one item out because the store ran out of it. Paid orders get its
     *  price back in the 369 Wallet at once; cash orders owe less at the door. */
    askRemove(order, line) {
        const value = this.money(line.price * line.qty, order.currency);
        const cash = order.method === "cod";
        this.dialog.add(Confirm, {
            title: _t("Take %s x %s out of #%s?", line.qty, line.name, order.ref),
            body: cash
                ? _t("It is marked out of stock and the cash to collect drops by %s.", value)
                : _t("It is marked out of stock and %s goes to the customer's 369 Wallet straight away.", value),
            confirmLabel: _t("Take it out"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(() =>
                    this.orm.call("sale.order", "mart369_admin_remove_line",
                        [order.ref, line.lineId, _t("Out of stock")])
                ),
            cancel: () => {},
        });
    }

    /** Offer the customer another product for an item that ran out. */
    askReplace(order, line) {
        this.dialog.add(ReplaceDialog, {
            order,
            line,
            money: (v) => this.money(v, order.currency),
            onSent: () => {
                this.notification.add(
                    _t("Replacement sent - #%s waits for the customer", order.ref), { type: "success" });
                this.load({ quiet: true });
            },
        });
    }

    /** The offer for this item, if one was made. */
    offerFor(order, line) {
        return (order.substitutes || []).find((s) => s.lineId === line.lineId && s.state === "offered");
    }

    withdraw(order, offer) {
        return this.run(() =>
            this.orm.call("sale.order", "mart369_admin_withdraw_substitute", [order.ref, offer.id]));
    }

    /** "8 min left" on an offer the customer has not answered yet. */
    leftOf(ms) {
        const mins = Math.max(0, Math.round((ms - Date.now()) / 60000));
        return mins < 60 ? _t("%s min left", mins) : _t("%s h left", Math.round(mins / 60));
    }

    setReason(reason) {
        this.state.reason = reason;
    }

    /** The shop's own cancellation reasons, which arrive as plain sentences.
     *  Doubled up into the [value, label] pairs the dropdown takes - the
     *  sentence is both what is shown and what is sent. */
    get reasonOptions() {
        return this.state.reasons.map((reason) => [reason, reason]);
    }

    // ---------------------------------------------------------- new orders

    /** A pop-up, and a chime, for every order placed since the screen last
     *  looked. The first look only remembers what is there. */
    announce(latest) {
        if (!this.seen) {
            this.seen = new Set(latest.map((o) => o.ref));
            return;
        }
        const fresh = latest.filter((o) => !this.seen.has(o.ref));
        if (!fresh.length) {
            return;
        }
        for (const o of fresh.reverse()) {
            this.seen.add(o.ref);
            this.notification.add(
                _t("#%s · %s", o.ref, this.money(o.total, o.currency)),
                { title: _t("New order"), type: "info" });
        }
        if (this.state.sound) {
            chime();
        }
    }

    toggleSound() {
        this.state.sound = !this.state.sound;
        try {
            window.localStorage.setItem(SOUND_KEY, this.state.sound ? "on" : "off");
        } catch {
            // Remembered for this visit only.
        }
        if (this.state.sound) {
            chime(); // the click that lets the browser play it later
        }
    }

    // ------------------------------------------------ rider, failed delivery

    riderValue(order) {
        return order.riderId ? String(order.riderId) : "";
    }

    setFailReason(reason) {
        this.state.failReason = reason;
    }

    riderOptions(order) {
        return [["", _t("No rider yet")], ...(order.riders || []).map((r) => [String(r.id), r.name])];
    }

    setRider(order, value) {
        return this.run(() =>
            this.orm.call("sale.order", "mart369_admin_set_rider", [order.ref, Number(value) || false])
        );
    }

    failOptions(order) {
        return (order.failReasons || []).map((r) => [r, r]);
    }

    /** It could not be delivered: out again with a new code, or back to the
     *  store with the money in the customer's 369 Wallet. */
    failed(order, then) {
        const reason = this.state.failReason || (order.failReasons || [])[0] || "";
        const go = () =>
            this.run(async () => {
                const r = await this.orm.call("sale.order", "mart369_admin_failed", [order.ref, reason, then]);
                this.notification.add(
                    then === "retry"
                        ? _t("#%s goes out again with a new door code", order.ref)
                        : r.refund
                          ? _t("#%s returned · %s to the 369 Wallet", order.ref, this.money(r.refund, order.currency))
                          : _t("#%s returned to the store", order.ref),
                    { type: "success" });
            });
        if (then === "retry") {
            return go();
        }
        this.dialog.add(Confirm, {
            title: _t("Return #%s to the store?", order.ref),
            body: order.method === "cod"
                ? _t('The order is closed as "%s". It was cash on delivery, so there is nothing to refund.', reason)
                : _t('The order is closed as "%s" and %s goes to the customer\'s 369 Wallet straight away.',
                     reason, this.money(order.paid || order.total, order.currency)),
            confirmLabel: _t("Return to store"),
            confirmClass: "btn-danger",
            confirm: go,
            cancel: () => {},
        });
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

    /* Counts down to the promise while it can still be kept: "due in 14 min".
       Once it is broken `overdue` takes over and counts up. */
    dueIn(ms) {
        const mins = Math.max(0, Math.round((ms - Date.now()) / 60000));
        if (mins < 1) {
            return _t("due now");
        }
        if (mins < 60) {
            return _t("due in %s min", mins);
        }
        if (mins < 1440) {
            const h = Math.floor(mins / 60);
            const m = mins % 60;
            return m ? _t("due in %s h %s min", h, m) : _t("due in %s h", h);
        }
        return _t("due in %s d", Math.floor(mins / 1440));
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

    get payOptions() {
        return [["", _t("Any payment")], ["cod", _t("Cash on delivery")], ["prepaid", _t("Prepaid")]];
    }

    get whenOptions() {
        return [["all", _t("All time")], ["today", _t("Today")], ["7d", _t("Last 7 days")]];
    }

    get sortOptions() {
        return [
            ["due", _t("Most urgent first")],
            ["old", _t("Longest wait first")],
            ["new", _t("Newest first")],
            ["value", _t("Highest value")],
        ];
    }

    /** The rows as the list draws them. "Needs me" is split by the next
     *  thing to do; every other tab is one plain list. */
    get groups() {
        const rows = this.state.rows;
        if (this.state.tab !== "needs") {
            return [{ key: "all", label: "", rows }];
        }
        const out = NEXT_GROUPS.map((g) => ({ ...g, rows: rows.filter((r) => g.states.includes(r.state)) }))
            .filter((g) => g.rows.length);
        const rest = rows.filter((r) => !NEXT_GROUPS.some((g) => g.states.includes(r.state)));
        if (rest.length) {
            out.push({ key: "other", label: _t("Other"), rows: rest });
        }
        return out;
    }

    /** Payment in plain words: is the money in, or still to collect? */
    payText(row) {
        if (row.method === "cod") {
            if (row.state === "delivered") {
                return _t("Cash collected");
            }
            return row.state === "cancelled" ? _t("Cash on delivery") : _t("Cash on delivery - collect at the door");
        }
        const how = PAID_BY[row.method] || row.payNote || row.method;
        return how ? _t("Paid by %s", how) : _t("Paid");
    }

    tagTone(tag) {
        const tones = ["grey", "red", "orange", "amber", "blue", "violet", "green", "blue", "red", "violet", "green", "orange"];
        return tones[(tag.color || 0) % tones.length];
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
        return this.addressLines(this.state.detail?.address).join(", ");
    }

    /** An address as the lines a parcel label reads, top to bottom. */
    addressLines(a) {
        if (!a) {
            return [];
        }
        const near = a.landmark && !/^(near|opp|opposite|behind|beside|next to)\b/i.test(a.landmark)
            ? "near " + a.landmark : a.landmark;
        const place = a.town
            ? `${a.town}${a.state ? ", " + a.state : ""}${a.pin ? " " + a.pin : ""}`
            : [a.city, a.state].filter(Boolean).join(", ");
        return [a.line, [a.area, near].filter(Boolean).join(", "), place].filter(Boolean);
    }

    // ------------------------------------------------- where the order goes

    startAddressChange() {
        this.state.addrPick = this.state.detail?.address?.id ?? null;
        if (this.state.addrPick === null && this.state.detail?.addresses?.length) {
            this.state.addrPick = this.state.detail.addresses[0].id;
        }
    }

    pickAddress(id) {
        this.state.addrPick = id;
    }

    cancelAddressChange() {
        this.state.addrPick = null;
    }

    /* The order decides whether it may still move (placed or packed), so a
       stale screen is refused there and reloads like any other write. */
    async saveAddressChange() {
        const ref = this.state.detail?.ref;
        const id = this.state.addrPick;
        if (!ref || id === null) {
            return;
        }
        const done = await this.run(() =>
            this.orm.call("sale.order", "mart369_admin_set_address", [ref, id])
        );
        this.state.addrPick = null;
        if (done) {
            this.notification.add(_t("#%s will be delivered to the new address", ref), { type: "success" });
        }
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
            return _t("Used %s.", this.when(otp.usedAt));
        }
        return _t(
            "Sent %s, not used yet. The customer has it in their app.",
            this.when(otp.issuedAt)
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
/* A new order's chime: two short notes made here, so there is no sound file
   to ship. Browsers only play sound after somebody has clicked on the page,
   which is what the "Sound on" switch is for - switching it on is the click. */
const SOUND_KEY = "mart369.orders.sound";
let audio = null;

export function chime() {
    try {
        audio = audio || new (window.AudioContext || window.webkitAudioContext)();
        if (audio.state === "suspended") {
            audio.resume();
        }
        const start = audio.currentTime;
        [880, 1318.5].forEach((freq, i) => {
            const osc = audio.createOscillator();
            const gain = audio.createGain();
            osc.type = "sine";
            osc.frequency.value = freq;
            const at = start + i * 0.16;
            gain.gain.setValueAtTime(0.0001, at);
            gain.gain.exponentialRampToValueAtTime(0.25, at + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.35);
            osc.connect(gain).connect(audio.destination);
            osc.start(at);
            osc.stop(at + 0.4);
        });
    } catch {
        // No sound on this browser - the pop-up still says it.
    }
}

function soundWanted() {
    try {
        return window.localStorage.getItem(SOUND_KEY) !== "off";
    } catch {
        return true;
    }
}

/** Pick a replacement for an item that ran out and send it to the customer,
 *  who accepts or refuses it on their order page (order_substitute.py). */
export class ReplaceDialog extends Component {
    static template = "mart369_order.ReplaceDialog";
    static components = { Dialog, Icon };
    static props = {
        close: { type: Function },
        order: { type: Object },
        line: { type: Object },
        money: { type: Function },
        onSent: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        // Up to three: the customer picks one of them.
        this.state = useState({ q: "", products: [], picked: [], loading: true, busy: false, error: "" });
        this.search = useDebounced(() => this.load(), 300);
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.products = await this.orm.call("sale.order", "mart369_admin_substitutes",
                [this.props.order.ref, this.props.line.lineId, this.state.q.trim() || null]);
            this.state.error = "";
        } catch (err) {
            this.state.error = err.data?.message || err.message || String(err);
        } finally {
            this.state.loading = false;
        }
    }

    isPicked(product) {
        return this.state.picked.includes(product.id);
    }

    pick(product) {
        const picked = this.state.picked;
        if (picked.includes(product.id)) {
            this.state.picked = picked.filter((id) => id !== product.id);
        } else if (picked.length < 3) {
            this.state.picked = [...picked, product.id];
        }
    }

    type(ev) {
        this.state.q = ev.target.value;
        this.search();
    }

    async send() {
        if (!this.state.picked.length || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("sale.order", "mart369_admin_offer_substitute",
                [this.props.order.ref, this.props.line.lineId, this.state.picked]);  // one to three ids
            this.props.onSent();
            this.props.close();
        } catch (err) {
            this.state.error = err.data?.message || err.message || String(err);
        } finally {
            this.state.busy = false;
        }
    }
}

export class OrderDialog extends Component {
    static template = "mart369_order.OrderDialog";
    static components = { Dialog, Pick, Icon, Pill };
    static props = {
        desk: { type: Object },
        close: { type: Function },
    };

    setup() {
        this.desk = this.props.desk;
        this.state = useState(this.props.desk.state);
        // The dialog's own bits: the note being written or changed.
        this.local = useState({ note: "", editing: null, editText: "", busy: false });
    }

    // ------------------------------------------------ plain-words helpers

    /** Where the order stands, as one sentence. */
    statusLine(o) {
        const promised = o.dueAt ? this.desk.clock(o.dueAt) : "";
        if (o.state === "cancelled") {
            return _t("Cancelled.");
        }
        if (o.state === "delivered") {
            return _t("Delivered.");
        }
        if (o.late) {
            return promised
                ? _t("%s - it was promised by %s.", this.desk.overdue(o.dueAt), promised)
                : _t("%s.", this.desk.overdue(o.dueAt));
        }
        return promised ? _t("On time - %s (promised by %s).", this.desk.dueIn(o.dueAt), promised) : _t("On time.");
    }

    whenLine(o) {
        const promised = o.dueAt ? _t("promised by %s", this.desk.when(o.dueAt)) : "";
        return [o.slot, promised].filter(Boolean).join(" · ") || "-";
    }

    payLine(o) {
        const total = this.desk.money(o.bill.total, o.currency);
        if (o.method === "cod") {
            return o.state === "delivered" ? _t("Cash on delivery - collected at the door.")
                : o.state === "cancelled" ? _t("Cash on delivery - nothing to collect.")
                : _t("Cash on delivery - collect %s at the door.", total);
        }
        const how = o.payNote || o.method || _t("Paid online");
        return o.txn ? _t("%s - paid %s (ref %s).", how, total, o.txn) : _t("%s - paid %s.", how, total);
    }

    orderOrdinal(o) {
        const n = o.customer.orderCount || 0;
        return n <= 1 ? _t("first order") : _t("%s orders so far", n);
    }

    riskLine(o) {
        const r = o.customer.risk;
        if (!r) {
            return "";
        }
        return [
            r.cancelledByCustomer && _t("%s cancelled by them", r.cancelledByCustomer),
            r.refused && _t("%s refused at the door", r.refused),
            r.returned && _t("%s returned", r.returned),
            r.codOff && _t("cash on delivery is off for them"),
        ].filter(Boolean).join(" · ");
    }

    tone(tag) {
        const tones = ["grey", "red", "orange", "amber", "blue", "violet", "green", "blue", "red", "violet", "green", "orange"];
        return tones[(tag.color || 0) % tones.length];
    }

    callHref(o) {
        const p = o.customer.phone;
        return p ? "tel:" + p.replace(/[^\d+]/g, "") : "";
    }

    waHref(o) {
        return o.customer.waPhone ? "https://wa.me/" + o.customer.waPhone : "";
    }

    // --------------------------------------------------------- navigating

    openCustomer(o) {
        if (!o.customer.userId) {
            return;
        }
        this.props.close();
        this.desk.action.doAction({
            type: "ir.actions.client", tag: "mart369_order.customer_profile",
            name: o.customer.name, params: { userId: o.customer.userId },
        });
    }

    openTicket(t) {
        this.props.close();
        this.desk.action.doAction({
            type: "ir.actions.act_window", res_model: "mart369.ticket", res_id: t.id,
            views: [[false, "form"]], target: "current",
        });
    }

    // -------------------------------------------------------------- notes

    async noteCall(method, args) {
        if (this.local.busy) {
            return false;
        }
        this.local.busy = true;
        try {
            this.state.detail.notes = await this.desk.orm.call("sale.order", method, args);
            return true;
        } catch (err) {
            this.desk.notification.add(err?.data?.message || err?.message || _t("That did not work."), { type: "danger" });
            return false;
        } finally {
            this.local.busy = false;
        }
    }

    async addNote(o) {
        if (await this.noteCall("mart369_admin_add_order_note", [o.ref, this.local.note.trim()])) {
            this.local.note = "";
        }
    }

    async saveNote(o, n) {
        if (await this.noteCall("mart369_admin_edit_order_note", [o.ref, n.id, this.local.editText.trim()])) {
            this.local.editing = null;
        }
    }

    deleteNote(o, n) {
        return this.noteCall("mart369_admin_delete_order_note", [o.ref, n.id]);
    }

    /** The invoice's own URL. A method rather than an expression in the
     *  template: an OWL template is evaluated without globals, so
     *  `encodeURIComponent` in there is a ReferenceError at render time
     *  rather than a mistake anybody sees while writing it. */
    /** This one order's packing slip - the same report the bulk print uses. */
    slipHref(ref) {
        return `/369mart/admin/orders/print?kind=slips&refs=${encodeURIComponent(ref)}`;
    }

    invoiceHref(ref) {
        return `/369mart/admin/orders/${encodeURIComponent(ref)}/invoice`;
    }
}

registry.category("actions").add("mart369_order.desk", OrderDesk);
