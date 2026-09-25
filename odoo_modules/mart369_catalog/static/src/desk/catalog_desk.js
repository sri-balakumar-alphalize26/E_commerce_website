/**
 * The app's categories, as the console draws them.
 *
 * The twin of /admin/catalog, and the sibling of the searches desk beside it.
 * It answers "what does the app look like from the outside" - which groups a
 * shopper sees, how each looks, and which of them are standing empty - which the kanban next door cannot without opening each one.
 *
 * Everything it reads is `mart369_admin_list` on the model, the same one call
 * the console makes. Nothing here is a second implementation of anything.
 *
 * Two rules carried from the console:
 *
 *  - **The tiles count everything, never the filtered rows.**
 *  - **The name and the address are not editable here.** The name is Odoo's
 *    own field, leaned on by the catalogue and every report; the address is a
 *    URL a customer may have saved. Both are one click away in the form, where
 *    the change is made deliberately rather than in passing.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Search } from "@mart369/ui/search";
import { Pick } from "@mart369/ui/pick";
import { Icon } from "@mart369/ui/icon";
import { Tabs } from "@mart369/ui/tabs";

const MODEL = "product.public.category";

const TILES = [
    { key: "live", tab: "live", label: _t("In the app"), icon: "grid" },
    { key: "hidden", tab: "hidden", label: _t("Hidden"), icon: "eye-off" },
    { key: "empty", tab: "empty", label: _t("Standing empty"), icon: "box", warn: true },
    { key: "products", label: _t("Products a shopper can reach"), icon: "box", flat: true },
];

const TABS = [
    { key: "all", label: _t("All"), badge: "all" },
    { key: "live", label: _t("In the app"), badge: "live" },
    { key: "hidden", label: _t("Hidden"), badge: "hidden" },
    { key: "empty", label: _t("Standing empty"), badge: "empty" },
];

const POLL_MS = 60000;

/* Pale background + readable heading ink, in pairs, so a tap cannot give ink
   the shopper cannot read. The same pairs as the web admin's (PALETTE in
   components/admin/AdminCategories.jsx). [background, heading, name] */
const PALETTE = [
    ["#f4f6f8", "#0b4a6e", _t("Default")],
    ["#eef3f7", "#12405e", _t("Steel")],
    ["#e8f3f9", "#0a78ab", _t("Sky")],
    ["#e8f5e9", "#1f7a4c", _t("Leaf")],
    ["#fdf3e2", "#9a5b00", _t("Amber")],
    ["#fdecec", "#a32020", _t("Berry")],
    ["#f3eefb", "#5b3aa6", _t("Violet")],
    ["#f8f4f2", "#6b3326", _t("Cocoa")],
    ["#eef6f4", "#0f6b5c", _t("Teal")],
    ["#f1f1f1", "#222222", _t("Ink")],
];

// The app's grey for the line under the title (browse.css .cg-hero p).
const LINE_GREY = "#4a5a66";

function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

/**
 * How the app draws one category.
 *
 * A dialog rather than editing in the row, because the three things that
 * matter here - the blurb and the two colours - only make sense seen
 * together, and a colour picked beside the words it sits behind is picked
 * once rather than three times.
 */
export class CategoryDialog extends Component {
    static template = "mart369_catalog.CategoryDialog";
    static components = { Dialog, Pick, Icon };
    static props = {
        close: { type: Function },
        // null for a new category.
        row: { type: [Object, { value: null }] },
        // "new", "edit" (everything, from the Edit button) or "look" (the
        // line and the colours, from How it looks). Defaults from `row`.
        mode: { type: String, optional: true },
        // [[id, name]] of the categories a new one can sit under.
        parents: { type: Array, optional: true },
        onSave: { type: Function },
    };

