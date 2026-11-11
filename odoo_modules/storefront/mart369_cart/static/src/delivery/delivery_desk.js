/**
 * The delivery desk - 369 Mart > Delivery & Pricing > Delivery.
 *
 * The twin of the app's console screen, and deliberately the same one: staff
 * who work in 369ai should not get a different answer to "what does delivery
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
 * back into a float on save, and then the thing typed and the thing 369ai
 * constrains to 0-24 are no longer the same thing.
 *
 * Nothing here deletes. A rule, a slot and an area are each pointed at by
 * orders that have gone out, so each is switched off instead.
 */
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadCSS, loadJS } from "@web/core/assets";
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

const pad2 = (n) => String(n).padStart(2, "0");
const blank = (v) => v === "" || v === null || v === undefined;

/** "6 - 8 PM", or "11 AM - 1 PM" when the two halves of the day differ. */
function span(from, to) {
    const a = clock(from);
    const b = clock(to);
    return a.slice(-2) === b.slice(-2) ? `${a.slice(0, -3)} - ${b}` : `${a} - ${b}`;
}

/** "Thu, 18 Sep" - `_mart369_day_label` on the model. */
function dayLabel(days) {
    const d = new Date();
    d.setDate(d.getDate() + days);
    const weekday = d.toLocaleDateString("en-GB", { weekday: "short" });
    const month = d.toLocaleDateString("en-GB", { month: "short" });
    return `${weekday}, ${d.getDate()} ${month}`;
}

/**
 * What a slot is called, worked out from its kind, day and time: the
 * heading, the detail, the key and its place in the list. The base key is
 * `_mart369_auto_key` on the model, which also adds -2, -3 when it is taken.
 * AdminDelivery.jsx keeps the same function - change both together.
 */
export function slotWording(draft) {
    const days = Math.max(0, Math.floor(num(draft.day_offset)));
    const from = num(draft.from_hour);
    const when = days === 0 ? "Today" : days === 1 ? "Tomorrow" : `In ${days} days`;
    if (draft.kind === "now") {
        return { top: "Now", sub: "10-20 min", key: "now", sequence: 0 };
    }
    if (draft.kind === "days") {
        return { top: when, sub: "", key: `d${days}`, sequence: 1000 + days };
    }
    const hour = Math.floor(from) % 24;
    const minute = Math.round((from - Math.floor(from)) * 60);
    const stem = days === 0 ? "today" : days === 1 ? "tm" : `d${days}`;
    return {
        top: when,
        sub: span(from, num(draft.to_hour)),
        key: `${stem}-${pad2(hour)}${minute ? pad2(minute) : ""}`,
        sequence: 1 + days * 100 + Math.round(from * 4),
    };
}

/** The confirmation line the shop writes when that box is left empty -
 *  `_mart369_serialize` on the model, from what the slot says right now. */
export function slotLabelPreview(draft) {
    const days = Math.max(0, Math.floor(num(draft.day_offset)));
    if (draft.kind === "now") {
        return `Arriving in ${draft.sub || ""}`.trim();
    }
    if (draft.kind === "days") {
        return `Arrives by ${dayLabel(days)}`;
    }
    const window = draft.sub || span(num(draft.from_hour), num(draft.to_hour));
    return days === 0 ? `Today, ${window}` : `${dayLabel(days)}, ${window}`;
}

/** The fields whose change moves the wording along. */
const WORDING_DRIVERS = ["kind", "day_offset", "from_hour", "to_hour"];

/**
 * Set `field` on a slot draft, and move the wording along with it: a field
 * that is empty or still says what was filled in for it follows; anything
 * the operator typed stays. The key follows only on a slot not yet saved.
 */
