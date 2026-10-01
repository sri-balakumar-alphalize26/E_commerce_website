/**
 * Attributes & Variants, on the Products desk.
 *
 * The twin of the web console's VariantsBlock (components/admin/ProductEditor.jsx),
 * drawn with the same classes (editor_look.scss is generated from its CSS), so
 * the two Edit product screens offer the same thing: the choices customers make -
 * Brand, Processor, RAM, Colour - with the values this product offers and what
 * each adds to the price, then every variant's own image, photos, specs and
 * stock. The same records Odoo's Attributes & Variants tab and Product Variants
 * form edit, so the website and the WhatsApp page show what is saved here.
 *
 * Nothing is written until the desk's Save: changes sit in `vx.per[id]`, and the
 * lines are sent whole once touched (`variantsBody`, used by product_desk.js).
 */
import { Component, useState } from "@odoo/owl";
import { getDataURLFromFile } from "@web/core/utils/urls";
import { _t } from "@web/core/l10n/translation";
import { Icon } from "@mart369/ui/icon";
import { Pick } from "@mart369/ui/pick";

/** The Variants block's working copy, from a `mart369_desk_form` answer. */
export function vxFrom(variants) {
    if (!variants) {
        return null;
    }
    return {
        attributes: variants.attributes || [],
        lines: (variants.lines || []).map((l) => ({
            ...l, value_ids: [...l.value_ids], new_values: [], extras: { ...(l.extras || {}) },
        })),
        rows: variants.rows || [],
        media: !!variants.media,
        warning: variants.warning || "",
        per: {},
        linesDirty: false,
    };
}

/** What the desk sends: every changed variant, and the lines only when they
 *  were touched (writing them can make or retire variants). */
export function variantsBody(vx) {
    if (!vx) {
        return undefined;
    }
    const per = {};
    for (const [id, p] of Object.entries(vx.per)) {
        const out = {};
        if (p.image !== undefined) {
            out.image = p.image;
        }
        if (p.onHand !== undefined && p.onHand !== "") {
            out.onHand = p.onHand;
        }
        if (p.pictures && (p.pictures.add.length || p.pictures.remove.length || p.pictures.order.length)) {
            out.pictures = {
                add: p.pictures.add.map(({ name, data }) => ({ name, data })),
                remove: p.pictures.remove,
                order: p.pictures.order,
            };
        }
        if (p.specs) {
            out.specs = p.specs.filter((s) => (s.name || "").trim())
                .map(({ id, name, value }) => ({ id, name, value }));
            // Only these rows go: one added meanwhile in Odoo's own Product
            // Variants form is on neither list and stays (variant_desk.py).
            out.specs_removed = [
                ...p.specsRemoved,
                ...p.specs.filter((s) => s.id && !(s.name || "").trim()).map((s) => s.id),
            ];
        }
        if (p.fill) {
            out.fill = true;
        }
        per[id] = out;
    }
    return { per, ...(vx.linesDirty ? { lines: vx.lines } : {}) };
}

/** Digits and one point, plus a minus in front: an extra can take money off. */
function signedNumber(raw) {
    const minus = String(raw).trim().startsWith("-");
    let v = String(raw).replace(/[^\d.]/g, "");
    const [a, ...rest] = v.split(".");
    v = rest.length ? `${a}.${rest.join("")}` : a;
    return minus ? `-${v}` : v;
}

function plainNumber(raw) {
    let v = String(raw).replace(/[^\d.]/g, "");
    const [a, ...rest] = v.split(".");
    return rest.length ? `${a}.${rest.join("")}` : a;
}

export class VariantsBlock extends Component {
    static template = "mart369_product.VariantsBlock";
    static components = { Icon, Pick };
    static props = {
        // The editor's `form.vx` (see vxFrom), changed in place.
        vx: Object,
        // Prints a price the way the shop does.
        money: Function,
        // Called after every change, so the desk knows there is something to save.
        onChange: Function,
    };

    setup() {
        this.vx = useState(this.props.vx);
        this.ui = useState({
            open: null,      // the variant row unfolded
            adding: "",      // the attribute being added
            typed: {},       // new value boxes, per attribute
        });
    }

    changed() {
        this.props.onChange();
    }

    // ------------------------------------------------------- the attributes

    attribute(id) {
        return this.vx.attributes.find((a) => a.id === id);
    }

    get addOptions() {
        const used = new Set(this.vx.lines.map((l) => l.attribute_id));
        return [["", _t("+ Add an attribute (Brand, RAM, Colour…)")],
            ...this.vx.attributes.filter((a) => !used.has(a.id)).map((a) => [String(a.id), a.name])];
    }

    /** The values a line offers right now: chosen ones, then new ones typed. */
    chosen(line) {
        const a = this.attribute(line.attribute_id);
        return [
            ...(a ? a.values.filter((v) => line.value_ids.includes(v.id)) : []).map((v) => ({
                key: String(v.id), name: v.name, extra: v.extra,
            })),
            ...line.new_values.map((n) => ({ key: n, name: n, isNew: true })),
        ];
    }

    touchLines() {
        this.vx.linesDirty = true;
        this.changed();
    }

    toggleValue(line, id) {
        line.value_ids = line.value_ids.includes(id)
            ? line.value_ids.filter((v) => v !== id)
            : [...line.value_ids, id];
        this.touchLines();
    }

    setTyped(aid, value) {
        this.ui.typed[aid] = value;
    }

