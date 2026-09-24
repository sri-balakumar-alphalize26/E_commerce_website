/**
 * Products - 369 Mart > Products.
 *
 * The shop's products, and the page each one will actually show.
 *
 * The builder next door answers "what should a product page contain" and is
 * organised that way: a preview, a panel, and a scope switch between the whole
 * shop and one product. It is the right screen for deciding. It is the wrong
 * screen for checking, because to see a single product you have to switch
 * scope and hunt for it in a picker.
 *
 * This is the other direction. Browse the shop, tap a product, and read what
 * its page will show - section by section, field by field, with the value each
 * one resolved to.
 *
 * It does not decide visibility: the server's `mart369_product_page` runs the
 * same `_visible_for` / `_value_for` ladders the shopper's own route runs, so
 * this screen cannot disagree with the page it is describing.
 *
 * It does write, but only a product's own columns - name, price, category,
 * the wording, the photographs. The page configuration, which is the four
 * layers and the per-product exceptions, stays the builder's alone, one
 * button away under Edit page. That split is the point: two screens writing
 * one setting is how they start to differ, so each setting has exactly one
 * writer. A box the page has been told not to print is not offered here
 * either - `mart369_desk_form` reads the same `mart_page_hidden` the Odoo
 * form reads.
 */
import { Component, onWillStart, useExternalListener, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "@mart369/ui/icon";
import { Search } from "@mart369/ui/search";
import { Pill } from "@mart369/ui/pill";
import { Empty } from "@mart369/ui/empty";
import { Tabs } from "@mart369/ui/tabs";
import { Pick } from "@mart369/ui/pick";
import { ProductEditor, money } from "./product_editor";

const FIELD = "mart369.product.field";
const PRODUCT = "product.template";

/* The Stock desk's four tiles, drawn only when mart369_catalog is installed
   and sends them - it is the module that knows about stock. */
const TILES = [
    { key: "count", label: _t("Products"), icon: "layers", flat: true },
    { key: "value", label: _t("Stock value"), icon: "wallet", flat: true, money: true },
    { key: "low", tab: "low", label: _t("Low stock"), icon: "warn", warn: true },
    { key: "out", tab: "out", label: _t("Out of stock"), icon: "warn", bad: true },
];

const TABS = [
    ["all", _t("All")],
    ["low", _t("Low")],
    ["out", _t("Out of stock")],
    ["off", _t("Hidden")],
];

const MODES = [["", _t("Both storefronts")], ["quick", _t("Quick")], ["all", _t("Express")]];
const SORTS = [["name", _t("Name A-Z")], ["low", _t("Lowest stock")], ["sold", _t("Best selling")], ["price", _t("Highest price")]];

/* Which layer a value came from, in the shop's words. `odoo` means the value
   is the product's own field rather than anything anybody typed here. */
const SOURCE = {
    product: { label: _t("this product"), tone: "blue" },
    category: { label: _t("its category"), tone: "violet" },
    odoo: { label: _t("the product record"), tone: "grey" },
    default: { label: _t("the shop"), tone: "grey" },
};

function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

export class ProductDesk extends Component {
    static template = "mart369_product.ProductDesk";
    static components = { Layout, Icon, Search, Pill, Empty, Tabs, Pick, ProductEditor };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.action = useService("action");

        this.SOURCE = SOURCE;
        // Bumped each time the editor opens, so it starts from a fresh copy.
        this.formKey = 0;
        this.editor = null;
        // What the sticky bar says about the product being edited; the
        // editor keeps it up to date as boxes change.
        this.formStatus = useState({ name: "", dirty: false });

        // Ctrl/Cmd+S saves, like every other editor people already know.
        useExternalListener(window, "keydown", (ev) => {
            if (this.state.form && (ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "s") {
                ev.preventDefault();
                this.save();
            }
        });
        this.TILES = TILES;
        this.MODES = MODES;
        this.SORTS = SORTS;

        this.state = useState({
            // the list
            tree: [],
            products: [],
            allCount: 0,
            uncategorised: 0,
            total: 0,
            categ: null,
            q: "",
            tab: "all",
            mode: "",
            sort: "name",
            // From mart369_catalog when it is installed; null leaves the
            // tiles, stock tabs and filters off rather than drawing zeros.
            tiles: null,
            counts: {},
            stock: {},
            // {id: row} from mart369_catalog: unit, category, sold, stock, live.
            rows: {},
            currency: null,
            // Kanban or list, the two Odoo offers on its own product list.
            // Remembered per browser, because it is a reading preference and
            // being put back on cards every visit is its own small annoyance.
            view: browser.localStorage?.getItem("mart369.products.view") || "kanban",
            // the product being read, or null for the list
            open: null,
            page: null,
            // Its numbers strip, from mart369_catalog when installed.
            stats: null,
            loading: true,
            error: "",
            // The editor, or null when nothing is being edited. `id` is null
            // for a product being created, which is also what tells `save`
            // whether to create or to write.
            form: null,
            saving: false,
        });


        // Arriving from a product's own form means that product was asked
        // for, so open straight onto it rather than making somebody find it
        // again in a list they did not ask to see.
        this.asked = this.props.action?.context?.mart369_product_id || null;

        onWillStart(async () => {
            await this.load();
            if (this.asked) {
                const row = this.state.products.find((p) => p.id === this.asked);
                // Named from the list when it is there, so the header reads
                // properly; the page itself is fetched by id either way, so an
                // unpublished or filtered-out product still opens.
                await this.open(row || { id: this.asked, name: "" });
            }
        });
    }

    // ------------------------------------------------------------- the list

    /** The same call the builder's picker makes, so the two cannot disagree
     *  about what is in the shop. */
    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(PRODUCT, "mart369_page_picker", [], {
                categ_id: this.state.categ,
                q: this.state.q.trim() || "",
                tab: this.state.tab,
                mode: this.state.mode || null,
                sort: this.state.sort,
            });
            this.state.tree = data.categories || [];
            this.state.products = data.products || [];
            this.state.allCount = data.all_count || 0;
            this.state.uncategorised = data.uncategorised || 0;
            this.state.total = data.total || 0;
            this.state.tiles = data.tiles || null;
            this.state.counts = data.counts || {};
            this.state.stock = data.stock || {};
            this.state.rows = data.rows || {};
            this.state.currency = data.currency || null;
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    onSearch(q) {
        this.state.q = q;
        this.load();
    }

    /** The rail, one level deep. The picker returns a flat list with
     *  `parent_id`, and its counts are already rolled up through the tree, so
     *  the top-level rows alone account for everything without double
     *  counting a product filed under two of them. */
    get topCategories() {
        return this.state.tree.filter((c) => !c.parent_id);
    }

    /** The category chips: every category, named the way the web admin
     *  names them - "Peripherals / Keyboards". */
    get categChips() {
        const byId = Object.fromEntries(this.state.tree.map((c) => [c.id, c]));
        const path = (c) => {
            const names = [];
            for (let at = c; at; at = at.parent_id ? byId[at.parent_id] : null) {
                names.unshift(at.name);
            }
            return names.join(" / ");
        };
        return this.state.tree.map((c) => ({ id: c.id, label: path(c) }));
    }

    /** Anything narrowing the list, so the line under the chips says so and
     *  offers to clear it. */
    // ---- one product's line or card, as the web admin draws it

    rowOf(p) {
        return this.state.rows[p.id] || {};
    }

    imageOf(p) {
        return this.rowOf(p).image || p.image || "";
    }

    unitCode(p) {
        return [this.rowOf(p).unit, p.code].filter(Boolean).join(" · ");
    }

    unitCat(p) {
        return [this.rowOf(p).unit, this.rowOf(p).cat].filter(Boolean).join(" · ") || " ";
    }

    hasQty(p) {
        const q = this.rowOf(p).qty;
        return q !== null && q !== undefined;
    }

    qtyText(p) {
        return this.hasQty(p) ? this.rowOf(p).qty : "-";
    }

    /** The web admin's colours: red when out, orange when low, else green. */
    stockTone(p) {
        return { out: "red", low: "orange" }[this.rowOf(p).state] || "green";
    }

    stockPill(p) {
        return this.rowOf(p).state === "out" ? _t("Out") : _t("%s left", this.rowOf(p).qty);
    }

    rowTone(p) {
        const st = this.rowOf(p).state;
        return st === "out" ? "ad-row-bad" : st === "low" ? "ad-row-warn" : "";
    }

    cardTone(p) {
        const st = this.rowOf(p).state;
        return st === "out" || st === "low" ? "pdk-" + st : "";
    }

    /** A row opens the product - unless a button in it was pressed. */
    onRowClick(ev, p) {
        if (!ev.target.closest("button")) {
            this.open(p);
        }
    }

    /** A tile or chip pressed again goes back to everything. */
    toggleTab(tab) {
        this.setFilter("tab", this.state.tab === tab ? "all" : tab);
    }

    toggleCateg(id) {
        this.pickCateg(this.state.categ === id ? null : id);
    }

    get filtered() {
        return !!(this.state.q.trim() || this.state.categ !== null || this.state.tab !== "all");
    }

    get matchLine() {
        const shown = this.state.products.length;
        const total = this.state.total;
        if (!this.filtered) {
            return _t("%s products. The tiles count the whole shop.", total);
        }
        const chip = this.categChips.find((c) => c.id === this.state.categ);
        const where = this.state.categ === 0 ? _t("Uncategorised") : chip ? chip.label : "";
        return where
            ? _t("Showing %s of %s that match in %s. The tiles count the whole shop.", shown, total, where)
            : _t("Showing %s of %s that match. The tiles count the whole shop.", shown, total);
    }

    clearFilters() {
        Object.assign(this.state, { q: "", categ: null, tab: "all" });
        this.load();
    }

    pickCateg(id) {
        this.state.categ = id;
        this.load();
    }

    /** Tabs, tiles, storefront and sort all narrow the same list. */
    setFilter(key, value) {
        if (value !== undefined && value !== null) {
            this.state[key] = value;
            this.load();
        }
    }

    /** All counts what the All tab lists - published products - rather than
     *  the Products tile, which counts everything for sale. */
    get tabItems() {
        const counts = { ...this.state.counts, all: this.state.allCount };
        return TABS.map(([key, label]) => [key, label, counts[key] ?? null]);
    }

    tileValue(tile) {
        const v = this.state.tiles?.[tile.key] ?? 0;
        return tile.money ? this.money(v, this.state.currency) : v;
    }

    /** [qty or null, 'ok' | 'low' | 'out'] for a row, or null with no stock
     *  module to ask. */
    stockOf(product) {
        return this.state.stock[product.id] || null;
    }

    setView(view) {
        this.state.view = view;
        try {
            browser.localStorage?.setItem("mart369.products.view", view);
        } catch {
            // Private windows and blocked site data both throw here. The
            // switch still works for this visit; only remembering it fails.
        }
    }

    // ----------------------------------------------------------- the product

    async open(product) {
        this.state.open = product;
        this.state.page = null;
        this.state.stats = null;
        this.state.loading = true;
        try {
            [this.state.page, this.state.stats] = await Promise.all([
                this.orm.call(FIELD, "mart369_product_page", [product.id]),
                this.orm.call(PRODUCT, "mart369_product_stats", [product.id]),
            ]);
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    back() {
        this.state.open = null;
        this.state.page = null;
        this.state.stats = null;
    }

    /** The numbers strip: Odoo's figures, each opening Odoo's own screen for
     *  it. Empty (no strip) when mart369_catalog does not send them. */
    get statTiles() {
        const s = this.state.stats;
        if (!s || !Object.keys(s).length) {
            return [];
        }
        const cur = s.currency;
        const num = (v) => (v === null || v === undefined ? "-" : Number(v).toLocaleString());
        return [
            { key: "onHand", label: _t("On hand"), value: num(s.onHand), open: s.open?.onHand },
            { key: "forecast", label: _t("Forecast"), value: num(s.forecast), open: s.open?.forecast },
            { key: "sold", label: _t("Sold, %s days", s.soldDays), value: num(s.sold), open: s.open?.sold },
            { key: "price", label: _t("Price"), value: money(s.price, cur) },
            { key: "cost", label: _t("Cost"), value: s.cost ? money(s.cost, cur) : "-" },
            { key: "margin", label: _t("Margin"), value: s.margin === null ? "-" : `${s.margin} %`,
              bad: s.margin !== null && s.margin < 0 },
        ];
    }

    async openStat(tile) {
        if (!tile.open) {
            return;
        }
        const action = await this.orm.call(PRODUCT, tile.open, [[this.state.open.id]]);
        if (action) {
            await this.action.doAction(action);
        }
    }

    /** The product itself - name, price, stock, category - which is Odoo's
     *  own form and not something to rebuild here. Two different edits, so
     *  two buttons: this one changes the product, the other changes what its
     *  page shows. */
    editProduct() {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.template",
            res_id: this.state.open.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    /** Changing any of this is the builder's job, opened on this product.
     *  `mart369_product_id` is what tells it which one. */
    edit() {
        return this.action.doAction(
            "mart369_product.action_mart369_product_editor",
            { additionalContext: { mart369_product_id: this.state.open.id } }
        );
    }

    // ------------------------------------------------------------- editing

    /** A blank product. Nothing is resolved against a category yet, so the
     *  server offers every box; see `mart369_desk_form`. */
    newProduct() {
        return this.openForm(null);
    }

    /** The product's own details, in place. The Odoo form is still one click
     *  away for everything this screen deliberately leaves out - taxes,
     *  costing, routes, reordering. */
    editDetails() {
        return this.openForm(this.state.open.id);
    }

    async openForm(productId) {
        this.state.loading = true;
        this.state.error = "";
        try {
            const data = await this.orm.call(
                PRODUCT, "mart369_desk_form", [], { product_id: productId });
            // The editor keeps its own working copy of this; `key` gives it
            // a fresh one each time a product is opened.
            this.state.form = { id: data.id, data, key: ++this.formKey };
            this.formStatus.name = data.values.name || "";
            this.formStatus.dirty = false;
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    closeForm() {
        this.state.form = null;
        this.editor = null;
    }

    /** Cancel. Asks first when something was typed, so a stray click does
     *  not throw away a product's worth of wording. */
    cancelForm() {
        if (!this.formStatus.dirty) {
            return this.closeForm();
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Discard your changes?"),
            body: _t("What you typed on this product has not been saved."),
            confirmLabel: _t("Discard"),
            cancelLabel: _t("Keep editing"),
            confirm: () => this.closeForm(),
            cancel: () => {},
        });
    }

    async save() {
        if (!this.editor || this.state.saving) {
            return;
        }
        const form = this.editor.state.form;
        if (!(form.values.name || "").trim()) {
            // Said at the box, as on the web admin, and the box brought into view.
            this.editor.state.nameBad = true;
            const box = this.editor.root.querySelector('[data-box="name"]');
            box?.focus();
            box?.scrollIntoView({ block: "center", behavior: "smooth" });
            return;
        }
        this.state.saving = true;
        this.state.error = "";
        try {
            const id = await this.orm.call(PRODUCT, "mart369_desk_save", [], {
                values: form.values,
                product_id: form.id,
                photos: {
                    add: form.add,
                    remove: form.remove,
                    promote: form.promoted ? form.promoted.id : null,
                    demote: form.demote,
                },
            });
            this.closeForm();
            // The list's counts and cards are now stale either way - a new
            // product is not in it, and an edited one may have changed
            // category or name.
            await this.load();
            const row = this.state.products.find((p) => p.id === id);
            await this.open(row || { id, name: form.values.name });
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.saving = false;
        }
    }

    // ------------------------------------------------------------- drawing

    /** "2 of 3 shown", or that the whole band is off. A section switched off
     *  is drawn as switched off rather than dropped - missing and hidden look
     *  the same otherwise, and only one of them was a decision. */
    sectionNote(section) {
        if (!section.show) {
            return _t("Switched off");
        }
        return _t("%s of %s shown", section.shown, section.total);
    }

    sourceLabel(source) {
        return SOURCE[source] ? SOURCE[source].label : source;
    }

    /** Nothing typed anywhere. Said rather than left blank, so an empty row
     *  reads as "no wording yet" instead of looking like a broken read. */
    valueOf(row) {
        if (row.kind === "bool") {
            return row.value === "1" ? _t("Yes") : row.value === "0" ? _t("No") : _t("Not set");
        }
        // Price and MRP arrive as the bare number; drawn as money, the way
        // the tiles and the list draw it.
        if ((row.key === "price" || row.key === "mrp") && row.value && !isNaN(Number(row.value))) {
            return Number(row.value) ? this.money(row.value) : _t("Nothing set");
        }
        return row.value || _t("Nothing set");
    }

    /** The same shape of money as the Stock desk: the shop's decimals and
     *  symbol when the catalog module sends them, two plain decimals when not. */
    money(amount, currency = this.state.currency) {
        return money(amount, currency);
    }

    get visibleRows() {
        return (this.state.page?.sections || []).reduce(
            (n, s) => n + (s.show ? s.shown : 0), 0);
    }
}

registry.category("actions").add("mart369_product.products", ProductDesk);
