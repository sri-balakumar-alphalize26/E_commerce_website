/** @odoo-module **/

/**
 * The enquiry desk.
 *
 * Two stages on one screen, because they are two different questions:
 *   - "who should we ask?"   - waiting for a person here
 *   - "who has answered?"    - waiting for suppliers out there
 *
 * The second half used to be invisible: the card vanished the moment the
 * vendors were messaged, which is exactly when the shop starts wondering
 * whether anybody replied.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Alarm } from "./store_screen";
// The tones are shared with the background service, which rings the same two
// alarms from every other menu. One definition, so they cannot drift apart.
import {
    ENQUIRY_TONE, STALLED_TONE, presence,
} from "./enquiry_alarm_shared";
import { ColourKey, ENQUIRY_TABS, byDay, byProduct, dayName, enquiryPill, matches, pricesIn, remember, remembered, timeOf } from "./board";
import { VendorCards, cardState, replyTime } from "./vendor_cards";
import { ChatLog } from "./chat_log";
import { SaSelect } from "./fields";
const TICK_MS = 1000;

/** m:ss, or h:mm:ss once it has been going a while. */
function clock(totalSeconds) {
    const s = Math.max(0, Math.floor(totalSeconds || 0));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = `${s % 60}`.padStart(2, "0");
    return h ? `${h}:${`${m}`.padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

export class VendorDialog extends Component {
    static template = "sales_automation_store.VendorDialog";
    static components = { Dialog };
    static props = { close: Function, row: Object, onSend: Function };

    setup() {
        this.state = useState({ picked: {} });
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

    send() {
        if (!this.chosen.length) {
            return;
        }
        this.props.onSend(this.chosen);
        this.props.close();
    }
}

/** Everything that happened on one enquiry. */
export class TrackDialog extends Component {
    static template = "sales_automation_store.TrackDialog";
    static components = { Dialog };
    static props = { close: Function, requestId: Number };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ detail: null, loading: true });
        onWillStart(async () => {
            await this.load();
            this._tick = setInterval(() => {
                if (this.state.detail) {
                    this.state.detail.elapsed_seconds += 1;
                    if (this.state.detail.seconds_left > 0) {
                        this.state.detail.seconds_left -= 1;
                    }
                }
            }, TICK_MS);
            // The vendors answer while this is open; re-read now and then.
            this._poll = setInterval(() => this.load(), 15000);
        });
        onWillUnmount(() => {
            clearInterval(this._tick);
            clearInterval(this._poll);
        });
    }

    async load() {
        this.state.detail = await this.orm.call(
            "sa.group.request", "sa_enquiry_detail", [this.props.requestId]);
        this.state.loading = false;
    }

    clock(seconds) {
        return clock(seconds);
    }

    when(iso) {
        if (!iso) {
            return "";
        }
        const d = new Date(iso);
        return isNaN(d) ? "" : d.toLocaleTimeString();
    }

    get replied() {
        const d = this.state.detail;
        return d ? d.vendors.filter((v) => v.replied).length : 0;
    }
}

/**
 * Type in a price nobody answered with.
 *
 * The number is the SUPPLIER's price - the margin is added on top, the same
 * way a real vendor reply is treated - so the dialog shows what the customer
 * will be told before anything is written. A shopkeeper who has just come off
 * the phone should not have to work out which of the two numbers this field
 * wants.
 */
export class PriceDialog extends Component {
    static template = "sales_automation_store.PriceDialog";
    static components = { Dialog, SaSelect };
    static props = { close: Function, row: Object, onApply: Function,
                     sellMode: { type: Boolean, optional: true } };

    setup() {
        this.state = useState({
            // Prefilled with the price-list hint when there is one, so the
            // common case is one tap - but still a person's tap.
            cost: this.props.sellMode ? "" : (this.props.row.hint_cost ? `${this.props.row.hint_cost}` : ""),
            vendor: "",
            days: "",
            error: "",
        });
    }

    get cost() {
        // Same shapes the public page accepts: "500", "500.50", "1,200".
        const raw = (this.state.cost || "").trim().replace(/,/g, "");
        const value = parseFloat(raw);
        return raw !== "" && isFinite(value) ? value : 0;
    }

    get sell() {
        // In selling-price mode the number typed IS the customer's price.
        if (this.props.sellMode) {
            return this.cost;
        }
        return this.cost * (1 + (this.props.row.margin || 0) / 100);
    }

    get vendorOptions() {
        return [{ value: "", label: "Not saying" }].concat(this.props.row.vendors.map((v) => ({ value: `${v.id}`, label: v.name })));
    }

    onVendor(value) {
        this.state.vendor = value;
    }

    get vendorName() {
        const picked = this.props.row.vendors.find(
            (v) => `${v.id}` === `${this.state.vendor}`);
        return picked ? picked.name : "";
    }

    money(value) {
        return `${(value || 0).toFixed(2)} ${this.props.row.currency || ""}`;
    }

    apply() {
        if (this.cost <= 0) {
            this.state.error = "Type the price as a number, like 500.";
            return;
        }
        this.props.onApply({
            cost: this.cost,
            vendorIds: this.state.vendor ? [parseInt(this.state.vendor, 10)] : [],
            days: parseInt(this.state.days, 10) || 0,
        });
        this.props.close();
    }
}

export class EnquiryScreen extends Component {
    static template = "sales_automation_store.EnquiryScreen";
    static components = { ChatLog, ColourKey, SaSelect, VendorCards };
    // client action: 369ai 19 passes action / actionId / updateActionState / className
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.bus = useService("bus_service");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.alarm = new Alarm();
        // Its own instance, not a second tone on the shared one: `ring()`
        // stops whatever is already ringing, so one Alarm cannot sound two
        // alarms at once - the no-reply beep would silence the choose-a-
        // vendor beep and the shop would never know it had happened.
        this.stalledAlarm = new Alarm();

        this.state = useState({
            rows: [],
            tracking: [],
            ringing: 0,
            soundOn: true,
            soundBlocked: false,
            loading: true,
            busy: 0,
            ring: 30,
            repeat: 10,
            maxMinutes: 1,
            stalled: [],
            stalledRinging: 0,
            stalledRing: 30,
            stalledRepeat: 120,
            stalledMaxMinutes: 10,
            // the list (23 Nov 2026)
            view: remembered("sa_enquiries_view_2", "list"), by: remembered("sa_board_by", "product"),
            tab: "needs", sel: 0, search: "", days: 30, detail: null, detailOpen: false,
            old: [], counts: {}, more: false,
        });

        this._timer = null;
        this._stalledTimer = null;
        this._tick = null;
        this._alarmUntil = 0;
        this._stalledUntil = 0;
        this._onBus = this._onBus.bind(this);

        // While this screen is up it owns the sound; the background
        // service stands down so the two do not beat against each other.
        presence.screens += 1;

        onWillStart(async () => {
            await this.refresh();
            this.bus.addChannel("sa_store_0");
            this.bus.subscribe("sa_enquiry/refresh", this._onBus);
            this._tick = setInterval(() => this._countdown(), TICK_MS);
            // Vendor replies do not go through the bus, so the tracking half
            // needs a slow poll of its own.
            this._poll = setInterval(() => this.refresh(), 20000);
            await this.loadOld();
        });

        // The alarm is on by default (owner, 29 Sep 2026): a browser only
        // starts audio inside a user gesture, so both alarms are armed on
        // the first tap or key press anywhere - the menu click that opened
        // this screen usually counts already. The button appears only when
        // the browser refuses inside a gesture.
        this._armOnGesture = async () => {
            if (this._armed) {
                return;
            }
            const ok = (await this.alarm.arm()) && (await this.stalledAlarm.arm());
            if (ok) {
                this._armed = true;
                this.state.soundBlocked = false;
                document.removeEventListener("pointerdown", this._armOnGesture, true);
                document.removeEventListener("keydown", this._armOnGesture, true);
                this._syncAlarm();
                this._syncStalledAlarm();
            } else {
                this.state.soundBlocked = true;
            }
        };
        onMounted(async () => {
            document.addEventListener("pointerdown", this._armOnGesture, true);
            document.addEventListener("keydown", this._armOnGesture, true);
            // Already allowed (the tab was clicked before): arm right away,
            // silently - a refusal here is not a block, just "not yet".
            const ok = (await this.alarm.arm()) && (await this.stalledAlarm.arm());
            if (ok) {
                this._armed = true;
                this._syncAlarm();
                this._syncStalledAlarm();
            }
        });

        onWillUnmount(() => {
            presence.screens = Math.max(0, presence.screens - 1);
            document.removeEventListener("pointerdown", this._armOnGesture, true);
            document.removeEventListener("keydown", this._armOnGesture, true);
            this._stopAlarm();
            this._stopStalledAlarm();
            clearInterval(this._tick);
            clearInterval(this._poll);
            this.bus.unsubscribe("sa_enquiry/refresh", this._onBus);
        });
    }

    _onBus() {
        this.refresh();
    }

    _countdown() {
        for (const row of this.state.rows) {
            if (row.seconds_left > 0) {
                row.seconds_left -= 1;
            }
        }
        for (const row of this.state.tracking) {
            if (row.seconds_left > 0) {
                row.seconds_left -= 1;
            } else {
                row.closed = true;
            }
        }
    }

    async refresh() {
        const data = await this.orm.call(
            "sa.group.request", "sa_enquiry_queue", []);
        const wasRinging = this.state.ringing;
        this.state.rows = data.rows;
        this.state.tracking = data.tracking || [];
        this.state.ringing = data.ringing;
        this.state.ring = data.ring || this.state.ring;
        this.state.repeat = data.repeat || this.state.repeat;
        this.state.maxMinutes = data.max_minutes;
        const wasStalled = this.state.stalledRinging;
        this.state.stalled = data.stalled || [];
        this.state.stalledRinging = data.stalled_ringing || 0;
        this.state.stalledRing = data.stalled_ring || this.state.stalledRing;
        this.state.stalledRepeat =
            data.stalled_repeat || this.state.stalledRepeat;
        this.state.stalledMaxMinutes = data.stalled_max_minutes;
        this.state.counts = data.counts || this.state.counts;
        this.state.loading = false;
        this._keepSelection();
        if (this.state.sel && this.state.view === "list") {
            this.loadDetail();
        }
        if (this.state.ringing > wasRinging) {
            this._stopAlarm();          // a new arrival restarts the clock
        }
        if (this.state.stalledRinging > wasStalled) {
            this._stopStalledAlarm();
        }
        this._syncAlarm();
        this._syncStalledAlarm();
    }

    /**
     * The no-reply alarm, on its own cadence: it rings for `stalledRing`
     * seconds and comes back every `stalledRepeat` seconds - minutes apart,
     * not seconds, because clearing this card means phoning a supplier.
     */
    _syncStalledAlarm() {
        if (this.state.stalledRinging > 0 && this.state.soundOn) {
            if (!this._stalledTimer) {
                const minutes = this.state.stalledMaxMinutes;
                this._stalledUntil = minutes
                    ? Date.now() + minutes * 60000
                    : Infinity;
                this.stalledAlarm.ring(this.state.stalledRing, STALLED_TONE);
                this._stalledTimer = setInterval(() => {
                    if (Date.now() >= this._stalledUntil) {
                        this._stopStalledAlarm();
                        return;
                    }
                    this.stalledAlarm.ring(
                        this.state.stalledRing, STALLED_TONE);
                }, this.state.stalledRepeat * 1000);
            }
        } else {
            this._stopStalledAlarm();
        }
    }

    _stopStalledAlarm() {
        if (this._stalledTimer) {
            clearInterval(this._stalledTimer);
            this._stalledTimer = null;
        }
        this.stalledAlarm.stop();
    }

    /** Open the "type the price in" dialog for a stalled enquiry. */
    /** Vendor price differs from the product page: the counter picks one
     *  and confirms it once more - that confirmation is what turns it into
     *  the order and invoice price. */
    onApprovePrice(row, which) {
        const cur = row.currency || "";
        const ask = (price, extra) => {
            this.dialog.add(ConfirmationDialog, {
                title: `Approve the price for #${row.ref}`,
                body: `Quote the customer ${price.toFixed(2)} ${cur} for ${row.product}? `
                    + `This becomes the order and invoice price.`,
                confirmLabel: `Yes - quote ${price.toFixed(2)}`,
                cancelLabel: "Back",
                confirm: () => this.act(row, "approve_price", [], { choice: which, ...extra }),
            });
        };
        if (which === "page") {
            ask(row.choice.page, {});
        } else if (which === "vendor") {
            ask(row.choice.vendor, {});
        } else {
            this.dialog.add(PriceDialog, {
                row,
                sellMode: true,
                onApply: ({ cost }) => ask(cost, { cost }),
            });
        }
    }

    onSetPrice(row) {
        this.dialog.add(PriceDialog, {
            row,
            onApply: ({ cost, vendorIds, days }) =>
                this.act(row, "set_price", vendorIds, { cost, days }),
        });
    }

    _syncAlarm() {
        if (this.state.ringing > 0 && this.state.soundOn) {
            if (!this._timer) {
                const minutes = this.state.maxMinutes;
                this._alarmUntil = minutes
                    ? Date.now() + minutes * 60000
                    : Infinity;
                this.alarm.ring(this.state.ring, ENQUIRY_TONE);
                this._timer = setInterval(() => {
                    if (Date.now() >= this._alarmUntil) {
                        this._stopAlarm();
                        return;
                    }
                    this.alarm.ring(this.state.ring, ENQUIRY_TONE);
                }, (this.state.ring + this.state.repeat) * 1000);
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
        this.alarm.stop();
    }

    async onEnableSound() {
        if (await this.alarm.arm()) {
            // Both instances are armed from this one click: a browser only
            // allows an AudioContext to start inside a user gesture, so an
            // alarm armed later never sounds at all.
            await this.stalledAlarm.arm();
            this._armed = true;
            this.state.soundBlocked = false;
            this.state.soundOn = true;
            this.alarm.ring(2, ENQUIRY_TONE);
            this._syncAlarm();
            this._syncStalledAlarm();
        } else {
            this.notification.add(
                "This browser will not play sound on this page. Check the "
                + "tab is not muted and the device volume is up.",
                { type: "warning" });
        }
    }

    async onTestSound() {
        if (!(await this.alarm.arm())) {
            return this.onEnableSound();
        }
        this.state.soundOn = true;
        if (!this._timer) {
            this.alarm.ring(2, ENQUIRY_TONE);
        }
    }

    countdown(row) {
        return clock(row.seconds_left);
    }

    // ------------------------------------------------------------ the list
    get boardRows() {
        const kind = (rows, k) => rows.map((r) => Object.assign(r, { kind: typeof k === "function" ? k(r) : k, key: r.id }));
        switch (this.state.tab) {
            case "needs":
                return kind(this.state.rows, "pick").concat(kind(this.state.stalled, (r) => (r.choice ? "choice" : r.pick_vendor ? "vendor" : "price")));
            case "vendors":
                return kind(this.state.tracking.filter((r) => r.state === "sourcing"), "vendors");
            case "sent":
                return kind(this.state.tracking.filter((r) => r.state !== "sourcing"), "sent");
        }
        return kind(this.state.old, this.state.tab);
    }
    get enquiryTabs() {
        const c = this.state.counts;
        const n = { needs: this.state.rows.length + this.state.stalled.length,
                    vendors: this.state.tracking.filter((r) => r.state === "sourcing").length,
                    sent: this.state.tracking.filter((r) => r.state !== "sourcing").length, ordered: c.ordered || 0, closed: c.closed || 0 };
        return ENQUIRY_TABS.map(([key, name]) => ({ key, name, count: n[key] }));
    }
    get enquiryDays() {
        const since = new Date();
        since.setHours(0, 0, 0, 0);
        since.setDate(since.getDate() - (this.state.days - 1));
        const rows = this.boardRows.filter((r) => matches(r, this.state.search) && (!r.at || new Date(r.at) >= since));
        return this.state.by === "day" ? byDay(rows, () => false) : byProduct(rows, () => false, (r) => r.product);
    }
    /** The Cards view: the same sections, one per product. */
    sections(rows) {
        return byProduct(rows, () => false, (r) => r.product);
    }
    setBy(by) {
        this.state.by = by;
        remember("sa_board_by", by);
    }
    pricesIn(rows) {
        return pricesIn(rows);
    }
    dayOf(iso) {
        return dayName(iso).split(",")[0];
    }
    replyTime(card) {
        return replyTime(card.replied_at);
    }
    cardWords(card) {
        return cardState(card);
    }
    onChooseVendor(row, card) {
        const cur = row.currency || card.currency || "";
        this.dialog.add(ConfirmationDialog, {
            title: `Choose ${card.vendor} for #${row.ref}`,
            body: `${card.vendor} asks ${card.price.toFixed(2)} ${card.currency || cur}. With your margin the customer pays ${card.sell.toFixed(2)} ${cur}. Choose this vendor?`,
            confirmLabel: "Choose " + card.vendor,
            cancelLabel: "Back",
            confirm: async () => {
                this.state.busy = row.id;
                try {
                    await this.orm.call("sa.group.request", "sa_vendor_choose", [row.id, card.quote_id]);
                } finally {
                    this.state.busy = 0;
                    await this.refresh();
                }
            },
            cancel: () => {},
        });
    }
    get selected() {
        return this.boardRows.find((r) => r.id === this.state.sel) || null;
    }
    _keepSelection() {
        if (!this.selected) {
            const first = this.enquiryDays[0];
            this.state.sel = first ? first.rows[0].id : 0;
            this.state.detail = null;
            this.state.detailOpen = false;
        }
    }
    async openTab(key) {
        this.state.tab = key;
        this.state.sel = 0;
        this.state.detail = null;
        this.state.detailOpen = false;
        await this.loadOld();
        this._keepSelection();
        await this.loadDetail();
    }
    async loadOld(more = false) {
        if (!["ordered", "closed"].includes(this.state.tab)) {
            this.state.more = false;
            return;
        }
        const data = await this.orm.call("sa.group.request", "sa_enquiry_board", [this.state.tab, this.state.search.trim(), this.state.days,
            more ? this.state.old.length : 0]);
        this.state.old = more ? this.state.old.concat(data.rows) : data.rows;
        this.state.counts = data.counts;
        this.state.more = data.more;
    }
    loadMore() {
        return this.loadOld(true);
    }
    get whenOptions() {
        return [{ value: 30, label: "30 days" }, { value: 1, label: "Today" }, { value: 7, label: "7 days" }];
    }
    async onWhen(value) {
        this.state.days = parseInt(value, 10) || 30;
        await this.loadOld();
        this._keepSelection();
    }
    async select(row) {
        this.state.sel = row.id;
        this.state.detailOpen = true;
        await this.loadDetail();
    }
    async loadDetail() {
        const id = this.state.sel;
        if (!id) {
            this.state.detail = null;
            return;
        }
        try {
            const detail = await this.orm.silent.call("sa.group.request", "sa_enquiry_detail", [id]);
            if (id === this.state.sel) {
                this.state.detail = detail;
            }
        } catch {
            /* gone meanwhile: the list is read again in a moment */
        }
    }
    closeDetail() {
        this.state.detailOpen = false;
    }
    onRowKey(ev, row) {
        if (ev.target === ev.currentTarget && (ev.key === "Enter" || ev.key === " ")) {
            ev.preventDefault();
            this.select(row);
        }
    }
    toggleView() {
        this.state.view = this.state.view === "list" ? "cards" : "list";
        remember("sa_enquiries_view_2", this.state.view);
    }
    pill(row) {
        return enquiryPill(row);
    }
    timeOf(iso) {
        return timeOf(iso);
    }
    talk(d) {
        return d.messages.concat(d.vendor_messages).sort((a, b) => String(a.at).localeCompare(String(b.at)));
    }
    useLate(row, better) {
        this.dialog.add(ConfirmationDialog, {
            title: "Use this price?",
            body: "The customer gets the lower price now, instead of the one they were told.",
            confirmLabel: "Use this price",
            confirm: async () => {
                await this.orm.call("sa.group.request", "sa_enquiry_use_late", [row.id, better.quote_id]);
                await this.refresh();
            },
            cancel: () => {},
        });
    }

    onPick(row) {
        this.dialog.add(VendorDialog, {
            row,
            onSend: (ids) => this.act(row, "send", ids),
        });
    }

    onTrack(row) {
        this.dialog.add(TrackDialog, { requestId: row.id });
    }

    async act(row, action, vendorIds, kwargs) {
        if (this.state.busy === row.id) {
            return;
        }
        this.state.busy = row.id;
        try {
            const data = await this.orm.call(
                "sa.group.request", "sa_enquiry_act",
                [row.id, action, vendorIds || []], kwargs || {});
            this.state.rows = data.rows;
            this.state.tracking = data.tracking || [];
            this.state.ringing = data.ringing;
            this.state.stalled = data.stalled || [];
            this.state.stalledRinging = data.stalled_ringing || 0;
            this.state.counts = data.counts || this.state.counts;
            this._keepSelection();
            this._syncAlarm();
            this._syncStalledAlarm();
        } finally {
            this.state.busy = 0;
        }
    }
}

registry.category("actions")
    .add("sales_automation_store.enquiries", EnquiryScreen);
