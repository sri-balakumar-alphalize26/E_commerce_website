/**
 * The coupons desk - 369 Mart > Coupons.
 *
 * The twin of the app's console screen (components/admin/AdminMore.jsx), and
 * the sibling of the deals desk next door. Until now Coupons was the one menu
 * in the suite that opened a stock Odoo list and form: fine for editing a row,
 * useless for the question somebody actually arrives with, which is "why is
 * this code not working for a customer who is standing in front of me".
 *
 * That question is why `live` exists and why it is the server's. Switched on
 * is not the same as usable - a code can be on and not started, on and
 * expired, or on and used up - and `_mart369_admin_serialize` works that out.
 * This screen prints it and says which of the three it is; it never decides.
 *
 * Reading is one call, `mart369_admin_list`, the same one the console makes,
 * so the two cannot disagree about a count. Writing goes through
 * `mart369_admin_save` and `mart369_admin_delete` on the model rather than the
 * HTTP routes the console uses, so the duplicate-code check and the date
 * validation have one implementation behind both screens.
 *
 * Deleting is offered but rarely allowed, and that is deliberate: an order
 * that used a code points at it, so the database refuses. The confirmation
 * says so in advance rather than letting somebody press it and read a stack
 * trace.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { Confirm } from "@mart369/ui/confirm";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "@mart369/ui/icon";
import { Pick } from "@mart369/ui/pick";
import { Search } from "@mart369/ui/search";
import { Switch } from "@mart369/ui/switch";
import { Empty } from "@mart369/ui/empty";
import { Tabs } from "@mart369/ui/tabs";

const MODEL = "mart369.coupon";

/* Tile -> which tab it shows. "Nearly used up" is the one worth having: a
   code that is on, inside its window and almost spent is about to start
   refusing customers, and nothing else on the screen would say so. */
const TILES = [
    { key: "all", tab: "all", label: _t("All coupons"), icon: "ticket" },
    { key: "live", tab: "live", label: _t("Working now"), icon: "check" },
    { key: "paused", tab: "paused", label: _t("Switched off"), icon: "eye-off" },
    { key: "nearlyUsedUp", tab: "nearly", label: _t("Nearly used up"), icon: "info", warn: true },
];

const TABS = [
    { key: "all", label: _t("All"), badge: "all" },
    { key: "live", label: _t("Working now"), badge: "live" },
    { key: "paused", label: _t("Switched off"), badge: "paused" },
    { key: "nearly", label: _t("Nearly used up"), badge: "nearlyUsedUp" },
];

function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

/* --------------------------------------------------------------- the form */

/**
 * One coupon, opened.
 *
 * Holds its own draft, so typing never rewrites the card behind it and
 * Cancel really does throw the change away. Nothing reaches the shop until
 * Save, and a refusal leaves the dialog open with the message in it - closing
 * would discard what somebody just typed, which is the worst moment to do it.
 */
export class CouponDialog extends Component {
    static template = "mart369_cart.CouponDialog";
    static components = { Dialog, Pick, Switch };
    static props = {
        coupon: { type: [Object, { value: null }], optional: true },
        kinds: { type: Array },
        groups: { type: Array },
        currency: { type: [Object, { value: null }], optional: true },
        onSaved: { type: Function },
        close: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        const c = this.props.coupon;
        this.state = useState({
            draft: c
                ? {
                    code: c.code, title: c.title, note: c.note,
                    kind: c.kind, value: c.value,
                    max_off: c.maxOff, min_spend: c.minSpend,
                    group: c.group || "",
                    active: c.active,
                    starts_on: c.startsOn || "", ends_on: c.endsOn || "",
                    limit_total: c.limitTotal, limit_per_customer: c.limitPerCustomer,
                }
                : {
                    code: "", title: "", note: "",
                    kind: "flat", value: 0,
                    max_off: 0, min_spend: 0,
                    group: "",
                    active: true,
                    starts_on: "", ends_on: "",
                    limit_total: 0, limit_per_customer: 0,
                },
            busy: false,
            error: "",
            field: "",
        });
    }

    edit(key, ev) {
        this.set(key, ev.target.value);
    }

