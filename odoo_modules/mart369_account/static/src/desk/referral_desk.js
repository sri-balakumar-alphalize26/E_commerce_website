/**
 * 369 Mart referrals, as the app's console draws them.
 *
 * The twin of /admin/referrals, and the sibling of the reviews desk beside it.
 * It answers "is this worth running" - how many invites went out, how many
 * turned into customers, and what that has cost - which the kanban next door
 * cannot say without counting columns by eye.
 *
 * Everything it reads is `mart369_admin_list` on the model, the same one call
 * the console makes. Nothing here is a second implementation of anything.
 *
 * Two rules carried from the console, both load-bearing:
 *
 *  - **The tiles count everything, never the filtered rows.** A "Joined 4"
 *    that dropped to 0 because somebody typed in the search box would be
 *    useless for deciding anything.
 *  - **An invite's three states are not buttons.** `invited`, `joined` and
 *    `ordered` are each a claim about something that really happened - a
 *    signup, a paid order - and a staff member who could set "Rewarded" by
 *    hand would be paying a reward for an order nobody placed. The only write
 *    on this screen is what the *next* reward is worth, because that is a
 *    marketing decision rather than a fact.
 *
 * The kanban and list keep what this does not try to do: grouping, the form
 * and exporting.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const MODEL = "mart369.referral";

/* Each tile sets the tab, so the strip is the filter rather than a read-out
   above one. Paid out is the exception - there is no "paid" tab to show, so it
   stays a plain figure and never looks clickable. */
const TILES = [
    { key: "invited", tab: "invited", label: _t("Invited"), icon: "fa-paper-plane" },
    { key: "joined", tab: "joined", label: _t("Joined"), icon: "fa-user-plus" },
    { key: "ordered", tab: "ordered", label: _t("Rewarded"), icon: "fa-gift", good: true },
    { key: "paid", label: _t("Paid out"), icon: "fa-money", money: true },
];

const TABS = [
    { key: "all", label: _t("All"), badge: "all" },
    { key: "invited", label: _t("Waiting"), badge: "invited" },
    { key: "joined", label: _t("Joined"), badge: "joined" },
    { key: "ordered", label: _t("Rewarded"), badge: "ordered" },
];

const STATES = {
    invited: { label: _t("Waiting"), cls: "rf-p-grey" },
    joined: { label: _t("Joined"), cls: "rf-p-blue" },
    ordered: { label: _t("Rewarded"), cls: "rf-p-green" },
};

const POLL_MS = 60000;

/** Odoo wraps a UserError a couple of ways; dig the sentence out of whichever
 *  one arrived. The same helper the other desks carry. */
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

/**
 * What the next referral pays.
 *
 * A dialog rather than a field on the strip because it is a shop-wide number
 * that quietly changes what everybody is paid, and one nudged by a stray
 * keystroke on a screen somebody left open is worth more than the dialog
 * costs. It says what it does not change, too: rewards already paid keep what
 * they were worth.
 */
export class RewardDialog extends Component {
    static template = "mart369_account.RewardDialog";
    static components = { Dialog };
    static props = {
        close: { type: Function },
        reward: { type: [Number, String] },
        formatted: { type: String, optional: true },
        onSave: { type: Function },
    };

    setup() {
        this.state = useState({
            value: String(this.props.reward ?? 0),
            busy: false,
            error: "",
        });
    }

    get amount() {
        return Number(this.state.value);
    }

    get canSave() {
        return Number.isFinite(this.amount) && this.amount >= 0;
    }

    edit(ev) {
        this.state.value = ev.target.value;
        this.state.error = "";
    }

    async save() {
        if (!this.canSave || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.props.onSave(this.amount);
            this.props.close();
        } catch (err) {
            // Shown on the dialog rather than as a toast behind it, so the
            // number that was refused is still on screen beside the reason.
            this.state.error = message(err);
        } finally {
            this.state.busy = false;
        }
    }
}

export class ReferralDesk extends Component {
    static template = "mart369_account.ReferralDesk";
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
            tab: "all",
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

        // Somebody leaves this open on a second monitor, and an invite moves
        // on its own when a customer signs up or pays. Quiet, so it never
        // flashes the loading line.
        this.timer = setInterval(() => {
            if (!this.state.busy) {
                this.load({ quiet: true });
            }
        }, POLL_MS);
        onWillUnmount(() => clearInterval(this.timer));
    }

    // -------------------------------------------------------------- reading

    async load({ quiet = false } = {}) {
        if (!quiet) {
            this.state.loading = true;
        }
        try {
            const page = await this.orm.call(MODEL, "mart369_admin_list", [], {
                state: this.state.tab,
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
            return; // the paid-out tile, which filters nothing
        }
        this.state.tab = tab;
        this.load();
    }

    tabCount(tab) {
        return tab.badge ? this.state.counts?.[tab.badge] ?? null : null;
    }

    /** Straight off the server counts, never `state.rows.length`. See the
     *  first rule in the file header. */
    tileValue(tile) {
        if (tile.money) {
            // The formatted string, because the tile is read rather than
            // counted. The console does its own formatting off `paid_amount`.
            return this.state.tiles.paid || "0";
        }
        return this.state.counts?.[tile.key] ?? 0;
    }

    // --------------------------------------------------------------- writing

    /** The one write on this screen, and it changes no invite. */
    askReward() {
        this.dialog.add(RewardDialog, {
            reward: this.state.tiles.reward_amount ?? 0,
            formatted: this.state.tiles.reward || "",
            onSave: async (amount) => {
                this.state.busy = true;
                try {
                    await this.orm.call(MODEL, "mart369_admin_set_reward", [amount]);
                    this.notification.add(_t("Saved."), { type: "success" });
                } finally {
                    this.state.busy = false;
                    await this.load({ quiet: true });
                }
            },
        });
    }

    /** The kanban and list, for what this screen does not do: grouping, the
        form and exporting. */
    allViews() {
        this.action.doAction("mart369_account.action_mart369_referrals");
    }

    // --------------------------------------------------------------- drawing

    stateLabel(key) {
        return STATES[key]?.label || key;
    }

    stateClass(key) {
        return STATES[key]?.cls || "rf-p-grey";
    }

    /** Letters only. An invited friend's name is free text a customer typed,
     *  so it arrives with brackets and punctuation in it - splitting on spaces
     *  alone drew "Meera (an example)" as "M(". */
    initials(name) {
        const words = (name || "").match(/[\p{L}\p{N}]+/gu) || [];
        return words.slice(0, 2).map((part) => part[0].toUpperCase()).join("") || "?";
    }

    ago(ms) {
        return ago(ms);
    }
}

registry.category("actions").add("mart369_account.referrals", ReferralDesk);
