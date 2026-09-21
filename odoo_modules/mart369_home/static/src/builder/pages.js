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
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "./builder";

const M = { version: "mart369.home.version" };

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

    switchOn(page) {
        this.run(
            () => this.orm.call(M.version, "action_mart369_make_current", [parseInt(page.id, 10)]),
            _t("Switched on. This is the everyday page now.")
        );
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
        this.duplicate(from);
    }

    remove(page) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete this page?"),
            body: _t(
                "“%s” and everything on it goes for good. This is not the Trash - there is no putting it back.",
                page.name
            ),
            confirmLabel: _t("Delete page"),
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
