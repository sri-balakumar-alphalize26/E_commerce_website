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
import { Component, onWillStart, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { getDataURLFromFile } from "@web/core/utils/urls";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "@mart369/ui/icon";
import { Search } from "@mart369/ui/search";
import { Pill } from "@mart369/ui/pill";
import { Empty } from "@mart369/ui/empty";

const FIELD = "mart369.product.field";
const PRODUCT = "product.template";

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
    static components = { Layout, Icon, Search, Pill, Empty };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.SOURCE = SOURCE;

        this.state = useState({
            // the list
            tree: [],
            products: [],
            allCount: 0,
            uncategorised: 0,
            total: 0,
            categ: null,
            q: "",
            // Kanban or list, the two Odoo offers on its own product list.
            // Remembered per browser, because it is a reading preference and
            // being put back on cards every visit is its own small annoyance.
            view: browser.localStorage?.getItem("mart369.products.view") || "kanban",
            // the product being read, or null for the list
            open: null,
            page: null,
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
            });
            this.state.tree = data.categories || [];
            this.state.products = data.products || [];
            this.state.allCount = data.all_count || 0;
            this.state.uncategorised = data.uncategorised || 0;
            this.state.total = data.total || 0;
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

    pickCateg(id) {
        this.state.categ = id;
        this.load();
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
        this.state.loading = true;
        try {
            this.state.page = await this.orm.call(
                FIELD, "mart369_product_page", [product.id]);
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
            const form = await this.orm.call(
                PRODUCT, "mart369_desk_form", [], { product_id: productId });
            // `values` is what the boxes are bound to and is edited in place;
            // `photos` is the gallery as saved, and `add` / `remove` are what
            // this visit changed, applied only when Save is pressed.
            this.state.form = {
                id: form.id,
                groups: form.groups,
                values: { ...form.values },
                categories: form.categories,
                photo: form.photo,
                photos: form.photos,
                add: [],
                remove: [],
            };
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    closeForm() {
        this.state.form = null;
    }

    setField(name, value) {
        this.state.form.values[name] = value;
    }

    /** Categories are a checklist rather than a picker: the four layers key
     *  off them, so which ones a product is in decides what the rest of this
     *  form even asks for. */
    toggleCategory(id) {
        const chosen = this.state.form.values.public_categ_ids || [];
        this.state.form.values.public_categ_ids = chosen.includes(id)
            ? chosen.filter((c) => c !== id)
            : [...chosen, id];
    }

    isChosen(id) {
        return (this.state.form.values.public_categ_ids || []).includes(id);
    }

    async onPhoto(ev, main) {
        const files = [...(ev.target.files || [])];
        ev.target.value = "";
        for (const file of files) {
            const data = (await getDataURLFromFile(file)).split(",")[1];
            if (main) {
                this.state.form.values.image_1920 = data;
                this.state.form.photo = "data:image/png;base64," + data;
                return; // only one picture goes on the card
            }
            this.state.form.add.push({ name: file.name, data });
        }
    }

    clearPhoto() {
        // '' rather than leaving it out: the server reads the difference as
        // "take it away" versus "was not mentioned".
        this.state.form.values.image_1920 = "";
        this.state.form.photo = "";
    }

    /** A saved photograph is marked for removal rather than removed, so
     *  nothing is lost until Save; one added this visit simply leaves. */
    dropPhoto(photo) {
        if (photo.id) {
            this.state.form.remove.push(photo.id);
            this.state.form.photos = this.state.form.photos.filter(
                (p) => p.id !== photo.id);
        } else {
            this.state.form.add = this.state.form.add.filter((p) => p !== photo);
        }
    }

    get pendingPhotos() {
        return this.state.form.add.map((p) => ({
            ...p, url: "data:image/png;base64," + p.data }));
    }

    async save() {
        const form = this.state.form;
        if (!(form.values.name || "").trim()) {
            this.state.error = _t("A product needs a name.");
            return;
        }
        this.state.saving = true;
        this.state.error = "";
        try {
            const id = await this.orm.call(PRODUCT, "mart369_desk_save", [], {
                values: form.values,
                product_id: form.id,
                photos: { add: form.add, remove: form.remove },
            });
            this.state.form = null;
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
        return row.value || _t("Nothing set");
    }

    money(amount) {
        return Number(amount || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    get visibleRows() {
        return (this.state.page?.sections || []).reduce(
            (n, s) => n + (s.show ? s.shown : 0), 0);
    }
}

registry.category("actions").add("mart369_product.products", ProductDesk);
