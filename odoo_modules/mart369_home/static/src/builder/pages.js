/**
 * Saved home pages - the screen you land on.
 *
 * A home page is a whole saved page, not a set of loose settings: "Diwali"
 * is nine banners, four rows and a tagline, kept together under a name. One
 * of them is switched on every day; another can be given a window and take
 * over by itself.
 *
 * This screen exists because the builder used to open straight onto whatever
 * was live. You could not tell, from inside it, which page you were changing
 * - and the answer was always "the one shoppers are looking at". Now you pick
 * a page first, and the builder is told which one.
 */
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "./builder";

const M = { version: "mart369.home.version" };

/**
 * "What shall we call it?"
 *
 * `ConfirmationDialog` has no field to type into, and a page called
 * "Everyday (copy)" that somebody meant to call "Diwali" is a page nobody
 * renames until they are looking for it six months later.
 */
export class NamePrompt extends Component {
    static template = "mart369_home.NamePrompt";
    static components = { Dialog };
    static props = {
        title: String,
        placeholder: { type: String, optional: true },
        confirmLabel: String,
        onConfirm: Function,
        close: Function,
    };

    setup() {
        this.inputRef = useRef("name");
        useAutofocus({ refName: "name" });
    }

    get value() {
        return (this.inputRef.el?.value || "").trim();
    }

    confirm() {
        const name = this.value;
        if (!name) {
            return;
        }
        this.props.close();
        this.props.onConfirm(name);
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.confirm();
        }
    }
}

/** An Odoo datetime ("2026-09-21 18:30:00") <-> a datetime-local input. */
const toInput = (v) => (v ? v.slice(0, 16).replace(" ", "T") : "");
const toOdoo = (v) => (v ? v.replace("T", " ") + ":00" : false);

