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
import { Confirm } from "@mart369/ui/confirm";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "@mart369/ui/icon";

const M = { version: "mart369.home.version" };

/**
 * "What shall we call it?"
 *
 * `Confirm` has no field to type into, and a page called
 * "Everyday (copy)" that somebody meant to call "Diwali" is a page nobody
 * renames until they are looking for it six months later.
 */
export class NamePrompt extends Component {
    static template = "mart369_home.NamePrompt";
    static components = { Dialog };
    static props = {
        title: String,
        placeholder: { type: String, optional: true },
        // The name already there, when renaming rather than naming a new page.
        value: { type: String, optional: true },
        hint: { type: String, optional: true },
        confirmLabel: String,
        onConfirm: Function,
        close: Function,
    };

    setup() {
        this.inputRef = useRef("name");
        useAutofocus({ refName: "name" });
        this.state = useState({ error: "", busy: false });
    }

    get value() {
        return (this.inputRef.el?.value || "").trim();
    }

    /** Stays open until the shop has accepted the name. A refusal, such as a
        name already in use, shows in red here, where it can be corrected. */
    async confirm() {
        const name = this.value;
        if (!name || this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        try {
            await this.props.onConfirm(name);
            this.props.close();
        } catch (err) {
            this.state.error = err?.data?.message || err?.message || _t("That did not work.");
            this.state.busy = false;
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.confirm();
        }
    }
}

/** The Rename box, the same on the pages list and in the editor. */
export const renameProps = (page, onConfirm) => ({
    title: _t("Rename this page"),
    value: page.name,
    hint: _t("This name is for you and your team. Shoppers don't see it."),
    confirmLabel: _t("Save name"),
    onConfirm,
});

/** An 369ai datetime ("2026-09-21 18:30:00") <-> a datetime-local input. */
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
        this.dialog.add(Confirm, {
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
        // No name sent: the shop picks one nobody has ("Demo (copy) 2").
        this.run(
            () => this.orm.call(M.version, "copy", [parseInt(page.id, 10)]),
            _t("Copied. Edit it, then switch it on when you are ready.")
        );
    }

    rename(page) {
        this.dialog.add(NamePrompt, renameProps(page, async (name) => {
            await this.orm.write(M.version, [parseInt(page.id, 10)], { name });
            await this.load();
            this.notification.add(_t('Renamed to "%s".', name), { type: "success" });
        }));
    }

    /** A new page from what the shop sells, opened to look over. Not switched
        on, so nothing shoppers see changes until somebody presses Switch on. */
    async createFromProducts() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const id = await this.orm.call(M.version, "mart369_create_from_products", []);
            this.edit({ id });
        } catch (err) {
            this.notification.add(
                err?.data?.message || err?.message || _t("That did not work."),
                { type: "danger" }
            );
        } finally {
            this.state.busy = false;
        }
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
            onConfirm: async (name) => {
                await this.orm.call(M.version, "copy", [parseInt(from.id, 10)], { default: { name } });
                await this.load();
                this.notification.add(
                    _t('"%s" created. Edit it, then switch it on when you are ready.', name),
                    { type: "success" }
                );
            },
        });
    }

    remove(page) {
        this.dialog.add(Confirm, {
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
        this.dialog.add(Confirm, {
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
