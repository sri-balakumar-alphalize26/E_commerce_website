/**
 * Stock - the app console's Products screen, inside Odoo.
 *
 * The twin of /admin/products. Everything it reads is `mart369_admin_list` on
 * product.template, the one call the console makes, so the two screens cannot
 * disagree about what "low stock" means or which storefront a product is on.
 *
 * Rules carried from the console:
 *
 *  - **The tiles count the shop, never the filtered rows.** Products, stock
 *    value, low and out stay put while somebody searches; the line above the
 *    rows is what counts the filter.
 *  - **Every filter is the server's.** Storefront, category, the stock tabs and
 *    the sort all go to the model - "lowest stock first" means nothing if it
 *    only sorts the rows already on screen.
 *  - **Read-only.** A stock count typed over here would disagree with
 *    Inventory the moment anything sold; a product opens on its own form,
 *    where price, stock and publishing are really changed.
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

const MODEL = "product.template";
const PAGE = 50;

/* The same four figures, in the same order, as the console's strip. Products
   and stock value are figures; low and out set the tab. */
const TILES = [
    { key: "count", label: _t("Products"), icon: "layers", flat: true },
    { key: "value", label: _t("Stock value"), icon: "wallet", flat: true, money: true },
    { key: "low", tab: "low", label: _t("Low stock"), icon: "warn", warn: true },
    { key: "out", tab: "out", label: _t("Out of stock"), icon: "warn", bad: true },
];

const TABS = [
    { key: "all", label: _t("All") },
    { key: "low", label: _t("Low") },
    { key: "out", label: _t("Out of stock") },
    { key: "off", label: _t("Hidden") },
];

const MODES = [["", _t("Both storefronts")], ["quick", _t("Quick")], ["all", _t("Express")]];
const SORTS = [["low", _t("Lowest stock")], ["sold", _t("Best selling")], ["price", _t("Highest price")], ["name", _t("Name A-Z")]];

const POLL_MS = 120000;

function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

/** The same shape of money as lib/money.js and the other desks. */
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

export class StockDesk extends Component {
    static template = "mart369_catalog.StockDesk";
    static components = { Layout, Search, Icon, Tabs, Pick };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.TILES = TILES;
        this.MODES = MODES;
        this.SORTS = SORTS;

        this.state = useState({
            tab: "all",
            q: "",
            categ: "",
            mode: "",
            sort: "low",
            limit: PAGE,
            rows: [],
            total: 0,
            tiles: {},
            counts: {},
            categories: [],
            currency: null,
            loading: true,
            error: "",
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
                categ: this.state.categ ? Number(this.state.categ) : null,
                mode: this.state.mode || null,
                q: this.state.q.trim() || null,
                sort: this.state.sort,
                limit: this.state.limit,
            });
            this.state.rows = page.rows || [];
            this.state.total = page.total || 0;
            this.state.tiles = page.tiles || {};
            this.state.counts = page.counts || {};
            this.state.categories = page.categories || [];
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

    pick(tab) {
        if (tab) {
            this.set("tab", tab);
        }
    }

    more() {
        this.state.limit += PAGE;
        this.load();
    }

    get tabItems() {
        return TABS.map((t) => [t.key, t.label, this.state.counts?.[t.key] ?? null]);
    }

    get categOptions() {
        return [["", _t("All categories")], ...this.state.categories.map((c) => [String(c.id), c.name])];
    }

    /** True when anything narrows the list, so the count line says so. */
    get filtered() {
        return !!(this.state.q.trim() || this.state.categ || this.state.mode || this.state.tab !== "all");
    }

    tileValue(tile) {
        const v = this.state.tiles?.[tile.key] ?? 0;
        return tile.money ? money(v, this.state.currency) : v;
    }

    money(amount) {
        return money(amount, this.state.currency);
    }

    // --------------------------------------------------------------- moving

    /** The product's own form - where price, stock and publishing change. */
    open(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: MODEL,
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("mart369_catalog.stock", StockDesk);
