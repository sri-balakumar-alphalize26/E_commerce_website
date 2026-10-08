/**
 * The Products desk's editor, inside Odoo's own product form.
 *
 * Inventory > Products > a product > 369 Mart tab draws exactly what the desk
 * draws - the same boxes, units, dropdowns, feature points and "how it looks"
 * cards - because it is the same component. What differs is where changes go:
 * here every change is written to the form's record, so Odoo's own Save and
 * Discard (and its unsaved-changes dot) are the only buttons, and nothing is
 * written until somebody presses Save.
 *
 * Which boxes to draw, and their labels and units, still come from
 * `mart369_desk_form`; the values come from the record, so an unsaved edit
 * made elsewhere on the form is what the editor starts from.
 *
 * Every field it writes is on the view (invisibly, in the tab) - the record
 * only saves fields the view knows about.
 */
import { Component, markup, useState } from "@odoo/owl";
import { useRecordObserver } from "@web/model/relational_model/utils";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { ProductEditor } from "./product_editor";

const IMAGE = "image_1920";

/** Where the Photographs box keeps the extra pictures. The product's gallery
 *  is shared by every variant, so on a variant's own form (Product Variants)
 *  they go to that variant's own media: Odoo's Extra Variant Media
 *  (website_sale), which the website reads for that colour only
 *  (mart369 `_mart369_variant_media`). The senior's Variant images tab
 *  (sales_automation_confirm) is the fallback on a form without it, and the
 *  product's gallery when there is neither, as before. */
const TEMPLATE_GALLERY = { field: "product_template_image_ids", model: "product.image", image: "image_1920", thumb: "image_256" };
const VARIANT_MEDIA = { field: "product_variant_image_ids", model: "product.image", image: "image_1920", thumb: "image_256" };
const VARIANT_GALLERY = { field: "sa_variant_picture_ids", model: "sa.confirm.picture", image: "image", thumb: "image/256x256" };

function galleryOf(record) {
    if (record.resModel === "product.product") {
        for (const gallery of [VARIANT_MEDIA, VARIANT_GALLERY]) {
            if (record.data[gallery.field]) {
                return gallery;
            }
        }
    }
    return TEMPLATE_GALLERY;
}

/** A binary field read into a form holds its size ("12.3 Kb"), not the
 *  picture, until somebody changes it - then it holds the base64 data. */
function isData(value) {
    return typeof value === "string" && value.length > 200;
}

