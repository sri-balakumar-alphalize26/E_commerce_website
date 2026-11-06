/** @odoo-module **/

/**
 * The shop's order screen.
 *
 * A list view would have been less code, but a person with their hands full
 * does not watch a list - they need to be told. So this is a client action
 * that listens on the bus and raises an alarm until every waiting order has
 * been accepted.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
// One definition of every alarm tone, shared with the enquiry desk, so
// four alarms on two screens cannot drift into sounding alike.
import { SUPPLY_TONE } from "./enquiry_alarm_shared";

/**
 * The alarm.
 *
 * Synthesised with the Web Audio API rather than played from a file: there is
 * no asset to ship or fail to load, it cannot be muted by a missing codec, and
 * the tone can be made deliberately unpleasant.
 *
 * The catch that matters: browsers refuse to play anything until the user has
 * interacted with the page. A screen left open on a counter would sit there
 * silently believing it was alerting somebody, which is worse than having no
 * alarm at all - so the screen says plainly when sound is not armed, and one
 * click arms it.
 */
export class Alarm {
    constructor() {
        this.ctx = null;
        this.armed = false;
    }

    async arm() {
        if (this.armed) {
            return true;
        }
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) {
            return false;
        }
        this.ctx = this.ctx || new Ctx();
        // Created inside a click handler, so this resume is allowed - but it
        // is asynchronous, and reading `state` before it settles says
        // "suspended" on a browser that is about to play perfectly well.
        try {
            await this.ctx.resume();
        } catch (_err) {
            // fall through: state tells the truth below
        }
        this.armed = this.ctx.state === "running";
        return this.armed;
    }

    /** One loud tone. */
    tone(freq, at, length) {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        // Square wave: harsh on purpose. It has to be heard over a shop.
        osc.type = "square";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, at);
        gain.gain.exponentialRampToValueAtTime(0.8, at + 0.01);
        gain.gain.setValueAtTime(0.8, at + length - 0.03);
        gain.gain.exponentialRampToValueAtTime(0.0001, at + length);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(at);
        osc.stop(at + length + 0.02);
    }

    /**
     * Ring for `seconds`: two tones alternating, 0.35 s on / 0.15 s off,
     * the cadence of a phone that wants answering. Scheduled a second at a
     * time so stop() actually stops it.
     */
    ring(seconds, tone) {
        this.stop();
        if (!this.armed || !this.ctx) {
            return;
        }
        // `tone` lets a second screen sound different from this one. A
        // counter with two alarms that sound alike has one alarm it learns
        // to ignore. Omitted, the cadence is exactly what it always was.
        const cfg = Object.assign(
            { lo: 1000, hi: 1400, step: 0.5, len: 0.35 }, tone || {});
        const step = cfg.step;
        const end = this.ctx.currentTime + seconds;
        let next = this.ctx.currentTime + 0.05;
        let hi = false;
        const schedule = () => {
            const horizon = this.ctx.currentTime + 1.0;
            while (next < horizon && next < end) {
                this.tone(hi ? cfg.hi : cfg.lo, next, cfg.len);
                hi = !hi;
                next += step;
            }
            if (next >= end) {
                this.stop();
            }
        };
        schedule();
        this._ringTimer = setInterval(schedule, 400);
    }

    stop() {
        if (this._ringTimer) {
            clearInterval(this._ringTimer);
            this._ringTimer = null;
        }
    }

    /** Kept for the one-off uses: a short sample of the ring. */
    beep() {
        this.ring(3);
    }
}

/** "Which company's shelf?" - asked once, on Accept. */
/** Six digits typed by the counter - the pickup code the rider shows, or
 *  the delivery code the customer gives after receiving the parcel. */
class OtpDialog extends Component {
    static template = "sales_automation_store.OtpDialog";
    static components = { Dialog };
    static props = { close: Function, title: String, hint: String, onConfirm: Function,
                     riders: { type: Array, optional: true }, riderId: { type: Number, optional: true } };

    setup() {
        this.state = useState({ code: "", error: "", rider: this.props.riderId ? `${this.props.riderId}` : "" });
    }

