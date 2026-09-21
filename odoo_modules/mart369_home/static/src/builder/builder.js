/**
 * 369 Mart home page builder.
 *
 * One screen: the app's home page drawn as a phone, using the app's own
 * stylesheet, next to a panel that edits whatever band is selected. Every
 * change saves on its own, then the page is reloaded from the server so the
 * mock always shows exactly what the app will receive.
 */
import { Component, onMounted, onPatched, onWillStart, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { useSortable } from "@web/core/utils/sortable_owl";
import { useDebounced } from "@web/core/utils/timing";
import { useSaveQueue } from "./save_queue";
import { getDataURLFromFile } from "@web/core/utils/urls";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const M = {
    mode: "mart369.home.mode",
    section: "mart369.home.section",
    banner: "mart369.home.banner",
    tile: "mart369.home.tile",
    tab: "mart369.home.tab",
    picked: "mart369.home.section.product",
    line: "mart369.home.section.banner",
    product: "product.template",
};

// Same strokes the app draws (components/home/shared.jsx).
const ICONS = {
    bag: '<path d="M5 8h14l-1 12H6z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
    basket: '<path d="M4 10h16l-1.6 9a2 2 0 0 1-2 1.6H7.6a2 2 0 0 1-2-1.6z"/><path d="m9 10 3-6 3 6"/>',
    leaf: '<path d="M5 19c0-8 5-14 15-14 0 10-6 15-14 15"/><path d="M5 19l8-8"/>',
    plug: '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0z"/><path d="M12 17v4"/>',
    pot: '<path d="M4 10h16v6a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z"/><path d="M2 10h2M20 10h2M9 6c0-1 1-2 3-2s3 1 3 2"/>',
    pen: '<path d="m4 20 1-4L16 5l3 3L8 19z"/><path d="m14 7 3 3"/>',
    ticket: '<path d="M3 8a2 2 0 0 0 2-2h14a2 2 0 0 0 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 0-2 2H5a2 2 0 0 0-2-2v-2a2 2 0 0 0 0-4z"/><path d="M10 6v12" stroke-dasharray="2 2"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    chev: '<path d="m6 9 6 6 6-6"/>',
    right: '<path d="m9 6 6 6-6 6"/>',
    cart: '<path d="M3 4h2l2.4 11.2a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.5L21 8H6"/><circle cx="10" cy="20" r="1.3"/><circle cx="17" cy="20" r="1.3"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    heart: '<path d="M12 20s-7.5-4.6-9.2-9.3C1.6 7.2 4 4 7.2 4c2 0 3.6 1.2 4.8 2.8C13.2 5.2 14.8 4 16.8 4 20 4 22.4 7.2 21.2 10.7 19.5 15.4 12 20 12 20z"/>',
    truck: '<path d="M3 6h11v10H3zM14 9h4l3 3.5V16h-7"/><circle cx="7" cy="17.5" r="1.8"/><circle cx="17.5" cy="17.5" r="1.8"/>',
    shirt: '<path d="m8 4-5 3 2 4 3-1v10h8V10l3 1 2-4-5-3a4 4 0 0 1-8 0z"/>',
    book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M8 7h7"/>',
    grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    scooter: '<path d="M4 16a3 3 0 1 0 6 0 3 3 0 0 0-6 0zM14 16a3 3 0 1 0 6 0 3 3 0 0 0-6 0z"/><path d="M7 16h7l3-8h3"/>',
    // Used by the editor's own chrome rather than by the shop.
    left: '<path d="m15 6-6 6 6 6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    trash: '<path d="M4 7h16M10 7V5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2"/><path d="M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"/>',
    eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    // The same eye with the lid drawn over it, so hidden reads as hidden.
    'eye-off': '<path d="M3 3l18 18"/><path d="M10.6 5.2A9.8 9.8 0 0 1 12 5c6 0 10 7 10 7a17 17 0 0 1-3.3 4"/><path d="M6.2 6.4A17 17 0 0 0 2 12s4 7 10 7a9.6 9.6 0 0 0 4.3-1"/>',
    clock: '<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>',
    check: '<path d="m5 12 4.5 4.5L19 7"/>',
    info: '<circle cx="12" cy="12" r="8"/><path d="M12 11v5M12 8h.01"/>',
};

const SOURCES = [
    ["category", _t("A product category")],
    ["manual", _t("Products I pick myself")],
    ["rule", _t("Chosen automatically")],
    ["tag", _t("A product tag")],
];
const RULES = [
    ["new", _t("Newest first")],
    ["best", _t("Best sellers")],
    ["discount", _t("Biggest discount")],
];
const ROUTE_VIEWS = [
    ["home", _t("The home page")],
    ["category", _t("A category page")],
    ["offers", _t("The offers page")],
    ["buyagain", _t("The buy-again page")],
];
const TONE_CSS = {
    green: "linear-gradient(120deg, #13613c, #2d9a5a)",
    navy: "linear-gradient(120deg, #083b59, #0a78ab)",
    brown: "linear-gradient(120deg, #7a4326, #b8774a)",
    orange: "linear-gradient(120deg, #d86a0c, #f7a23a)",
    teal: "linear-gradient(120deg, #0e5a63, #1c8c8f)",
    indigo: "linear-gradient(120deg, #26306b, #4a5bb0)",
};

const shortId = () => Math.random().toString(36).slice(2, 7);

/** Move `movedId` next to `prevId`/`nextId` inside `ids`, returning the new order. */
function reorderIds(ids, movedId, prevId, nextId) {
    const rest = ids.filter((id) => id !== movedId);
    let at;
    if (prevId !== null && rest.includes(prevId)) {
        at = rest.indexOf(prevId) + 1;
    } else if (nextId !== null && rest.includes(nextId)) {
        at = rest.indexOf(nextId);
    } else {
        at = 0;
    }
    rest.splice(at, 0, movedId);
    return rest;
}

export class Icon extends Component {
    static template = "mart369_home.Icon";
    static props = { n: String, size: { type: Number, optional: true }, class: { type: String, optional: true } };
    static defaultProps = { size: 20, class: "" };

    setup() {
        this.svg = useRef("svg");
        // The paths are drawn by hand rather than by `t-out`.
        //
        // `t-out` builds its markup as HTML, so every <path> came out in the
        // XHTML namespace - and an <svg> full of XHTML elements draws nothing
        // at all. The box was the right size, the stroke was the right colour,
        // and the icon was simply not there. Assigning innerHTML on the <svg>
        // node makes the browser parse the fragment in the SVG namespace,
        // which is the whole difference between an icon and an empty gap.
        const draw = () => {
            if (this.svg.el) {
                this.svg.el.innerHTML = ICONS[this.props.n] || ICONS.grid;
            }
        };
        onMounted(draw);
        onPatched(draw);
    }
}

export class HomeBuilder extends Component {
    static template = "mart369_home.HomeBuilder";
    static components = { Layout, Icon };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.SOURCES = SOURCES;
        this.RULES = RULES;
        this.ROUTE_VIEWS = ROUTE_VIEWS;
        this.TONE_CSS = TONE_CSS;

        // Which saved page this screen is editing. Without it `builder_load`
        // resolves whichever page is *live*, so opening a parked page and
        // changing a banner quietly changed what shoppers were seeing.
        // Null still means the live page, so the old /odoo/mart-home URL and
        // the tour keep working.
        this.pageId = this.props.action?.context?.mart369_page_id || null;

        this.state = useState({
            modeKey: this.props.action?.context?.mart369_mode || "quick",
            data: null,
            sel: { type: null, id: null },
            editItem: null,
            status: "saved",
            search: { q: "", results: [], busy: false },
        });

        // Edits are applied to local state at once and written a moment
        // after typing stops, batched per record. Shared with the other
        // builders so they cannot drift - see save_queue.js.
        this.save = useSaveQueue({
            orm: this.orm,
            notification: this.notification,
            reload: () => this.load(),
            onStatus: (s) => (this.state.status = s),
            find: (model, id) => this.findRecord(model, id),
        });
        this.searchProducts = useDebounced(this._searchProducts, 300);

        this.phoneRef = useRef("phone");
        this.panelListRef = useRef("panelList");

        useSortable({
            ref: this.phoneRef,
            elements: ".mart-band[data-band-id]",
            handle: ".mart-handle",
            cursor: "grabbing",
            onDrop: ({ element, previous, next }) => this.onBandDrop(element, previous, next),
        });
        useSortable({
            ref: this.panelListRef,
            elements: ".mart-item[data-id]",
            handle: ".mart-item-handle",
            cursor: "grabbing",
            onDrop: ({ element, previous, next }) => this.onItemDrop(element, previous, next),
        });

        onWillStart(() => this.load());
    }

    // ------------------------------------------------------------ loading

    get d() {
        return this.state.data;
    }

    async load() {
        const data = await this.orm.call(M.mode, "builder_load", [this.state.modeKey, this.pageId]);
        this.state.data = data;
        this.applyPending();
        // Keep the selection if the record still exists.
        const sel = this.state.sel;
        if (sel.type === "band" && !data.bands.some((b) => b.id === sel.id)) {
            this.state.sel = { type: null, id: null };
        }
    }

    async switchMode(key) {
        if (key === this.state.modeKey) {
            return;
        }
        await this.flushNow();
        this.state.modeKey = key;
        this.state.sel = { type: null, id: null };
        this.state.editItem = null;
        await this.load();
    }

    // ------------------------------------------------------------- lookups

    get activeTabs() {
        return this.d.tabs.filter((t) => t.active);
    }
    get activeBanners() {
        return this.d.banners.filter((b) => b.active);
    }
    get activeTiles() {
        return this.d.tiles.filter((t) => t.active);
    }
    bannerByKey(key) {
        return this.d.banners.find((b) => b.key === key);
    }
    get selectedBand() {
        const sel = this.state.sel;
        return sel.type === "band" ? this.d.bands.find((b) => b.id === sel.id) : null;
    }
    isSelected(type, id = null) {
        return this.state.sel.type === type && this.state.sel.id === id;
    }
    offPct(item) {
        return item.mrp ? Math.round(((item.mrp - item.price) / item.mrp) * 100) : 0;
    }
    inr(n) {
        return "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
    }
    bannerStyle(b) {
        if (b.image_url) {
            return `background-image:url('${b.image_url}?unique=${encodeURIComponent(b.write_date)}');background-size:cover;background-position:center;`;
        }
        return "";
    }
    tileStyle(t) {
        return `background:${t.bg || "#f1f4f6"};`;
    }
    toneStyle(tone) {
        return `background:${TONE_CSS[tone] || TONE_CSS.green};`;
    }
    stripBanners(band) {
        const keys = (band.preview && band.preview.banner) || [];
        return keys.map((k) => this.bannerByKey(k)).filter(Boolean);
    }
    labelOf(list, value) {
        const hit = list.find(([k]) => k === value);
        return hit ? hit[1] : value;
    }

    // ------------------------------------------------------------- select

    select(type, id = null) {
        this.state.sel = { type, id };
        this.state.editItem = null;
        this.state.search = { q: "", results: [], busy: false };
    }
    openTrash() {
        this.select("trash");
    }

    toggleEditItem(id) {
        this.state.editItem = this.state.editItem === id ? null : id;
    }

    // -------------------------------------------------------------- saving

    /** Locate the local copy of a record so pending edits can be re-applied. */
    findRecord(model, id) {
        const d = this.d;
        if (!d) {
            return null;
        }
        switch (model) {
            case M.mode:
                return d.mode.id === id ? d.mode : null;
            case M.section:
                return d.bands.find((r) => r.id === id);
            case M.banner:
                return d.banners.find((r) => r.id === id);
            case M.tile:
                return d.tiles.find((r) => r.id === id);
            case M.tab:
                return d.tabs.find((r) => r.id === id);
            case M.picked:
                for (const b of d.bands) {
                    const hit = b.picked.find((r) => r.id === id);
                    if (hit) {
                        return hit;
                    }
                }
                return null;
            case M.line:
                for (const b of d.bands) {
                    const hit = b.lines.find((r) => r.id === id);
                    if (hit) {
                        return hit;
                    }
                }
                return null;
        }
        return null;
    }

    // Thin delegations so the rest of this class reads unchanged.
    edit(model, rec, field, value) {
        this.save.edit(model, rec, field, value);
    }
    onField(model, rec, field, ev) {
        this.save.edit(model, rec, field, this.save.valueFrom(ev));
    }
    applyPending() {
        this.save.applyPending();
    }
    flushNow() {
        return this.save.flushNow();
    }
    run(fn, opts) {
        return this.save.run(fn, opts);
    }

    // ------------------------------------------------------------ actions

    toggleActive(model, rec) {
        return this.run(() => this.orm.write(model, [rec.id], { active: !rec.active }));
    }

    /** Remove, recoverably: the record goes to the Trash, not away. */
    remove(model, rec, what) {
        const days = this.d.trash_days;
        const body = days
            ? _t("%(what)s moves to the Trash. You can put it back for the next %(days)s days.", { what, days })
            : _t("%s moves to the Trash, where it is kept until you empty it.", what);
        this.dialog.add(ConfirmationDialog, {
            title: _t("Move to Trash?"),
            body,
            confirmLabel: _t("Move to Trash"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(
                    async () => {
                        await this.orm.call(model, "action_trash", [[rec.id]]);
                        if (this.state.sel.id === rec.id) {
                            this.state.sel = { type: null, id: null };
                        }
                        if (this.state.editItem === rec.id) {
                            this.state.editItem = null;
                        }
                    },
                    { successMessage: _t("Moved to Trash") }
                ),
            cancel: () => {},
        });
    }

    // ------------------------------------------------------------- the Trash

    restore(row) {
        return this.run(() => this.orm.call(row.model, "action_restore", [[row.id]]), {
            successMessage: _t("Put back"),
        });
    }

    /** Delete for good, skipping the rest of the retention. */
    deleteForever(row) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete for good?"),
            body: _t("%s will be gone for good. This cannot be undone.", row.name),
            confirmLabel: _t("Delete for good"),
            confirmClass: "btn-danger",
            confirm: () => this.run(() => this.orm.unlink(row.model, [row.id])),
            cancel: () => {},
        });
    }

    emptyTrash() {
        const rows = this.d.trash;
        this.dialog.add(ConfirmationDialog, {
            title: _t("Empty the Trash?"),
            body: _t("All %s item(s) will be gone for good. This cannot be undone.", rows.length),
            confirmLabel: _t("Empty the Trash"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(async () => {
                    const byModel = {};
                    for (const row of rows) {
                        (byModel[row.model] ||= []).push(row.id);
                    }
                    for (const [model, ids] of Object.entries(byModel)) {
                        await this.orm.unlink(model, ids);
                    }
                }),
            cancel: () => {},
        });
    }

    nextSequence(list) {
        return list.reduce((m, r) => Math.max(m, r.sequence || 0), 0) + 10;
    }

    async addBand(kind) {
        const vals = {
            mode_id: this.d.mode.id,
            kind,
            sequence: this.nextSequence(this.d.bands),
            name: kind === "rail" ? _t("New row") : _t("Banner strip"),
            source: "category",
        };
        const [id] = await this.run(() => this.orm.create(M.section, [vals]));
        this.select("band", id);
    }
    async addBanner() {
        const id = shortId();
        const [newId] = await this.run(() =>
            this.orm.create(M.banner, [{
                mode_id: this.d.mode.id,
                key: `b-${id}`,
                name: _t("New banner"),
                kicker: "",
                note: "",
                tone: "green",
                sequence: this.nextSequence(this.d.banners),
            }])
        );
        this.state.editItem = newId;
    }
    async addTile() {
        const id = shortId();
        const [newId] = await this.run(() =>
            this.orm.create(M.tile, [{
                mode_id: this.d.mode.id,
                key: `tile-${id}`,
                name: _t("New tile"),
                image_source: "art",
                art: "Pack",
                bg: "#f1f4f6",
                sequence: this.nextSequence(this.d.tiles),
            }])
        );
        this.state.editItem = newId;
    }
    async addTab() {
        const id = shortId();
        const [newId] = await this.run(() =>
            this.orm.create(M.tab, [{
                mode_id: this.d.mode.id,
                key: `tab-${id}`,
                name: _t("New tab"),
                icon: "grid",
                route_view: "category",
                sequence: this.nextSequence(this.d.tabs),
            }])
        );
        this.state.editItem = newId;
    }

    addLine(band, banner) {
        return this.run(() =>
            this.orm.create(M.line, [{
                section_id: band.id,
                banner_id: banner.id,
                sequence: this.nextSequence(band.lines),
            }])
        );
    }
    removeLine(line) {
        return this.run(() => this.orm.unlink(M.line, [line.id]));
    }
    linedBannerIds(band) {
        return new Set(band.lines.map((l) => l.banner_id));
    }

    // ------------------------------------------------------------ pictures

    async onUpload(model, rec, ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        const dataUrl = await getDataURLFromFile(file);
        const b64 = dataUrl.split(",")[1];
        const vals = { image_1920: b64 };
        if (model === M.tile) {
            vals.image_source = "upload";
        }
        await this.run(() => this.orm.write(model, [rec.id], vals));
    }
    clearImage(model, rec) {
        const vals = { image_1920: false };
        if (model === M.tile) {
            vals.image_source = "art";
        }
        return this.run(() => this.orm.write(model, [rec.id], vals));
    }

    // ------------------------------------------------- hand-picked products

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
        const rows = await this.orm.searchRead(
            M.product,
            [["is_published", "=", true], ["name", "ilike", q]],
            ["id", "display_name", "list_price"],
            { limit: 15 }
        );
        this.state.search.results = rows;
        this.state.search.busy = false;
    }
    async addPicked(band, product) {
        if (band.picked.some((p) => p.product_tmpl_id === product.id)) {
            this.notification.add(_t("That product is already in this row."), { type: "warning" });
            return;
        }
        await this.run(() =>
            this.orm.create(M.picked, [{
                section_id: band.id,
                product_tmpl_id: product.id,
                sequence: this.nextSequence(band.picked),
            }])
        );
        this.state.search = { q: "", results: [], busy: false };
    }
    removePicked(line) {
        return this.run(() => this.orm.unlink(M.picked, [line.id]));
    }

    // ------------------------------------------------------------- sorting

    idOf(el) {
        return el ? parseInt(el.dataset.bandId || el.dataset.id, 10) : null;
    }

    async onBandDrop(element, previous, next) {
        const ids = this.d.bands.map((b) => b.id);
        const order = reorderIds(ids, this.idOf(element), this.idOf(previous), this.idOf(next));
        if (order.join() === ids.join()) {
            return;
        }
        this.d.bands.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
        await this.run(() => this.orm.webResequence(M.section, order, { field_name: "sequence" }));
    }

    /** Which list the panel is currently showing, and where it lives. */
    panelList() {
        const el = this.panelListRef.el;
        const model = el && el.dataset.model;
        const band = this.selectedBand;
        switch (model) {
            case M.banner:
                return { model, list: this.d.banners };
            case M.tile:
                return { model, list: this.d.tiles };
            case M.tab:
                return { model, list: this.d.tabs };
            case M.picked:
                return band ? { model, list: band.picked } : null;
            case M.line:
                return band ? { model, list: band.lines } : null;
        }
        return null;
    }

    async onItemDrop(element, previous, next) {
        const target = this.panelList();
        if (!target) {
            return;
        }
        const ids = target.list.map((r) => r.id);
        const order = reorderIds(ids, this.idOf(element), this.idOf(previous), this.idOf(next));
        if (order.join() === ids.join()) {
            return;
        }
        target.list.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
        await this.run(() => this.orm.webResequence(target.model, order, { field_name: "sequence" }));
    }
}

registry.category("actions").add("mart369_home.builder", HomeBuilder);
