/**
 * The delivery desk - 369 Mart > Delivery & Pricing > Delivery.
 *
 * The twin of the app's console screen, and deliberately the same one: staff
 * who work in Odoo should not get a different answer to "what does delivery
 * cost" than staff who work in the console. Both read `mart369_admin_list` on
 * `mart369.delivery.rule`, so the two cannot drift apart.
 *
 * Three tabs, because three records decide one thing between them:
 *
 *  - **Fees** - what each storefront charges, and when it stops charging.
 *  - **Slots** - the windows the checkout offers, with their caps.
 *  - **Service areas** - the pincodes we reach, and how fast.
 *  - **Branches** - which branches do Quick, and how far each one reaches.
 *    An item is Quick only when such a branch is within reach of the
 *    customer's map pin and has it in stock; an address with no pin falls
 *    back to its pincode's area.
 *
 * What the three list views next door cannot say, and this does:
 *
 *  - **a storefront with no slot left open cannot be checked out of.** Six
 *    slots switched on and none of them Express is three screens away from
 *    anybody looking at the slot list, and the only place it shows is the
 *    customer's slot step, one step from the money.
 *  - **what the numbers mean together.** A fee of 30 and a free-above of 499
 *    are two cells in a list; "under 499.000 the basket is charged 30.000" is
 *    the sentence the customer effectively reads.
 *
 * Hours are edited as the numbers they are stored as - 18.5 is half past six
 * - with the time printed beside the box. The alternative is parsing English
 * back into a float on save, and then the thing typed and the thing Odoo
 * constrains to 0-24 are no longer the same thing.
 *
 * Nothing here deletes. A rule, a slot and an area are each pointed at by
 * orders that have gone out, so each is switched off instead.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Confirm } from "@mart369/ui/confirm";
import { Dialog } from "@web/core/dialog/dialog";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Switch } from "@mart369/ui/switch";
import { Icon } from "@mart369/ui/icon";

const M = {
    rule: "mart369.delivery.rule",
    slot: "mart369.delivery.slot",
    area: "mart369.service.area",
    branch: "stock.warehouse",
};

export const TABS = [
    { key: "fees", label: _t("Fees"), icon: "money" },
    { key: "slots", label: _t("Slots"), icon: "clock" },
    { key: "areas", label: _t("Service areas"), icon: "pin" },
    { key: "branches", label: _t("Branches"), icon: "store" },
];

/** Money, in whatever the shop quotes in. The same function the deals desk
 *  uses, for the same reason: the shop says which sign and where it goes. */
function format(amount, currency) {
    const n = Number(amount) || 0;
    const shown = n.toLocaleString(currency?.locale || undefined, {
        minimumFractionDigits: currency ? currency.decimals : 2,
        maximumFractionDigits: currency ? currency.decimals : 2,
    });
    if (!currency?.symbol) {
        return shown;
    }
    return currency.position === "after"
        ? `${shown} ${currency.symbol}`
        : `${currency.symbol}${shown}`;
}

/** 18.5 -> "6:30 PM". The same arithmetic as `_mart369_clock` on the model
 *  and `clock()` in the console. It only ever prints, never parses, so the
 *  three cannot disagree about what a valid hour is. */
export function clock(value) {
    const n = Number(value);
    if (!isFinite(n)) {
        return "";
    }
    const hour = Math.floor(n) % 24;
    const minute = Math.round((n - Math.floor(n)) * 60);
    const suffix = hour < 12 ? "AM" : "PM";
    const shown = hour % 12 || 12;
    return minute ? `${shown}:${String(minute).padStart(2, "0")} ${suffix}` : `${shown} ${suffix}`;
}

/** An empty box means 0, not NaN. Typing over a number goes through "" on
 *  the way, and a NaN saved comes back as a complaint about a field somebody
 *  is in the middle of filling in. */
function num(value) {
    return value === "" || value === null || value === undefined ? 0 : Number(value);
}

function message(err, fallback) {
    return (
        err?.data?.message || err?.message?.data?.message || err?.message || fallback
    );
}

/**
 * The slot editor, in a dialog.
 *
 * Holds its own draft so typing never rewrites the row behind it, and nothing
 * reaches the shop until Save.
 */