    setup() {
        const row = this.props.row || {};
        this.isNew = !this.props.row;
        this.mode = this.props.mode || (this.isNew ? "new" : "look");
        this.isEdit = this.mode === "edit";
        this.state = useState({
            draft: {
                name: this.isEdit ? row.name || "" : "",
                parent_id: this.isEdit && row.parentId ? String(row.parentId) : "",
                mart_blurb: row.blurb || "",
                mart_tone: row.tone || "#f4f6f8",
                mart_accent: row.accent || "#0b4a6e",
                // Empty until chosen: the app's grey, or the main category's.
                mart_blurb_color: row.blurbColor || "",
            },
            busy: false,
            error: "",
        });
        this.PALETTE = PALETTE;
        // Whether Background or Heading has been picked in this dialog. Until
        // then a new sub-category takes its main category's colours; after,
        // the picked ones stay whatever Under is set to.
        this.coloursPicked = this.isEdit;
    }

    /** Name and Under are asked for when making a category, and when editing
     *  one from the Edit button - not from How it looks. */
    get askPlace() {
        return this.isNew || this.isEdit;
    }

    /** A main category with sub-categories cannot go under another one: its
     *  sub-categories would become a third level. */
    get placeLocked() {
        return this.isEdit && !this.props.row.parentId && this.props.row.children > 0;
    }

    /** One tap sets both colours; the boxes below fine-tune either. */
    pickPair(tone, accent) {
        this.coloursPicked = true;
        this.state.draft.mart_tone = tone;
        this.state.draft.mart_accent = accent;
        this.state.error = "";
    }

    isPair(tone, accent) {
        const d = this.state.draft;
        return (d.mart_tone || "").toLowerCase() === tone && (d.mart_accent || "").toLowerCase() === accent;
    }

    /** The colour the line under the title is drawn in: its own, else (for a
     *  sub-category) its main category's, else the app's grey. */
    get lineColour() {
        return this.state.draft.mart_blurb_color
            || (this.isSub && this.main && this.main.blurbColor)
            || LINE_GREY;
    }

    get title() {
        if (this.isNew) {
            return _t("New category");
        }
        const name = this.props.row.name || _t("this category");
        return this.isEdit ? _t("Edit %s", name) : name;
    }

    /** A category can sit at the top, or under any main category - never
     *  under itself. */
    get parentOptions() {
        const self = this.props.row ? String(this.props.row.id) : null;
        return [
            ["", _t("None - a top-level category")],
            ...(this.props.parents || []).filter(([id]) => id !== self),
        ];
    }

    edit(key, ev) {
        this.set(key, ev.target.value);
    }

    /** The same write as `edit`, given the value rather than the event the
     *  input carried it in - which is what a component hands back. */
    set(key, value) {
        this.state.draft[key] = value;
        this.state.error = "";
        if (key === "mart_tone" || key === "mart_accent") {
            this.coloursPicked = true;
        } else if (key === "parent_id" && !this.coloursPicked) {
            // Nothing picked yet: start from the main category's colours, or
            // back to the defaults when Under goes back to None.
            const m = this.main;
            this.state.draft.mart_tone = (m && m.tone) || "#f4f6f8";
            this.state.draft.mart_accent = (m && m.accent) || "#0b4a6e";
        }
    }

    get preview() {
        return {
            background: this.state.draft.mart_tone || "#f4f6f8",
            color: this.state.draft.mart_accent || "#0b4a6e",
        };
    }

    /** The chosen colours, as the app's own variables: --tone fills the
     *  header (or a sub-category's circle), --accent colours the ring. */
    get previewStyle() {
        const p = this.preview;
        return `--tone: ${p.background}; --accent: ${p.color};`;
    }

    /** A sub-category: one being made with an Under chosen, or an existing
     *  one that has a parent. The app draws it as a round tile, in its own
     *  colours. */
    get isSub() {
        return this.askPlace ? !!this.state.draft.parent_id : !!this.props.row.parentId;
    }

    /** The main category a sub-category sits under: name and colours. */
    get main() {
        if (this.askPlace) {
            const hit = (this.props.parents || []).find(([id]) => id === this.state.draft.parent_id);
            return hit ? { name: hit[1], tone: hit[2], accent: hit[3], blurbColor: hit[4] } : null;
        }
        const row = this.props.row;
        return row.parentId
            ? { name: row.parent, tone: row.parentTone, accent: row.parentAccent, blurbColor: row.parentBlurbColor }
            : null;
    }

