/**
 * 369 Mart addresses, as the list the app's console draws.
 *
 * The twin of /admin/addresses, and the sibling of the rewards desk in
 * mart369_account. It answers "why did this not arrive" - a missing pincode,
 * no mobile number, no map pin - which the kanban it sits beside answers only
 * by colouring a row red.
 *
 * **Read-only, on purpose.** These are customers' home addresses, and the one
 * a customer has chosen is what Odoo ships to. Nothing here edits or removes
 * one, and there is no route behind such a thing either. Unlike the support
 * desk this has no `run()` and no confirmation dialog, because there is no
 * write to confirm. The kanban next door keeps the "Make default" button, for
 * the rare case where somebody really must.
 *
 * Two rules carried from the console:
 *
 *  - **The tiles count everything, never the filtered rows**, so "missing
 *    something" does not fall the moment somebody types in the search box.
 *  - **The gaps come from the server.** `mart369_gap_label` is worked out on
 *    the fly and cannot be searched or counted, so the payload sends the list
 *    of nouns and this only prints them - never recompute them here, or the
 *    two screens will disagree about what is missing.
 *
 * `Pick` is imported from the orders desk rather than copied - mart369_address
 * does not depend on mart369_order, so it is NOT available here; this desk
 * uses a plain search box and tabs instead.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const MODEL = "res.partner";

/* Each tile sets the tab, except the two that are figures with no tab of their
   own - "customers" and "missing something" cut across the tabs. */
const TILES = [
    { key: "all", tab: "all", label: _t("Addresses"), icon: "fa-map-marker" },
    { key: "customers", label: _t("Customers"), icon: "fa-users", flat: true },
    { key: "incomplete", label: _t("Missing something"), icon: "fa-exclamation-triangle", warn: true, flat: true },
    { key: "no_location", tab: "no_location", label: _t("No map pin"), icon: "fa-crosshairs" },
];

const TABS = [
    { key: "all", label: _t("All"), badge: "all" },
    { key: "no_pincode", label: _t("No pincode"), badge: "no_pincode" },
    { key: "no_mobile", label: _t("No mobile"), badge: "no_mobile" },
    { key: "no_location", label: _t("No map pin"), badge: "no_location" },
    { key: "archived", label: _t("Removed"), badge: "archived" },
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

export class AddressDesk extends Component {
    static template = "mart369_address.AddressDesk";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.TILES = TILES;
        this.TABS = TABS;

        this.state = useState({
            tab: "all",
            q: "",
            limit: PAGE,
            rows: [],
            total: 0,
            counts: null,
            customers: 0,
            incomplete: 0,
            loading: true,
            error: "",
        });

        this.search = useDebounced((ev) => {
            this.state.q = ev.target.value.trim();
            this.state.limit = PAGE;
            this.load();
        }, 300);

        onWillStart(() => this.load());

        // Slower than the working desks: nothing here is a queue somebody is
        // clearing, so a minute is soon enough.
        this.timer = setInterval(() => this.load({ quiet: true }), POLL_MS);
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
            this.state.rows = page.addresses || [];
            this.state.total = page.total || 0;
            this.state.counts = page.counts || null;
            this.state.customers = page.customers || 0;
            this.state.incomplete = page.incomplete || 0;
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
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

    /** Straight off the server's numbers, never `state.rows.length`. */
    tileValue(tile) {
        if (tile.key === "customers") {
            return this.state.customers;
        }
        if (tile.key === "incomplete") {
            return this.state.incomplete;
        }
        return this.state.counts?.[tile.key] ?? 0;
    }

    /** One line of address, as a person would read it out. */
    where(row) {
        return [row.name, row.line, row.city].filter(Boolean).join(" · ");
    }

    /** The kanban, for what this screen does not do: grouping, the form, and
        the one button that changes which address a customer ships to. */
    moreViews() {
        this.action.doAction("mart369_address.action_mart369_addresses");
    }
}

registry.category("actions").add("mart369_address.desk", AddressDesk);
