/**
 * 369 Mart reviews, as the queue the app's console draws.
 *
 * The twin of /admin/reviews, and the sibling of the orders and returns desks
 * in mart369_order. It answers "what has nobody looked at yet" and "what did
 * we take down", which the list next door cannot: a grid of rows is good for
 * sorting and exporting, and bad for reading a paragraph somebody wrote.
 *
 * Everything it reads is already on the model (models/rating_rating.py) and
 * already tested, because the console needed exactly the same answers.
 * `mart369_admin_list` brings the rows and the tile counts together in one
 * call. Nothing here is a second implementation of anything.
 *
 * Two rules carried from the console, both load-bearing:
 *
 *  - **The tiles count everything, never the filtered rows.** A "Waiting 3"
 *    that dropped to 0 because somebody ticked a filter would be useless for
 *    deciding whether there is anything to look at. The model does this
 *    deliberately; the desk must not undo it by counting `state.rows`.
 *  - **Publishing and hiding are the only writes.** Staff moderate a review,
 *    they do not edit one - the server allow-list is a single field, and this
 *    screen offers no control that would imply otherwise. What a customer
 *    wrote stays theirs.
 *
 * The list view keeps what this does not try to do: grouping, the form, the
 * sparkline strip, and exporting.
 *
 * `Pick` is imported from the orders desk rather than copied - mart369_account
 * depends on mart369_order, so it is already in the bundle. What must NOT be
 * reached for is anything in mart369_home: this module does not depend on it.
 * Icons are Font Awesome, as they are on the other two desks.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Confirm } from "@mart369/ui/confirm";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Search } from "@mart369/ui/search";

import { Pick } from "@mart369/ui/pick";
import { Icon } from "@mart369/ui/icon";
import { Tabs } from "@mart369/ui/tabs";

const MODEL = "rating.rating";

/* Each tile sets the tab, so the strip is the filter rather than a read-out
   above one. Average is the exception - there is no "average" tab to show, so
   it stays a plain figure and never looks clickable. */
const TILES = [
    { key: "average", label: _t("Average rating"), icon: "star", stars: true },
    { key: "pending", tab: "pending", label: _t("Waiting"), icon: "box", warn: true },
    { key: "published", tab: "published", label: _t("Published"), icon: "check" },
    { key: "hidden", tab: "hidden", label: _t("Hidden"), icon: "eye-off", bad: true },
];

const TABS = [
    { key: "pending", label: _t("Waiting"), badge: "pending" },
    { key: "published", label: _t("Published"), badge: "published" },
    { key: "hidden", label: _t("Hidden"), badge: "hidden" },
    { key: "all", label: _t("All"), badge: "all" },
];

const POLL_MS = 30000;

/** Odoo wraps a UserError a couple of ways; dig the sentence out of whichever
 *  one arrived. The same helper the other two desks carry. */
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

export class ReviewDesk extends Component {
    static template = "mart369_account.ReviewDesk";
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
            tab: "pending",
            q: "",
            verified: "",
            photos: "",
            rows: [],
            counts: null,
            average: 0,
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

        // Somebody leaves this open on a second monitor. Skipped while a write
        // is in flight, and quiet so it never flashes the loading line.
        this.timer = setInterval(() => {
            if (!this.state.busy) {
                this.load({ quiet: true });
            }
        }, POLL_MS);
        onWillUnmount(() => clearInterval(this.timer));
    }

    // -------------------------------------------------------------- reading

    /** A Pick sends "", "1" or "0". The model wants null, true or false -
     *  `false` has to survive, so this cannot be a truthiness test. */
    flag(value) {
        return value === "" ? null : value === "1";
    }

    async load({ quiet = false } = {}) {
        if (!quiet) {
            this.state.loading = true;
        }
        try {
            const page = await this.orm.call(MODEL, "mart369_admin_list", [], {
                state: this.state.tab === "all" ? null : this.state.tab,
                q: this.state.q.trim() || null,
                verified: this.flag(this.state.verified),
                photos: this.flag(this.state.photos),
            });
            this.state.rows = page.reviews || [];
            this.state.counts = page.counts || null;
            this.state.average = page.average || 0;
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    // ------------------------------------------------------------- filtering

    pick(tab) {
        if (!tab) {
            return; // the average tile, which filters nothing
        }
        this.state.tab = tab;
        this.load();
    }

    setFilter(key, value) {
        this.state[key] = value;
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
        if (tile.stars) {
            return (this.state.average || 0).toFixed(1);
        }
        return this.state.counts?.[tile.key] ?? 0;
    }

    // -------------------------------------------------------------- writing

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

    moderate(row, state) {
        return this.run(() =>
            this.orm.call(MODEL, "write", [[row.id], { mart369_state: state }])
        );
    }

    publish(row) {
        return this.moderate(row, "published");
    }

    /** Asked first, and the question says what it costs: the star goes too,
     *  which is the half nobody expects. */
    askHide(row) {
        this.dialog.add(Confirm, {
            title: _t("Hide this review?"),
            body: _t(
                "%s by %s will no longer show on the product page, and will stop counting towards its rating.",
                row.title || _t("This review"),
                row.by
            ),
            confirmLabel: _t("Hide review"),
            confirm: () => this.moderate(row, "hidden"),
            cancel: () => {},
        });
    }

    /** The list, for what this screen does not do: grouping, the form, the
        sparkline strip and exporting. */
    moreViews() {
        this.action.doAction("mart369_account.action_mart369_reviews");
    }

    // --------------------------------------------------------------- drawing

    get verifiedOptions() {
        return [
            ["", _t("Bought or not")],
            ["1", _t("Verified purchase")],
            ["0", _t("Not verified")],
        ];
    }

    get photoOptions() {
        return [
            ["", _t("With or without photos")],
            ["1", _t("With photos")],
            ["0", _t("Without photos")],
        ];
    }

    /** Green from four up, amber at three, red below. The same three bands the
     *  console paints, so a 2-star looks equally alarming in both. */
    starClass(stars) {
        if (stars >= 4) {
            return "rv-s-good";
        }
        return stars >= 3 ? "rv-s-mid" : "rv-s-bad";
    }

    initials(name) {
        return (name || "?")
            .split(/\s+/)
            .filter(Boolean)
            .slice(0, 2)
            .map((part) => part[0].toUpperCase())
            .join("");
    }

    ago(ms) {
        return ago(ms);
    }
}

registry.category("actions").add("mart369_account.reviews", ReviewDesk);
