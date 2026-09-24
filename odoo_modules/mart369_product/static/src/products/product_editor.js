/**
 * The product editor - photographs, the boxes, and "how it looks".
 *
 * One component with two hosts, so the two screens that edit a product cannot
 * drift apart:
 *
 *  - the Products desk (369 Mart > Products), which keeps its own Save and
 *    Cancel and writes through `mart369_desk_save`;
 *  - Odoo's own product form (Inventory > Products), where the editor sits in
 *    the 369 Mart tab and every change goes to the form's record, so Odoo's
 *    Save and Discard are the only buttons.
 *
 * On the desk the editor keeps everything in its own state until Save. In the
 * form (`embedded`) it still keeps the boxes' state, so typing never re-draws
 * the box under the cursor, but reports each change through `onValue`, and
 * hands photographs to `photoHost`, which changes the record and passes the
 * gallery back down as props.
 *
 * The boxes themselves come from `mart369_desk_form`, which reads the field
 * definitions and the page's hidden-box list - so both hosts ask the same
 * questions in the same words.
 */
import { Component, onPatched, onWillUpdateProps, useEffect, useExternalListener, useRef, useState } from "@odoo/owl";
import { getDataURLFromFile } from "@web/core/utils/urls";
import { _t } from "@web/core/l10n/translation";
import { Icon } from "@mart369/ui/icon";
import { Pick } from "@mart369/ui/pick";

/* Where each box shows up for the shopper, for the eye button's card.
   `card` and `page` draw a mock of that screen with the box outlined; `note`
   has no spot on either and says where it is used instead. `sample` fills an
   empty box so the mock always has something to point at. */
export const PREVIEW = {
    name: { where: "card", sample: _t("USB-C Fast Charger") },
    type: { where: "note", note: _t("Goods are counted and delivered; a service is not. Decides what Odoo does with stock and delivery.") },
    is_storable: { where: "note", note: _t("When on, Odoo keeps a stock count - and the app can say 'Only 3 left' and stop selling at zero.") },
    mart_on_hand: { where: "note", note: _t("Not shown as a number. The app uses it to say 'Only 3 left' and to stop selling at zero.") },
    barcode: { where: "note", note: _t("Not shown to shoppers. Scanned at the till and in the warehouse.") },
    categ_id: { where: "note", note: _t("Not shown to shoppers. Odoo's own category, for accounts and stock rules.") },
    taxes_id: { where: "note", note: _t("Added to the price when a shopper pays, as your tax settings say.") },
    supplier_taxes_id: { where: "note", note: _t("Not shown to shoppers. The tax on what you buy it for.") },
    company_id: { where: "note", note: _t("Not shown to shoppers. Which of your companies sells it.") },
    mart_brand: { where: "note", note: _t("The brand line on the product page, above the name. Empty falls back to the shop's brand.") },
    default_code: { where: "note", note: _t("Not shown to shoppers. It is your own code for the product, used in search and on your records.") },
    public_categ_ids: { where: "note", note: _t("Decides which aisles the product is listed under in the app, and which page settings apply to it.") },
    list_price: { where: "card", sample: "12.500" },
    compare_list_price: { where: "card", sample: "15.000" },
    standard_price: { where: "note", note: _t("Not shown to shoppers. What the product costs you - Odoo uses it for margins and stock value.") },
    mart_unit_text: { where: "card", sample: "250 g" },
    mart_per_unit: { where: "card", sample: "17.25 per 250 g" },
    mart_note: { where: "card", sample: _t("Approx 250-400 g") },
    mart_home_tag: { where: "card", sample: _t("New") },
    mart_low_stock_at: { where: "card", sample: "3" },
    mart_delivery_text: { where: "card", sample: _t("3-5 days") },
    mart_features: { where: "page", sample: _t("Fast charging\nFoldable plug") },
    mart_in_the_box: { where: "page", sample: _t("Charger, cable") },
    mart_material: { where: "page", sample: _t("Plastic") },
    mart_item_height: { where: "page", sample: "12 cm" },
    mart_item_length: { where: "page", sample: "8 cm" },
    mart_item_width: { where: "page", sample: "6 cm" },
    weight: { where: "page", sample: "0.25" },
    description_ecommerce: { where: "page", sample: _t("A short paragraph about the product.") },
};

