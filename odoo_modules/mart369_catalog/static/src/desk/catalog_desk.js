/**
 * The app's categories, as the console draws them.
 *
 * The twin of /admin/catalog, and the sibling of the searches desk beside it.
 * It answers "what does the app look like from the outside" - which groups a
 * shopper sees, which storefront each belongs to, and which of them are
 * standing empty - which the kanban next door cannot without opening each one.
 *
 * Everything it reads is `mart369_admin_list` on the model, the same one call
 * the console makes. Nothing here is a second implementation of anything.
 *
 * Two rules carried from the console:
 *
 *  - **The tiles count everything, never the filtered rows.**
 *  - **The name and the address are not editable here.** The name is Odoo's
 *    own field, leaned on by the catalogue and every report; the address is a
 *    URL a customer may have saved. Both are one click away in the form, where
 *    the change is made deliberately rather than in passing.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const MODEL = "product.public.category";

const TILES = [
    { key: "live", tab: "live", label: _t("In the app"), icon: "fa-th-large" },
    { key: "hidden", tab: "hidden", label: _t("Hidden"), icon: "fa-eye-slash" },
    { key: "empty", tab: "empty", label: _t("Standing empty"), icon: "fa-inbox", warn: true },
    { key: "products", label: _t("Products a shopper can reach"), icon: "fa-cube", flat: true },
];

const TABS = [
    { key: "all", label: _t("All"), badge: "all" },
    { key: "live", label: _t("In the app"), badge: "live" },
    { key: "hidden", label: _t("Hidden"), badge: "hidden" },
    { key: "empty", label: _t("Standing empty"), badge: "empty" },
];

const POLL_MS = 60000;

function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

/**
 * How the app draws one category.
 *
 * A dialog rather than editing in the row, because the three things that
 * matter here - the blurb and the two colours - only make sense seen
 * together, and a colour picked beside the words it sits behind is picked
 * once rather than three times.
 */
export class CategoryDialog extends Component {
    static template = "mart369_catalog.CategoryDialog";
    static components = { Dialog };
    static props = {
        close: { type: Function },
        row: { type: Object },
        onSave: { type: Function },
    };

    setup() {
        const row = this.props.row;
        this.state = useState({
            draft: {
                mart_blurb: row.blurb || "",
                mart_tone: row.tone || "#f4f6f8",
                mart_accent: row.accent || "#0b4a6e",
                mart_mode: row.ownMode || "quick",
            },
            busy: false,
            error: "",
        });
    }

    edit(key, ev) {
        this.state.draft[key] = ev.target.value;
        this.state.error = "";
    }

    get preview() {
        return {
            background: this.state.draft.mart_tone || "#f4f6f8",
            color: this.state.draft.mart_accent || "#0b4a6e",
        };
    }

    get previewStyle() {
        const p = this.preview;
        return `background: ${p.background}; color: ${p.color};`;
    }

    /* Its own copy rather than reaching into the desk: a dialog that reads its
       parent's methods is a dialog that breaks when the parent moves. */
    modeLabel(mode) {
        return mode === "all" ? _t("Express") : _t("Quick");
    }

    async save() {
        if (this.state.busy) {
            return;
        }
        const values = { ...this.state.draft };
        // A sub-category follows its top-level parent, so sending a storefront
        // for one would be refused by the model - correctly. Do not send it.
        if (!this.props.row.topLevel) {
            delete values.mart_mode;
        }
        this.state.busy = true;
        try {
            await this.props.onSave(values);
            this.props.close();
        } catch (err) {
            // On the dialog rather than as a toast behind it, so the value
            // that was refused is still on screen beside the reason.
            this.state.error = message(err);
        } finally {
            this.state.busy = false;
        }
    }
}

export class CatalogDesk extends Component {
    static template = "mart369_catalog.CatalogDesk";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.TILES = TILES;
        this.TABS = TABS;

        this.state = useState({
            tab: "all",
            mode: "",
            q: "",
            rows: [],
            counts: null,
            tiles: {},
            loading: true,
            busy: false,
            error: "",
        });

        this.search = useDebounced((ev) => {
            this.state.q = ev.target.value.trim();
            this.load();
        }, 300);

        onWillStart(() => this.load());

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
                mode: this.state.mode || null,
                q: this.state.q || null,
            });
            this.state.rows = page.rows || [];
            this.state.counts = page.counts || null;
            this.state.tiles = page.tiles || {};
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    // ------------------------------------------------------------ filtering

    pick(tab) {
        if (!tab) {
            return; // the products tile, which filters nothing
        }
        this.state.tab = tab;
        this.load();
    }

    setMode(mode) {
        this.state.mode = mode;
        this.load();
    }

    /* Three chips rather than the shared `Pick` dropdown: that lives in
       mart369_order, and this module does not depend on it - pulling a whole
       module in for one select would be the wrong trade. Three options fit on
       a line anyway, and a chip shows which is on without being opened. */
    get modeOptions() {
        return [
            ["", _t("Both storefronts")],
            ["quick", _t("Quick")],
            ["all", _t("Express")],
        ];
    }

    tabCount(tab) {
        return tab.badge ? this.state.counts?.[tab.badge] ?? null : null;
    }

    tileValue(tile) {
        return this.state.tiles?.[tile.key] ?? 0;
    }

    // --------------------------------------------------------------- writing

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

    write(row, values) {
        return this.run(() =>
            this.orm.call(MODEL, "mart369_admin_write", [[row.id], values])
        );
    }

    /** Shown or hidden is the one change worth making from the row: it is the
     *  only one whose effect is obvious without seeing the page. */
    toggleShown(row) {
        return this.write(row, { mart_in_app: !row.inApp });
    }

    edit(row) {
        this.dialog.add(CategoryDialog, {
            row,
            onSave: async (values) => {
                this.state.busy = true;
                try {
                    await this.orm.call(MODEL, "mart369_admin_write", [[row.id], values]);
                    this.notification.add(_t("Saved."), { type: "success" });
                } finally {
                    this.state.busy = false;
                    await this.load({ quiet: true });
                }
            },
        });
    }

    /** The kanban and list, for what this screen does not do: the name, the
        app address, the parent, the order and the products themselves. */
    allViews() {
        this.action.doAction("mart369_catalog.action_mart369_catalog");
    }

    // --------------------------------------------------------------- drawing

    modeLabel(mode) {
        return mode === "all" ? _t("Express") : _t("Quick");
    }

    swatch(row) {
        return `background: ${row.tone || "#f4f6f8"}; color: ${row.accent || "#0b4a6e"};`;
    }
}

registry.category("actions").add("mart369_catalog.catalog", CatalogDesk);