export class SlotDialog extends Component {
    static template = "mart369_cart.SlotDialog";
    static components = { Dialog, Switch, Icon };
    static props = {
        slot: { type: [Object, { value: null }], optional: true },
        modes: { type: Array, optional: true },
        kinds: { type: Array, optional: true },
        onSaved: Function,
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        const s = this.props.slot;
        this.state = useState({
            draft: s
                ? {
                    id: s.id, mode: s.mode, kind: s.kind, key: s.key, top: s.top,
                    sub: s.sub, label: s.label, from_hour: s.fromHour,
                    to_hour: s.toHour, day_offset: s.dayOffset,
                    order_before: s.orderBefore, fee: s.fee, capacity: s.capacity,
                    sequence: s.sequence, active: s.active,
                }
                : {
                    id: null, mode: "quick", kind: "window", key: "", top: "Today",
                    sub: "", label: "", from_hour: 18, to_hour: 20, day_offset: 0,
                    order_before: 24, fee: 0, capacity: 0, sequence: 10, active: true,
                },
            error: "",
            busy: false,
        });
    }

    get isWindow() {
        return this.state.draft.kind === "window";
    }

    set(field, value) {
        this.state.draft[field] = value;
    }

    clock(value) {
        return clock(num(value));
    }

    async save() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        const d = this.state.draft;
        const values = {
            mode: d.mode, kind: d.kind, top: (d.top || "").trim(),
            sub: d.sub || "", label: d.label || "",
            from_hour: num(d.from_hour), to_hour: num(d.to_hour),
            day_offset: num(d.day_offset), order_before: num(d.order_before),
            fee: num(d.fee), capacity: num(d.capacity),
            sequence: num(d.sequence), active: d.active,
        };
        try {
            if (!values.top) {
                throw new Error(_t("A slot needs a heading - it is the bold line on the chip."));
            }
            if (d.id) {
                /* The key is not here on purpose. It is what the app calls
                   this slot and what an order stores when somebody books one,
                   so renaming it would orphan every order already out for
                   that window. */
                await this.orm.write(M.slot, [d.id], values);
            } else {
                const key = (d.key || "").trim();
                if (!key) {
                    throw new Error(_t("A slot needs a key. Keep it short: now, eve, tm, std."));
                }
                await this.orm.create(M.slot, [{ ...values, key }]);
            }
            this.props.close();
            await this.props.onSaved(d.id ? _t("Slot updated.") : _t("Slot added."));
        } catch (err) {
            /* The dialog stays open with the message in it: the model refuses
               a 25th hour in its own words, and closing would throw away
               everything just typed. */
            this.state.error = message(err, _t("That could not be saved."));
        } finally {
            this.state.busy = false;
        }
    }
}

/** The service-area editor. Short enough that it is all one panel. */
export class AreaDialog extends Component {
    static template = "mart369_cart.AreaDialog";
    static components = { Dialog, Switch, Icon };
    static props = {
        area: { type: [Object, { value: null }], optional: true },
        onSaved: Function,
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        const a = this.props.area;
        this.state = useState({
            draft: a
                ? {
                    id: a.id, pincode: a.pincode, name: a.name, quick: a.quick,
                    express: a.express, eta: a.eta, active: a.active,
                }
                : {
                    id: null, pincode: "", name: "", quick: true, express: true,
                    eta: "13 mins", active: true,
                },
            error: "",
            busy: false,
        });
    }

    set(field, value) {
        this.state.draft[field] = value;
    }

    async save() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        const d = this.state.draft;
        /* Whitespace out first: a pincode pasted from a spreadsheet arrives
           as "682 016", which is digits with a space in it, and refusing that
           teaches nobody anything. */
        const values = {
            pincode: (d.pincode || "").split(/\s+/).join(""),
            name: d.name || "", eta: d.eta || "",
            quick: !!d.quick, express: !!d.express, active: !!d.active,
        };
        try {
            if (!values.pincode) {
                throw new Error(_t("A pincode is digits only."));
            }
            if (d.id) {
                await this.orm.write(M.area, [d.id], values);
            } else {
                await this.orm.create(M.area, [values]);
            }
            this.props.close();
            await this.props.onSaved(d.id ? _t("Area updated.") : _t("Area added."));
        } catch (err) {
            this.state.error = message(err, _t("That could not be saved."));
        } finally {
            this.state.busy = false;
        }
    }
}

/** One branch's Quick settings. Branches themselves are made in Inventory,
 *  so this edits the four things delivery owns and nothing else. */
export class BranchDialog extends Component {
    static template = "mart369_cart.BranchDialog";
    static components = { Dialog, Switch, Icon };
    static props = {
        branch: Object,
        onSaved: Function,
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        const b = this.props.branch;
        this.state = useState({
            draft: {
                quick: b.quick,
                quickKm: b.quickKm ? String(b.quickKm) : "",
                lat: b.lat ?? "",
                lng: b.lng ?? "",
            },
            error: "",
            busy: false,
        });
    }

