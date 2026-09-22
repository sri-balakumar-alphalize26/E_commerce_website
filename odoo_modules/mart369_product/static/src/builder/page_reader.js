/**
 * What both product-page screens know about the page.
 *
 * There are two of them - the desk editor (editor.js, the front door) and the
 * phone builder (product_builder.js, "all settings") - and they draw the same
 * product page from the same `builder_load` payload. Everything that is only
 * *reading* that payload lives here, so the two can never disagree about
 * whether a row is visible or what a section is called.
 *
 * The drawing itself is shared the same way: page_reader.xml holds the page
 * body and the mock bands, and each screen passes in its own band wrapper.
 */
import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export const M = {
    section: "mart369.product.section",
    field: "mart369.product.field",
    override: "mart369.product.override",
    categoryValue: "mart369.product.category.value",
    product: "product.template",
};

/** The three answers a single product can give to a shop-wide switch. */
export const STATES = [
    ["follow", _t("Follow the default")],
    ["show", _t("Always show")],
    ["hide", _t("Always hide")],
];

/** Which bands draw inside the buy card's accordion, and which below it. */
const ACCORDION = ["features", "info", "specs", "description", "returns"];
const TAIL = ["delivery", "bundle", "similar"];

export class ProductPageReader extends Component {
    get d() {
        return this.state.data;
    }

    // ------------------------------------------------------------ the bands

    /** The bands that draw as an accordion inside the buy card. */
    get accordionSections() {
        return (this.d?.sections || []).filter((s) => ACCORDION.includes(s.key));
    }

    /** The bands that sit below the fold. */
    get tailSections() {
        return (this.d?.sections || []).filter((s) => TAIL.includes(s.key));
    }

    sectionByKey(key) {
        return (this.d?.sections || []).find((s) => s.key === key);
    }

    sectionById(id) {
        return (this.d?.sections || []).find((s) => s.id === id);
    }

    // ------------------------------------------------------------- the rows

    /** A section always has rows server-side, but never assume it here:
     *  a half-loaded payload should not take the whole screen down. */
    rowsOf(section) {
        return (section && section.rows) || [];
    }

    row(sectionKey, fieldKey) {
        return this.rowsOf(this.sectionByKey(sectionKey)).find(
            (r) => r.key === fieldKey
        );
    }

    rowById(id) {
        for (const section of this.d?.sections || []) {
            const found = this.rowsOf(section).find((r) => r.id === id);
            if (found) {
                return found;
            }
        }
        return null;
    }

    /** The section a row belongs to - the panel needs it to go back up. */
    sectionOfRow(id) {
        return (this.d?.sections || []).find((s) =>
            this.rowsOf(s).some((r) => r.id === id)
        );
    }

    /**
     * Would a shopper see this row, in the scope being edited?
     *
     * Every row carries both answers: `show` is the shop-wide default and
     * `visible` is what this one product ends up with once its own state is
     * applied. Which one the canvas should draw depends on the question being
     * asked - "what does the shop do?" or "what does this product do?" - and
     * they differ exactly when somebody has made the product differ.
     *
     * Reading the right one per scope is also what lets the scope toggle be
     * instant: the payload already holds both, so switching needs no reload,
     * and `builder_load` costs well over a second.
     */
    shown(row) {
        if (!row) {
            return false;
        }
        return this.state.tab === "global" ? row.show : row.visible;
    }

    rowVisible(sectionKey, fieldKey) {
        return this.shown(this.row(sectionKey, fieldKey));
    }

    rowValue(sectionKey, fieldKey) {
        const row = this.row(sectionKey, fieldKey);
        return row ? row.value : "";
    }

    visibleRows(section) {
        return this.rowsOf(section).filter((r) => this.shown(r));
    }

    /** How many of this section's rows this one product answers for itself. */
    differing(section) {
        if (this.state.tab !== "product") {
            return 0;
        }
        return this.rowsOf(section).filter((r) => r.state !== "follow").length;
    }

    // -------------------------------------------------------- the buy card

    get offPct() {
        const card = this.d?.card;
        if (!card || !card.mrp || !card.price) {
            return 0;
        }
        return Math.round(((card.mrp - card.price) / card.mrp) * 100);
    }

    get ratingText() {
        return this.rowValue("reviews", "rating") || "No rating yet";
    }

    // ------------------------------------------------- the rails below the fold

    /** The products the payload says would appear on a rail. `builder_load`
     *  ships them in `preview` precisely so the canvas can draw the real
     *  thing rather than a count - inventing products on an admin screen is
     *  not an option, and "3 of 4 shown" tells an employee nothing about
     *  what the rail will actually look like. */
    rail(key) {
        return (this.d?.preview && this.d.preview[key]) || [];
    }

    /** Is this rail's own switch on? Each rail is one field in its section. */
    railOn(sectionKey, fieldKey) {
        return this.rowVisible(sectionKey, fieldKey);
    }

    /** The page prices in whole rupees, the way the buy card already does.
     *  builder_load carries no currency, and guessing one would be worse
     *  than the symbol the rest of this screen already shows. */
    money(n) {
        return '₹' + Math.round(Number(n) || 0);
    }

    /** Bought-together is the product itself plus the rail. */
    get bundleItems() {
        const me = this.d?.card;
        return me ? [me, ...this.rail('bundle')] : this.rail('bundle');
    }

    get bundleTotal() {
        return this.bundleItems.reduce((sum, i) => sum + (Number(i.price) || 0), 0);
    }

    get ratingCountText() {
        const count = this.rowValue("reviews", "rating_count");
        return count ? `(${count} ratings)` : "";
    }
}