    async confirm() {
        const code = (this.state.code || "").replace(/\D/g, "");
        if (code.length !== 6) {
            this.state.error = "Type the 6-digit code.";
            return;
        }
        if (this.props.riders && !this.state.rider) {
            this.state.error = "Pick the rider who is collecting.";
            return;
        }
        try {
            await this.props.onConfirm(code, this.state.rider ? parseInt(this.state.rider, 10) : null);
            this.props.close();
        } catch (err) {
            this.state.error = (err && err.data && err.data.message) || (err && err.message) || "Wrong code.";
        }
    }
}

/** Branch-controlled pickup: the code the staff read out to the rider.
 *  Closes by itself once the rider has typed it (the card leaves `accepted`). */
class DispatchCodeDialog extends Component {
    static template = "sales_automation_store.DispatchCodeDialog";
    static components = { Dialog };
    static props = { close: Function, title: String, code: String, rider: String,
                     arrived: Boolean, expires: { type: String, optional: true },
                     getRow: Function, onNew: Function };

    setup() {
        this.state = useState({ code: this.props.code, expires: this.props.expires || "",
                                left: "", done: false, busy: false });
        this._tick = () => {
            const row = this.props.getRow();
            if (!this.state.done && (!row || row.state !== "accepted")) {
                this.state.done = true;
                setTimeout(() => this.props.close(), 2500);
            }
            if (this.state.expires) {
                const ms = new Date(this.state.expires).getTime() - Date.now();
                this.state.left = ms > 0 ? Math.ceil(ms / 60000) + " min left" : "expired - press New code";
            }
        };
        onMounted(() => {
            this._tick();
            this._timer = setInterval(this._tick, 1000);
        });
        onWillUnmount(() => clearInterval(this._timer));
    }

    get digits() {
        return (this.state.code || "").split("");
    }

    async newCode() {
        this.state.busy = true;
        try {
            const res = await this.props.onNew();
            if (res && res.code) {
                this.state.code = res.code;
                this.state.expires = res.expires_at || "";
            }
        } finally {
            this.state.busy = false;
        }
    }
}

class CallRiderDialog extends Component {
    static template = "sales_automation_store.CallRiderDialog";
    static components = { Dialog };
    static props = { close: Function, title: String, candidates: Array, mode: String, onConfirm: Function };

    setup() {
        // picked: rider id -> true. Several may be ticked; the server calls
        // them one at a time, in rank order.
        this.state = useState({ picked: {}, error: "", tab: "free" });
    }

    get count() {
        return Object.values(this.state.picked).filter(Boolean).length;
    }

    /** Can be called now: on duty, not on a delivery, not already tried. */
    get free() {
        return this.props.candidates.filter(
            (c) => c.available !== false && !c.busy && !c.declined && c.on_duty !== false);
    }

    /** Everybody else, shown in their own list with the reason. */
    get others() {
        const free = new Set(this.free.map((c) => c.id));
        return this.props.candidates.filter((c) => !free.has(c.id));
    }

    why(c) {
        if (c.sos) {
            return "SOS open";
        }
        if (c.declined) {
            return "Did not answer";
        }
        if (c.busy) {
            return "On a delivery" + (c.in_hand ? " " + c.in_hand : "");
        }
        return "Off duty";
    }

    get allFreeTicked() {
        const free = this.free;
        return free.length > 0 && free.every((c) => this.state.picked[c.id]);
    }

    toggle(c) {
        if (!this.free.some((f) => f.id === c.id)) {
            return;                 // only an available rider can be ticked
        }
        this.state.picked[c.id] = !this.state.picked[c.id];
    }

    toggleAll() {
        const on = !this.allFreeTicked;
        for (const c of this.free) {
            this.state.picked[c.id] = on;
        }
    }

    rank(c) {
        return c.rank === null || c.rank === undefined ? "-" : c.rank + 1;
    }

    idle(c) {
        if (!c.on_duty) {
            return "-";
        }
        const m = c.idle_min || 0;
        return m >= 60 ? Math.floor(m / 60) + " h " + (m % 60) + " min" : m + " min";
    }

