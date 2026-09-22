/**
 * The product page editor - the page itself, with a switch on everything.
 *
 * The front door of 369 Mart > Product Page, and the twin of the home page's
 * editor (mart369_home/static/src/builder/editor.js). The canvas is not a
 * picture of the product page; it is the shop's own markup and the shop's own
 * stylesheet, drawn from the same `builder_load` the app's console reads. So
 * "what will shoppers see?" is answered by looking.
 *
 * Three rules this screen keeps:
 *
 *  - Two scopes, never mixed up. "Whole shop" sets the default every product
 *    follows. "This product" answers for one product only, and a row left on
 *    *Follow the default* keeps up with the shop - now and later. The toolbar
 *    says which you are in, because the same switch means different things.
 *  - The page is the index. Click a band to open its fields; open a field to
 *    edit it. Nothing is buried in a form you have to know the name of.
 *  - Nothing is saved by hand. Wording writes itself a moment after typing
 *    stops; a switch writes at once, because there is no second keystroke
 *    coming and a toggle that looks done but is not gets pressed twice.
 *
 * Where this deliberately differs from the app's console (ProductPageSection.jsx):
 * the console measures the real page's nodes with a ResizeObserver and floats
 * boxes over them, because it renders a React page it cannot change. Here the
 * QWeb is ours, so a band *is* its own overlay - the same thing the home
 * editor does. The two are meant to look alike, not to be written alike.
 */
import { onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "@mart369_home/builder/builder";
import { useSaveQueue } from "@mart369_home/builder/save_queue";
import { M, STATES, ProductPageReader } from "./page_reader";

export class ProductEditor extends ProductPageReader {
    static template = "mart369_product.ProductEditor";
    static components = { Layout, Icon };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.STATES = STATES;

        this.state = useState({
            tab: "global",        // "global" (the whole shop) | "product"
            data: null,
            productId: this.props.action?.context?.mart369_product_id || null,
            sel: null,            // "section:<id>" | "field:<id>" | null
            showHidden: false,
            status: "idle",       // idle | saving | saved | error
            loading: true,
            error: "",
            // Choosing "One product" opens the shop to browse. The search
            // box this replaces only answered "is there a product called
            // X?", which needed you to know the name first.
            picking: false,
            // Whether this product has been changed since it was opened. Only
            // used to decide whether moving to another one is worth a
            // question - nothing here is unsaved.
            touched: false,
            pick: { categ: null, q: "", onlyEdited: false, data: null, busy: false },
        });

        this.save = useSaveQueue({
            orm: this.orm,
            notification: this.notification,
            reload: () => this.load(),
            onStatus: (s) => (this.state.status = s),
            find: (model, id) => this.findRecord(model, id),
        });

        this.searchPicker = useDebounced(() => this.loadPicker(), 300);
        // Same 600ms the save queue uses, so wording in either scope settles
        // at the same moment and the chip means one thing.
        this.pushValue = useDebounced(
            (fieldId, value) =>
                this.save.run(() =>
                    this.orm.call(M.field, "set_product_value", [
                        fieldId,
                        this.state.productId,
                        value,
                    ])
                ),
            600
        );
        this.canvasRef = useRef("canvas");

        onWillStart(() => this.load());
    }

    // ------------------------------------------------------------- loading

    async load() {
        try {
            const data = await this.orm.call(M.field, "builder_load", [
                this.state.productId,
            ]);
            this.state.data = data;
            this.state.error = "";
            if (data.product) {
                this.state.productId = data.product.id;
            }
            this.save.applyPending();
            // Drop a selection whose record has gone, or the panel edits a
            // ghost and every keystroke fails.
            if (this.state.sel && !this.selected) {
                this.state.sel = null;
            }
        } catch (err) {
            this.state.error =
                err?.data?.message || err?.message || "We could not reach the shop.";
        } finally {
            this.state.loading = false;
        }
    }

    /** Where a record lives in the payload, for the save queue's replay. */
    findRecord(model, id) {
        if (model === M.field) {
            return this.rowById(id);
        }
        return model === M.section ? this.sectionById(id) : null;
    }

    // ----------------------------------------------------------- selection

    /** `{kind, section, row}` - a band, or a field inside one. */
    get selected() {
        if (!this.state.sel || !this.d) {
            return null;
        }
        const [kind, raw] = this.state.sel.split(":");
        const id = parseInt(raw, 10);
        if (kind === "section") {
            const section = this.sectionById(id);
            return section ? { kind, section, row: null } : null;
        }
        const row = this.rowById(id);
        return row ? { kind, section: this.sectionOfRow(id), row } : null;
    }

    select(kind, id) {
        this.state.sel = kind + ":" + id;
    }

    clearSelection() {
        this.state.sel = null;
    }

    isSelected(kind, id) {
        return this.state.sel === kind + ":" + id;
    }

    /** Click the band, not its buttons - the eye is its own control. */
    onBandClick(section, ev) {
        if (ev.target.closest(".pe-tool")) {
            return;
        }
        this.select("section", section.id);
    }

    // -------------------------------------------------------------- drawing

    /** Sections still draw when switched off; the canvas greys them. But
     *  "show what is off" decides whether they are drawn at all. */
    get hiddenCount() {
        let n = 0;
        for (const section of this.d?.sections || []) {
            if (!section.show) {
                n += 1;
            }
            n += this.rowsOf(section).filter((r) => !this.shown(r)).length;
        }
        return n;
    }

    shownOf(section) {
        return this.visibleRows(section).length;
    }

    /** "3 of 11 shown" - the line the whole-page list is made of. */
    countLabel(section) {
        return this.shownOf(section) + " of " + this.rowsOf(section).length + " shown";
    }

    get scopeLabel() {
        return this.state.tab === "global" ? _t("Whole shop") : _t("This product");
    }

    get productName() {
        return this.d?.product ? this.d.product.name : "";
    }

    // ---------------------------------------------------------------- edits

    /** The band's master switch. Writes at once - see save_queue's `now`. */
    toggleSection(section) {
        return this.save.run(() =>
            this.orm.write(M.section, [section.id], { show: !section.show })
        );
    }

    /** The shop-wide switch on one field. */
    toggleGlobal(row) {
        return this.save.run(() =>
            this.orm.write(M.field, [row.id], { show: !row.show })
        );
    }

    /** This product's own answer: follow, always show, always hide. */
    setState(row, state) {
        this.state.touched = true;
        return this.save.run(() =>
            this.orm.call(M.field, "set_product_state", [
                row.id,
                this.state.productId,
                state,
            ])
        );
    }

    /** The shop-wide wording. Debounced: there is another keystroke coming. */
    editDefault(row, ev) {
        this.save.edit(M.field, row, "default_value", this.save.valueFrom(ev));
    }

    /**
     * Wording for this one product. This one cannot go through the save
     * queue's `edit`: the queue writes fields on a record, and there is no
     * record to write until the model decides whether this product needs an
     * override row at all (and, when the words are cleared, whether to remove
     * one). So it is the same debounce, spelled out against the model method.
     */
    setProductValue(row, ev) {
        // `product_value` is the raw wording; `value` is what the page ends up
        // drawing, which is that run through _as_text. Edit the raw one - a
        // bool would come back as "Yes" and be written back as the word.
        row.product_value = ev.target.value;
        this.state.touched = true;
        this.pushValue(row.id, row.product_value);
    }

    /**
     * Put one field back to following the shop. Deliberately not optimistic:
     * a reset clears an override row *and* whatever wording was on it, and
     * guessing what the page falls back to is exactly the guess that would be
     * wrong. Ask the server.
     */
    resetRow(row) {
        this.state.touched = true;
        this.dialog.add(ConfirmationDialog, {
            title: _t("Put this one back?"),
            body: _t(
                "“%s” goes back to following the shop, and any wording " +
                    "set just for this product is cleared.",
                row.name
            ),
            confirmLabel: _t("Put it back"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.save.run(
                    () =>
                        this.orm.call(M.field, "reset_product_state", [
                            [row.id],
                            this.state.productId,
                        ]),
                    { successMessage: _t("Back to the shop default") }
                ),
            cancel: () => {},
        });
    }

    resetSection(section) {
        this.state.touched = true;
        const ids = this.rowsOf(section).map((r) => r.id);
        this.dialog.add(ConfirmationDialog, {
            title: _t("Put this whole section back?"),
            body: _t(
                "Every field under “%s” goes back to following the shop " +
                    "for this product.",
                section.name
            ),
            confirmLabel: _t("Put them back"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.save.run(
                    () =>
                        this.orm.call(M.field, "reset_product_state", [
                            ids,
                            this.state.productId,
                        ]),
                    { successMessage: _t("Back to the shop defaults") }
                ),
            cancel: () => {},
        });
    }

    // ----------------------------------------------------------- the scopes

    /**
     * The scope switch, with a question in front of it.
     *
     * The two scopes look identical and mean opposite things: the same eye
     * hides a row on one product, or on all 117 of them. Somebody who has
     * been editing one product and reaches for "Whole shop" without noticing
     * is one click from changing the whole catalogue, and nothing on screen
     * would look different afterwards. So the dangerous direction asks first
     * and says what it is about to become.
     *
     * Only that direction. Going the other way opens the picker, which is
     * self-evidently about one product, and a confirm on every switch trains
     * people to click through the one that matters.
     */
    async switchTab(tab) {
        if (tab === this.state.tab) {
            return;
        }
        await this.save.flushNow().catch(() => {});
        if (tab === "global" && this.state.tab === "product") {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Switch to the whole shop?"),
                body: this.leavingProductNote,
                confirmLabel: _t("Edit the whole shop"),
                confirm: () => this._goTab("global"),
                cancel: () => {},
            });
            return;
        }
        await this._goTab(tab);
    }

    /** What is true about the product being left behind. Counted, not
     *  guessed: "3 things" is worth reading, "some things" is not. */
    get leavingProductNote() {
        const name = this.productName || _t("this product");
        let differs = 0;
        for (const section of this.d?.sections || []) {
            differs += this.rowsOf(section).filter((r) => r.state !== "follow").length;
        }
        const kept = differs
            ? _t(
                  "The %s thing(s) you set just for “%s” stay as they are.",
                  differs,
                  name
              )
            : _t("“%s” keeps following the shop.", name);
        return (
            _t(
                "From here, anything you switch or reword changes every " +
                    "product in the shop, not just one."
            ) +
            " " +
            kept
        );
    }

    async _goTab(tab) {
        this.state.tab = tab;
        // The selection deliberately survives: you stay on the field you were
        // looking at and see what it says in the other scope. The tour pins
        // this.
        if (tab === "product") {
            // "List out all the products" is the whole point of the switch:
            // it opens the shop rather than an empty search box.
            this.state.picking = true;
            await this.loadPicker();
            return;
        }
        this.state.picking = false;
        // No reload. `builder_load` carries both answers on every row - the
        // shop-wide `show` and this product's `visible` - so the scope toggle
        // is a question about the payload we already hold, not a new one for
        // the server. It used to re-fetch, and that call costs well over a
        // second: the toggle sat there looking broken.
    }

    // ----------------------------------------------------- picking a product

    /** Everything the picker draws, in one call - the same one the console
        reads through /369mart/admin/product/catalog. */
    async loadPicker() {
        const pick = this.state.pick;
        pick.busy = true;
        try {
            pick.data = await this.orm.call(M.product, "mart369_page_picker", [], {
                categ_id: pick.categ,
                q: pick.q,
                only_edited: pick.onlyEdited,
            });
        } finally {
            pick.busy = false;
        }
    }

    /** The flat list of categories, hung back into the tree the shop keeps
        it in, so the rail can nest children under their parent. */
    get categoryTree() {
        const all = this.state.pick.data?.categories || [];
        const kids = new Map();
        for (const c of all) {
            if (c.parent_id) {
                if (!kids.has(c.parent_id)) {
                    kids.set(c.parent_id, []);
                }
                kids.get(c.parent_id).push(c);
            }
        }
        // Flattened back out with a depth, because QWeb has no recursion:
        // one loop over rows that already know how far to indent.
        const rows = [];
        const walk = (list, depth) => {
            for (const c of list) {
                rows.push({ ...c, depth });
                walk(kids.get(c.id) || [], depth + 1);
            }
        };
        walk(all.filter((c) => !c.parent_id), 0);
        return rows;
    }

    get pickedProducts() {
        return this.state.pick.data?.products || [];
    }

    get pickTruncated() {
        const d = this.state.pick.data;
        return !!d && d.total > d.products.length;
    }

    setCategory(id) {
        this.state.pick.categ = id;
        this.loadPicker();
    }

    onPickSearch(ev) {
        this.state.pick.q = ev.target.value;
        this.searchPicker();
    }

    toggleOnlyEdited() {
        this.state.pick.onlyEdited = !this.state.pick.onlyEdited;
        this.loadPicker();
    }

    /** Out of the list again, still on the product you were editing. Browsing
     *  is not choosing, so looking at the shop and changing your mind has to
     *  leave you where you were. */
    backToProduct() {
        this.state.picking = false;
    }

    /** Back to the shop, to choose a different product. */
    changeProduct() {
        this.state.picking = true;
        this.loadPicker();
    }

    /**
     * Moving to a different product, having changed the one you were on.
     *
     * Nothing is lost here - every write has already landed - so the question
     * is not "save?" but "did you mean these to apply to that one product?".
     * That is worth asking once, because the two scopes look the same and the
     * whole point of this screen is that one product can differ deliberately
     * rather than by accident.
     */
    async pickProduct(id) {
        if (this.state.touched && id !== this.state.productId) {
            const from = this.productName;
            this.dialog.add(ConfirmationDialog, {
                title: _t("Move to a different product?"),
                body: _t(
                    "What you changed stays on “%s” and applies to " +
                        "that product only. Anything you change next belongs " +
                        "to the product you are about to open.",
                    from
                ),
                confirmLabel: _t("Open it"),
                confirm: () => this._openProduct(id),
                cancel: () => {},
            });
            return;
        }
        await this._openProduct(id);
    }

    async _openProduct(id) {
        this.state.productId = id;
        this.state.sel = null;
        this.state.touched = false;
        // Load first, leave the picker second. The other way round re-renders
        // the editor the moment the flag flips, which draws the *previous*
        // product's page until the new one lands - so tapping a tile flashed
        // up the wrong product, complete with its name in the toolbar.
        await this.load();
        this.state.picking = false;
    }

    // --------------------------------------------------------------- moving

    /** The phone builder, for the fields this screen leaves out: the
        shop-wide field registry, sections in a phone frame, wording by
        category. */
    moreSettings() {
        this.action.doAction("mart369_product.action_mart369_product_builder", {
            additionalContext: { mart369_product_id: this.state.productId },
        });
    }
}

registry.category("actions").add("mart369_product.editor", ProductEditor);