const OTHER = "__other";
const NUMBER = /^\d+(?:\.\d+)?$/;
const RANGE = /^\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?$/;

function unitIn(units, word) {
    return units.find((u) => u.toLowerCase() === (word || "").toLowerCase());
}

/** A saved value split into the parts its boxes edit. Anything that does not
 *  fit keeps its text in `other`, so nothing is lost on the way in. */
export function splitValue(box, raw) {
    if (box.numeric) {
        // A number column kept in the first unit (weight: kg).
        return { value: raw ? String(raw) : "", unit: box.units[0], other: null };
    }
    const text = String(raw || "").trim();
    if (box.kind === "points") {
        // Features are one per line; In the box is a comma list.
        const split = box.sep ? /,/ : /\n/;
        const list = text ? text.split(split).map((l) => l.trim()).filter(Boolean) : [];
        return { list: list.length ? list : [""] };
    }
    if (box.kind === "choice") {
        if (!text) {
            return { choice: "", other: "" };
        }
        const hit = box.options.find((o) => o.toLowerCase() === text.toLowerCase());
        return hit ? { choice: hit, other: "" } : { choice: OTHER, other: text };
    }
    const units = box.units || [];
    if (box.kind === "per_unit") {
        const m = text.match(/^(\d+(?:\.\d+)?)\s*(?:per|\/)\s*(\d+(?:\.\d+)?)?\s*(\S+)$/i);
        if (!text) {
            return { price: "", value: "", unit: units[0], other: null };
        }
        if (m && unitIn(units, m[3])) {
            return { price: m[1], value: m[2] || "", unit: unitIn(units, m[3]), other: null };
        }
        return { price: "", value: "", unit: units[0], other: text };
    }
    // measure
    if (!text) {
        return { value: "", unit: units[0], other: null };
    }
    const m = text.match(/^(\S+?)\s*([a-zA-Z]+)$/);
    const ok = m && (box.range ? RANGE : NUMBER).test(m[1]) && unitIn(units, m[2]);
    return ok
        ? { value: m[1], unit: unitIn(units, m[2]), other: null }
        : { value: "", unit: units[0], other: text };
}

/** The parts back into the one value the column holds. */
export function joinValue(box, p) {
    if (box.kind === "points") {
        return p.list.map((l) => l.trim()).filter(Boolean).join(box.sep || "\n");
    }
    if (box.kind === "choice") {
        return p.choice === OTHER ? p.other.trim() : p.choice;
    }
    if (box.numeric) {
        // Back into the first unit: 250 g is saved as 0.25 kg.
        if (!p.value) {
            return "";
        }
        const n = Number(p.value);
        return p.unit === box.units[0] ? n : n / 1000;
    }
    if (p.other !== null) {
        return p.other.trim();
    }
    if (box.kind === "per_unit") {
        if (!p.price) {
            return "";
        }
        return `${p.price} per ${p.value ? p.value + " " : ""}${p.unit}`;
    }
    return p.value ? `${p.value} ${p.unit}` : "";
}

