/**
 * 369 Mart product page builder - "all settings".
 *
 * The real product page drawn as a phone, with a switch on everything it can
 * show. Two tabs: the shop-wide defaults, and one product at a time. Saving
 * is the same shared queue the home builder uses, so the two behave alike.
 *
 * This used to be the front door of 369 Mart > Product Page. It now sits
 * behind the desk editor (editor.js) at /odoo/mart-product-advanced, the way
 * the home page's phone builder sits behind its editor: one screen for the
 * page as shoppers see it, one for every last field. Both read the same
 * payload through ProductPageReader and draw the same page through
 * mart369_product.PageBody, so they cannot disagree.
 */
import { onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "@mart369_home/builder/builder";
import { useSaveQueue } from "@mart369_home/builder/save_queue";
import { M, STATES, ProductPageReader } from "./page_reader";

export class ProductBuilder extends ProductPageReader {
    static template = "mart369_product.ProductBuilder";
    static components = { Layout, Icon };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
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

    async load() {
        this.state.data = await this.orm.call(M.field, "builder_load", [
            this.state.productId,
        ]);
        if (this.d.product) {
            this.state.productId = this.d.product.id;
        }
    }

    // ------------------------------------------------------------- reading

    get openSectionRecord() {
        return this.d.sections.find((s) => s.id === this.state.openSection);
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
        const ids = this.rowsOf(section).map((r) => r.id);
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

    /** Back to the page as shoppers see it. */
    backToEditor() {
        this.action.doAction("mart369_product.action_mart369_product_editor", {
            additionalContext: { mart369_product_id: this.state.productId },
        });
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