    async confirm(auto) {
        const ids = auto ? [] : Object.keys(this.state.picked)
            .filter((k) => this.state.picked[k]).map((k) => parseInt(k, 10));
        if (!auto && !ids.length) {
            this.state.error = "Tick at least one rider.";
            return;
        }
        try {
            await this.props.onConfirm(ids);
            this.props.close();
        } catch (err) {
            this.state.error = (err && err.data && err.data.message) || (err && err.message) || "Could not call a rider.";
        }
    }
}

class CompanyDialog extends Component {
    static template = "sales_automation_store.CompanyDialog";
    static components = { Dialog };
    static props = {
        title: String,
        options: Array,
        onPick: Function,
        onSupply: Function,
        close: Function,
    };

    pick(company) {
        this.props.onPick(company);
        this.props.close();
    }

    /** True when not one company can supply this - the dead-end case. */
    get stuck() {
        return !this.props.options.some((c) => c.ok);
    }

    supply() {
        this.props.onSupply();
        this.props.close();
    }
}

/**
 * Nothing on any shelf: ask suppliers, then record what we pay and when it
 * will be here.
 *
 * Two steps in one dialog on purpose. The shopkeeper rings round while the
 * dialog is open, so closing it to reopen somewhere else to type the number
 * is exactly the friction that leaves orders unrecorded.
 */
class SupplyDialog extends Component {
    static template = "sales_automation_store.SupplyDialog";
    static components = { Dialog };
    static props = {
        row: Object,
        vendors: Array,
        noCateg: Boolean,
        onAsk: Function,
        onSave: Function,
        close: Function,
    };

    setup() {
        this.state = useState({
            picked: {},
            partner: "",
            cost: "",
            day: this.today(),
            asked: false,
            error: "",
        });
    }

    today() {
        // The browser's own date, formatted for <input type="date">.
        const now = new Date();
        const pad = (n) => `${n}`.padStart(2, "0");
        return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    }

    toggle(vendor) {
        if (!vendor.ok) {
            return;                 // no phone: nothing to send to
        }
        this.state.picked[vendor.id] = !this.state.picked[vendor.id];
    }

    isPicked(vendor) {
        return !!this.state.picked[vendor.id];
    }

    get chosen() {
        return Object.keys(this.state.picked)
            .filter((id) => this.state.picked[id])
            .map((id) => parseInt(id, 10));
    }

    /** Same rule as the server: today is Quick, later is Express. */
    get kindLabel() {
        return this.state.day && this.state.day > this.today()
            ? "Express"
            : "Same day";
    }

    ask() {
        if (!this.chosen.length) {
            this.state.error = "Tick at least one supplier first.";
            return;
        }
        this.state.error = "";
        this.state.asked = true;
        this.props.onAsk(this.chosen);
    }

    save() {
        const cost = parseFloat((this.state.cost || "").replace(/,/g, ""));
        if (!(cost >= 0) || this.state.cost === "") {
            this.state.error = "Type the amount as a number, like 900.";
            return;
        }
        this.props.onSave({
            partner_id: this.state.partner
                ? parseInt(this.state.partner, 10) : false,
            cost,
            promised_date: this.state.day,
        });
        this.props.close();
    }
}

export class StoreScreen extends Component {
    static template = "sales_automation_store.StoreScreen";
    // client action: 369ai 19 passes action / actionId / updateActionState / className
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.bus = useService("bus_service");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.action = useService("action");
        this.alarm = new Alarm();
        // Its own instance: `ring()` stops whatever is already ringing, so one
        // Alarm cannot sound two alarms at once - the waiting-stock reminder
        // would silence the packing alarm and nobody would know.
        this.supplyAlarm = new Alarm();

        this.state = useState({
            rows: [],
            shops: [],
            shopId: 0,
            ringing: 0,
            packing: 0,
            isManager: false,
            soundOn: true,
            soundBlocked: false,
            loading: true,
            busy: 0,
            repeat: 10,
            ring: 30,
            waitingSupply: 0,
            supplyRinging: 0,
        });

        this._timer = null;
        this._supplyTimer = null;
        this._onBus = this._onBus.bind(this);

        onWillStart(async () => {
            this.state.shops = await this.orm.call(
                "stock.picking", "sa_store_shops", []);
            if (this.state.shops.length === 1) {
                this.state.shopId = this.state.shops[0].id;
            }
            await this.refresh();
            this._listen();
        });

