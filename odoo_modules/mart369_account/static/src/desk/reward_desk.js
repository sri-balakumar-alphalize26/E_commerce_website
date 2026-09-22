/**
 * 369 Mart rewards, as the list the app's console draws.
 *
 * The twin of /admin/rewards, and the sibling of the reviews desk next door.
 * It answers "what have we paid out, and what is still waiting to be opened".
 * The list it replaces answers "show me the cards", and keeps what this does
 * not try to do: grouping, the form, the sparkline strip and exporting.
 *
 * **Read-only, on purpose.** A scratch card is money - opening one credits the
 * 369 Wallet out of the shop's pocket - so there is nothing here that mints,
 * edits or voids one, and no route behind one either. Unlike the other desks
 * this has no `run()` and no confirmation dialog, because there is no write to
 * confirm.
 *
 * Two rules carried from the console:
 *
 *  - **The tiles count everything, never the filtered rows.** A "waiting to be
 *    opened" that fell when somebody typed in the search box would stop
 *    answering the only question it is there to answer.
 *  - **Money is formatted, never glued together.** The server sends the number
 *    and the currency separately; a card keeps the currency it was minted in,
 *    so a prize already promised is not revalued by a later change of company
 *    currency, and two currencies are never added into one total.
 *
 * `Pick` is imported from the orders desk rather than copied - mart369_account
 * depends on mart369_order, so it is already in the bundle.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

import { Pick } from "@mart369_order/desk/order_desk";

const MODEL = "mart369.scratch";

/* Each tile sets the tab, so the strip is the filter rather than a read-out
   above one. "Paid out" is the exception - there is no tab for a sum. */
const TILES = [
    { key: "all", tab: "all", label: _t("Cards minted"), icon: "fa-gift" },
    { key: "unscratched", tab: "unscratched", label: _t("Waiting to be opened"), icon: "fa-inbox", warn: true },
    { key: "paidAmount", label: _t("Paid out"), icon: "fa-money", money: true, flat: true },
    { key: "nothing", tab: "nothing", label: _t("Won nothing"), icon: "fa-ban" },
];

const TABS = [
    { key: "unscratched", label: _t("Waiting to be opened"), badge: "unscratched" },
    { key: "cash", label: _t("Cash won"), badge: "cash" },
    { key: "coupon", label: _t("Coupon won"), badge: "coupon" },
    { key: "nothing", label: _t("Won nothing"), badge: "nothing" },
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

/**
 * Format what the shop sent, never glue on a symbol of our own. The amount and
 * its currency travel together, because a card carries the currency it was
 * minted in and a later change must not rewrite an old prize. Same rule as the
 * returns desk and lib/money.js.
 */
function money(amount, currency) {
    const value = Number(amount) || 0;
    const decimals = currency?.decimals ?? 2;
    const shown = value.toLocaleString(currency?.locale, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
    if (!currency?.symbol) {
        return shown;
    }
    return currency.position === "after"
        ? `${shown} ${currency.symbol}`
        : `${currency.symbol}${shown}`;
}

function ago(ms) {
    if (!ms) {
        return "";
    }
    const mins = Math.round((Date.now() - ms) / 60000);
    if (mins < 60) {
        return _t("%s min ago", Math.max(1, mins));
    }
    const hours = Math.round(mins / 60);
    return hours < 24 ? _t("%s h ago", hours) : _t("%s d ago", Math.round(hours / 24));
}

export class RewardDesk extends Component {
    static template = "mart369_account.RewardDesk";
    static components = { Layout, Pick };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.TILES = TILES;
        this.TABS = TABS;

        this.state = useState({
            tab: "unscratched",
            q: "",
            limit: PAGE,
            rows: [],
            total: 0,
            counts: null,
            paidAmount: 0,
            currency: null,
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
            this.state.rows = page.cards || [];
            this.state.total = page.total || 0;
            this.state.counts = page.counts || null;
            this.state.paidAmount = page.paidAmount || 0;
            this.state.currency = page.currency || null;
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    pick(tab) {
        if (!tab) {
            return; // the paid-out tile, which filters nothing
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
        if (tile.money) {
            return money(this.state.paidAmount, this.state.currency);
        }
        return this.state.counts?.[tile.key] ?? 0;
    }

    /** What the row leads with: the prize, in words a person reads. */
    prize(row) {
        if (row.reward === "cash") {
            return money(row.amount, this.state.currency);
        }
        return row.reward === "coupon" ? row.coupon || _t("A coupon") : _t("No prize");
    }

    /** The list, for what this screen does not do: grouping, the form, the
        sparkline strip and exporting. */
    moreViews() {
        this.action.doAction("mart369_account.action_mart369_rewards");
    }

    ago(ms) { return ago(ms); }
}

registry.category("actions").add("mart369_account.rewards", RewardDesk);
