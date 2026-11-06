/**
 * The Products desk's editor, inside 369ai's own product form.
 *
 * Inventory > Products > a product > 369 Mart tab draws exactly what the desk
 * draws - the same boxes, units, dropdowns, feature points and "how it looks"
 * cards - because it is the same component. What differs is where changes go:
 * here every change is written to the form's record, so 369ai's own Save and
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
import { Component, markup, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useRecordObserver } from "@web/model/relational_model/utils";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { ProductEditor } from "./product_editor";

const IMAGE = "image_1920";

/** Where the Photographs box keeps the extra pictures. The product's gallery
 *  is shared by every variant, so on a variant's own form (Product Variants)
 *  they go to that variant's own media: 369ai's Extra Variant Media
 *  (website_sale), which the website reads for that colour only
 *  (mart369 `_mart369_variant_media`). The senior's Variant images tab
 *  (sales_automation_confirm) is the fallback on a form without it, and the
 *  product's gallery when there is neither, as before. */
const TEMPLATE_GALLERY = { field: "product_template_image_ids", model: "product.image", image: "image_1920", thumb: "image_256" };
const VARIANT_MEDIA = { field: "product_variant_image_ids", model: "product.image", image: "image_1920", thumb: "image_256" };
const VARIANT_GALLERY = { field: "sa_variant_picture_ids", model: "sa.confirm.picture", image: "image", thumb: "image/256x256" };

/** The field holding the card picture. A variant's own form shows that variant's
 *  own picture, not the product's it falls back to, when the form carries it
 *  (mart369_whatsapp_bridge, Variant images tab), so a red phone's box never
 *  lists the product's photo. */
function imageField(record) {
    return record.resModel === "product.product" && "image_variant_1920" in record.activeFields
        ? "image_variant_1920"
        : IMAGE;
}

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

/** An Image Server link pasted but not saved yet is a small marker on the record
 *  (ai369_image_server): base64 of "<!--imgsrv-linked:URL-->". The server swaps
 *  it for the linked picture on Save; until then it is drawn from the link. */
const LINK_MARK = btoa("<!--imgsrv-linked:").slice(0, 16);
const linkPreviews = new Map();

/** A binary field read into a form holds its size ("12.3 Kb"), not the
 *  picture, until somebody changes it - then it holds the base64 data or a
 *  link marker. */
function isData(value) {
    return typeof value === "string" && (value.length > 200 || value.startsWith(LINK_MARK));
}

