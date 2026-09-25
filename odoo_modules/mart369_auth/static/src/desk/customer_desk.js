/**
 * Customers - the app console's Customers screen, inside Odoo.
 *
 * The twin of /admin/customers. It reads `res.users.mart369_admin_list` and
 * `mart369_admin_detail`, the same two calls the console makes, so the two
 * screens cannot disagree about who is dormant or what somebody has spent.
 *
 *  - **The tiles count the shop, never the filter.** Searching does not make
 *    the shop look smaller; the line above the rows counts the filter.
 *  - **Every filter is the server's** - tab, area, joined, wallet.
 *  - **Read-only here.** The full customer form, one button away, is where an
 *    account is changed.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Search } from "@mart369/ui/search";
import { Icon } from "@mart369/ui/icon";
import { Tabs } from "@mart369/ui/tabs";
import { Pick } from "@mart369/ui/pick";
import { Switch } from "@mart369/ui/switch";

const MODEL = "res.users";
const PAGE = 50;

const TILES = [
    { key: "all", tab: "all", label: _t("Customers"), icon: "users" },
    { key: "active", tab: "active", label: _t("Active"), icon: "check" },
    { key: "new", tab: "new", label: _t("New customers"), icon: "plus" },
    { key: "dormant", tab: "dormant", label: _t("Dormant"), icon: "clock", warn: true },
];

const TABS = [
    ["all", _t("All")],
    ["active", _t("Active")],
    ["new", _t("New")],
    ["dormant", _t("Dormant")],
];

const JOINED = [["", _t("Any time")], ["month", _t("This month")], ["3m", _t("Last 3 months")], ["year", _t("This year")]];
const WALLET = [["", _t("Any wallet")], ["1", _t("Has a balance")]];
/* The server's orders (SORTS in customer_admin.py); the first is the default.
   The console's sort menu offers the same five. */
const SORTS = [
    ["new", _t("Newest first")], ["old", _t("Oldest first")],
    ["name", _t("Name A → Z")], ["name_desc", _t("Name Z → A")], ["seen", _t("Recently active")],
];

const STATUS = {
    active: [_t("Active"), "green"],
    new: [_t("New"), "blue"],
    dormant: [_t("Dormant"), "grey"],
    archived: [_t("Archived"), "grey"],
};

const POLL_MS = 120000;

/* A tag's colour, from Odoo's own colour index on the tag (0-11). */
const TAG_TONES = ["grey", "red", "orange", "amber", "blue", "violet", "green", "blue", "red", "violet", "green", "orange"];

function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

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

function ago(ms) {
    if (!ms) {
        return _t("Never");
    }
    const mins = Math.round((Date.now() - ms) / 60000);
    if (mins < 1) {
        return _t("just now");
    }
    if (mins < 60) {
        return _t("%s min ago", mins);
    }
    const hours = Math.round(mins / 60);
    if (hours < 24) {
        return _t("%s h ago", hours);
    }
    return _t("%s d ago", Math.round(hours / 24));
}