export function setSlotField(draft, field, value) {
    const before = slotWording(draft);
    draft[field] = value;
    if (!WORDING_DRIVERS.includes(field)) {
        return draft;
    }
    const after = slotWording(draft);
    for (const name of ["top", "sub", "sequence"]) {
        if (blank(draft[name]) || String(draft[name]) === String(before[name])) {
            draft[name] = after[name];
        }
    }
    if (!draft.id && (blank(draft.key) || draft.key === before.key)) {
        draft.key = after.key;
    }
    return draft;
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
                : (() => {
                    // Already filled in: Today, 6 - 8 PM, today-18.
                    const fresh = {
                        id: null, mode: "quick", kind: "window", key: "", top: "",
                        sub: "", label: "", from_hour: 18, to_hour: 20, day_offset: 0,
                        order_before: 24, fee: 0, capacity: 0, sequence: "", active: true,
                    };
                    return { ...fresh, ...slotWording(fresh) };
                })(),
            error: "",
            busy: false,
        });
    }

    get isWindow() {
        return this.state.draft.kind === "window";
    }

    set(field, value) {
        setSlotField(this.state.draft, field, value);
    }

    clock(value) {
        return clock(num(value));
    }

    /** What the order will say if the Confirmation line is left empty. */
    get labelPreview() {
        return slotLabelPreview(this.state.draft);
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
                /* Still the filled-in key, or empty: the model works it out
                   again and adds -2, -3 when it is taken in this storefront
                   (`_mart369_auto_key`). A typed key goes as typed. */
                let key = (d.key || "").trim();
                if (key === slotWording(d).key) {
                    key = "";
                }
                await this.orm.create(M.slot, [key ? { ...values, key } : values]);
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

/** What an area can promise. Picked, never typed, so every screen says it
 *  the same way. AdminDelivery.jsx keeps the same list. */
const AREA_PROMISES = [
    "15 mins", "30 mins", "45 mins", "1 hour", "2 hours", "Same day", "Next day",
];

/** The one "We deliver here" switch, as the two old fields - the same rule
 *  as _mart369_switch_values in service_area.py. Off: both off. On: an area
 *  that already delivers keeps what it had; one that did not gets both. */
function switchValues(deliver, area) {
    if (!deliver) {
        return { quick: false, express: false };
    }
    if (area && (area.quick || area.express)) {
        return {};
    }
    return { quick: true, express: true };
}

/** The service-area editor. Short enough that it is all one panel. A new
 *  area takes several pincodes at once, ticked from the ones we know. */
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
                    id: a.id, pincode: a.pincode, name: a.name,
                    deliver: !!(a.quick || a.express), eta: a.eta, active: a.active,
                }
                : {
                    id: null, pincode: "", name: "", deliver: true,
                    eta: "30 mins", active: true,
                },
            known: null,        // the pincodes we know, grouped by branch
            ticked: {},         // pincode -> true
            open: {},           // which groups are unfolded
            error: "",
            busy: false,
        });
        if (!a) {
            // Not awaited: the window opens at once and the list fills in.
            this.loadKnown();
        }
    }

    async loadKnown() {
        try {
            const known = await this.orm.call(M.area, "mart369_admin_known_pincodes", []);
            const ticked = {};
            for (const group of known.groups) {
                for (const row of group.pincodes) {
                    if (row.near) {
                        ticked[row.pincode] = true;
                    }
                }
            }
            this.state.known = known;
            this.state.ticked = ticked;
        } catch {
            // Not fatal: the box below still takes typed pincodes.
            this.state.known = { groups: [], noPin: [], covered: [] };
        }
    }

    set(field, value) {
        this.state.draft[field] = value;
    }

    /** "0.4 km away", "2,511 km away". */
    kmText(km) {
        if (km === null || km === undefined) {
            return "";
        }
        return _t("%s km away", km < 100 ? km : Math.round(km).toLocaleString());
    }

    tick(pincode) {
        this.state.ticked[pincode] = !this.state.ticked[pincode];
    }

    /** Tick or untick a whole branch's list at once. */
    tickAll(rows) {
        const on = !rows.every((r) => this.state.ticked[r.pincode]);
        for (const r of rows) {
            this.state.ticked[r.pincode] = on;
        }
    }

    /** Groups start folded to one line; this opens or closes one. */
    toggleOpen(key) {
        this.state.open[key] = !this.state.open[key];
    }

    /** Where the ticks come from, for the Add button: "Ruwi 4 · Sohar 37".
     *  Folded groups hide their ticks, so the button says it out loud. */
    get tickedSplit() {
        const known = this.state.known;
        if (!known) {
            return "";
        }
        const parts = known.groups.map((g) => [g.branch.split(" ")[0], this.tickedIn(g.pincodes)]);
        parts.push([_t("far"), this.tickedIn(known.far || [])]);
        parts.push([_t("no pin"), this.tickedIn(known.noPin || [])]);
        const shown = parts.filter(([, n]) => n);
        return shown.length > 1 ? shown.map(([name, n]) => `${name} ${n}`).join(" · ") : "";
    }

    tickedIn(rows) {
        return rows.filter((r) => this.state.ticked[r.pincode]).length;
    }

    allTicked(rows) {
        return rows.length && rows.every((r) => this.state.ticked[r.pincode]);
    }

    get tickedCount() {
        return Object.values(this.state.ticked).filter(Boolean).length;
    }

    /** The list, plus whatever an older area already says, so opening it
     *  never quietly changes its promise. */
    get promises() {
        const eta = this.state.draft.eta;
        return eta && !AREA_PROMISES.includes(eta) ? [eta, ...AREA_PROMISES] : AREA_PROMISES;
    }

    async save() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        const d = this.state.draft;
        if (!d.id) {
            const ticked = Object.keys(this.state.ticked).filter((p) => this.state.ticked[p]);
            const pincodes = [...ticked, d.pincode || ""].filter((p) => p.trim()).join(", ");
            try {
                const done = await this.orm.call(M.area, "mart369_admin_add_many", [pincodes, {
                    name: d.name || "", eta: d.eta || "",
                    deliver: !!d.deliver, active: true,
                }]);
                this.props.close();
                let said = done.added.length === 1
                    ? _t("1 area added.")
                    : _t("%s areas added.", done.added.length);
                if (done.skipped.length) {
                    said += " " + _t("Already there, left as they were: %s.",
                                     done.skipped.join(", "));
                }
                await this.props.onSaved(said);
            } catch (err) {
                this.state.error = message(err, _t("That could not be saved."));
            } finally {
                this.state.busy = false;
            }
            return;
        }
        /* Whitespace out first: a pincode pasted from a spreadsheet arrives
           as "682 016", which is digits with a space in it, and refusing that
           teaches nobody anything. */
        const values = {
            pincode: (d.pincode || "").split(/\s+/).join(""),
            name: d.name || "", eta: d.eta || "", active: !!d.active,
            ...switchValues(d.deliver, this.props.area),
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

/** Minutes for Quick `km` away: 10 to pack, 5 a km, rounded up to the next
 *  5. The same sum as quick_time_text in branch.py, so the window shows what
 *  the shop will say. */
function quickTime(km) {
    const mins = Math.ceil((10 + 5 * Math.max(0, Number(km) || 0)) / 5 - 1e-9) * 5;
    if (mins < 60) {
        return `${mins} mins`;
    }
    const rest = mins % 60;
    return `${Math.floor(mins / 60)} hr${rest ? ` ${rest} mins` : ""}`;
}

/* The same free map as the shop's "Pick on map" and the tracking page:
 * OpenFreeMap's style through MapLibre, no key. Loaded only when somebody
 * opens the map. */
const MAPLIBRE_JS = "https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.js";
const MAPLIBRE_CSS = "https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.css";
const MAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";

/** "Pick on map" for a branch: the pin stays in the middle and the map moves
 *  under it, as in the shop's address form. Opens on the boxes' location, or
 *  wide when they are empty. */
export class BranchPinMap extends Component {
    static template = "mart369_cart.BranchPinMap";
    static props = {
        lat: { type: [String, Number], optional: true },
        lng: { type: [String, Number], optional: true },
        onPick: Function,
        onCancel: Function,
    };

    setup() {
        this.canvas = useRef("canvas");
        this.state = useState({ status: "loading", note: "", locating: false });
        onMounted(() => this.start());
        onWillUnmount(() => {
            this.gone = true;
            try {
                this.map?.remove();
            } catch {
                // never started
            }
        });
    }

    async start() {
        const lat = Number(this.props.lat);
        const lng = Number(this.props.lng);
        const known = (lat || lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180;
        try {
            await loadCSS(MAPLIBRE_CSS);
            await loadJS(MAPLIBRE_JS);
        } catch {
            this.state.status = "failed";
            return;
        }
        const ml = window.maplibregl;
        if (this.gone) {
            return;
        }
        if (!ml || !this.canvas.el) {
            this.state.status = "failed";
            return;
        }
        try {
            this.map = new ml.Map({
                container: this.canvas.el, style: MAP_STYLE,
                center: known ? [lng, lat] : [78.9629, 22.5937], zoom: known ? 16 : 4,
                maxZoom: 19, dragRotate: false, pitchWithRotate: false, touchPitch: false,
                attributionControl: { compact: false },
            });
        } catch {
            this.state.status = "failed";
            return;
        }
        this.map.touchZoomRotate.disableRotation();
        this.map.addControl(new ml.NavigationControl({ showCompass: false }), "bottom-right");
        this.map.on("error", (ev) => {
            if (this.state.status === "loading" && !ev?.sourceId) {
                this.state.status = "failed";
            }
        });
        this.map.once("load", () => {
            if (!this.gone) {
                this.map.resize();
                this.state.status = "ready";
            }
        });
        if (!known) {
            this.state.note = _t("Zoom in to the branch, or use Where I am now if you are there.");
        }
    }

    here() {
        if (!navigator.geolocation) {
            this.state.note = _t("Location isn't available in this browser. Move the map instead.");
            return;
        }
        this.state.locating = true;
        navigator.geolocation.getCurrentPosition(
            ({ coords }) => {
                this.state.locating = false;
                this.map?.flyTo({ center: [coords.longitude, coords.latitude], zoom: 17 });
                this.state.note = _t("Moved to where you are now. Check the pin is on the branch.");
            },
            () => {
                this.state.locating = false;
                this.state.note = _t("We couldn't get your location. Move the map instead.");
            },
            { enableHighAccuracy: true, timeout: 8000 }
        );
    }

    confirm() {
        const c = this.map?.getCenter();
        if (c) {
            this.props.onPick(c.lat.toFixed(6), c.lng.toFixed(6));
        }
    }
}

/** One branch's Quick settings. Branches themselves are made in Inventory,
 *  so this edits only the things delivery owns: Quick on or off, its reach,
 *  "Quick if possible up to" and its pin. The Quick time is worked out. */
export class BranchDialog extends Component {
    static template = "mart369_cart.BranchDialog";
    static components = { Dialog, Switch, Icon, BranchPinMap };
    static props = {
        branch: Object,
        onSaved: Function,
        onChanged: { type: Function, optional: true },
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        const b = this.props.branch;
        this.state = useState({
            draft: {
                quick: b.quick,
                quickKm: b.quickKm ? String(b.quickKm) : "",
                maybeKm: b.maybeKm ? String(b.maybeKm) : "",
                ownFees: !!b.ownFees,
                quickFee: b.quickFee ? String(b.quickFee) : "",
                expressFee: b.expressFee ? String(b.expressFee) : "",
                freeAbove: b.freeAbove ? String(b.freeAbove) : "",
                // 0/0 is how Odoo stores "no pin": shown as two empty boxes.
                lat: b.lat || b.lng ? String(b.lat) : "",
                lng: b.lat || b.lng ? String(b.lng) : "",
            },
            find: null,     // how "Find pincodes around this branch" is going
            locate: null,   // what "Find from the address" said
            address: null,  // {street, city, zip} being typed for a branch with none
            picking: false, // the map is open
            error: "",
            busy: false,
        });
        onWillUnmount(() => clearTimeout(this.findTimer));
        // A lookup already under way shows its progress as the window opens.
        this.orm.call(M.branch, "mart369_admin_find_status", [b.id]).then((status) => {
            if (status.state === "running") {
                this.showFind(status);
            }
        }).catch(() => {});
    }

    set(field, value) {
        this.state.draft[field] = value;
    }

    /** Google Maps copies both numbers at once ("10.3673, 77.9803"): pasted
     *  into either box, they fill both. A single number is typed as usual. */
    setCoord(field, value, input) {
        const m = String(value || "").match(
            /^\s*(-?\d+(?:\.\d+)?)\s*(?:,|\s)\s*(-?\d+(?:\.\d+)?)\s*$/);
        if (m) {
            this.state.draft.lat = m[1];
            this.state.draft.lng = m[2];
            // The box pasted into holds the pair until told otherwise: Owl
            // only rewrites a value that changed since it last drew it.
            if (input) {
                input.value = field === "lat" ? m[1] : m[2];
            }
        } else {
            this.state.draft[field] = value;
        }
    }

    /** Quick on with the boxes still empty fills the usual reaches. */
    toggleQuick() {
        const d = this.state.draft;
        d.quick = !d.quick;
        if (d.quick && !Number(d.quickKm)) {
            d.quickKm = "5";
        }
        if (d.quick && !Number(d.maybeKm)) {
            d.maybeKm = String(Math.max(15, Number(d.quickKm) || 0));
        }
    }

    /** "Find from the address": the branch's address in Odoo, looked up on
     *  OpenStreetMap, fills the two boxes. The location is not saved until
     *  Save. With no address in Odoo, three boxes ask for it right here;
     *  `address` is what was typed in them, saved on the contact first. */
    async locate(address = null) {
        this.state.locate = { state: "running", message: _t("Looking up the branch's address…") };
        try {
            const args = [this.props.branch.id];
            if (address) {
                args.push(address);
            }
            const found = await this.orm.call(M.branch, "mart369_admin_locate", args);
            if (!found.found) {
                this.state.address = this.state.address || { street: "", city: "", zip: "" };
                this.state.locate = { state: "rough", message: found.message,
                                      name: found.name, country: found.country };
                return;
            }
            this.state.address = null;
            this.state.draft.lat = String(found.lat);
            this.state.draft.lng = String(found.lng);
            this.state.locate = { state: found.level === "street" ? "done" : "rough",
                                  message: found.message };
        } catch (err) {
            this.state.locate = { state: "failed", message: message(err, _t("That didn't work.")) };
        }
    }

    /** The map's "Use this spot". */
    picked(lat, lng) {
        this.state.draft.lat = lat;
        this.state.draft.lng = lng;
        this.state.picking = false;
        this.state.locate = { state: "done", message: _t("Spot picked. Save to keep it.") };
    }

    /** What the boxes say, as mart369_admin_save takes it, or null with the
     *  reason shown when they cannot be saved as they are. */
    values() {
        const d = this.state.draft;
        if (!String(d.lat).trim() !== !String(d.lng).trim()) {
            this.state.error = _t("Type both the latitude and the longitude, or leave both empty.");
            return null;
        }
        return {
            quick: !!d.quick, quickKm: d.quickKm, maybeKm: d.maybeKm,
            lat: d.lat, lng: d.lng, ownFees: !!d.ownFees, quickFee: d.quickFee,
            expressFee: d.expressFee, freeAbove: d.freeAbove,
        };
    }

    /** "Find pincodes around this branch": saves what is typed first, so the
     *  search uses this location and reach; the answer comes with a sentence
     *  that says what is happening; while OpenStreetMap is still looking, ask
     *  again every few seconds so the count climbs on screen. */
    async findPincodes() {
        this.state.error = "";
        const values = this.values();
        if (!values) {
            return;
        }
        this.state.find = { state: "starting", message: _t("Saving, then looking…") };
        try {
            await this.orm.call(M.branch, "mart369_admin_save", [this.props.branch.id, values]);
            this.props.onChanged?.();
        } catch (err) {
            this.state.find = null;
            this.state.error = message(err, _t("That could not be saved."));
            return;
        }
        this.state.find = {
            state: "starting",
            message: _t("Working out which country this branch is in, and getting its postcode list. The first time for a country this can take up to a minute…"),
        };
        try {
            const status = await this.orm.call(M.branch, "mart369_admin_find_pincodes",
                                               [this.props.branch.id]);
            this.showFind(status);
        } catch (err) {
            this.state.find = { state: "failed", message: message(err, _t("That didn't work.")) };
        }
    }

    get findPercent() {
        const f = this.state.find;
        return f && f.total ? Math.round((100 * f.done) / f.total) : 0;
    }

    showFind(status) {
        this.state.find = status;
        clearTimeout(this.findTimer);
        if (status.state === "running") {
            this.findTimer = setTimeout(async () => {
                try {
                    this.showFind(await this.orm.call(M.branch, "mart369_admin_find_status",
                                                      [this.props.branch.id]));
                } catch {
                    // A missed check is not news; the next button press asks again.
                }
            }, 4000);
        }
    }

    /** "15 mins to 35 mins" for the reach typed in, or "" with none. */
    get quickTimes() {
        const km = Number(this.state.draft.quickKm);
        return km > 0 ? `${quickTime(0)} to ${quickTime(km)}` : "";
    }

    async save() {
        if (this.state.busy) {
            return;
        }
        this.state.error = "";
        const values = this.values();
        if (!values) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call(M.branch, "mart369_admin_save", [this.props.branch.id, values]);
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
            const data = await this.orm.call(M.rule, "mart369_admin_list", [], {
                // Always the website's own settings, even where the bridge
                // shows the senior's Quick / Express records in the console.
                context: { mart369_desk: true },
            });
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
        // "Find pincodes" saves without closing the window; the list behind
        // it is read again once the window closes.
        let changed = false;
        this.dialog.add(BranchDialog, {
            branch,
            onSaved: async (msg) => {
                changed = false;
                await this.load();
                this.notification.add(msg, { type: "success" });
            },
            onChanged: () => {
                changed = true;
            },
        }, {
            onClose: () => changed && this.load(),
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