    /** The same write, given the value rather than the event an input carried
     *  it in - which is what a component hands back. */
    set(key, value) {
        const numbers = ["value", "max_off", "min_spend"];
        const counts = ["limit_total", "limit_per_customer"];
        if (numbers.includes(key)) {
            this.state.draft[key] = parseFloat(value || 0) || 0;
        } else if (counts.includes(key)) {
            this.state.draft[key] = parseInt(value || 0, 10) || 0;
        } else {
            this.state.draft[key] = value;
        }
        this.state.error = "";
        this.state.field = "";
    }

    get kindOptions() {
        return this.props.kinds.map(([value, label]) => [String(value), label]);
    }

    /** Everybody, or one of the shop's own groups. The empty first line is
     *  "anybody", which is what no group means. */
    get groupOptions() {
        return [
            ["", _t("Anybody with the code")],
            ...this.props.groups.map(([value, label]) => [String(value), label]),
        ];
    }

    get isPercent() {
        return this.state.draft.kind === "percent";
    }

    get title() {
        return this.props.coupon ? _t("Edit coupon") : _t("New coupon");
    }

    /** Enough to be worth sending. The server checks properly - this only
     *  keeps the button from offering an obviously empty save. */
    get canSave() {
        const d = this.state.draft;
        return !!(d.code || "").trim() && !!(d.title || "").trim() && d.value > 0;
    }

    async save() {
        if (!this.canSave || this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        const values = { ...this.state.draft };
        values.code = (values.code || "").trim().toUpperCase();
        values.title = (values.title || "").trim();
        try {
            await this.orm.call(MODEL, "mart369_admin_save", [
                this.props.coupon ? this.props.coupon.id : false,
                values,
            ]);
            this.props.onSaved();
            this.props.close();
        } catch (err) {
            // Stays open with the message in it. The code being taken is the
            // usual reason, and it is the one thing somebody has to change.
            this.state.error = message(err);
        } finally {
            this.state.busy = false;
        }
    }
}

/* --------------------------------------------------------------- the list */

export class CouponDesk extends Component {
    static template = "mart369_cart.CouponDesk";
    static components = { Layout, Icon, Search, Switch, Empty, Tabs };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.TILES = TILES;
        this.TABS = TABS;

        this.state = useState({
            coupons: [],
            counts: {},
            redemptions: 0,
            currency: null,
            kinds: [],
            groups: [],
            tab: "all",
            q: "",
            loading: true,
            busy: false,
            error: "",
        });

        /* The box writes to state at once, so typing is never swallowed by
           the wait. Filtering is local here - the whole list arrives in one
           call - so there is nothing to debounce but the redraw. */
        onWillStart(() => this.load());
    }

