/**
 * The 369 Wallets, as the app's console draws them.
 *
 * The twin of /admin/wallets. It answers "how much of this money is ours" -
 * a wallet balance is money the shop has already been paid and still owes,
 * and the total of them is a liability rather than takings.
 *
 * **Read-only, deliberately.** The only thing that moves a balance is
 * `_mart369_move`, called by a top-up, an order, a refund or a reward - each
 * a thing that actually happened, each leaving a row the customer can see in
 * their own app. A button here that credited a wallet would be money paid out
 * with no approval, no cap and no second pair of eyes, on a screen fenced by
 * the group that also edits the website. `loyalty.card.write()` would refuse
 * a raw balance write anyway; the safety is that there is nothing to call.
 *
 * The one alarm is **out of step**: a wallet whose balance does not equal its
 * own movements. That is a bug, not something a customer did, and nothing
 * here offers to "recalculate" it - writing the balance to match the ledger
 * would destroy the evidence of whatever went wrong.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const MODEL = "loyalty.card";

const TILES = [
    { key: "wallets", tab: "all", label: _t("Wallets") },
    { key: "held", label: _t("Money we hold"), flat: true },
    { key: "biggest", label: _t("Largest balance"), flat: true },
    { key: "broken", tab: "broken", label: _t("Out of step"), bad: true },
];

const TABS = [
    { key: "all", label: _t("All"), badge: "all" },
    { key: "money", label: _t("With money"), badge: "money" },
    { key: "empty", label: _t("Empty"), badge: "empty" },
    { key: "broken", label: _t("Out of step"), badge: "broken" },
];

/* The four kinds of movement, in the customer's own words - these are the
   same rows they see in the app, so they must read the same way. */
const KINDS = {
    add: { label: _t("Added"), cls: "wd-p-green", sign: "+" },
    spend: { label: _t("Spent"), cls: "wd-p-grey", sign: "-" },
    refund: { label: _t("Refunded"), cls: "wd-p-blue", sign: "+" },
    reward: { label: _t("Reward"), cls: "wd-p-violet", sign: "+" },
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

/**
 * One wallet's movements.
 *
 * The rows are `loyalty.history._mart369_serialize()` verbatim - the same six
 * fields the customer sees in their own app. Staff reading a different story
 * about the same money is its own kind of lie.
 */
export class LedgerDialog extends Component {
    static template = "mart369_payment.LedgerDialog";
    static components = { Dialog };
    static props = {
        close: { type: Function },
        card: { type: Object },
        load: { type: Function },
    };

    setup() {
        this.state = useState({
            card: this.props.card,
            moves: [],
            before: null,
            loading: true,
            error: "",
        });
        onWillStart(() => this.more());
    }

    async more() {
        this.state.loading = true;
        try {
            const page = await this.props.load(this.state.before);
            this.state.card = page.card || this.state.card;
            this.state.moves = this.state.moves.concat(page.moves || []);
            this.state.before = page.before || null;
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    kindLabel(kind) {
        return KINDS[kind]?.label || kind;
    }

    kindClass(kind) {
        return KINDS[kind]?.cls || "wd-p-grey";
    }

    sign(kind) {
        return KINDS[kind]?.sign || "";
    }

    ago(ms) {
        return ago(ms);
    }
}

export class WalletDesk extends Component {
    static template = "mart369_payment.WalletDesk";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");

        this.TILES = TILES;
        this.TABS = TABS;

        this.state = useState({
            tab: "all",
            q: "",
            rows: [],
            counts: null,
            tiles: {},
            loading: true,
            error: "",
        });

        this.search = useDebounced((ev) => {
            this.state.q = ev.target.value.trim();
            this.load();
        }, 300);

        onWillStart(() => this.load());
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

    pick(tab) {
        if (!tab) {
            return;
        }
        this.state.tab = tab;
        this.load();
    }

    tabCount(tab) {
        return tab.badge ? this.state.counts?.[tab.badge] ?? null : null;
    }

    tileValue(tile) {
        return this.state.tiles?.[tile.key] ?? 0;
    }

    tileNote(tile) {
        const t = this.state.tiles || {};
        if (tile.key === "held") {
            return _t("Already paid for, and still owed");
        }
        if (tile.key === "biggest") {
            return t.biggest_who || "";
        }
        if (tile.key === "broken") {
            return t.broken
                ? _t("A bug, not a customer action")
                : _t("Every balance matches its history");
        }
        return _t("Show these");
    }

    openLedger(row) {
        this.dialog.add(LedgerDialog, {
            card: row,
            load: (before) =>
                this.orm.call(MODEL, "mart369_admin_ledger", [row.id], {
                    before: before || null,
                }),
        });
    }

    allViews() {
        this.action.doAction("mart369_payment.action_mart369_wallets");
    }

    // --------------------------------------------------------------- drawing

    kindLabel(kind) {
        return KINDS[kind]?.label || kind;
    }

    ago(ms) {
        return ago(ms);
    }
}

registry.category("actions").add("mart369_payment.wallets", WalletDesk);