function day(ms) {
    if (!ms) {
        return "";
    }
    return new Date(ms).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export class CustomerDesk extends Component {
    static template = "mart369_auth.CustomerDesk";
    static components = { Layout, Search, Icon, Tabs, Pick, Switch };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.TILES = TILES;
        this.JOINED = JOINED;
        this.WALLET = WALLET;
        this.SORTS = SORTS;

        this.state = useState({
            tab: "all",
            q: "",
            area: "",
            joined: "",
            wallet: "",
            sort: "new",
            tag: "",
            limit: PAGE,
            rows: [],
            total: 0,
            counts: {},
            areas: [],
            currency: null,
            loading: true,
            error: "",
            open: null,      // the row whose panel is open
            detail: null,    // its detail, once read
            allTags: [],     // every tag, for the filter and the picker
            tagging: false,  // the panel's "+ Add tag" picker is open
            tagText: "",
            note: "",        // the note being written
            editing: null,   // the id of the note being changed
            editText: "",
            giving: false,   // the goodwill form is open
            giveAmount: "",
            giveReason: "",
            busy: false,
        });

        this.reload = useDebounced(() => this.load(), 300);
        this.onSearch = (q) => {
            this.state.q = q;
            this.state.limit = PAGE;
            this.reload();
        };

        onWillStart(() => this.load());
        this.timer = setInterval(() => this.load({ quiet: true }), POLL_MS);
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
                q: this.state.q.trim() || null,
                area: this.state.area || null,
                joined: this.state.joined || null,
                wallet: this.state.wallet || null,
                sort: this.state.sort,
                tag: this.state.tag || null,
                limit: this.state.limit,
            });
            this.state.rows = page.rows || [];
            this.state.total = page.total || 0;
            this.state.counts = page.counts || {};
            this.state.areas = page.areas || [];
            this.state.currency = page.currency || null;
            this.state.allTags = page.tags || [];
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    // ------------------------------------------------------------ filtering

    set(key, value) {
        this.state[key] = value;
        this.state.limit = PAGE;
        this.load();
    }

    more() {
        this.state.limit += PAGE;
        this.load();
    }

    get tabItems() {
        return TABS.map(([key, label]) => [key, label, this.state.counts?.[key] ?? null]);
    }

    get areaOptions() {
        return [["", _t("All areas")], ...this.state.areas.map((a) => [a, a])];
    }

    get filtered() {
        return !!(this.state.q.trim() || this.state.area || this.state.joined || this.state.wallet || this.state.tag);
    }

    // ---------------------------------------------------------------- panel

    async openRow(row) {
        this.state.open = row;
        this.state.detail = null;
        this.state.tagging = false;
        this.state.tagText = "";
        this.state.note = "";
        try {
            this.state.detail = await this.orm.call(MODEL, "mart369_admin_detail", [row.id]);
        } catch (err) {
            this.state.detail = { error: message(err) };
        }
    }

    close() {
        this.state.open = null;
        this.state.detail = null;
    }

    // ------------------------------------------------------- tags and notes

    get tagOptions() {
        return [["", _t("All tags")], ...this.state.allTags.map((t) => [String(t.id), t.name])];
    }

    tone(tag) {
        return TAG_TONES[(tag.color || 0) % TAG_TONES.length];
    }

    /** What the picker offers: tags not on this customer that match the text,
     *  and "Create" when the text is a new name. */
    get tagChoices() {
        const on = new Set((this.state.detail?.tags || this.state.open?.tags || []).map((t) => t.id));
        const text = this.state.tagText.trim().toLowerCase();
        return this.state.allTags.filter((t) => !on.has(t.id) && t.name.toLowerCase().includes(text));
    }

    get tagIsNew() {
        const text = this.state.tagText.trim().toLowerCase();
        return !!text && !this.state.allTags.some((t) => t.name.toLowerCase() === text);
    }

    currentTags() {
        return this.state.detail?.tags || this.state.open?.tags || [];
    }

    /** Save the customer's tags, then refresh the panel and the list. */
    async saveTags(names) {
        if (this.state.busy || !this.state.open) {
            return;
        }
        this.state.busy = true;
        try {
            const tags = await this.orm.call(MODEL, "mart369_admin_set_tags", [this.state.open.id, names]);
            if (this.state.detail) {
                this.state.detail.tags = tags;
            }
            this.state.open.tags = tags;
            this.state.tagging = false;
            this.state.tagText = "";
            await this.load({ quiet: true });
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    addTag(name) {
        const clean = (name || "").trim();
        if (clean) {
            this.saveTags([...this.currentTags().map((t) => t.name), clean]);
        }
    }

    removeTag(tag) {
        this.saveTags(this.currentTags().filter((t) => t.id !== tag.id).map((t) => t.name));
    }

    onTagKey(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            const first = this.tagChoices[0];
            this.addTag(this.tagIsNew || !first ? this.state.tagText : first.name);
        } else if (ev.key === "Escape") {
            this.state.tagging = false;
        }
    }

    async addNote() {
        const text = this.state.note.trim();
        if (!text || this.state.busy || !this.state.open) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.detail.notes = await this.orm.call(MODEL, "mart369_admin_add_note", [this.state.open.id, text]);
            this.state.note = "";
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    /** + Add address: the same dialog the customer form's "+ Add address"
     *  opens (mart369_address), then the panel reads the book again. */
    async addAddress() {
        const open = this.state.open;
        if (!open || this.state.busy) {
            return;
        }
        try {
            const action = await this.orm.call(MODEL, "action_mart369_add_address", [[open.id]]);
            await this.action.doAction(action, {
                onClose: async () => {
                    if (this.state.open?.id !== open.id) {
                        return;
                    }
                    this.state.detail = await this.orm.call(MODEL, "mart369_admin_detail", [open.id]);
                    await this.load({ quiet: true });
                },
            });
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
        }
    }

    // ------------------------------------------------------------- risk
    // mart369_order adds risk to the detail, and the methods below; without
    // it the panel simply shows none of this.

    riskLine(r) {
        if (!r) {
            return "";
        }
        return [
            r.cancelledByCustomer && _t("%s cancelled by them", r.cancelledByCustomer),
            r.refused && _t("%s refused at the door", r.refused),
            r.returned && _t("%s returned", r.returned),
            r.returnRequests && _t("%s return requests", r.returnRequests),
        ].filter(Boolean).join(" · ");
    }

    async setCod(off) {
        if (this.state.busy || !this.state.open) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.detail.risk = await this.orm.call(MODEL, "mart369_admin_set_cod", [this.state.open.id, off]);
            this.notification.add(off ? _t("Cash on delivery is off for this customer.") : _t("Cash on delivery is back on."), { type: "success" });
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    get canGive() {
        return Number(this.state.giveAmount) > 0 && !!this.state.giveReason.trim() && !this.state.busy;
    }

    setGiveAmount(value) {
        this.state.giveAmount = (value || "").replace(/[^0-9.]/g, "");
    }

    async giveGoodwill() {
        const amount = Number(this.state.giveAmount);
        const reason = this.state.giveReason.trim();
        if (!(amount > 0) || !reason || this.state.busy || !this.state.open) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call(MODEL, "mart369_admin_goodwill", [this.state.open.id, amount, reason]);
            this.notification.add(_t("Goodwill credit added to the wallet."), { type: "success" });
            this.state.giving = false;
            this.state.giveAmount = "";
            this.state.giveReason = "";
            const open = this.state.open;
            await this.load({ quiet: true });
            this.state.open = this.state.rows.find((r) => r.id === open.id) || open;
            this.state.detail = await this.orm.call(MODEL, "mart369_admin_detail", [open.id]);
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    startEdit(note) {
        this.state.editing = note.id;
        this.state.editText = note.text;
    }

    async saveEdit(note) {
        const text = this.state.editText.trim();
        if (!text || this.state.busy || !this.state.open) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.detail.notes = await this.orm.call(MODEL, "mart369_admin_edit_note", [this.state.open.id, note.id, text]);
            this.state.editing = null;
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    async deleteNote(note) {
        if (this.state.busy || !this.state.open) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.detail.notes = await this.orm.call(MODEL, "mart369_admin_delete_note", [this.state.open.id, note.id]);
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    /** tel: and wa.me links; empty when there is no number to use. */
    get callHref() {
        const phone = this.state.open?.phone;
        return phone ? "tel:" + phone.replace(/[^\d+]/g, "") : "";
    }

    get waHref() {
        const digits = this.state.detail?.waPhone;
        return digits ? "https://wa.me/" + digits : "";
    }

    /** The full Odoo form - the place an account is changed. */
    openForm() {
        const id = this.state.open?.id;
        if (!id) {
            return;
        }
        // The full profile page - the console's twin - when mart369_order is
        // installed to draw it (orders, tickets, returns, wallet history).
        if (registry.category("actions").contains("mart369_order.customer_profile")) {
            this.action.doAction({
                type: "ir.actions.client",
                tag: "mart369_order.customer_profile",
                name: this.state.open.name,
                params: { userId: id },
            });
            return;
        }
        // Otherwise the customers action, so it opens on the 369 Mart customer
        // form (with its timeline and buttons), not Odoo's generic user form.
        this.action.doAction("mart369_auth.action_mart369_customers", {
            viewType: "form",
            props: { resId: id },
        });
    }

    // --------------------------------------------------------------- drawing

    money(amount) {
        return money(amount, this.state.currency);
    }

    ago(ms) {
        return ago(ms);
    }

    day(ms) {
        return day(ms);
    }

    /** The badges, as [label, tone] pairs. A New customer's first badge says
     *  how long it has left (Settings > Customers); the second says whether
     *  they have ordered yet. Every Active / Dormant badge says when they last
     *  placed an order - placed, so cash on delivery counts before it is
     *  confirmed. */
    badges(row) {
        const ordered = row?.lastPlaced ? _t("ordered %s", ago(row.lastPlaced)) : "";
        if (row?.status === "new") {
            const left = row.newDaysLeft;
            return [
                [!left ? _t("New") : left === 1 ? _t("New · last day") : _t("New · %s days left", left), "blue"],
                ordered ? [_t("Active · %s", ordered), "green"] : [_t("Not ordered yet"), "amber"],
            ];
        }
        if (row?.status === "active") {
            return [[_t("Active · %s", ordered || _t("no orders yet")), "green"]];
        }
        if (row?.status === "dormant") {
            return [[_t("Dormant · %s", ordered || _t("no orders")), "grey"]];
        }
        return [STATUS[row?.status] || STATUS.active];
    }

    badgeLine(row) {
        return this.badges(row).map(([label]) => label).join(" · ");
    }

    /** Whether the rows carry an address count - mart369_address adds it. */
    hasBooks() {
        return this.state.rows.length > 0 && this.state.rows[0].addressCount !== undefined;
    }

    /** An address as the lines a parcel label reads, top to bottom. */
    addressLines(a) {
        const near = a.landmark && !/^(near|opp|opposite|behind|beside|next to)\b/i.test(a.landmark)
            ? "near " + a.landmark : a.landmark;
        const place = a.town
            ? `${a.town}${a.state ? ", " + a.state : ""}${a.pin ? " " + a.pin : ""}`
            : [a.city, a.state].filter(Boolean).join(", ");
        return [a.line, [a.area, near].filter(Boolean).join(", "), place].filter(Boolean);
    }
}

registry.category("actions").add("mart369_auth.customers", CustomerDesk);