    onTypedKey(ev, line) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.addTyped(line);
        }
    }

    /** A value typed in: an existing one is ticked, a new one is added to
     *  the attribute when saved. */
    addTyped(line) {
        const aid = line.attribute_id;
        const name = (this.ui.typed[aid] || "").trim().replace(/\s+/g, " ");
        if (!name) {
            return;
        }
        const known = this.attribute(aid)?.values.find((v) => v.name.toLowerCase() === name.toLowerCase());
        if (known) {
            if (!line.value_ids.includes(known.id)) {
                line.value_ids = [...line.value_ids, known.id];
            }
        } else if (!line.new_values.some((n) => n.toLowerCase() === name.toLowerCase())) {
            line.new_values = [...line.new_values, name];
        }
        this.ui.typed[aid] = "";
        this.touchLines();
    }

    extraOf(line, key) {
        const v = line.extras[key];
        return v === undefined || v === null ? "" : String(v);
    }

    onExtra(ev, line, key) {
        const v = signedNumber(ev.target.value);
        ev.target.value = v;
        line.extras[key] = v;
        this.touchLines();
    }

    dropLine(index) {
        this.vx.lines.splice(index, 1);
        this.touchLines();
    }

    addLine(aid) {
        if (!aid) {
            return;
        }
        this.vx.lines.push({ attribute_id: Number(aid), value_ids: [], new_values: [], extras: {} });
        this.ui.adding = "";
        this.touchLines();
    }

    // --------------------------------------------------------- the variants

    toggleRow(id) {
        this.ui.open = this.ui.open === id ? null : id;
    }

    /** One variant's pending changes, started from what is saved. */
    pending(row) {
        const key = String(row.id);
        if (!this.vx.per[key]) {
            this.vx.per[key] = {
                pictures: { add: [], remove: [], order: (row.pictures || []).map((p) => p.id) },
                specs: (row.specs || []).map((s) => ({ ...s })),
                specsRemoved: [],
            };
        }
        return this.vx.per[key];
    }

    /** What a row shows: its pending changes over what is saved. */
    view(row) {
        const p = this.vx.per[String(row.id)] || {};
        const order = p.pictures?.order || (row.pictures || []).map((x) => x.id);
        const saved = order.map((pid) => (row.pictures || []).find((x) => x.id === pid)).filter(Boolean);
        return {
            image: p.image === undefined ? row.image : (p.image ? p.imageUrl : ""),
            onHand: p.onHand === undefined ? (row.onHand ?? "") : p.onHand,
            pictures: [
                ...saved.map((x) => ({ ...x, kind: "saved", key: "s" + x.id })),
                ...(p.pictures?.add || []).map((x, i) => ({ ...x, kind: "new", i, key: "n" + i })),
            ],
            specs: p.specs || row.specs || [],
            fill: !!p.fill,
        };
    }

    async pickImage(ev, row) {
        const file = [...(ev.target.files || [])].find((f) => (f.type || "").startsWith("image/"));
        ev.target.value = "";
        if (!file) {
            return;
        }
        const url = await getDataURLFromFile(file);
        const p = this.pending(row);
        p.image = url.split(",")[1];
        p.imageUrl = url;
        this.changed();
    }

    dropImage(row) {
        const p = this.pending(row);
        p.image = "";
        p.imageUrl = "";
        this.changed();
    }

    async addPictures(ev, row) {
        const files = [...(ev.target.files || [])].filter((f) => (f.type || "").startsWith("image/"));
        ev.target.value = "";
        const read = [];
        for (const file of files) {
            const url = await getDataURLFromFile(file);
            read.push({ name: file.name, data: url.split(",")[1], url });
        }
        if (!read.length) {
            return;
        }
        const p = this.pending(row);
        p.pictures.add = [...p.pictures.add, ...read];
        this.changed();
    }

    dropPicture(row, pic) {
        const p = this.pending(row);
        if (pic.kind === "new") {
            p.pictures.add = p.pictures.add.filter((_, i) => i !== pic.i);
        } else {
            p.pictures.remove = [...p.pictures.remove, pic.id];
            p.pictures.order = p.pictures.order.filter((x) => x !== pic.id);
        }
        this.changed();
    }

    movePicture(row, pid, by) {
        const p = this.pending(row);
        const order = [...p.pictures.order];
        const i = order.indexOf(pid);
        const j = i + by;
        if (i < 0 || j < 0 || j >= order.length) {
            return;
        }
        [order[i], order[j]] = [order[j], order[i]];
        p.pictures.order = order;
        this.changed();
    }

    setSpec(row, i, key, value) {
        this.pending(row).specs[i][key] = value;
        this.changed();
    }

    moveSpec(row, i, by) {
        const p = this.pending(row);
        const list = [...p.specs];
        const j = i + by;
        if (j < 0 || j >= list.length) {
            return;
        }
        [list[i], list[j]] = [list[j], list[i]];
        p.specs = list;
        this.changed();
    }

    dropSpec(row, i) {
        const p = this.pending(row);
        const gone = p.specs[i];
        if (gone.id) {
            p.specsRemoved = [...p.specsRemoved, gone.id];
        }
        p.specs = p.specs.filter((_, k) => k !== i);
        this.changed();
    }

    addSpec(row) {
        const p = this.pending(row);
        p.specs = [...p.specs, { name: "", value: "" }];
        this.changed();
    }

    fillSpecs(row) {
        this.pending(row).fill = true;
        this.changed();
    }

    onHand(ev, row) {
        const v = plainNumber(ev.target.value);
        ev.target.value = v;
        this.pending(row).onHand = v;
        this.changed();
    }
}