    get previewName() {
        if (this.askPlace) {
            return this.state.draft.name.trim() || (this.isNew ? _t("New category") : this.props.row.name);
        }
        return this.props.row.name;
    }

    async save() {
        if (this.state.busy) {
            return;
        }
        const values = { ...this.state.draft };
        if (this.askPlace) {
            if (!values.name.trim()) {
                this.state.error = _t("A category needs a name.");
                return;
            }
            values.parent_id = values.parent_id ? Number(values.parent_id) : false;
            if (this.placeLocked) {
                delete values.parent_id;
            }
        } else {
            // The name and the parent of an existing category are changed in
            // the form, under All views - see the note at the top.
            delete values.name;
            delete values.parent_id;
        }
        this.state.busy = true;
        try {
            await this.props.onSave(values);
            this.props.close();
        } catch (err) {
            // On the dialog rather than as a toast behind it, so the value
            // that was refused is still on screen beside the reason.
            this.state.error = message(err);
        } finally {
            this.state.busy = false;
        }
    }
}

export class CatalogDesk extends Component {
    static template = "mart369_catalog.CatalogDesk";
    static components = { Layout, Pick, Search, Icon, Tabs };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.TILES = TILES;
        this.TABS = TABS;

        this.state = useState({
            tab: "all",
            q: "",
            // The category just created, drawn highlighted once.
            fresh: null,
            rows: [],
            counts: null,
            tiles: {},
            loading: true,
            busy: false,
            error: "",
        });

        /* The box writes to state at once, so typing is never swallowed by
           the wait; only the reload is debounced, which is all the 300ms
           was ever for. The text is kept raw and trimmed when it is sent -
           trimming it here would eat the space between two words. */
        this.reload = useDebounced(() => this.load(), 300);
        this.onSearch = (q) => {
            this.state.q = q;
            this.reload();
        };

        onWillStart(() => this.load());