/** The shop's money shape: its decimals and symbol when known. */
export function money(amount, currency) {
    const decimals = currency?.decimals ?? 2;
    const shown = Number(amount || 0).toLocaleString(currency?.locale, {
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

/** The editor's working copy, from a `mart369_desk_form` answer. */
function formFrom(data) {
    const boxes = {};
    const parts = {};
    for (const g of data.groups) {
        for (const b of g.boxes) {
            boxes[b.name] = b;
            if (b.kind) {
                parts[b.name] = splitValue(b, data.values[b.name]);
            }
        }
    }
    return {
        id: data.id,
        groups: data.groups,
        boxes,
        parts,
        values: { ...data.values },
        categories: data.categories,
        photo: data.photo,
        photos: data.photos,
        // The desk's own photograph bookkeeping, applied on its Save. Unused
        // in the form, where the record keeps it.
        add: [],
        remove: [],
        promoted: null,
        demote: false,
        demotedUrl: "",
        // Anything touched, so Cancel knows to ask first.
        dirty: false,
        categQ: "",
    };
}

export class ProductEditor extends Component {
    static template = "mart369_product.DetailsEditor";
    static components = { Icon, Pick };
    static props = {
        // A `mart369_desk_form` answer: groups, values, categories, photos.
        data: Object,
        currency: { type: [Object, { value: null }], optional: true },
        // Inside Odoo's form rather than on the desk.
        embedded: { type: Boolean, optional: true },
        // Each value change, as (name, value) - the form's host writes it to
        // the record.
        onValue: { type: Function, optional: true },
        // In the form: { add(files), remove(item), useOnCard(item) }, each
        // changing the record. The gallery then comes back down in `data`.
        photoHost: { type: Object, optional: true },
        // Handed the editor once it exists, so the desk can read its state
        // on Save and Cancel.
        onReady: { type: Function, optional: true },
        // The desk's sticky bar: { name, dirty }, kept current as boxes change.
        status: { type: Object, optional: true },
    };

    setup() {
        this.state = useState({
            form: formFrom(this.props.data),
            // The photograph open in the popup, as an index into `photoList`.
            viewing: null,
            // The box lit on the "How shoppers see it" panel. Set by hovering
            // an eye or clicking into a box, and kept until another takes over.
            focus: null,
            // The box pointed at just now: its spot pulses once. Cleared and
            // set again on the next frame, so pointing twice pulses twice.
            beat: null,
            // Photographs being dragged over the section.
            dragging: false,
            // Save was pressed with no name.
            nameBad: false,
            // Ticked photographs, for "Remove selected".
            picked: [],
            // The category dropdown - a panel over the form, so the boxes
            // below never jump while choosing.
            categOpen: false,
        });
        this.props.onReady?.(this);

        // In the form the gallery lives on the record; take each new copy of
        // it as it comes down. The boxes are left alone - they are the
        // editor's own and already up to date.
        onWillUpdateProps((next) => {
            if (next.embedded) {
                this.state.form.photo = next.data.photo;
                this.state.form.photos = next.data.photos;
                const left = this.photoList.length;
                if (this.state.viewing !== null && this.state.viewing >= left) {
                    this.state.viewing = left ? left - 1 : null;
                }
            }
        });

        // Focus goes to the photo popup as it opens, so Escape and the arrow
        // keys work without a click first.
        this.viewerRef = useRef("viewer");
        useEffect(
            (open) => {
                if (open) {
                    this.viewerRef.el?.focus();
                }
            },
            () => [this.state.viewing !== null]
        );
        // Escape closes whichever popup is open, wherever focus happens to be.
        // Listened for on the way down (capture): Odoo's own hotkeys take
        // Escape on the way up, and the category panel never heard it.
        useExternalListener(window, "keydown", (ev) => {
            if (ev.key !== "Escape") {
                return;
            }
            if (this.state.categOpen) {
                ev.stopPropagation();
                this.state.categOpen = false;
            } else if (this.state.viewing !== null) {
                ev.stopPropagation();
                this.closePhoto();
            }
        }, { capture: true });

        // A click outside the category panel closes it.
        this.categRef = useRef("categ");
        useExternalListener(document, "mousedown", (ev) => {
            if (this.state.categOpen && !this.categRef.el?.contains(ev.target)) {
                this.state.categOpen = false;
            }
        });

        onPatched(() => {
            if (this.pendingFocus) {
                const { name, i } = this.pendingFocus;
                this.pendingFocus = null;
                this.root?.querySelector(
                    `.pdk-points[data-name="${name}"] input[data-i="${i}"]`)?.focus();
            }
        });
        this.rootRef = useRef("root");
    }

    get root() {
        return this.rootRef.el || document;
    }

    // ------------------------------------------------------------- values

    /** Every value change goes through here: kept, marked, and reported. */
    /** Something was changed - photo or box - so Cancel asks, and the desk's
     *  bar says "Unsaved changes". */
    markDirty() {
        this.state.form.dirty = true;
        if (this.props.status) {
            this.props.status.dirty = true;
        }
    }

    changed(name) {
        const form = this.state.form;
        this.markDirty();
        if (this.props.status) {
            if (name === "name") {
                this.props.status.name = form.values.name || "";
            }
        }
        this.props.onValue?.(name, form.values[name]);
    }

    setField(name, value) {
        this.state.form.values[name] = value;
        if (name === "name" && String(value).trim()) {
            this.state.nameBad = false;
        }
        this.changed(name);
    }

    /** Inside Odoo's own form, the groups Odoo already draws above are left
     *  out (Stock, tax and company), so nothing appears twice. */
    get shownGroups() {
        const groups = this.state.form.groups;
        return this.props.embedded ? groups.filter((g) => !g.deskOnly) : groups;
    }

    /** A box that only makes sense once another is on - On hand, once the
     *  product is counted at all. */
    shownBoxes(group) {
        const values = this.state.form.values;
        return group.boxes.filter((b) => !b.showIf || values[b.showIf]);
    }

    /** A select box's value, as the string its options are keyed by. */
    selectValue(box) {
        const v = this.state.form.values[box.name];
        return v === undefined || v === null || v === false ? "" : String(v);
    }

    // Several of a list (taxes): chips for the chosen, a dropdown to add.

    chosenTags(box) {
        const ids = this.state.form.values[box.name] || [];
        return box.options.filter(([id]) => ids.includes(id));
    }

    tagChoices(box) {
        const ids = this.state.form.values[box.name] || [];
        return [["", _t("Add...")], ...box.options
            .filter(([id]) => !ids.includes(id))
            .map(([id, label]) => [String(id), label])];
    }

    addTag(name, value) {
        if (!value) {
            return;
        }
        const ids = this.state.form.values[name] || [];
        this.setFocus(name);
        this.setField(name, [...ids, Number(value)]);
    }

    dropTag(name, id) {
        const ids = this.state.form.values[name] || [];
        this.setFocus(name);
        this.setField(name, ids.filter((x) => x !== id));
    }

    /** One part changed: keep it, and write the joined value back. */
    setPart(name, key, value) {
        const form = this.state.form;
        form.parts[name][key] = value;
        form.values[name] = joinValue(form.boxes[name], form.parts[name]);
        this.changed(name);
    }

    /** The old price below the price is not a discount - said under the box
     *  rather than refused, since the person may be mid-way through typing. */
    get mrpWarning() {
        const v = this.state.form.values;
        const mrp = Number(v.compare_list_price || 0);
        const price = Number(v.list_price || 0);
        return mrp > 0 && price > 0 && mrp <= price;
    }

    /** A dropdown choice: light the box, then keep the value. */
    pickField(name, value) {
        this.setFocus(name);
        this.setField(name, value);
    }

    pickPart(name, value) {
        this.setFocus(name);
        this.setPart(name, "choice", value);
    }

    toggleCateg(name) {
        this.setFocus(name);
        this.state.categOpen = !this.state.categOpen;
    }

    get chosenNames() {
        const ids = this.state.form.values.public_categ_ids || [];
        return this.state.form.categories.filter((c) => ids.includes(c.id)).map((c) => c.name).join(", ");
    }

    setCategQ(q) {
        this.state.form.categQ = q;
    }

    /** The category chips, narrowed by the filter box; chosen ones first. */
    get shownCategories() {
        const form = this.state.form;
        const q = form.categQ.trim().toLowerCase();
        const hits = form.categories.filter((c) => !q || c.name.toLowerCase().includes(q));
        return [
            ...hits.filter((c) => this.isChosen(c.id)),
            ...hits.filter((c) => !this.isChosen(c.id)),
        ];
    }

    /** Categories are a checklist rather than a picker: the four layers key
     *  off them, so which ones a product is in decides what the rest of this
     *  form even asks for. */
    toggleCategory(id) {
        const chosen = this.state.form.values.public_categ_ids || [];
        this.state.form.values.public_categ_ids = chosen.includes(id)
            ? chosen.filter((c) => c !== id)
            : [...chosen, id];
        this.changed("public_categ_ids");
    }

    isChosen(id) {
        return (this.state.form.values.public_categ_ids || []).includes(id);
    }

    /** Numbers only, as typed: digits and one point, plus one dash where a
     *  range is allowed. Anything else never reaches the box. */
    onNumber(ev, name, key, range = false) {
        const oneDot = (s) => {
            const [a, ...rest] = s.split(".");
            return rest.length ? `${a}.${rest.join("")}` : a;
        };
        const raw = ev.target.value.replace(range ? /[^\d.\-]/g : /[^\d.]/g, "");
        const [from, ...to] = raw.split("-");
        const v = to.length ? `${oneDot(from)}-${oneDot(to.join(""))}` : oneDot(from);
        ev.target.value = v;
        this.setPart(name, key, v);
    }

    /** The plain number boxes - price, MRP, cost, on hand, the stock warning.
     *  Not the browser's number box, which lets "e", "+" and "-" through;
     *  digits and one point only, and digits alone where it counts whole
     *  things. */
    onPlainNumber(ev, name, whole = false) {
        let v = ev.target.value.replace(whole ? /[^\d]/g : /[^\d.]/g, "");
        const [a, ...rest] = v.split(".");
        v = rest.length ? `${a}.${rest.join("")}` : a;
        ev.target.value = v;
        this.setField(name, v);
    }

    /** Leave a text that did not fit, for the number and unit boxes. */
    useBoxes(name) {
        this.setPart(name, "other", null);
    }

    unitOptions(box) {
        return box.units.map((u) => [u, u]);
    }

    choiceOptions(box) {
        return [["", _t("None")], ...box.options.map((o) => [o, o]), [OTHER, _t("Other...")]];
    }

    // Key features and In the box, one box per point.

    setPoint(name, i, value) {
        const list = [...this.state.form.parts[name].list];
        list[i] = value;
        this.setPart(name, "list", list);
    }

    /** Enter starts the next point; Backspace in an empty one removes it. */
    onPointKey(ev, name, i) {
        const list = this.state.form.parts[name].list;
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.setPart(name, "list", [...list.slice(0, i + 1), "", ...list.slice(i + 1)]);
            this.focusPoint(name, i + 1);
        } else if (ev.key === "Backspace" && !ev.target.value && list.length > 1) {
            ev.preventDefault();
            this.setPart(name, "list", list.filter((_, j) => j !== i));
            this.focusPoint(name, Math.max(0, i - 1));
        }
    }

    addPoint(name) {
        const list = this.state.form.parts[name].list;
        this.setPart(name, "list", [...list, ""]);
        this.focusPoint(name, list.length);
    }

    removePoint(name, i) {
        const list = this.state.form.parts[name].list;
        this.setPart(name, "list", list.length > 1 ? list.filter((_, j) => j !== i) : [""]);
    }

    /** Focused once the render that draws it has happened (see onPatched in
     *  setup) - a timer alone fires before OWL has drawn the new box. */
    focusPoint(name, i) {
        this.pendingFocus = { name, i };
    }

    // ------------------------------------------- "How shoppers see it" panel

    /** Light a box on the panel. Hovering its eye or clicking into it does
     *  this; it stays lit until another box takes over, as on the web admin. */
    setFocus(name) {
        this.state.focus = name;
    }

    /** Point at a box from its ⓘ: light it, and pulse its spot. */
    point(name) {
        this.setFocus(name);
        this.state.beat = null;
        requestAnimationFrame(() => {
            this.state.beat = name;
        });
    }

    hasPreview(name) {
        return !!PREVIEW[name];
    }

    /** What the panel prints for a box: what is typed, or the grey sample. */
    pv(name) {
        const typed = this.state.form.values[name];
        const has = typed !== undefined && typed !== null && typed !== "" && typed !== 0;
        return { text: has ? String(typed) : (PREVIEW[name]?.sample || ""), sample: !has };
    }

    pvLines(name) {
        return this.pv(name).text.split("\n").filter(Boolean);
    }

    /** Classes for a spot on the panel: grey when only a sample, outlined
     *  when it is the box being looked at. */
    cls(name) {
        return (this.pv(name).sample ? " pdk-sample" : "") + this.lit(name);
    }

    lit(name) {
        if (this.state.focus !== name) {
            return "";
        }
        return " pdk-lit" + (this.state.beat === name ? " pdk-beat" : "");
    }

    /** A spot is drawn once it has a value - or while it is being looked at,
     *  with its sample, so the outline always has something to sit on. */
    show(name) {
        return !this.pv(name).sample || this.state.focus === name;
    }

    /** The line under the panel. */
    get panelNote() {
        const f = this.state.focus;
        const box = f && this.state.form.boxes[f];
        if (f && PREVIEW[f]?.where === "note") {
            return { label: box ? box.label : f, text: PREVIEW[f].note };
        }
        if (box) {
            return { outlined: true, label: "Outlined", text: box.label };
        }
        return null;
    }

    /** A box shoppers never see has no spot to pulse, so its note line does. */
    get noteBeats() {
        const f = this.state.focus;
        return !!f && this.state.beat === f && PREVIEW[f]?.where === "note";
    }

    /** The page rows the panel's "Product information" table can show. */
    get infoRows() {
        return [["mart_in_the_box", _t("In the box")], ["mart_material", _t("Material")],
            ["mart_item_height", _t("Item height")], ["mart_item_length", _t("Item length")],
            ["mart_item_width", _t("Item width")], ["weight", _t("Net weight")]]
            .filter(([k]) => this.state.form.boxes[k] && this.show(k));
    }

    isMoney(box) {
        return ["list_price", "compare_list_price", "standard_price"].includes(box.name);
    }

    get currencySymbol() {
        return this.props.currency?.symbol || "";
    }

    get chosenCount() {
        return (this.state.form.values.public_categ_ids || []).length;
    }

    /** Digits only (the barcode): 0-9 as typed or pasted, nothing else, and
     *  leading zeros kept - which a number box would drop. */
    onDigits(ev, name, max) {
        let v = ev.target.value.replace(/\D/g, "");
        if (max) {
            v = v.slice(0, max);
        }
        ev.target.value = v;
        this.setField(name, v);
    }

    isDigits(value) {
        return !value || /^\d+$/.test(String(value));
    }

    money(amount) {
        return money(amount, this.props.currency);
    }

    // -------------------------------------------------------- photographs

    /** One box takes one picture or many. With no card photograph yet the
     *  first one chosen becomes it, and the rest join the gallery. */
    async onPhotos(ev) {
        const files = [...(ev.target.files || [])];
        ev.target.value = "";
        return this.addFiles(files);
    }

    onDragOver(ev) {
        ev.preventDefault();
        this.state.dragging = true;
    }

    onDragLeave(ev) {
        if (!ev.currentTarget.contains(ev.relatedTarget)) {
            this.state.dragging = false;
        }
    }

    onDrop(ev) {
        ev.preventDefault();
        this.state.dragging = false;
        return this.addFiles([...(ev.dataTransfer?.files || [])]);
    }

    /** Pictures from the + tile or dropped on the section; anything that is
     *  not a picture is left out. */
    async addFiles(all) {
        const files = all.filter((f) => (f.type || "").startsWith("image/"));
        if (!files.length) {
            return;
        }
        const read = [];
        for (const file of files) {
            const url = await getDataURLFromFile(file);
            read.push({ name: file.name, data: url.split(",")[1], url });
        }
        const form = this.state.form;
        this.markDirty();
        if (this.props.photoHost) {
            return this.props.photoHost.add(read);
        }
        for (const ph of read) {
            if (!form.photo) {
                form.values.image_1920 = ph.data;
                form.photo = ph.url;
            } else {
                form.add.push(ph);
            }
        }
    }

    /** Every photograph in the order the shopper swipes them: the card's
     *  first, then the gallery. In the form each gallery item may carry
     *  `pending` - added since the last Save. */
    get photoList() {
        const form = this.state.form;
        const list = [];
        if (form.photo) {
            list.push({ kind: "main", url: form.photo });
        }
        // The old card picture, moving to the gallery once saved (desk).
        if (form.demote && form.demotedUrl) {
            list.push({ kind: "demoted", url: form.demotedUrl });
        }
        for (const ph of form.photos) {
            list.push({ kind: ph.pending ? "new" : "saved", url: ph.url, photo: ph });
        }
        for (const ph of form.add) {
            list.push({ kind: "new", url: ph.url, photo: ph });
        }
        return list;
    }

    /** A saved photograph is marked for removal rather than removed, so
     *  nothing is lost until Save; one added this visit simply leaves. */
    dropPhoto(item) {
        const form = this.state.form;
        this.markDirty();
        if (this.props.photoHost) {
            this.props.photoHost.remove(item);
        } else if (item.kind === "main") {
            // '' rather than leaving it out: the server reads the difference
            // as "take it away" versus "was not mentioned".
            form.values.image_1920 = "";
            form.photo = "";
            if (form.promoted) {
                // A gallery picture picked for the card, then removed.
                form.remove.push(form.promoted.id);
                form.promoted = null;
            }
        } else if (item.kind === "demoted") {
            // The old card picture, dropped instead of kept in the gallery.
            form.demote = false;
            form.demotedUrl = "";
        } else if (item.kind === "saved") {
            form.remove.push(item.photo.id);
            form.photos = form.photos.filter((p) => p.id !== item.photo.id);
        } else {
            form.add = form.add.filter((p) => p !== item.photo);
        }
        const left = this.photoList.length;
        if (!left) {
            this.state.viewing = null;
        } else if (this.state.viewing >= left) {
            this.state.viewing = left - 1;
        }
    }

    // Ticked photographs, kept by kind and address rather than position, so
    // removing one does not tick its neighbour.

    photoKey(ph) {
        return `${ph.kind}:${ph.url.slice(-48)}`;
    }

    isPicked(ph) {
        return this.state.picked.includes(this.photoKey(ph));
    }

    togglePick(ph) {
        const key = this.photoKey(ph);
        this.state.picked = this.isPicked(ph)
            ? this.state.picked.filter((k) => k !== key)
            : [...this.state.picked, key];
    }

    pickAll() {
        this.state.picked = this.photoList.map((ph) => this.photoKey(ph));
    }

    clearPicked() {
        this.state.picked = [];
    }

    /** Remove every ticked photograph. Collected first: removing one changes
     *  the list the rest are found in. */
    async dropPicked() {
        const items = this.photoList.filter((ph) => this.isPicked(ph));
        this.state.picked = [];
        for (const item of items) {
            await this.dropPhoto(item);
        }
        this.state.viewing = null;
    }

    /** "Use on the card": this picture goes on the card and the current card
     *  picture steps back into the gallery. Nothing is lost, and nothing is
     *  written until Save. */
    useOnCard(item) {
        const f = this.state.form;
        if (item.kind === "main") {
            return;
        }
        this.markDirty();
        this.state.viewing = 0;
        if (this.props.photoHost) {
            return this.props.photoHost.useOnCard(item);
        }
        if (f.photo) {
            if (f.promoted) {
                f.photos = [f.promoted, ...f.photos];
            } else if (f.values.image_1920) {
                f.add = [{ name: "photo", data: f.values.image_1920, url: f.photo }, ...f.add];
            } else if (!f.demote) {
                f.demote = true;
                f.demotedUrl = f.photo;
            }
        }
        f.promoted = null;
        if (item.kind === "new") {
            f.values.image_1920 = item.photo.data;
            f.add = f.add.filter((p) => p !== item.photo);
        } else if (item.kind === "saved") {
            f.promoted = item.photo;
            f.photos = f.photos.filter((p) => p.id !== item.photo.id);
            delete f.values.image_1920;
        } else if (item.kind === "demoted") {
            f.demote = false;
            f.demotedUrl = "";
            delete f.values.image_1920;
        }
        f.photo = item.url;
    }

    // ------------------------------------------------------ the photo popup

    viewPhoto(index) {
        this.state.viewing = index;
    }

    closePhoto() {
        this.state.viewing = null;
    }

    stepPhoto(by) {
        const n = this.photoList.length;
        if (n) {
            this.state.viewing = (this.state.viewing + by + n) % n;
        }
    }

    get viewed() {
        return this.state.viewing === null ? null : this.photoList[this.state.viewing] || null;
    }

    onPopupKey(ev) {
        if (ev.key === "Escape") {
            this.closePhoto();
        } else if (ev.key === "ArrowRight") {
            this.stepPhoto(1);
        } else if (ev.key === "ArrowLeft") {
            this.stepPhoto(-1);
        }
    }
}