/** The address to draw a picture still on the record, not saved yet. */
function unsavedUrl(value) {
    return value.startsWith(LINK_MARK)
        ? linkPreviews.get(value) || "/web/static/img/placeholder.png"
        : "data:image/png;base64," + value;
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

        this.useFullWidth();

        this.photoHost = {
            add: (photos) => this.addPhotos(photos),
            addLinks: (urls, onBad) => this.addLinks(urls, onBad),
            remove: (item) => this.removePhoto(item),
            useOnCard: (item) => this.useOnCard(item),
            move: (from, to) => this.movePhoto(from, to),
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

    /** On a wide screen 369ai puts the log (chatter) in a column beside the
     *  whole form, which squeezed this editor - its details and its "How
     *  shoppers see it" preview - into the left part, over an empty strip of
     *  log. Here the log stops just above 369 MART and the editor runs to the
     *  right edge of the page: details from the left to the centre, the
     *  preview from the centre to the right.
     *
     *  Measured rather than styled: the editor sits deep inside the form's
     *  column, and how far it has to reach depends on the window. Narrower
     *  windows put the log underneath and need nothing. */
    useFullWidth() {
        this.root = useRef("root");
        let chatter = null;
        const reset = (el) => {
            el?.classList.remove("o_mart369_breakout");
            el?.style.removeProperty("--mart-breakout");
            if (chatter) {
                chatter.style.removeProperty("max-height");
                chatter.style.removeProperty("overflow");
                chatter = null;
            }
        };
        const layout = () => {
            const el = this.root.el;
            const column = el?.parentElement;
            const renderer = el?.closest(".o_form_renderer");
            const aside = renderer?.querySelector(":scope > .o-mail-Form-chatter.o-aside");
            if (!el || !column || !aside || !el.offsetParent) {
                return reset(el);
            }
            // The column's edge, not the editor's: the editor's own edge moves
            // once it reaches out, the column's does not.
            const box = renderer.getBoundingClientRect();
            const reach = Math.max(0, box.right - column.getBoundingClientRect().right - 16);
            el.style.setProperty("--mart-breakout", `${reach}px`);
            el.classList.add("o_mart369_breakout");
            const stop = Math.max(160, el.getBoundingClientRect().top - box.top - 8);
            chatter = aside;
            aside.style.maxHeight = `${stop}px`;
            aside.style.overflow = "auto";
        };
        let observer = null;
        let frame = 0;
        const later = () => {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(layout);
        };
        onMounted(() => {
            layout();
            window.addEventListener("resize", later);
            if (window.ResizeObserver) {
                // Also fires when the General Information tab is shown or hidden.
                observer = new ResizeObserver(later);
                observer.observe(this.root.el);
                const renderer = this.root.el.closest(".o_form_renderer");
                if (renderer) {
                    observer.observe(renderer);
                }
            }
        });
        onWillUnmount(() => {
            cancelAnimationFrame(frame);
            window.removeEventListener("resize", later);
            observer?.disconnect();
            reset(this.root.el);
        });
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
        const main = record.data[imageField(record)];
        let photo = "";
        if (isData(main)) {
            photo = unsavedUrl(main);
        } else if (main && record.resId) {
            photo = `/web/image/${record.resModel}/${record.resId}/image_256?unique=${encodeURIComponent(record.data.write_date || "")}`;
        }
        const gallery = galleryOf(record);
        const list = record.data[gallery.field];
        const recs = list ? [...list.records].map((rec, i) => ({ rec, i }))
            .sort((a, b) => ((a.rec.data.sequence ?? 0) - (b.rec.data.sequence ?? 0)) || a.i - b.i)
            .map(({ rec }) => rec) : [];
        const photos = recs.map((rec) => ({
            id: rec.resId || rec.id,
            rec,
            pending: !rec.resId,
            url: isData(rec.data[gallery.image])
                ? unsavedUrl(rec.data[gallery.image])
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
            // An HTML field holds markup, as 369ai's own editor writes it.
            v = value ? markup(value) : false;
        } else if (v === "") {
            v = false;
        }
        await this.record.update({ [name]: v });
    }

    // --------------------------------------------------------- photographs

    async addPhotos(photos) {
        for (const ph of photos) {
            if (!this.record.data[imageField(this.record)]) {
                await this.record.update({ [imageField(this.record)]: ph.data });
                continue;
            }
            const gallery = galleryOf(this.record);
            const rec = await this.record.data[gallery.field].addNewRecord({ position: "bottom" });
            await rec.update({ name: ph.name || this.record.data.name || "Photograph", [gallery.image]: ph.data });
        }
        this.refreshPhotos();
    }

    /** Pictures already on the Image Server, by their links: they show at
     *  once, from the links, like any other photographs, and each link is
     *  checked behind them. A wrong one is taken out again and named to `onBad`.
     *  A check that gets no answer keeps the picture; Save checks it again. */
    async addLinks(urls, onBad) {
        const bad = [];
        const added = [];
        for (const url of urls) {
            try {
                const data = btoa(`<!--imgsrv-linked:${url}-->`);
                linkPreviews.set(data, url);
                added.push({ url, data });
            } catch {
                bad.push(url); // not plain characters, so it cannot be a link of ours
            }
        }
        await this.addPhotos(added.map(({ data }) => ({ data })));
        const answers = await Promise.all(added.map(({ url }) =>
            rpc("/ai369_image_server/check_link", { url }).catch(() => ({ ok: true }))));
        for (const [i, answer] of answers.entries()) {
            if (!answer.ok) {
                await this.removeLink(added[i].data);
                bad.push(added[i].url);
            }
        }
        if (bad.length) {
            await this.keepFirstOnCard();
            this.refreshPhotos();
            onBad(bad);
        }
    }

    /** Take a pasted link back out, wherever it is by now. */
    async removeLink(data) {
        if (this.record.data[imageField(this.record)] === data) {
            await this.record.update({ [imageField(this.record)]: false });
            return;
        }
        const gallery = galleryOf(this.record);
        const rec = this.galleryRecords(gallery).find((r) => r.data[gallery.image] === data);
        if (rec) {
            await this.record.data[gallery.field].delete(rec);
        }
    }

    /** The first link pasted went on the card; when that one was wrong, the
     *  next picture still waiting to be saved takes its place. */
    async keepFirstOnCard() {
        if (this.record.data[imageField(this.record)]) {
            return;
        }
        const gallery = galleryOf(this.record);
        const first = this.galleryRecords(gallery)[0];
        if (first && isData(first.data[gallery.image])) {
            const data = first.data[gallery.image];
            await this.record.data[gallery.field].delete(first);
            await this.record.update({ [imageField(this.record)]: data });
        }
    }

    async removePhoto(item) {
        if (item.kind === "main") {
            await this.record.update({ [imageField(this.record)]: false });
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
            : await this.readPhoto(gallery.model, rec.resId, gallery.image);
        const mainNow = this.record.data[imageField(this.record)];
        const mainData = isData(mainNow)
            ? mainNow
            : mainNow && this.record.resId
                ? await this.readPhoto(this.record.resModel, this.record.resId, imageField(this.record))
                : false;
        if (mainData) {
            await rec.update({ [gallery.image]: mainData });
        } else {
            await this.record.data[gallery.field].delete(rec);
        }
        await this.record.update({ [imageField(this.record)]: galleryData });
        this.refreshPhotos();
    }

    /** A photograph dragged from one place to another, in the order the
     *  editor shows them: the card picture first, then the gallery. Dragged
     *  to the front it becomes the card picture, and the old card picture
     *  takes its place in the gallery - the same swap as "Use on the card".
     *  The gallery's order is each picture's `sequence`; nothing is written
     *  until 369ai's Save. */
    async movePhoto(from, to) {
        const gallery = galleryOf(this.record);
        const recs = this.galleryRecords(gallery);
        const hasMain = !!this.record.data[imageField(this.record)];
        const items = [...(hasMain ? ["main"] : []), ...recs];
        if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) {
            return;
        }
        const [moved] = items.splice(from, 1);
        items.splice(to, 0, moved);
        if (hasMain && items[0] !== "main") {
            const rec = items[0];
            const galleryData = isData(rec.data[gallery.image])
                ? rec.data[gallery.image]
                : await this.readPhoto(gallery.model, rec.resId, gallery.image);
            const mainNow = this.record.data[imageField(this.record)];
            const mainData = isData(mainNow)
                ? mainNow
                : await this.readPhoto(this.record.resModel, this.record.resId, imageField(this.record));
            await rec.update({ [gallery.image]: mainData });
            await this.record.update({ [imageField(this.record)]: galleryData });
            // That gallery row now holds the old card picture: it goes where
            // the card picture was dropped.
            items[items.indexOf("main")] = rec;
            items.shift();
        } else if (hasMain) {
            items.shift();
        }
        for (let i = 0; i < items.length; i++) {
            // A gallery whose rows carry no order on this form (the older
            // Variant images tab) keeps its order; only the card swap applies.
            if (!("sequence" in (items[i].activeFields || {}))) {
                continue;
            }
            if (items[i].data.sequence !== (i + 1) * 10) {
                await items[i].update({ sequence: (i + 1) * 10 });
            }
        }
        this.refreshPhotos();
    }

    /** The gallery's rows in the order the shop shows them. */
    galleryRecords(gallery = galleryOf(this.record)) {
        const list = this.record.data[gallery.field];
        const recs = list ? [...list.records] : [];
        return recs
            .map((rec, i) => ({ rec, i }))
            .sort((a, b) => ((a.rec.data.sequence ?? 0) - (b.rec.data.sequence ?? 0)) || a.i - b.i)
            .map(({ rec }) => rec);
    }

    /** A saved picture's value, to move it to another place. A pasted Image
     *  Server link moves as that link, so moving it never makes a copy on the
     *  server. An uploaded picture moves as its bytes: its file belongs to the
     *  product's server folder, and replacing a photo can overwrite it. */
    async readPhoto(model, id, field = IMAGE) {
        if (this.state.data?.imageLink) {
            try {
                const res = await rpc("/ai369_image_server/image_url", { model, res_id: id, field });
                if (res.linked && res.url) {
                    const data = btoa(`<!--imgsrv-linked:${res.url}-->`);
                    linkPreviews.set(data, res.url);
                    return data;
                }
            } catch {
                // the bytes below still do the job
            }
        }
        return this.readImage(model, id, field);
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