        // Alarm on by default: armed on the first tap or key anywhere.
        this._armOnGesture = async () => {
            if (this._armed) {
                return;
            }
            const ok = (await this.alarm.arm()) && (await this.supplyAlarm.arm());
            if (ok) {
                this._armed = true;
                this.state.soundBlocked = false;
                document.removeEventListener("pointerdown", this._armOnGesture, true);
                document.removeEventListener("keydown", this._armOnGesture, true);
                this._syncAlarm();
                this._syncSupplyAlarm();
            } else {
                this.state.soundBlocked = true;
            }
        };
        onMounted(async () => {
            // Safety net: the screen is pushed, not polled - but a push that
            // never arrives (server restart, tablet asleep, dropped socket)
            // must not leave the counter looking at an old list.
            this._safetyPoll = setInterval(() => {
                if (!this.state.busy) {
                    this.refresh().catch(() => {});
                }
            }, 20000);
            document.addEventListener("pointerdown", this._armOnGesture, true);
            document.addEventListener("keydown", this._armOnGesture, true);
            const ok = (await this.alarm.arm()) && (await this.supplyAlarm.arm());
            if (ok) {
                this._armed = true;
                this._syncAlarm();
                this._syncSupplyAlarm();
            }
        });

        onWillUnmount(() => {
            clearInterval(this._safetyPoll);
            document.removeEventListener("pointerdown", this._armOnGesture, true);
            document.removeEventListener("keydown", this._armOnGesture, true);
            this._stopAlarm();
            this._stopSupplyAlarm();
            this.bus.deleteChannel(this._channel());
            this.bus.unsubscribe("sa_store/refresh", this._onBus);
        });
    }

    _channel() {
        return `sa_store_${this.state.shopId || 0}`;
    }

    _listen() {
        this.bus.addChannel(this._channel());
        this.bus.subscribe("sa_store/refresh", this._onBus);
    }

    _onBus() {
        this.refresh();
    }

    async refresh() {
        const data = await this.orm.call(
            "stock.picking", "sa_store_queue", [this.state.shopId || null]);
        this.state.rows = data.rows;
        this.state.isManager = !!data.is_manager;
        this.state.ringing = data.ringing;
        this.state.packing = data.packing;
        this.state.waitingSupply = data.waiting_supply || 0;
        this.state.supplyRinging = data.supply_ringing || 0;
        this.state.loading = false;
        // A changed cadence must restart the timer, not wait for the next
        // order to arrive.
        if ((data.repeat && data.repeat !== this.state.repeat)
            || (data.ring && data.ring !== this.state.ring)) {
            this.state.repeat = data.repeat || this.state.repeat;
            this.state.ring = data.ring || this.state.ring;
            this._stopAlarm();
        }
        this._syncAlarm();
        this._syncSupplyAlarm();
    }

    /**
     * The morning reminder, on its own slow tone.
     *
     * Rings only for jobs this morning's cron actually named, so a shelf full
     * of things on order is not a permanent noise - it is a reminder, once a
     * day, that stops when the goods are marked in.
     */
    _syncSupplyAlarm() {
        if (this.state.supplyRinging > 0 && this.state.soundOn) {
            if (!this._supplyTimer) {
                this.supplyAlarm.ring(this.state.ring, SUPPLY_TONE);
                this._supplyTimer = setInterval(
                    () => this.supplyAlarm.ring(this.state.ring, SUPPLY_TONE),
                    (this.state.ring + this.state.repeat) * 1000);
            }
        } else {
            this._stopSupplyAlarm();
        }
    }

    _stopSupplyAlarm() {
        if (this._supplyTimer) {
            clearInterval(this._supplyTimer);
            this._supplyTimer = null;
        }
        this.supplyAlarm.stop();
    }

    /** One alarm for the queue, not one per order. */
    _syncAlarm() {
        if (this.state.ringing > 0 && this.state.soundOn) {
            if (!this._timer) {
                this.alarm.ring(this.state.ring);
                this._timer = setInterval(
                    () => this.alarm.ring(this.state.ring),
                    (this.state.ring + this.state.repeat) * 1000);
            }
        } else {
            this._stopAlarm();
        }
    }

    _stopAlarm() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
        // Accept must cut the sound mid-ring, not at the end of the burst.
        this.alarm.stop();
    }

    async onEnableSound() {
        if (await this.alarm.arm()) {
            // Both armed from the one click: a browser only lets an
            // AudioContext start inside a user gesture, so an alarm armed
            // later never sounds at all.
            await this.supplyAlarm.arm();
            this._armed = true;
            this.state.soundBlocked = false;
            this.state.soundOn = true;
            this.alarm.beep();
            this._syncAlarm();
            this._syncSupplyAlarm();
        } else {
            this.notification.add(
                "This browser will not play sound on this page. Check the "
                + "tab is not muted and the device volume is up.",
                { type: "warning" });
        }
    }

    /** Three seconds of the ring, so the shop can prove the speaker works. */
    async onTestSound() {
        if (!(await this.alarm.arm())) {
            return this.onEnableSound();
        }
        this.state.soundOn = true;
        if (!this._timer) {
            this.alarm.ring(3);
        }
    }

    async onShopChange(ev) {
        this.bus.deleteChannel(this._channel());
        this.state.shopId = parseInt(ev.target.value, 10) || 0;
        this._listen();
        await this.refresh();
    }

    /** Accept starts with the question of whose stock it comes from. */
    async onAccept(row) {
        if (this.state.busy === row.id) {
            return;
        }
        const options = await this.orm.call(
            "stock.picking", "sa_store_company_options", [row.id]);
        if (!options.length) {
            return this.act(row, "accept");
        }
        this.dialog.add(CompanyDialog, {
            title: "Accept #" + row.ref + " - from which company?",
            options,
            onPick: (company) => this.act(row, "accept", { company_id: company.id }),
            onSupply: () => this.onSupply(row),
        });
    }

    /** Nothing on any shelf: buy it in. */
    async onSupply(row) {
        const data = await this.orm.call(
            "stock.picking", "sa_store_supply_options", [row.id]);
        this.dialog.add(SupplyDialog, {
            row,
            vendors: data.vendors || [],
            noCateg: !!data.no_categ,
            onAsk: (ids) => this.act(row, "supply_ask", { vendor_ids: ids }),
            onSave: (vals) => this.act(row, "supply_set", vals),
        });
    }

    async act(row, action, extra = {}) {
        // Guarded: two taps on Accept must not send two calls, and a shop
        // screen is exactly where a button gets hit twice.
        if (this.state.busy === row.id) {
            return;
        }
        this.state.busy = row.id;
        try {
            const data = await this.orm.call(
                "stock.picking", "sa_store_act", [row.id, action], extra);
            this.state.rows = data.rows;
            this.state.ringing = data.ringing;
            this.state.packing = data.packing;
            this.state.waitingSupply = data.waiting_supply || 0;
            this.state.supplyRinging = data.supply_ringing || 0;
            this._syncAlarm();
            this._syncSupplyAlarm();
            if (data.otp_message) {
                this.notification.add(data.otp_message + (data.otp_code ? " Code: " + data.otp_code : ""),
                    { type: data.otp_code ? "success" : "warning", sticky: !!data.otp_code });
            }
            return data;
        } finally {
            this.state.busy = 0;
        }
    }

    onCallRider(row, force = false) {
        const extra = force ? { force: true } : {};
        if (row.call_mode === "auto" || row.call_mode === "auto_radius") {
            // Automatic mode (Delivery Settings): no list, the system picks.
            this.act(row, "call_rider", extra);
            return;
        }
        this.dialog.add(CallRiderDialog, {
            title: "Call a Rider - #" + row.ref,
            candidates: row.candidates || [],
            mode: row.call_mode || "ask",
            onConfirm: (riderIds) => this.act(row, "call_rider", { rider_ids: riderIds, ...extra }),
        });
    }

    /** An online order that is not paid yet: a delivery manager may still call, after a confirm step. */
    onForceCall(row) {
        this.dialog.add(ConfirmationDialog, {
            title: "Not paid yet - call anyway?",
            body: "Order #" + row.ref + " has a pay link out and no payment. The rider is called by itself when the customer pays. Call a rider now anyway?",
            confirmLabel: "Call anyway",
            confirm: () => this.onCallRider(row, true),
            cancel: () => {},
        });
    }

    /** Branch-controlled pickup: make the code, show it large, wait for
     *  the rider to type it in the app. */
    async onBranchDispatch(row) {
        const data = await this.act(row, "branch_dispatch");
        const res = data && data.branch_code;
        if (!res) {
            return;
        }
        this.dialog.add(DispatchCodeDialog, {
            title: "Dispatch #" + row.ref + " - pickup code",
            code: res.code,
            rider: res.rider || row.rider || "",
            arrived: !!res.arrived,
            expires: res.expires_at || "",
            getRow: () => this.state.rows.find((r) => r.id === row.id),
            onNew: async () => {
                const again = await this.act(row, "branch_dispatch");
                return again && again.branch_code;
            },
        });
    }

    onDispatch(row) {
        if (row.pickup_handover === "branch" && row.state === "accepted") {
            this.onBranchDispatch(row);
            return;
        }
        this.dialog.add(OtpDialog, {
            title: "Dispatch #" + row.ref + " - pickup code",
            hint: "Pick the rider and type the 6-digit pickup code the rider shows you (Delivery > Create OTP).",
            riders: row.riders || [],
            riderId: row.rider_id || 0,
            onConfirm: (code, riderId) => this.act(row, "dispatch_otp", { code, rider_id: riderId }),
        });
    }

    onOtp(row, kind) {
        this.dialog.add(OtpDialog, {
            title: kind === "pickup" ? "Pickup - enter the code for #" + row.ref
                                     : "Delivered - enter the customer code for #" + row.ref,
            hint: kind === "pickup"
                ? "The 6-digit pickup code the rider shows you."
                : "Ask the customer for the code they received on WhatsApp, after handing over.",
            onConfirm: (code) => this.act(row, kind === "pickup" ? "pickup_otp" : "deliver_otp", { code }),
        });
    }

    onFail(row) {
        this.dialog.add(ConfirmationDialog, {
            title: "Delivery failed - #" + row.ref + "?",
            body: "The customer and the rider are told; the job stays open to retry or return.",
            confirmLabel: "Mark as failed",
            cancelLabel: "Back",
            confirm: () => this.act(row, "fail", { reason: "Failed - marked at the counter" }),
        });
    }

    /** Cancelling is asked twice: it messages the customer and the rider. */
    onCancel(row) {
        this.dialog.add(ConfirmationDialog, {
            title: "Cancel order #" + row.ref + "?",
            body: "The customer and the rider are told straight away. "
                + (row.invoice_paid
                    ? "The invoice is already paid - refund it from the Delivery form afterwards."
                    : "Nothing has been paid on this order."),
            confirmLabel: "Cancel the order",
            cancelLabel: "Keep it",
            confirm: () => this.act(row, "cancel"),
        });
    }

    /** "Updated 12 s ago" / "Last seen 3 min ago" for the card's live line. */
    freshText(live) {
        if (!live || !live.has_pos) { return "No position yet"; }
        const age = (live.age || 0) + Math.max(0, Math.round((Date.now() - new Date(live.at).getTime()) / 1000));
        if (live.stale) { return `Last seen ${age < 90 ? age + " s" : Math.round(age / 60) + " min"} ago`; }
        return `Updated ${age} s ago`;
    }

    /** The office live map, filtered to this shop (and this card's rider). */
    openLiveMap(row) {
        this.action.doAction({
            type: "ir.actions.client", tag: "sales_automation_delivery.fleet_map", name: "Live map",
            context: { sa_shop_id: this.state.shopId || 0, sa_focus_rider: (row && row.rider_id) || 0 },
        });
    }

    stageLabel(row) {
        return {
            awaiting_shop: "New order",
            preparing: "Packing",
            ready: "Waiting for the rider",
            offered: "Rider called",
            accepted: "Rider on the way",
            picked: "Collected by rider",
            dispatched: "Collected by rider",
            out_for_delivery: "Rider near customer",
        }[row.state] || row.state;
    }
}

registry.category("actions").add("sales_automation_store.screen", StoreScreen);
