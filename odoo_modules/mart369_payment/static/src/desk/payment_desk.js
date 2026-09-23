/**
 * Payments, as the app's console draws them.
 *
 * The twin of /admin/payments, and the sibling of the orders and referrals
 * desks. It answers "did the money arrive, and if not where is it" - which
 * the list next door cannot put on one screen.
 *
 * **Nothing on this screen writes anything, and that is the point.** A
 * payment becomes true in `_post_process`, after the provider's own webhook
 * has verified the signature; a button here that marked one paid would be a
 * claim about money nobody received. The one settlement that happens away
 * from a gateway is cash at the door, and it keeps its button on the Odoo
 * form, pressed by somebody who knows whether the rider was handed the notes.
 * Refunds belong to Returns.
 *
 * Three things the tiles are careful about, because each was wrong before:
 *
 *  - **Money in today** follows `last_state_change`, not `write_date`, which
 *    moves whenever anything brushes past a row.
 *  - An order settled **entirely from the wallet** is not counted again; that
 *    money was counted when it was topped up.
 *  - **Settled** says what it is out of, because payments still waiting are
 *    not in the denominator.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const MODEL = "payment.transaction";

const TILES = [
    { key: "collected", tab: "paid", label: _t("Money in today"), money: true },
    { key: "success_pct", label: _t("Settled"), pct: true, flat: true },
    { key: "pending", tab: "waiting", label: _t("Waiting on a bank"), warn: true },
    { key: "cash", tab: "cash", label: _t("Cash to collect"), money: true },
];

const TABS = [
    { key: "all", label: _t("All"), badge: "all" },
    { key: "paid", label: _t("Paid"), badge: "paid" },
    { key: "waiting", label: _t("Waiting on a bank"), badge: "waiting" },
    { key: "cash", label: _t("Cash to collect"), badge: "cash" },
    { key: "failed", label: _t("Failed"), badge: "failed" },
];

/* Odoo's six states in the words a shopkeeper uses. `authorized` and `draft`
   keep their own pill rather than being folded into Paid: a payment a gateway
   is holding, and one the customer never submitted, are not money in. */
const STATES = {
    draft: { label: _t("Never sent"), cls: "pd-p-grey" },
    pending: { label: _t("Waiting"), cls: "pd-p-amber" },
    authorized: { label: _t("Held by the bank"), cls: "pd-p-violet" },
    done: { label: _t("Paid"), cls: "pd-p-green" },
    cancel: { label: _t("Cancelled"), cls: "pd-p-grey" },
    error: { label: _t("Failed"), cls: "pd-p-red" },
};

const KINDS = {
    order: _t("Order"),
    topup: _t("Wallet top-up"),
    validation: _t("Saving a card"),
};

const POLL_MS = 30000;

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

export class PaymentDesk extends Component {
    static template = "mart369_payment.PaymentDesk";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.TILES = TILES;
        this.TABS = TABS;

        this.state = useState({
            tab: "all",
            kind: "",
            q: "",
            rows: [],
            counts: null,
            tiles: {},
            loading: true,
            busy: false,
            error: "",
        });

        this.search = useDebounced((ev) => {
            this.state.q = ev.target.value.trim();
            this.load();
        }, 300);

        onWillStart(() => this.load());

        // Money moves while somebody is looking at this, so it polls faster
        // than the screens where nothing changes on its own.
        this.timer = setInterval(() => this.load({ quiet: true }), POLL_MS);
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
                kind: this.state.kind || null,
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

    // ------------------------------------------------------------ filtering

    pick(tab) {
        if (!tab) {
            return; // the settled tile, which filters nothing
        }
        this.state.tab = tab;
        this.load();
    }

    setKind(kind) {
        this.state.kind = kind;
        this.load();
    }

    get kindOptions() {
        return [
            ["", _t("Orders and top-ups")],
            ["order", _t("Orders")],
            ["topup", _t("Top-ups")],
        ];
    }

    tabCount(tab) {
        return tab.badge ? this.state.counts?.[tab.badge] ?? null : null;
    }

    tileValue(tile) {
        const tiles = this.state.tiles || {};
        if (tile.pct) {
            return `${tiles.success_pct ?? 0}%`;
        }
        return tiles[tile.key] ?? 0;
    }

    /** The sub-line under each tile. These say what the number is *not*, which
     *  is where all three of this screen's old mistakes lived. */
    tileNote(tile) {
        const t = this.state.tiles || {};
        if (tile.key === "collected") {
            const paid = t.collected_count ?? 0;
            const wallet = t.from_wallet_count ?? 0;
            const line = _t("%s paid today", paid);
            /* Concatenated rather than one format string with two named
               placeholders: `_t` is translation, not printf, and a format it
               does not expand would be printed to the screen verbatim. */
            return wallet
                ? line + _t("; %s more settled from wallets, counted at top-up", wallet)
                : line;
        }
        if (tile.pct) {
            return _t("of %s that finished", t.success_of ?? 0);
        }
        if (tile.key === "pending") {
            return t.pending_oldest || _t("Nothing waiting");
        }
        if (tile.key === "cash") {
            return _t("%s at the door", t.cash_count ?? 0);
        }
        return "";
    }

    // --------------------------------------------------------------- drawing

    stateLabel(key) {
        return STATES[key]?.label || key;
    }

    stateClass(key) {
        return STATES[key]?.cls || "pd-p-grey";
    }

    kindLabel(key) {
        return KINDS[key] || key;
    }

    ago(ms) {
        return ago(ms);
    }

    /** Only when the reference really is an order. `mart369_order_ref` is
     *  text, so a link drawn for every row would 404 for half of them. */
    openOrder(row) {
        if (!row.orderId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "sale.order",
            res_id: row.orderId,
            views: [[false, "form"]],
        });
    }

    allViews() {
        this.action.doAction("mart369_payment.action_mart369_payments");
    }
}

registry.category("actions").add("mart369_payment.payments", PaymentDesk);
