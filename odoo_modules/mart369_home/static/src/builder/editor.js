/**
 * The home page editor - the page itself, with a switch on everything.
 *
 * The canvas is not a picture of the shop; it is the shop's own markup and
 * the shop's own stylesheet, drawn from the same payload /369mart/home sends
 * the app. So "what will shoppers see?" is answered by looking, not by
 * reading a form and imagining.
 *
 * Three rules this screen keeps, each learned the hard way:
 *
 *  - It edits the page you opened. The old builder always resolved the *live*
 *    page, so parking a page and changing a banner changed what shoppers were
 *    looking at. The page id arrives in the action context and goes into the
 *    load.
 *  - Hiding and removing are different. The eye takes something out of the
 *    app and leaves it here. Remove starts a clock: it waits in the Trash,
 *    drawn rather than described, until the days run out.
 *  - Nothing is saved by hand. A field writes itself a moment after typing
 *    stops; a switch writes at once, because there is no second keystroke
 *    coming and a toggle that looks done but is not gets pressed twice.
 */
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSortable } from "@web/core/utils/sortable_owl";
import { _t } from "@web/core/l10n/translation";
import { Confirm } from "@mart369/ui/confirm";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "@mart369/ui/icon";
import { Switch } from "@mart369/ui/switch";
import { Pick } from "@mart369/ui/pick";
import { useSaveQueue } from "./save_queue";

const M = {
    mode: "mart369.home.mode",
    banner: "mart369.home.banner",
    tile: "mart369.home.tile",
    tab: "mart369.home.tab",
    section: "mart369.home.section",
};

/**
 * The four things on a home page, and which of their fields this screen
 * offers. A list rather than "every field": a form that can set anything can
 * set `key`, which the app matches on, or `sequence` for a band on another
 * page. Kept in step with BAND_FIELDS in controllers/admin_api.py.
 */
const KINDS = {
    tab: {
        title: "Tab", short: "tab",
        group: "tabs", src: "tabs", model: M.tab,
        fields: [
            ["name", "Label", "The word on the pill"],
            ["icon", "Icon", "", "icons"],
        ],
    },
    banner: {
        title: "Banner", short: "banner",
        group: "banners", src: "banners", model: M.banner,
        fields: [
            ["kicker", "Kicker", "The small line above the headline"],
            ["name", "Headline", "The big line"],
            ["note", "Note", "One line under it"],
            ["tone", "Colour", "", "tones"],
            ["href", "Link", "Where tapping it goes"],
        ],
    },
    tile: {
        title: "Category tile", short: "tile",
        group: "categories", src: "tiles", model: M.tile,
        fields: [
            ["name", "Label", "What it is called under the picture"],
            ["route", "Link", "The category slug it opens"],
        ],
    },
    section: {
        title: "Row", short: "row",
        group: "sections", src: "bands", model: M.section,
        fields: [
            ["name", "Title", "The heading above the row"],
            ["subtitle", "Subtitle", "One line under the heading"],
            ["view_all_route", "See all link", "The category it opens"],
        ],
    },
};

const GROUPS = ["tab", "banner", "tile", "section"];

/**
 * A field is called one thing in Odoo and another in the payload the app
 * reads. Typing in the panel has to change the drawing straight away, so the
 * edit is applied to both - and this is the translation between them.
 */
const PREVIEW_FIELD = {
    banner: { name: "title" },
    tile: { name: "label" },
    tab: { name: "label" },
    section: { name: "title", view_all_route: "route" },
};