        this.timer = setInterval(() => {
            if (!this.state.busy) {
                this.load({ quiet: true });
            }
        }, POLL_MS);
        onWillUnmount(() => clearInterval(this.timer));
    }

    // -------------------------------------------------------------- reading

    async load({ quiet = false } = {}) {
        if (!quiet) {
            this.state.loading = true;
        }
        try {
            const page = await this.orm.call(MODEL, "mart369_admin_list", [], {
                tab: this.state.tab,
                q: this.state.q.trim() || null,
            });
            this.state.rows = page.rows || [];
            this.state.counts = page.counts || null;
            this.state.tiles = page.tiles || {};
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    // ------------------------------------------------------------ filtering

    pick(tab) {
        if (!tab) {
            return; // the products tile, which filters nothing
        }
        this.state.tab = tab;
        this.load();
    }


    /** The tabs as the kit's strip takes them: [key, label, count] triples.
     *  `tabCount` returns null for a tab that counts nothing, and the strip
     *  draws no badge for null - which is how a tab stays quiet. */
    get tabItems() {
        return this.TABS.map((tab) => [tab.key, tab.label, this.tabCount(tab)]);
    }

    tabCount(tab) {
        return tab.badge ? this.state.counts?.[tab.badge] ?? null : null;
    }

    tileValue(tile) {
        return this.state.tiles?.[tile.key] ?? 0;
    }

    // --------------------------------------------------------------- writing

    async run(fn) {
        if (this.state.busy) {
            return false;
        }
        this.state.busy = true;
        try {
            await fn();
            return true;
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
            return false;
        } finally {
            this.state.busy = false;
            await this.load({ quiet: true });
        }
    }

    write(row, values) {
        return this.run(() =>
            this.orm.call(MODEL, "mart369_admin_write", [[row.id], values])
        );
    }

    /** Shown or hidden is the one change worth making from the row: it is the
     *  only one whose effect is obvious without seeing the page. */
    toggleShown(row) {
        return this.write(row, { mart_in_app: !row.inApp });
    }

    edit(row) {
        this.dialog.add(CategoryDialog, {
            row,
            onSave: async (values) => {
                this.state.busy = true;
                try {
                    await this.orm.call(MODEL, "mart369_admin_write", [[row.id], values]);
                    this.notification.add(_t("Saved."), { type: "success" });
                } finally {
                    this.state.busy = false;
                    await this.load({ quiet: true });
                }
            },
        });
    }

    /** What a category can go under: [id, name, background, heading, line].
     *  Main categories only - the app shows two levels, so a sub-category
     *  goes under a main one and nothing goes under a sub-category. Read
     *  from the model, not the rows on screen, so a filter never hides one. */
    async mains() {
        const mains = await this.orm.searchRead(
            MODEL, [["parent_id", "=", false]], ["name", "mart_tone", "mart_accent", "mart_blurb_color"],
            { order: "sequence, name" });
        return mains.map((c) => [String(c.id), c.name, c.mart_tone, c.mart_accent, c.mart_blurb_color || ""]);
    }

    /** Everything about a category: its name, where it sits, and how it
     *  looks. The app address stays - a customer may have saved the link. */
    async editAll(row) {
        this.dialog.add(CategoryDialog, {
            row,
            mode: "edit",
            parents: await this.mains(),
            onSave: async (values) => {
                this.state.busy = true;
                try {
                    await this.orm.call(MODEL, "mart369_admin_edit", [[row.id], values]);
                    this.notification.add(_t("Saved."), { type: "success" });
                } finally {
                    this.state.busy = false;
                    await this.load({ quiet: true });
                }
            },
        });
    }

    /** A new category, from the same dialog as editing one: a name, an
     *  optional parent, and how it looks. */
    async newCategory() {
        this.dialog.add(CategoryDialog, {
            row: null,
            parents: await this.mains(),
            onSave: async (values) => {
                this.state.busy = true;
                try {
                    const made = await this.orm.call(MODEL, "mart369_admin_create", [values]);
                    this.notification.add(_t("%s is in the catalogue.", made.name), { type: "success" });
                    this.state.fresh = made.id;
                } finally {
                    this.state.busy = false;
                    await this.load({ quiet: true });
                }
            },
        });
    }

    /** The kanban and list, for what this screen does not do: the name, the
        app address, the parent, the order and the products themselves. */
    allViews() {
        this.action.doAction("mart369_catalog.action_mart369_catalog");
    }

    // --------------------------------------------------------------- drawing

    /** Main categories as headings, each with its sub-categories under it.
     *  A sub-category matching the filter when its main one does not still
     *  gets its heading, drawn plainly, so it never shows without a home. */
    get groups() {
        const rows = this.state.rows;
        const byId = new Map(rows.map((r) => [r.id, r]));
        const out = [];
        const index = new Map();
        for (const r of rows) {
            const key = r.parentId || r.id;
            let group = index.get(key);
            if (!group) {
                group = {
                    main: r.parentId
                        ? byId.get(r.parentId) || { id: r.parentId, name: r.parent, stub: true }
                        : r,
                    subs: [],
                };
                index.set(key, group);
                out.push(group);
            }
            if (r.parentId) {
                group.subs.push(r);
            }
        }
        return out;
    }

    get counted() {
        const subs = this.state.rows.filter((r) => r.parentId).length;
        return { mains: this.state.rows.length - subs, subs };
    }

    groupStyle(group, index) {
        return `--i: ${index}; --tone: ${group.main.tone || "#f4f6f8"}; --accent: ${group.main.accent || "#0b4a6e"};`;
    }

    swatch(row) {
        return `background: ${row.tone || "#f4f6f8"}; color: ${row.accent || "#0b4a6e"};`;
    }
}

registry.category("actions").add("mart369_catalog.catalog", CatalogDesk);
