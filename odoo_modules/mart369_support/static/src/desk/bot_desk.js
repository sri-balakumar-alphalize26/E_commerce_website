/**
 * 369 Mart bot answers, as the screen that edits them.
 *
 * The twin of /admin/bot-answers, and the sibling of the support desk next
 * door. The list it replaces is an editable grid with no search view and no
 * filters at all - fine for a developer who knows what a pattern is, poor for
 * somebody deciding what the shop should say.
 *
 * **Order is meaning.** The bot tries these in `sequence` and the first match
 * wins, so a broad pattern moved above a narrow one silently swallows it: the
 * narrow answer still exists, still looks right, and never fires again. Moving
 * one is therefore its own action, and the list is never sorted any other way.
 *
 * **A pattern is a regular expression**, and one that will not compile used to
 * save happily and then never match. The model refuses it now; this screen
 * shows the message it comes back with rather than inventing its own.
 *
 * **Switched off is not deleted.** Somebody wrote it for a reason.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const MODEL = "mart369.bot.rule";

const TILES = [
    { key: "on", tab: "on", label: _t("In use"), icon: "fa-comments-o" },
    { key: "agent", tab: "agent", label: _t("Hands over"), icon: "fa-user" },
    { key: "off", tab: "off", label: _t("Switched off"), icon: "fa-ban" },
    { key: "broken", label: _t("Cannot match"), icon: "fa-exclamation-triangle", bad: true, flat: true },
];

const TABS = [
    { key: "on", label: _t("In use"), badge: "on" },
    { key: "agent", label: _t("Hands over"), badge: "agent" },
    { key: "off", label: _t("Switched off"), badge: "off" },
    { key: "all", label: _t("All"), badge: "all" },
];

const PAGE = 30;
const POLL_MS = 60000;

function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

/* --------------------------------------------------------------- the form */

export class AnswerDialog extends Component {
    static template = "mart369_support.AnswerDialog";
    static components = { Dialog };
    static props = {
        answer: { type: [Object, { value: false }], optional: true },
        kinds: { type: Array },
        onSaved: { type: Function },
        close: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        const a = this.props.answer;
        this.state = useState({
            form: {
                title: a ? a.title : "",
                pattern: a ? a.pattern : "",
                kind: a ? a.kind : "static",
                reply: a ? a.reply : "",
                reply_alt: a ? a.replyAlt : "",
                chips: a ? (a.chips || []).join(", ") : "",
                action_label: a ? a.actionLabel : "",
                action_view: a ? a.actionView : "",
                action_param: a ? a.actionParam : "",
            },
            busy: false,
            error: "",
        });
    }

    /** Only a fixed answer says the words below; every other kind works the
     *  answer out from the customer's own orders, wallet or coupons, and the
     *  words are a fallback. It changes what editing them does. */
    get saysTheWords() {
        return this.state.form.kind === "static";
    }

    async save() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        const values = {
            ...this.state.form,
            chips: this.state.form.chips
                .split(",").map((c) => c.trim()).filter(Boolean),
        };
        try {
            await this.orm.call(MODEL, "mart369_admin_save", [
                this.props.answer ? this.props.answer.id : false, values,
            ]);
            this.props.onSaved();
            this.props.close();
        } catch (err) {
            // Stays open with the message in it - the pattern is the usual
            // reason, and closing would throw away what was typed.
            this.state.error = message(err);
        } finally {
            this.state.busy = false;
        }
    }

    get title() {
        return this.props.answer ? _t("Edit answer") : _t("New answer");
    }
}

/* --------------------------------------------------------------- the list */

export class BotDesk extends Component {
    static template = "mart369_support.BotDesk";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.TILES = TILES;
        this.TABS = TABS;

        this.state = useState({
            tab: "on",
            q: "",
            limit: PAGE,
            rows: [],
            total: 0,
            counts: null,
            broken: 0,
            kinds: [],
            loading: true,
            busy: false,
            error: "",
        });

        this.search = useDebounced((ev) => {
            this.state.q = ev.target.value.trim();
            this.state.limit = PAGE;
            this.load();
        }, 300);

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
                q: this.state.q || null,
                limit: this.state.limit,
            });
            this.state.rows = page.answers || [];
            this.state.total = page.total || 0;
            this.state.counts = page.counts || null;
            this.state.broken = page.broken || 0;
            this.state.kinds = page.kinds || [];
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

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

    write(answer) {
        this.dialog.add(AnswerDialog, {
            answer: answer || false,
            kinds: this.state.kinds,
            onSaved: () => this.load({ quiet: true }),
        });
    }

    putBack(row) {
        return this.run(() =>
            this.orm.call(MODEL, "mart369_admin_switch", [row.id, true])
        );
    }

    askSwitchOff(row) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Switch this answer off?"),
            body: _t(
                "The bot stops using it. It is kept, not deleted - you can put " +
                    "it back at any time."
            ),
            confirmLabel: _t("Switch it off"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(() =>
                    this.orm.call(MODEL, "mart369_admin_switch", [row.id, false])
                ),
            cancel: () => {},
        });
    }

    /** Only while the list is whole: with a tab or a search on, the ids sent
     *  are a subset and everything outside it would be renumbered around
     *  them. */
    get canReorder() {
        return this.state.tab === "all" && !this.state.q;
    }

    move(index, by) {
        const next = [...this.state.rows];
        const target = index + by;
        if (target < 0 || target >= next.length) {
            return;
        }
        [next[index], next[target]] = [next[target], next[index]];
        return this.run(() =>
            this.orm.call(MODEL, "mart369_admin_reorder", [next.map((a) => a.id)])
        );
    }

    pick(tab) {
        if (!tab) {
            return; // a flat tile, which filters nothing
        }
        this.state.tab = tab;
        this.state.limit = PAGE;
        this.load();
    }

    showMore() {
        this.state.limit += PAGE;
        this.load();
    }

    tabCount(tab) {
        return tab.badge ? this.state.counts?.[tab.badge] ?? null : null;
    }

    tileValue(tile) {
        if (tile.key === "broken") {
            return this.state.broken;
        }
        return this.state.counts?.[tile.key] ?? 0;
    }

    /** The editable list, for bulk work and exporting. */
    moreViews() {
        this.action.doAction("mart369_support.action_mart369_rules");
    }
}

registry.category("actions").add("mart369_support.answers", BotDesk);
