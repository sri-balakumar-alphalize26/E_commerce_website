/**
 * What people searched for, as the app's console draws it.
 *
 * The twin of /admin/searches, and the sibling of the referrals and reviews
 * desks in mart369_account. It answers the one question the list next door
 * cannot put on screen: **what did customers ask for that the shop does not
 * sell?** Those are the rows with no results, and they are the reason
 * `mart369.search.term` was written at all.
 *
 * Everything it reads is `mart369_admin_list` on the model, the same one call
 * the console makes. Nothing here is a second implementation of anything.
 *
 * Two rules carried from the console, both load-bearing:
 *
 *  - **The tiles count everything, never the filtered rows.** A "Nothing
 *    found 7" that dropped to 0 because somebody typed in the search box
 *    would be useless for deciding whether there is anything to act on.
 *  - **Only `trending` can be written.** What was searched for, how often, how
 *    many results it found and when are counts of things that really
 *    happened. A screen that could edit them could make the catalogue's own
 *    gaps disappear by typing over them.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Search } from "@mart369/ui/search";
import { Switch } from "@mart369/ui/switch";
import { Icon } from "@mart369/ui/icon";
import { Tabs } from "@mart369/ui/tabs";

const MODEL = "mart369.search.term";

/* Each tile sets the tab, so the strip is the filter rather than a read-out
   above one. Searches is the exception - there is no "searches" tab to show,
   so it stays a plain figure and never looks clickable. */
const TILES = [
    { key: "searches", label: _t("Searches"), icon: "search", flat: true },
    { key: "terms", tab: "popular", label: _t("Different terms"), icon: "menu" },
    { key: "empty", tab: "empty", label: _t("Found nothing"), icon: "warn", bad: true },
    { key: "blocked", tab: "blocked", label: _t("Not suggested"), icon: "eye-off" },
];

const TABS = [
    { key: "all", label: _t("All"), badge: "all" },
    { key: "popular", label: _t("Most searched"), badge: "popular" },
    { key: "empty", label: _t("Found nothing"), badge: "empty" },
    { key: "blocked", label: _t("Not suggested"), badge: "blocked" },
];

const POLL_MS = 60000;

/** Odoo wraps a UserError a couple of ways; dig the sentence out of whichever
 *  one arrived. The same helper the other desks carry. */
function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

/** How long ago, in the words the console uses. Hand-rolled rather than
 *  `toLocaleString` so this and components/admin/format.js agree. */
function ago(ms) {
    if (!ms) {
        return "";
    }
    const mins = Math.round((Date.now() - ms) / 60000);
    if (mins < 1) {
        return _t("just now");
    }
    if (mins < 60) {
        return _t("%s min ago", mins);
    }
    const hours = Math.round(mins / 60);
    if (hours < 24) {
        return _t("%s h ago", hours);
    }
    return _t("%s d ago", Math.round(hours / 24));
}

export class SearchDesk extends Component {
    static template = "mart369_catalog.SearchDesk";
    static components = { Layout, Search, Switch, Icon, Tabs };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.TILES = TILES;
        this.TABS = TABS;

        this.state = useState({
            tab: "all",
            q: "",
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

        // Somebody leaves this open on a second monitor, and the counts move
        // on their own every time a shopper searches. Quiet, so it never
        // flashes the loading line.
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
            return; // the searches tile, which filters nothing
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

    /** Straight off the server counts, never `state.rows.length`. See the
     *  first rule in the file header. */
    tileValue(tile) {
        return this.state.tiles?.[tile.key] ?? 0;
    }

    // --------------------------------------------------------------- writing

    /** Never optimistic. A refusal means the screen was stale, so it reloads
     *  either way rather than arguing with the model. */
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

    /** The only write on this screen. It stops the term being offered to
     *  shoppers as a suggestion; it never stops it being counted. */
    toggleTrending(row) {
        return this.run(() =>
            this.orm.call(MODEL, "mart369_admin_set_trending", [[row.id], !row.trending])
        );
    }

    /** The list, for what this screen does not do: grouping and exporting. */
    allViews() {
        this.action.doAction("mart369_catalog.action_mart369_searches");
    }

    // --------------------------------------------------------------- drawing

    ago(ms) {
        return ago(ms);
    }
}

registry.category("actions").add("mart369_catalog.searches", SearchDesk);
