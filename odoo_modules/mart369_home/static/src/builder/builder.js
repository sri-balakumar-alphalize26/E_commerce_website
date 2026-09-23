/**
 * 369 Mart home page builder.
 *
 * One screen: the app's home page drawn as a phone, using the app's own
 * stylesheet, next to a panel that edits whatever band is selected. Every
 * change saves on its own, then the page is reloaded from the server so the
 * mock always shows exactly what the app will receive.
 */
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Confirm } from "@mart369/ui/confirm";
import { useService } from "@web/core/utils/hooks";
import { useSortable } from "@web/core/utils/sortable_owl";
import { useDebounced } from "@web/core/utils/timing";
import { useSaveQueue } from "./save_queue";
import { getDataURLFromFile } from "@web/core/utils/urls";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "@mart369/ui/icon";
import { Switch } from "@mart369/ui/switch";
import { Pick } from "@mart369/ui/pick";

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

export class HomeBuilder extends Component {
    static template = "mart369_home.HomeBuilder";
    static components = { Layout, Icon, Pick, Switch };
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

    /** A many2one, written from the dropdown's string - and `false` when the
     *  empty first line is chosen, which is how Odoo clears one. */
    editId(model, rec, field, value) {
        this.save.edit(model, rec, field, parseInt(value) || false);
    }

    /** The categories, as the [value, label] pairs the dropdown takes. Ids are
     *  cast to strings because the dropdown compares strings; `none` is the
     *  wording of the empty first line, which differs by where it is used. */
    categoryOptions(none) {
        return [["", none], ...(this.d?.categories || []).map((c) => [String(c.id), c.name])];
    }

    tagOptions(none) {
        return [["", none], ...(this.d?.tags || []).map((tg) => [String(tg.id), tg.name])];
    }

    /** What a many2one's current value is, as the string the dropdown wants. */
    idValue(id) {
        return id ? String(id) : "";
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
        this.dialog.add(Confirm, {
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
        this.dialog.add(Confirm, {
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
        this.dialog.add(Confirm, {
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