    set(field, value) {
        this.state.draft[field] = value;
    }

    /** A pin pasted from Google Maps arrives as "23.588, 58.3829" in one box. */
    pastePin(ev) {
        const parts = (ev.target.value || "").split(",").map((x) => x.trim());
        if (parts.length === 2 && parts.every((x) => x !== "" && !isNaN(Number(x)))) {
            this.state.draft.lat = parts[0];
            this.state.draft.lng = parts[1];
            ev.target.value = parts[0];
        } else {
            this.state.draft.lat = ev.target.value;
        }
    }

    async save() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        const d = this.state.draft;
        try {
            await this.orm.call(M.branch, "mart369_admin_save", [this.props.branch.id, {
                quick: !!d.quick, quickKm: d.quickKm, lat: d.lat, lng: d.lng,
            }]);
            this.props.close();
            await this.props.onSaved(_t("%s saved.", this.props.branch.name));
        } catch (err) {
            this.state.error = message(err, _t("That could not be saved."));
        } finally {
            this.state.busy = false;
        }
    }
}

export class DeliveryDesk extends Component {
    static template = "mart369_cart.DeliveryDesk";
    static components = { Layout, Switch, Icon };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.TABS = TABS;

        this.state = useState({
            rules: [],
            slots: [],
            areas: [],
            branches: [],
            modes: [],
            kinds: [],
            counts: {},
            currency: null,
            /* The panels' own copies of the fee numbers, so typing in one
               does not rewrite what the server last said - which is what
               "unsaved" is measured against. Keyed by rule id. */
            drafts: {},
            tab: "fees",
            loading: true,
            busy: false,
            error: "",
        });

