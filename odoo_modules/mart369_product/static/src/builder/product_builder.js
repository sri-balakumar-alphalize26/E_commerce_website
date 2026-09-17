/**
 * 369 Mart product page builder.
 *
 * The real product page drawn as a phone, with a switch on everything it can
 * show. Two tabs: the shop-wide defaults, and one product at a time. Saving
 * is the same shared queue the home builder uses, so the two behave alike.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "@mart369_home/builder/builder";
import { useSaveQueue } from "@mart369_home/builder/save_queue";

const M = {
    section: "mart369.product.section",
    field: "mart369.product.field",
    override: "mart369.product.override",
    categoryValue: "mart369.product.category.value",
    product: "product.template",
};

const STATES = [
    ["follow", _t("Follow the default")],
    ["show", _t("Always show")],
    ["hide", _t("Always hide")],
];

export class ProductBuilder extends Component {
    static template = "mart369_product.ProductBuilder";
    static components = { Layout, Icon };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.STATES = STATES;

        this.state = useState({
            tab: "global",          // "global" | "product"
            data: null,
            productId: this.props.action?.context?.mart369_product_id || null,
            openSection: null,
            status: "saved",
            search: { q: "", results: [], busy: false },
        });

        this.save = useSaveQueue({
            orm: this.orm,
            notification: this.notification,
            reload: () => this.load(),
            onStatus: (s) => (this.state.status = s),
        });
        this.searchProducts = useDebounced(this._searchProducts, 300);

        onWillStart(() => this.load());
    }

    get d() {
        return this.state.data;
    }

    async load() {
        this.state.data = await this.orm.call(M.field, "builder_load", [
            this.state.productId,
        ]);
        if (this.d.product) {
            this.state.productId = this.d.product.id;
        }
    }

    // ------------------------------------------------------------- reading

    /** The bands that draw as an accordion inside the buy card. */
    get accordionSections() {
        const inAccordion = ["features", "info", "specs", "description", "returns"];
        return this.d.sections.filter((s) => inAccordion.includes(s.key));
    }

    /** The bands that sit below the fold. */
    get tailSections() {
        const tail = ["delivery", "bundle", "similar"];
        return this.d.sections.filter((s) => tail.includes(s.key));
    }

    get openSectionRecord() {
        return this.d.sections.find((s) => s.id === this.state.openSection);
    }

    sectionByKey(key) {
        return this.d.sections.find((s) => s.key === key);
    }

    row(sectionKey, fieldKey) {
        const section = this.sectionByKey(sectionKey);
        return section && section.rows.find((r) => r.key === fieldKey);
    }

    rowVisible(sectionKey, fieldKey) {
        const row = this.row(sectionKey, fieldKey);
        return !!row && row.visible;
    }

    rowValue(sectionKey, fieldKey) {
        const row = this.row(sectionKey, fieldKey);
        return row ? row.value : "";
    }

    visibleRows(section) {
        return section.rows.filter((r) => r.visible);
    }

    differing(section) {
        if (this.state.tab !== "product") {
            return 0;
        }
        return section.rows.filter((r) => r.state !== "follow").length;
    }

    get offPct() {
        const card = this.d.card;
        if (!card || !card.mrp || !card.price) {
            return 0;
        }
        return Math.round(((card.mrp - card.price) / card.mrp) * 100);
    }

    get ratingText() {
        return this.rowValue("reviews", "rating") || "No rating yet";
    }

    get ratingCountText() {
        const count = this.rowValue("reviews", "rating_count");
        return count ? `(${count} ratings)` : "";
    }

    // ------------------------------------------------------------- writing

    toggleSection(section) {
        return this.save.run(() =>
            this.orm.write(M.section, [section.id], { show: !section.show })
        );
    }

    toggleGlobal(row) {
        return this.save.run(() =>
            this.orm.write(M.field, [row.id], { show: !row.show })
        );
    }

    setState(row, state) {
        return this.save.run(() =>
            this.orm.call(M.field, "set_product_state", [
                row.id,
                this.state.productId,
                state,
            ])
        );
    }

    editDefault(row, ev) {
        this.save.edit(M.field, row, "default_value", ev.target.value);
    }

    resetSection(section) {
        const ids = section.rows.map((r) => r.id);
        return this.save.run(
            () =>
                this.orm.call(M.field, "reset_product_state", [
                    ids,
                    this.state.productId,
                ]),
            { successMessage: _t("Back to the shop defaults") }
        );
    }

    openSection(section) {
        this.state.openSection =
            this.state.openSection === section.id ? null : section.id;
    }

    async switchTab(tab) {
        await this.save.flushNow();
        this.state.tab = tab;
        await this.load();
    }

    // ----------------------------------------------------- picking a product

    onSearchInput(ev) {
        this.state.search.q = ev.target.value;
        this.state.search.busy = true;
        this.searchProducts();
    }

    async _searchProducts() {
        const q = this.state.search.q.trim();
        if (!q) {
            this.state.search.results = [];
            this.state.search.busy = false;
            return;
        }
        this.state.search.results = await this.orm.searchRead(
            M.product,
            [
                ["is_published", "=", true],
                ["name", "ilike", q],
            ],
            ["id", "display_name"],
            { limit: 15 }
        );
        this.state.search.busy = false;
    }

    async pickProduct(id) {
        this.state.productId = id;
        this.state.search = { q: "", results: [], busy: false };
        this.state.tab = "product";
        await this.load();
    }
}

registry.category("actions").add("mart369_product.builder", ProductBuilder);