    // ------------------------------------------------------------- reading

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(MODEL, "mart369_admin_list", []);
            this.state.coupons = data.coupons || [];
            this.state.counts = data.counts || {};
            this.state.redemptions = data.redemptions || 0;
            this.state.currency = data.currency || null;
            this.state.kinds = data.kinds || [];
            this.state.groups = data.groups || [];
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    /* Read-after-write, like every other screen in the suite. `live` and the
       tile numbers are the server's, and guessing them is how a screen starts
       lying about which codes still work. A refusal reloads too, because it
       usually means this screen was stale. */
    async run(fn, ok) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await fn();
            if (ok) {
                this.notification.add(ok, { type: "success" });
            }
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
        } finally {
            this.state.busy = false;
            await this.load();
        }
    }

    // ----------------------------------------------------------- filtering

    pick(tab) {
        this.state.tab = tab;
    }

    onSearch(q) {
        this.state.q = q;
    }


    /** The tabs as the kit's strip takes them: [key, label, count] triples.
     *  `tabCount` returns null for a tab that counts nothing, and the strip
     *  draws no badge for null - which is how a tab stays quiet. */
    get tabItems() {
        return this.TABS.map((tab) => [tab.key, tab.label, this.tabCount(tab)]);
    }

    tabCount(tab) {
        return tab.badge ? this.state.counts[tab.badge] ?? 0 : null;
    }

    tileValue(tile) {
        return this.state.counts[tile.key] ?? 0;
    }

    /** The tab, then the search. Both are local: the whole list is already
     *  here, and a round trip to hide four rows would only make it slower. */
    get rows() {
        const q = this.state.q.trim().toLowerCase();
        return this.state.coupons.filter((c) => {
            if (this.state.tab === "live" && !c.live) {
                return false;
            }
            if (this.state.tab === "paused" && c.active) {
                return false;
            }
            if (this.state.tab === "nearly" &&
                !(c.live && c.limitTotal && c.usedCount >= c.limitTotal * 0.9)) {
                return false;
            }
            if (!q) {
                return true;
            }
            return (
                (c.code || "").toLowerCase().includes(q) ||
                (c.title || "").toLowerCase().includes(q) ||
                (c.note || "").toLowerCase().includes(q)
            );
        });
    }

    // ------------------------------------------------------------- writing

    toggle(coupon) {
        return this.run(
            () => this.orm.call(MODEL, "mart369_admin_save", [
                coupon.id, { active: !coupon.active },
            ]),
            coupon.active
                ? _t("%s is switched off", coupon.code)
                : _t("%s is working again", coupon.code)
        );
    }

    open(coupon) {
        this.dialog.add(CouponDialog, {
            coupon: coupon || null,
            kinds: this.state.kinds,
            groups: this.state.groups,
            currency: this.state.currency,
            onSaved: () => this.load(),
        });
    }

    /** Offered, rarely allowed, and the question says so. An order that used
     *  a code points at it, so the database refuses - and being told that
     *  before pressing is better than a refusal afterwards. */
    askDelete(coupon) {
        this.dialog.add(Confirm, {
            title: _t("Delete %s?", coupon.code),
            body: coupon.usedCount
                ? _t(
                    "It has been used %s times, so the shop will keep it and " +
                    "ask you to switch it off instead.",
                    coupon.usedCount
                )
                : _t("Nobody has used it, so it goes for good."),
            confirmLabel: _t("Delete coupon"),
            confirm: () => this.run(
                () => this.orm.call(MODEL, "mart369_admin_delete", [coupon.id]),
                _t("%s is gone", coupon.code)
            ),
            cancel: () => {},
        });
    }

    copy(coupon) {
        // `clipboard` is missing on an insecure origin, which a self-hosted
        // Odoo often is. Say so rather than failing silently.
        if (!navigator.clipboard) {
            this.notification.add(_t("This browser will not let the page copy."),
                                  { type: "warning" });
            return;
        }
        navigator.clipboard.writeText(coupon.code);
        this.notification.add(_t("%s copied", coupon.code), { type: "success" });
    }

    allViews() {
        this.action.doAction("mart369_cart.action_mart369_coupons");
    }

    // ------------------------------------------------------------- drawing

    money(amount) {
        const c = this.state.currency;
        const n = Number(amount || 0);
        const shown = n.toLocaleString(c?.locale || undefined, {
            minimumFractionDigits: c ? c.decimals : 2,
            maximumFractionDigits: c ? c.decimals : 2,
        });
        if (!c?.symbol) {
            return shown;
        }
        return c.position === "after" ? `${shown} ${c.symbol}` : `${c.symbol}${shown}`;
    }

    /** What the code takes off, in the shop's words. */
    worth(coupon) {
        if (coupon.kind === "percent") {
            const off = _t("%s%% off", coupon.value);
            return coupon.maxOff ? `${off} · ${_t("up to %s", this.money(coupon.maxOff))}` : off;
        }
        return _t("%s off", this.money(coupon.value));
    }

    /** Why a switched-on code is still not working. The server already said
     *  it is not `live`; this only names which of the reasons it is. */
    why(coupon) {
        if (!coupon.active) {
            return _t("switched off");
        }
        if (coupon.live) {
            return "";
        }
        const today = new Date().toISOString().slice(0, 10);
        if (coupon.startsOn && coupon.startsOn > today) {
            return _t("starts %s", coupon.startsOn);
        }
        if (coupon.endsOn && coupon.endsOn < today) {
            return _t("ended %s", coupon.endsOn);
        }
        if (coupon.limitTotal && coupon.usedCount >= coupon.limitTotal) {
            return _t("used up");
        }
        return _t("not working");
    }

    used(coupon) {
        return coupon.limitTotal
            ? _t("%s of %s used", coupon.usedCount, coupon.limitTotal)
            : _t("%s used", coupon.usedCount);
    }

    /** How far through its allowance, as a width. Nothing when there is no
     *  cap, because a bar with no end is not measuring anything. */
    usedPct(coupon) {
        if (!coupon.limitTotal) {
            return 0;
        }
        return Math.min(100, Math.round((coupon.usedCount / coupon.limitTotal) * 100));
    }
}

registry.category("actions").add("mart369_cart.coupons", CouponDesk);