        onWillStart(() => this.load());
    }

    // ------------------------------------------------------------- reading

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(M.rule, "mart369_admin_list", []);
            this.state.rules = data.rules;
            this.state.slots = data.slots;
            this.state.areas = data.areas;
            this.state.branches = data.branches || [];
            this.state.modes = data.modes;
            this.state.kinds = data.kinds;
            this.state.counts = data.counts;
            this.state.currency = data.currency;
            this.state.drafts = Object.fromEntries(
                data.rules.map((r) => [r.id, {
                    label: r.label, eta: r.eta, min_order: r.minOrder,
                    free_above: r.freeAbove, fee: r.fee, active: r.active,
                }])
            );
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err, _t("We could not reach the shop."));
        } finally {
            this.state.loading = false;
        }
    }

    /* Read-after-write, like every other screen in the suite. */
    async run(fn, ok) {
        if (this.state.busy) {
            return false;
        }
        this.state.busy = true;
        try {
            await fn();
            await this.load();
            if (ok) {
                this.notification.add(ok, { type: "success" });
            }
            return true;
        } catch (err) {
            this.notification.add(message(err, _t("That did not work.")), { type: "danger" });
            return false;
        } finally {
            this.state.busy = false;
        }
    }

    pick(tab) {
        this.state.tab = tab;
    }

    tabCount(tab) {
        return this.state.counts?.[tab.key === "fees" ? "rules" : tab.key] ?? 0;
    }

    // --------------------------------------------------------------- fees

    draft(rule) {
        return this.state.drafts[rule.id] || {};
    }

    setFee(rule, field, value) {
        const d = this.state.drafts[rule.id];
        if (d) {
            d[field] = value;
        }
    }

    /* Enabled only when something actually moved, so the button is an
       answer to "is there anything to save" rather than decoration. */
    dirty(rule) {
        const d = this.draft(rule);
        return (
            d.label !== rule.label || d.eta !== rule.eta ||
            num(d.min_order) !== rule.minOrder ||
            num(d.free_above) !== rule.freeAbove ||
            num(d.fee) !== rule.fee || d.active !== rule.active
        );
    }

    saveRule(rule) {
        const d = this.draft(rule);
        return this.run(
            () => this.orm.write(M.rule, [rule.id], {
                label: (d.label || "").trim(), eta: (d.eta || "").trim(),
                min_order: num(d.min_order), free_above: num(d.free_above),
                fee: num(d.fee), active: d.active,
            }),
            _t("%s delivery saved.", rule.modeLabel)
        );
    }

    /** What the customer effectively reads, from the numbers in the boxes. */
    sentence(rule) {
        const d = this.draft(rule);
        const fee = this.money(num(d.fee));
        if (num(d.free_above) > 0) {
            return _t("Under %s the basket is charged %s — above it, nothing.",
                      this.money(num(d.free_above)), fee);
        }
        return _t("Delivery is never free here: every basket is charged %s, whatever it comes to.", fee);
    }

    minimum(rule) {
        const d = this.draft(rule);
        return num(d.min_order) > 0
            ? _t("Below %s the customer cannot pay at all.", this.money(num(d.min_order)))
            : "";
    }

    // --------------------------------------------------------------- slots

    openSlot(slot) {
        this.dialog.add(SlotDialog, {
            slot: slot || null,
            modes: this.state.modes,
            kinds: this.state.kinds,
            onSaved: async (msg) => {
                await this.load();
                this.notification.add(msg, { type: "success" });
            },
        });
    }

    toggleSlot(slot) {
        if (slot.active) {
            this.dialog.add(Confirm, {
                title: _t('Switch "%s" off?', slot.top),
                body: _t(
                    "It stops being offered at checkout. Orders already booked " +
                        "into it keep their slot - this only closes it to new ones."
                ),
                confirmLabel: _t("Switch it off"),
                confirmClass: "btn-danger",
                confirm: () => this.run(
                    () => this.orm.write(M.slot, [slot.id], { active: false }),
                    _t("Slot switched off.")
                ),
                cancel: () => {},
            });
            return Promise.resolve(false);
        }
        return this.run(
            () => this.orm.write(M.slot, [slot.id], { active: true }),
            _t("Slot back on.")
        );
    }

    /** When a slot runs, in the words somebody would use asking. */
    when(slot) {
        if (slot.kind !== "window") {
            return "";
        }
        return `${clock(slot.fromHour)} - ${clock(slot.toHour)}`;
    }

    which(slot) {
        const day = slot.dayOffset === 0
            ? _t("Today")
            : slot.dayOffset === 1
                ? _t("Tomorrow")
                : _t("In %s days", slot.dayOffset);
        return slot.orderBefore < 24
            ? _t("%s · until %s", day, clock(slot.orderBefore))
            : day;
    }

    // --------------------------------------------------------------- areas

    openArea(area) {
        this.dialog.add(AreaDialog, {
            area: area || null,
            onSaved: async (msg) => {
                await this.load();
                this.notification.add(msg, { type: "success" });
            },
        });
    }

    toggleArea(area) {
        if (area.active) {
            this.dialog.add(Confirm, {
                title: _t("Stop delivering to %s?", area.pincode),
                body: _t(
                    "Customers there will be told we do not deliver to them " +
                        "yet. Orders already placed are unaffected."
                ),
                confirmLabel: _t("Switch it off"),
                confirmClass: "btn-danger",
                confirm: () => this.run(
                    () => this.orm.write(M.area, [area.id], { active: false }),
                    _t("Area switched off.")
                ),
                cancel: () => {},
            });
            return Promise.resolve(false);
        }
        return this.run(
            () => this.orm.write(M.area, [area.id], { active: true }),
            _t("Area back on.")
        );
    }

    // ------------------------------------------------------------ branches

    openBranch(branch) {
        this.dialog.add(BranchDialog, {
            branch,
            onSaved: async (msg) => {
                await this.load();
                this.notification.add(msg, { type: "success" });
            },
        });
    }

    toggleBranch(branch) {
        return this.run(
            () => this.orm.call(M.branch, "mart369_admin_save", [branch.id, { quick: !branch.quick }]),
            branch.quick ? _t("Quick switched off at %s.", branch.name)
                         : _t("Quick switched on at %s.", branch.name)
        );
    }

    /** Branches with Quick on that cannot actually reach anyone yet. */
    get unready() {
        return this.state.branches.filter((b) => b.unready);
    }

    // -------------------------------------------------------------- saying

    /** A storefront with nothing open cannot be checked out of, and the only
     *  other place that shows is the customer's slot step. */
    get shut() {
        const open = this.state.slots.filter((s) => s.active);
        return this.state.modes.filter((m) => !open.some((s) => s.mode === m.key));
    }

    get dark() {
        return this.state.rules.filter((r) => !r.active);
    }

    money(amount) {
        return format(amount, this.state.currency);
    }

    /* The three list views are still there for grouping, export and
       everything this screen deliberately does not do. */
    allViews() {
        this.action.doAction("mart369_cart.action_mart369_delivery_rules");
    }
}

registry.category("actions").add("mart369_cart.delivery", DeliveryDesk);
