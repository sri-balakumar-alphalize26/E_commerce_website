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

const MODEL = "res.users";
const PAGE = 50;

const TILES = [
    { key: "all", tab: "all", label: _t("Customers"), icon: "users" },
    { key: "active", tab: "active", label: _t("Active"), icon: "check" },
    { key: "new", tab: "new", label: _t("New this week"), icon: "plus" },
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

const STATUS = {
    active: [_t("Active"), "green"],
    new: [_t("New"), "blue"],
    dormant: [_t("Dormant"), "grey"],
    archived: [_t("Archived"), "grey"],
};

const POLL_MS = 120000;

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
    static components = { Layout, Search, Icon, Tabs, Pick };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.TILES = TILES;
        this.JOINED = JOINED;
        this.WALLET = WALLET;

        this.state = useState({
            tab: "all",
            q: "",
            area: "",
            joined: "",
            wallet: "",
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
                limit: this.state.limit,
            });
            this.state.rows = page.rows || [];
            this.state.total = page.total || 0;
            this.state.counts = page.counts || {};
            this.state.areas = page.areas || [];
            this.state.currency = page.currency || null;
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
        return !!(this.state.q.trim() || this.state.area || this.state.joined || this.state.wallet);
    }

    // ---------------------------------------------------------------- panel

    async openRow(row) {
        this.state.open = row;
        this.state.detail = null;
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

    /** The full Odoo form - the place an account is changed. */
    openForm() {
        const id = this.state.open?.id;
        if (!id) {
            return;
        }
        // Through the customers action, so it opens on the 369 Mart customer
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

    status(row) {
        return STATUS[row?.status] || STATUS.active;
    }
}

registry.category("actions").add("mart369_auth.customers", CustomerDesk);