const uid = (kind, id) => kind + ":" + id;
const reduced = () =>
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export class PageEditor extends Component {
    static template = "mart369_home.PageEditor";
    static components = { Layout, Icon, Pick, Switch };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.KINDS = KINDS;
        this.GROUPS = GROUPS;

        this.pageId = this.props.action?.context?.mart369_page_id || null;

        this.state = useState({
            modeKey: this.props.action?.context?.mart369_mode || "quick",
            data: null,
            sel: null,            // "kind:id", or null for the tab's own settings
            showHidden: false,
            status: "idle",       // idle | saving | saved | error
            loading: true,
            error: "",
            trashOpen: false,
            landed: null,         // a band to scroll to and flash
            switching: null,      // the Quick/Express curtain
        });

        this.save = useSaveQueue({
            orm: this.orm,
            notification: this.notification,
            reload: () => this.load(),
            onStatus: (s) => (this.state.status = s),
            find: (model, id) => this.findRecord(model, id),
        });

        // One sortable per group. A single one over the whole canvas would
        // happily let a tab be dropped between two banners, and the drop
        // would then be written as a sequence on the wrong model.
        this.refs = {};
        for (const kind of GROUPS) {
            this.refs[kind] = useRef("group_" + kind);
            useSortable({
                ref: this.refs[kind],
                elements: ".pe-band[data-band]",
                handle: ".pe-grip",
                cursor: "grabbing",
                onDrop: (params) => this.onDrop(kind, params),
            });
        }

        this.canvasRef = useRef("canvas");

        // Something just added is at the bottom of a list you are not looking
        // at. Take the screen there and flash it, or "+ Banner" looks broken.
        useEffect(
            (landed) => {
                if (landed) {
                    this.scrollToBand(landed);
                }
            },
            () => [this.state.landed]
        );

        onWillStart(() => this.load());
    }

    // ------------------------------------------------------------- loading

    get d() {
        return this.state.data;
    }

    get page() {
        return this.d?.page || null;
    }

    async load() {
        try {
            const data = await this.orm.call(M.mode, "builder_load", [
                this.state.modeKey,
                this.pageId,
            ]);
            this.state.data = data;
            this.state.error = "";
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
        for (const spec of Object.values(KINDS)) {
            if (spec.model === model) {
                return (this.d?.[spec.src] || []).find((r) => r.id === id);
            }
        }
        return model === M.mode ? this.d?.mode : null;
    }

    // ------------------------------------------------------------ selection

    get selected() {
        if (!this.state.sel || !this.d) {
            return null;
        }
        const parts = this.state.sel.split(":");
        const kind = parts[0];
        const id = parseInt(parts[1], 10);
        const spec = KINDS[kind];
        if (!spec) {
            return null;
        }
        const record = (this.d[spec.src] || []).find((r) => r.id === id);
        return record ? { kind, spec, record } : null;
    }

    select(kind, id) {
        this.state.sel = uid(kind, id);
    }

    isSelected(kind, id) {
        return this.state.sel === uid(kind, id);
    }

    /** Click the band, not its buttons - the grip and the eye are their own. */
    onBandClick(kind, rid, ev) {
        if (ev.target.closest(".pe-tool")) {
            return;
        }
        this.select(kind, rid);
    }

    // --------------------------------------------------------------- drawing

    /** The rows of one group, as the app would receive them. */
    rows(kind) {
        const all = this.d?.preview?.[KINDS[kind].group] || [];
        // The canvas shows what shoppers see. Hidden things are still here,
        // but stay out of the way until asked for.
        return this.state.showHidden ? all : all.filter((r) => r.active);
    }

    get hiddenCount() {
        if (!this.d?.preview) {
            return 0;
        }
        return GROUPS.reduce(
            (n, kind) =>
                n + (this.d.preview[KINDS[kind].group] || []).filter((r) => !r.active).length,
            0
        );
    }

    get isEmpty() {
        return GROUPS.every((kind) => !(this.d?.preview?.[KINDS[kind].group] || []).length);
    }

    get allHidden() {
        return !this.isEmpty && this.hiddenCount > 0 &&
            GROUPS.every((kind) => !this.rows(kind).length);
    }

    /** The builder-side record behind a drawn row - what actually gets written. */
    recordFor(kind, rid) {
        return (this.d?.[KINDS[kind].src] || []).find((r) => r.id === rid);
    }

    labelOf(kind, row) {
        return row.title || row.label || row.name || "Untitled";
    }

    offPct(item) {
        return item.mrp && item.mrp > item.price
            ? Math.round(((item.mrp - item.price) / item.mrp) * 100)
            : 0;
    }

    inr(n) {
        const c = this.d?.currency;
        const symbol = (c && c.symbol) || "₹";
        const decimals = c && typeof c.decimals === "number" ? c.decimals : 0;
        return symbol + Number(n || 0).toFixed(decimals);
    }

    /** A banner strip serialises to {banner: [keys]} and nothing else. */
    stripKeys(row) {
        return (row && row.banner) || null;
    }

    bannerByKey(key) {
        return (this.d?.preview?.banners || []).find((b) => b.id === key) || null;
    }

    stripBanners(row) {
        return (this.stripKeys(row) || []).map((k) => this.bannerByKey(k)).filter(Boolean);
    }

    // ----------------------------------------------------------------- edits

    /**
     * Apply a field edit to the record that gets written *and* to the row the
     * canvas draws, so typing shows up under the cursor rather than a moment
     * later when the reload lands.
     */
    onField(kind, rid, field, ev) {
        this.setField(kind, rid, field, this.save.valueFrom(ev));
    }

    /** The same edit as `onField`, given the value rather than the event an
     *  input carried it in - which is what a component hands back. */
    setField(kind, rid, field, value) {
        const record = this.recordFor(kind, rid);
        if (!record) {
            return;
        }
        this.save.edit(KINDS[kind].model, record, field, value);

        const row = (this.d.preview?.[KINDS[kind].group] || []).find((r) => r.rid === rid);
        if (row) {
            row[PREVIEW_FIELD[kind]?.[field] || field] = value;
        }
    }

    /** One of the server's vocabularies - icons, tones, artwork - as the
     *  [value, label] pairs the dropdown takes. They arrive that shape already
     *  (ICON_CHOICES and friends in mart369/models/serializers.py); only the
     *  value is cast, because the dropdown compares strings.
     *
     *  The `<select>` this replaced printed each pair with `t-esc`, so the
     *  options read "bolt,Lightning (quick)" and picking one wrote that whole
     *  string as the value - nothing ever showed as chosen. */
    vocabOptions(key) {
        return (this.d.vocab?.[key] || []).map(([value, label]) => [String(value), label]);
    }

    /** The eye. Writes at once - see save_queue's `now`. */
    toggleActive(kind, rid) {
        const record = this.recordFor(kind, rid);
        if (!record) {
            return;
        }
        const next = !record.active;
        this.save.edit(KINDS[kind].model, record, "active", next, { now: true });
        const row = (this.d.preview?.[KINDS[kind].group] || []).find((r) => r.rid === rid);
        if (row) {
            row.active = next;
        }
    }

    /** The tab's own settings - the panel when nothing is selected. */
    onModeField(field, ev) {
        this.setModeField(field, this.save.valueFrom(ev));
    }

    setModeField(field, value) {
        this.save.edit(M.mode, this.d.mode, field, value);
    }

    // ------------------------------------------------------- add and remove

    async add(kind) {
        const spec = KINDS[kind];
        const rows = this.d?.[spec.src] || [];
        const sequence = rows.length
            ? Math.max(...rows.map((r) => r.sequence || 0)) + 10
            : 10;
        let created = null;
        await this.save.run(async () => {
            const id = await this.orm.create(spec.model, [
                { mode_id: this.d.mode.id, sequence, ...this.newBandVals(kind) },
            ]);
            created = Array.isArray(id) ? id[0] : id;
        });
        if (created) {
            this.select(kind, created);
            this.state.landed = uid(kind, created);
        }
    }

    /**
     * What a brand-new band is before anybody types into it. The same values
     * NEW_BAND in admin_api.py uses, on purpose: one made here and one made
     * from the console have to be the same kind of thing, or "it looks
     * different depending on where you made it" becomes a bug nobody can
     * reproduce.
     */
    newBandVals(kind) {
        const key = Math.random().toString(36).slice(2, 7);
        return {
            banner: {
                key: "b-" + key, name: "New banner",
                kicker: "", note: "", tone: "green",
            },
            tile: { key: "t-" + key, name: "New tile", art: "Pack" },
            tab: {
                key: "tb-" + key, name: "New tab",
                icon: "grid", route_view: "home",
            },
            section: {
                key: "sec-" + key, name: "New row",
                kind: "rail", source: "rule", rule: "new",
            },
        }[kind];
    }

    remove(kind, rid) {
        const days = this.d?.trash_days ?? 30;
        this.dialog.add(Confirm, {
            title: _t("Remove this %s?", KINDS[kind].short),
            body: _t(
                "It goes to the Trash, where you can put it back for %s days.",
                days
            ),
            confirmLabel: _t("Remove"),
            confirmClass: "btn-danger",
            confirm: async () => {
                await this.save.run(
                    () => this.orm.call(KINDS[kind].model, "action_trash", [[rid]]),
                    { successMessage: _t("Removed. It is in the Trash.") }
                );
                if (this.state.sel === uid(kind, rid)) {
                    this.state.sel = null;
                }
            },
            cancel: () => {},
        });
    }

    restore(row) {
        this.save.run(
            () => this.orm.call(KINDS[row.kind].model, "action_restore", [[row.id]]),
            { successMessage: _t("Put back.") }
        );
    }

    // ------------------------------------------------------------ reordering

    async onDrop(kind, { element, previous, next }) {
        const spec = KINDS[kind];
        const group = this.d.preview[spec.group];
        const idOf = (el) => parseInt(el.dataset.band.split(":")[1], 10);
        const moved = idOf(element);
        const from = group.findIndex((r) => r.rid === moved);
        if (from < 0) {
            return;
        }
        const before = [...group];

        const [row] = group.splice(from, 1);
        let to = 0;
        if (previous) {
            to = group.findIndex((r) => r.rid === idOf(previous)) + 1;
        } else if (next) {
            to = Math.max(0, group.findIndex((r) => r.rid === idOf(next)));
        }
        group.splice(to, 0, row);

        try {
            await this.orm.call(
                spec.model,
                "web_resequence",
                [group.map((r) => r.rid), {}],
                { field_name: "sequence" }
            );
            await this.load();
        } catch {
            // Put it back where it was. A row that springs back is honest; one
            // that stays put and is wrong after the next refresh is not.
            this.d.preview[spec.group] = before;
            this.notification.add(_t("That order did not save."), { type: "danger" });
        }
    }

    // ------------------------------------------------------------- the tabs

    async switchMode(key, ev) {
        if (key === this.state.modeKey || this.state.switching) {
            return;
        }
        // Read the words before the swap. Reading them after showed the tab
        // you were leaving, which is the one thing the curtain must not say.
        const target = (this.d?.modes || []).find((m) => m.key === key);
        const copy = {
            label: (target && target.label) || (key === "quick" ? "Quick" : "Express"),
            tagline: (target && target.tagline) || "",
            to: key,
        };
        await this.save.flushNow().catch(() => {});

        const go = async () => {
            this.state.modeKey = key;
            this.state.sel = null;
            await this.load();
        };

        if (reduced() || !ev) {
            await go();
            return;
        }

        const box = ev.currentTarget.getBoundingClientRect();
        const canvas = this.canvasRef.el?.getBoundingClientRect();
        this.state.switching = {
            ...copy,
            phase: "in",
            x: canvas ? Math.round(box.left + box.width / 2 - canvas.left) : 0,
            y: canvas ? Math.round(box.top + box.height / 2 - canvas.top) : 0,
        };
        setTimeout(async () => {
            this.state.switching = { ...this.state.switching, phase: "hold" };
            await go();
            setTimeout(() => {
                this.state.switching = { ...this.state.switching, phase: "out" };
                setTimeout(() => (this.state.switching = null), 560);
            }, 380);
        }, 520);
    }

    // ---------------------------------------------------------------- trash

    get trashGroups() {
        const order = { banner: 0, tile: 1, tab: 2, section: 3 };
        const titles = {
            banner: "Banners", tile: "Tiles", tab: "Tabs", section: "Rows",
        };
        const by = {};
        for (const row of this.d?.trash || []) {
            (by[row.kind] = by[row.kind] || []).push(row);
        }
        return Object.keys(by)
            .sort((a, b) => (order[a] ?? 9) - (order[b] ?? 9))
            .map((kind) => ({ kind, title: titles[kind] || kind, rows: by[kind] }));
    }

    trashDrawing(row) {
        return this.d?.trash_preview?.[row.kind + ":" + row.id] || null;
    }

    // --------------------------------------------------------------- moving

    back() {
        this.action.doAction("mart369_home.action_mart369_home_pages");
    }

    /** The phone builder, for the fields this screen deliberately leaves out:
        images, the products inside a row, banner lines, rules, route params. */
    moreSettings() {
        this.action.doAction("mart369_home.action_mart369_home_builder", {
            additionalContext: {
                mart369_page_id: this.pageId,
                mart369_mode: this.state.modeKey,
            },
        });
    }

    scrollToBand(key, tries = 0) {
        const el = this.canvasRef.el?.querySelector('[data-band="' + key + '"]');
        if (!el) {
            // The reload has not painted yet. Two seconds of trying, then give
            // up quietly rather than hold a timer open for the session.
            if (tries < 40) {
                setTimeout(() => this.scrollToBand(key, tries + 1), 50);
            }
            return;
        }
        el.scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: "center" });
        el.classList.add("pe-landed");
        setTimeout(() => el.classList.remove("pe-landed"), 1600);
        this.state.landed = null;
    }
}

registry.category("actions").add("mart369_home.editor", PageEditor);