export class ProductEditorWidget extends Component {
    static template = "mart369_product.ProductEditorWidget";
    static components = { ProductEditor };
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ data: null, key: 0, error: "" });
        // Re-built from the record whenever it comes back clean - after a Save,
        // a Discard, or moving to another product - so the boxes never show a
        // value the record no longer has.
        this.wasDirty = false;
        this.resId = this.props.record.resId;

        this.photoHost = {
            add: (photos) => this.addPhotos(photos),
            remove: (item) => this.removePhoto(item),
            useOnCard: (item) => this.useOnCard(item),
        };

        // First call builds; later calls fire whenever the record changes.
        this.built = false;
        useRecordObserver(async (rec) => {
            const dirty = rec.dirty;
            const photos = this.photosOf(rec); // read, so photo changes are watched
            const moved = rec.resId !== this.resId;
            const cameBackClean = this.wasDirty && !dirty;
            this.wasDirty = dirty;
            if (!this.built || moved || cameBackClean) {
                this.built = true;
                this.resId = rec.resId;
                await this.build(rec);
            } else if (this.state.data) {
                // The gallery may have changed under us (a photo added,
                // removed or swapped); the boxes are the editor's own.
                this.state.data = { ...this.state.data, ...photos };
            }
        });
    }

    get record() {
        return this.props.record;
    }

    /** The boxes from the server, the values from the record. */
    async build(record = this.record) {
        try {
            // On a variant's form the record is the variant; the boxes are its product's.
            const productId = record.resModel === "product.product"
                ? record.data.product_tmpl_id?.id || null
                : record.resId || null;
            const form = await this.orm.call("product.template", "mart369_desk_form", [], {
                product_id: productId,
            });
            const values = {};
            for (const g of form.groups) {
                for (const b of g.boxes) {
                    values[b.name] = this.valueOf(record, b.name);
                }
            }
            this.state.data = { ...form, values, ...this.photosOf(record) };
            this.state.key++;
            this.state.error = "";
        } catch (err) {
            this.state.error = err?.data?.message || err?.message || String(err);
        }
    }

    valueOf(record, name) {
        const field = record.fields[name];
        const raw = record.data[name];
        if (!field) {
            return "";
        }
        if (field.type === "many2many") {
            return raw ? raw.currentIds : [];
        }
        if (field.type === "float" || field.type === "monetary") {
            return raw || "";
        }
        if (field.type === "integer") {
            return raw || 0;
        }
        return raw || "";
    }

    /** The card picture and the gallery, as the editor draws them. */
    photosOf(record) {
        const main = record.data[IMAGE];
        let photo = "";
        if (isData(main)) {
            photo = "data:image/png;base64," + main;
        } else if (main && record.resId) {
            photo = `/web/image/${record.resModel}/${record.resId}/image_256?unique=${encodeURIComponent(record.data.write_date || "")}`;
        }
        const gallery = galleryOf(record);
        const list = record.data[gallery.field];
        const photos = (list ? list.records : []).map((rec) => ({
            id: rec.resId || rec.id,
            rec,
            pending: !rec.resId,
            url: isData(rec.data[gallery.image])
                ? "data:image/png;base64," + rec.data[gallery.image]
                : `/web/image/${gallery.model}/${rec.resId}/${gallery.thumb}`,
        }));
        return { photo, photos };
    }

    // --------------------------------------------------------------- values

    /** One box changed: the matching column on the record. */
    async onValue(name, value) {
        const field = this.record.fields[name];
        if (!field) {
            return;
        }
        if (field.type === "many2many") {
            const list = this.record.data[name];
            const now = new Set(list.currentIds);
            const want = new Set(value || []);
            await list.addAndRemove({
                add: [...want].filter((id) => !now.has(id)),
                remove: [...now].filter((id) => !want.has(id)),
            });
            return;
        }
        let v = value;
        if (field.type === "float" || field.type === "monetary") {
            v = Number(value) || 0;
        } else if (field.type === "integer") {
            v = parseInt(value, 10) || 0;
        } else if (field.type === "html") {
            // An HTML field holds markup, as Odoo's own editor writes it.
            v = value ? markup(value) : false;
        } else if (v === "") {
            v = false;
        }
        await this.record.update({ [name]: v });
    }

    // --------------------------------------------------------- photographs

    async addPhotos(photos) {
        for (const ph of photos) {
            if (!this.record.data[IMAGE]) {
                await this.record.update({ [IMAGE]: ph.data });
                continue;
            }
            const gallery = galleryOf(this.record);
            const rec = await this.record.data[gallery.field].addNewRecord({ position: "bottom" });
            await rec.update({ name: ph.name || this.record.data.name || "Photograph", [gallery.image]: ph.data });
        }
        this.refreshPhotos();
    }

    async removePhoto(item) {
        if (item.kind === "main") {
            await this.record.update({ [IMAGE]: false });
        } else {
            await this.record.data[galleryOf(this.record).field].delete(item.photo.rec);
        }
        this.refreshPhotos();
    }

    /** Swap in place: the chosen gallery picture goes on the card and the
     *  card picture takes its place in the gallery. Nothing is lost. */
    async useOnCard(item) {
        const rec = item.photo.rec;
        const gallery = galleryOf(this.record);
        const galleryData = isData(rec.data[gallery.image])
            ? rec.data[gallery.image]
            : await this.readImage(gallery.model, rec.resId, gallery.image);
        const mainNow = this.record.data[IMAGE];
        const mainData = isData(mainNow)
            ? mainNow
            : mainNow && this.record.resId
                ? await this.readImage(this.record.resModel, this.record.resId)
                : false;
        if (mainData) {
            await rec.update({ [gallery.image]: mainData });
        } else {
            await this.record.data[gallery.field].delete(rec);
        }
        await this.record.update({ [IMAGE]: galleryData });
        this.refreshPhotos();
    }

    async readImage(model, id, field = "image_1920") {
        const [row] = await this.orm.read(model, [id], [field], {
            context: { bin_size: false },
        });
        return row ? row[field] : false;
    }

    refreshPhotos() {
        if (this.state.data) {
            this.state.data = { ...this.state.data, ...this.photosOf(this.record) };
        }
    }
}

registry.category("view_widgets").add("mart369_product_editor", {
    component: ProductEditorWidget,
});
