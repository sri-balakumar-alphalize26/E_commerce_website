/**
 * 369 Mart notifications, as the screen that writes them.
 *
 * The twin of /admin/notifications, and the sibling of the reviews and rewards
 * desks. A notice is a line that turns up in every customer's notification
 * list, so this writes - but narrowly: the words, the window, and taking one
 * down. The list it replaces has no form and no search view at all.
 *
 * **Nothing deletes a notice.** Somebody has already read it, and removing the
 * record does not untell them. Taking it down stops it reaching anybody new,
 * and that is the whole of it - there is no delete route behind a button here.
 *
 * Two rules carried from the console:
 *
 *  - **The state is the server's.** Live, scheduled and expired fall out of
 *    the two dates and whether it is switched on, and `mart369_admin_list`
 *    works that out. This prints `row.state`; it never decides it, or the two
 *    screens disagree the moment a clock ticks past a date.
 *  - **Writes are never optimistic.** `run()` re-reads in `finally`, even when
 *    the write failed, because a refusal means this screen was out of date.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Confirm } from "@mart369/ui/confirm";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Search } from "@mart369/ui/search";
import { Pick } from "@mart369/ui/pick";
import { Icon } from "@mart369/ui/icon";
import { Tabs } from "@mart369/ui/tabs";
import { Pill } from "@mart369/ui/pill";

const MODEL = "mart369.notice";

const TILES = [
    { key: "live", tab: "live", label: _t("Live now"), icon: "megaphone" },
    { key: "scheduled", tab: "scheduled", label: _t("Scheduled"), icon: "clock" },
    { key: "expired", tab: "expired", label: _t("Finished"), icon: "check" },
    { key: "off", tab: "off", label: _t("Taken down"), icon: "ban", warn: true },
];

const TABS = [
    { key: "live", label: _t("Live now"), badge: "live" },
    { key: "scheduled", label: _t("Scheduled"), badge: "scheduled" },
    { key: "expired", label: _t("Finished"), badge: "expired" },
    { key: "off", label: _t("Taken down"), badge: "off" },
    { key: "all", label: _t("All"), badge: "all" },
];

const PAGE = 30;

/* Which tone each state wears. A notice's state is its own label, so there
   is nothing to translate - only to colour. */
const TONES = {
    live: { tone: "green" },
    scheduled: { tone: "blue" },
    expired: { tone: "grey" },
    off: { tone: "amber" },
};
const POLL_MS = 60000;

function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

/** Odoo speaks "YYYY-MM-DD HH:MM:SS"; a datetime-local input speaks
 *  "YYYY-MM-DDTHH:MM". Translated at the edge, never in the payload. */
function toInput(ms) {
    if (!ms) {
        return "";
    }
    const d = new Date(ms);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function toOdoo(value) {
    return value ? value.replace("T", " ") + ":00" : false;
}

function when(ms) {
    return ms ? new Date(ms).toLocaleString() : "";
}

/* --------------------------------------------------------------- the form */

export class NoticeDialog extends Component {
    static template = "mart369_account.NoticeDialog";
    static components = { Dialog, Pick, Icon, Pill };
    static props = {
        notice: { type: [Object, { value: false }], optional: true },
        kinds: { type: Array },
        onSaved: { type: Function },
        close: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        const n = this.props.notice;
        this.state = useState({
            form: {
                name: n ? n.title : "",
                text: n ? n.text : "",
                kind: n ? n.kind : "offer",
                publish_at: n ? toInput(n.from) : "",
                until: n ? toInput(n.until) : "",
                go_view: n ? n.goView : "",
                go_param: n ? n.goParam : "",
            },
            busy: false,
            error: "",
        });
    }

    /** The kinds the server offers, as the [value, label] pairs the dropdown
     *  takes. Empty until the desk behind this has loaded them, which `Pick`
     *  shows as a blank toggle rather than falling over. */
    get kindOptions() {
        return this.props.kinds.map((kind) => [String(kind.key), kind.label]);
    }

    setKind(kind) {
        this.state.form.kind = kind;
    }

    async save() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        const values = {
            ...this.state.form,
            publish_at: toOdoo(this.state.form.publish_at),
            until: toOdoo(this.state.form.until),
        };
        try {
            await this.orm.call(MODEL, "mart369_admin_save", [
                this.props.notice ? this.props.notice.id : false, values,
            ]);
            this.props.onSaved();
            this.props.close();
        } catch (err) {
            // The dialog stays open with the message in it: closing it would
            // throw away everything just typed.
            this.state.error = message(err);
        } finally {
            this.state.busy = false;
        }
    }

    get title() {
        return this.props.notice ? _t("Edit notification") : _t("New notification");
    }
}

/* --------------------------------------------------------------- the list */

export class NoticeDesk extends Component {
    static template = "mart369_account.NoticeDesk";
    static components = { Layout, Search, Icon, Tabs, Pill };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.TILES = TILES;
        this.TABS = TABS;
        this.TONES = TONES;

        this.state = useState({
            tab: "live",
            q: "",
            limit: PAGE,
            rows: [],
            total: 0,
            counts: null,
            kinds: [],
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
            this.state.limit = PAGE;
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

    async load({ quiet = false } = {}) {
        if (!quiet) {
            this.state.loading = true;
        }
        try {
            const page = await this.orm.call(MODEL, "mart369_admin_list", [], {
                tab: this.state.tab,
                q: this.state.q.trim() || null,
                limit: this.state.limit,
            });
            this.state.rows = page.notices || [];
            this.state.total = page.total || 0;
            this.state.counts = page.counts || null;
            this.state.kinds = page.kinds || [];
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    /** Never optimistic: a refusal means this screen was stale, so it reloads
     *  either way rather than arguing with the model. */
    async run(fn) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await fn();
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
        } finally {
            this.state.busy = false;
            await this.load({ quiet: true });
        }
    }

    write(notice) {
        this.dialog.add(NoticeDialog, {
            notice: notice || false,
            kinds: this.state.kinds,
            onSaved: () => this.load({ quiet: true }),
        });
    }

    putBack(row) {
        return this.run(() =>
            this.orm.call(MODEL, "mart369_admin_retire", [row.id, false])
        );
    }

    askTakeDown(row) {
        this.dialog.add(Confirm, {
            title: _t("Take this down?"),
            body: _t(
                "It stops appearing to anybody new. Customers who have already " +
                    "seen it keep it in their list - taking it down does not " +
                    "untell them."
            ),
            confirmLabel: _t("Take it down"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(() =>
                    this.orm.call(MODEL, "mart369_admin_retire", [row.id, true])
                ),
            cancel: () => {},
        });
    }

    pick(tab) {
        if (!tab) {
            return;
        }
        this.state.tab = tab;
        this.state.limit = PAGE;
        this.load();
    }

    showMore() {
        this.state.limit += PAGE;
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

    /** Straight off the server's counts, never `state.rows.length`. */
    tileValue(tile) {
        return this.state.counts?.[tile.key] ?? 0;
    }

    /** The list, for what this screen does not do: grouping and exporting. */
    moreViews() {
        this.action.doAction("mart369_account.action_mart369_notices");
    }

    when(ms) { return when(ms); }
}

registry.category("actions").add("mart369_account.notices", NoticeDesk);