export class HomePages extends Component {
    static template = "mart369_home.HomePages";
    static components = { Layout, Icon };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.state = useState({
            pages: [],
            trash: [],
            trashOpen: false,
            trashDays: 30,
            loading: true,
            error: "",
            busy: false,
            /** Which card has its schedule panel open, and its draft dates. */
            scheduling: null,
            draft: { startsOn: "", endsOn: "" },
        });

        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(M.version, "pages_load", []);
            this.state.pages = data.pages;
            this.state.trash = data.trash || [];
            this.state.trashDays = data.trash_days;
            this.state.error = "";
        } catch (err) {
            // The screen says so and offers to try again, rather than showing
            // an empty list that reads as "you have no saved pages".
            this.state.error = err?.data?.message || err?.message || _t("We could not reach the shop.");
        } finally {
            this.state.loading = false;
        }
    }

    /** Run a change, then reload, with one place that reports failure. */
    async run(fn, successMessage) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await fn();
            await this.load();
            if (successMessage) {
                this.notification.add(successMessage, { type: "success" });
            }
        } catch (err) {
            // The model refuses some of these on purpose - deleting the live
            // page, or the last one. Show what it said, not a generic line.
            this.notification.add(
                err?.data?.message || err?.message || _t("That did not work."),
                { type: "danger" }
            );
        } finally {
            this.state.busy = false;
        }
    }

    // ------------------------------------------------------------- the moves

    edit(page, modeKey = "quick") {
        // The page id travels in the context, so the builder cannot end up
        // editing a different page from the one whose Edit button was clicked.
        this.action.doAction("mart369_home.action_mart369_home_editor", {
            additionalContext: {
                mart369_page_id: parseInt(page.id, 10),
                mart369_mode: modeKey,
            },
        });
    }

    /** Whichever page shoppers are on right now - not necessarily the one
        flagged everyday, because an open window beats the flag. */
    get livePage() {
        return this.state.pages.find((p) => p.state === "live");
    }

    switchOn(page) {
        const from = this.livePage;
        const body = from && from.id !== page.id
            ? _t('Shoppers are on "%(from)s". They will be on "%(to)s" straight away.',
                 { from: from.name, to: page.name })
            : _t('Shoppers will be on "%s" straight away.', page.name);
        this.dialog.add(ConfirmationDialog, {
            title: from && from.id !== page.id
                ? _t('Switch from "%(from)s" to "%(to)s"?',
                     { from: from.name, to: page.name })
                : _t('Switch on "%s"?', page.name),
            body,
            confirmLabel: _t("Switch on"),
            confirm: () =>
                this.run(
                    () => this.orm.call(M.version, "action_mart369_make_current",
                                        [parseInt(page.id, 10)]),
                    _t("Switched on. This is the everyday page now.")
                ),
            cancel: () => {},
        });
    }

    duplicate(page) {
        this.run(async () => {
            const copy = await this.orm.call(M.version, "copy", [parseInt(page.id, 10)], {
                default: { name: _t("%s (copy)", page.name) },
            });
            return copy;
        }, _t("Copied. Edit it, then switch it on when you are ready."));
    }

    newPage() {
        const from = this.state.pages.find((p) => p.isCurrent) || this.state.pages[0];
        if (!from) {
            this.notification.add(
                _t("There is no page to copy. Install the home page demo data first."),
                { type: "warning" }
            );
            return;
        }
        // Named up front rather than renamed later. It still starts as a copy
        // of the everyday page - nobody wants to rebuild a home page from
        // nothing to run a three-day sale.
        this.dialog.add(NamePrompt, {
            title: _t("What is this page for?"),
            placeholder: _t("Festival sale"),
            confirmLabel: _t("Create page"),
            onConfirm: (name) =>
                this.run(
                    () => this.orm.call(M.version, "copy", [parseInt(from.id, 10)],
                                        { default: { name } }),
                    _t('"%s" created. Edit it, then switch it on when you are ready.',
                       name)
                ),
        });
    }

    remove(page) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove this page?"),
            body: this.state.trashDays
                ? _t('"%(name)s" goes to the Trash, where you can put it back for %(days)s days.',
                     { name: page.name, days: this.state.trashDays })
                : _t('"%s" goes to the Trash, where you can put it back.', page.name),
            confirmLabel: _t("Remove page"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(
                    () => this.orm.call(M.version, "action_trash",
                                        [parseInt(page.id, 10)]),
                    _t("Moved to the Trash.")
                ),
            cancel: () => {},
        });
    }

    // ------------------------------------------------------------- the Trash

    openTrash() {
        this.state.trashOpen = !this.state.trashOpen;
    }

    restore(page) {
        this.run(
            () => this.orm.call(M.version, "action_restore", [parseInt(page.id, 10)]),
            _t('"%s" is back.', page.name)
        );
    }

    /** Gone now rather than in thirty days. Only offered from the Trash, so
        nothing is destroyed without having been visible there first. */
    deleteForever(page) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete for good?"),
            body: _t('"%s" and everything on it goes now. There is no putting it back.',
                     page.name),
            confirmLabel: _t("Delete for good"),
            confirmClass: "btn-danger",
            confirm: () =>
                this.run(
                    () => this.orm.unlink(M.version, [parseInt(page.id, 10)]),
                    _t("Deleted.")
                ),
            cancel: () => {},
        });
    }

    // ------------------------------------------------------------- scheduling

    openSchedule(page) {
        if (this.state.scheduling === page.id) {
            this.state.scheduling = null;
            return;
        }
        this.state.scheduling = page.id;
        this.state.draft = {
            startsOn: toInput(page.startsOn),
            endsOn: toInput(page.endsOn),
        };
    }

    saveSchedule(page) {
        const { startsOn, endsOn } = this.state.draft;
        this.run(
            () =>
                this.orm.write(M.version, [parseInt(page.id, 10)], {
                    starts_on: toOdoo(startsOn),
                    ends_on: toOdoo(endsOn),
                }),
            _t("Dates saved.")
        ).then(() => (this.state.scheduling = null));
    }

    clearSchedule(page) {
        this.state.draft = { startsOn: "", endsOn: "" };
        this.saveSchedule(page);
    }

    // ---------------------------------------------------------------- drawing

    /** Green for the page shoppers see, blue for one waiting its turn. */
    toneOf(page) {
        return { live: "green", scheduled: "blue", ended: "grey", off: "grey" }[page.state] || "grey";
    }

    countsOf(page, modeKey) {
        return page.bands?.[modeKey] || { banners: 0, tabs: 0, tiles: 0, sections: 0 };
    }
}

registry.category("actions").add("mart369_home.pages", HomePages);
