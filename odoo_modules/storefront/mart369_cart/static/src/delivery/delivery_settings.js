/**
 * Delivery settings - 369 Mart > Store > Delivery settings (13 Nov 2026).
 *
 * Every delivery option on one page, saved with one Save: how we deliver
 * (one area / many branches), the branches, the Between-branches grid that
 * replaces the hub rules list, fees, the delivery slots (on/off and the list
 * itself, 17 Nov 2026), the WhatsApp delivery
 * section and, folded away, service areas and per-branch own fees.
 *
 * The twin of the console's Delivery > Settings. Both read
 * `mart369_settings_get` and save through `mart369_settings_save` on
 * `mart369.delivery.settings.page`, so the two screens cannot disagree.
 * Save is all or nothing: a wrong value comes back under its field and
 * nothing is written.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Switch } from "@mart369/ui/switch";
import { Icon } from "@mart369/ui/icon";

const PAGE = "mart369.delivery.settings.page";
const NONE = "Not delivered";

export const STATE_TONE = { ok: "green", wait: "blue", todo: "amber", off: "grey" };
export const STATE_WORD = { ok: _t("Ready"), wait: _t("Setting up"), todo: _t("Needs you"), off: _t("Not delivering") };

const str = (v) => (v === null || v === undefined ? "" : String(v));

/** What the page edits, as strings where people type numbers. */
export function draftOf(page) {
    const cells = {};
    for (const c of page.routes?.cells || []) {
        cells[`${c.from}-${c.to}`] = { ...c };
    }
    const fees = {};
    for (const [k, f] of Object.entries(page.fees || {})) {
        if (f) {
            fees[k] = { ...f, fee: str(f.fee), freeAbove: str(f.freeAbove), minOrder: str(f.minOrder) };
        }
    }
    return {
        mode: page.mode,
        branches: (page.branches || []).map((b) => ({
            ...b, quickKm: str(b.quickKm), maybeKm: str(b.maybeKm),
            quickFee: str(b.quickFee), expressFee: str(b.expressFee), freeAbove: str(b.freeAbove),
        })),
        cells,
        fees,
        slotsOn: !!page.slots?.on,
        slots: (page.slots?.rows || []).map((s) => ({
            ...s, key: `s${s.id}`, dayOffset: str(s.dayOffset), fromHour: str(s.fromHour), toHour: str(s.toHour),
            orderBefore: str(s.orderBefore), fee: str(s.fee), capacity: str(s.capacity),
        })),
        whatsapp: page.whatsapp ? {
            ...page.whatsapp, quickHours: str(page.whatsapp.quickHours),
            cutoffHour: str(page.whatsapp.cutoffHour), expressDays: str(page.whatsapp.expressDays),
        } : null,
    };
}

export class DeliverySettings extends Component {
    static template = "mart369_cart.DeliverySettings";
    static components = { Layout, Switch, Icon };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.NONE = NONE;
        this.STATE_TONE = STATE_TONE;
        this.STATE_WORD = STATE_WORD;
        this.state = useState({
            page: null, draft: null, base: "", errs: {}, banner: "", done: null,
            loading: true, busy: false, error: "",
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.show(await this.orm.call(PAGE, "mart369_settings_get", []));
            this.state.error = "";
        } catch (err) {
            this.state.error = err?.data?.message || err?.message || _t("We could not read the delivery settings.");
        } finally {
            this.state.loading = false;
        }
    }

    show(page) {
        this.state.page = page;
        this.state.draft = draftOf(page);
        this.state.base = JSON.stringify(this.state.draft);
        this.state.errs = {};
        this.state.banner = "";
    }

    get dirty() {
        return !!this.state.draft && JSON.stringify(this.state.draft) !== this.state.base;
    }

    get todos() {
        const status = this.state.page?.status || { branches: [], shop: [] };
        const out = [];
        for (const b of status.branches) {
            for (const c of b.checks) {
                if (c.state === "todo") {
                    out.push({ ...c, branch: b });
                }
            }
        }
        for (const c of status.shop) {
            if (c.state === "todo") {
                out.push(c);
            }
        }
        return out;
    }

    setVal(obj, key, value) {
        obj[key] = value;
    }

    isFree(fee) {
        return Number(fee.freeAbove) > 0;
    }

    err(section, row, field) {
        return this.state.errs[`${section}|${row}|${field}`] || "";
    }

    // ------------------------------------------------------------- the grid

    cell(from, to) {
        const k = `${from}-${to}`;
        return this.state.draft.cells[k] || { from, to, arrives: "", cargo: false, auto: false };
    }

    options(c) {
        const choices = this.state.page.routes?.choices || [];
        return c.arrives && !choices.includes(c.arrives) ? [c.arrives, ...choices] : choices;
    }

    setCell(from, to, key, value) {
        const k = `${from}-${to}`;
        const c = { ...this.cell(from, to), [key]: value, auto: false };
        this.state.draft.cells[k] = c;
    }

    // ------------------------------------------------------------- the slots

    /** A new slot row: Quick, today 6 - 8 PM, on - saved with Save all. */
    addSlot() {
        this.newSlots = (this.newSlots || 0) + 1;
        this.state.draft.slots.push({
            id: null, key: `new-${this.newSlots}`, mode: "quick", kind: "window",
            heading: _t("Today"), detail: this.state.page.slots?.detail ? "6 - 8 PM" : "",
            dayOffset: "0", fromHour: "18", toHour: "20", orderBefore: "24",
            fee: "0", capacity: "0", active: true,
        });
    }

    slotRowKey(s) {
        return s.id || s.key;
    }

    // -------------------------------------------------------------- actions

    async save() {
        const d = this.state.draft;
        const body = {
            mode: d.mode,
            branches: d.branches.map((b) => ({
                id: b.id, pin: b.pin, quick: b.quick, quickKm: b.quickKm, maybeKm: b.maybeKm,
                ownFees: b.ownFees, quickFee: b.quickFee, expressFee: b.expressFee, freeAbove: b.freeAbove,
            })),
            cells: Object.values(d.cells).filter((c) => c.arrives),
            fees: d.fees,
            slotsOn: d.slotsOn,
            slots: d.slots,
        };
        if (d.whatsapp) {
            body.whatsapp = d.whatsapp;
        }
        this.state.busy = true;
        try {
            const result = await this.orm.call(PAGE, "mart369_settings_save", [body]);
            if (!result.ok) {
                const map = {};
                for (const e of result.errors || []) {
                    map[`${e.section}|${e.row}|${e.field}`] = e.message;
                }
                this.state.errs = map;
                const n = (result.errors || []).length;
                this.state.banner = n === 1
                    ? _t("Nothing was saved. Fix the value marked in red, then Save all again.")
                    : _t("Nothing was saved. Fix the %s values marked in red, then Save all again.", n);
                if (n && !Object.keys(map).some((k) => k.split("|")[2])) {
                    this.state.banner = result.errors[0].message;
                }
                return;
            }
            this.show(result.page);
            this.notification.add(_t("Delivery settings saved"), { type: "success" });
        } catch (err) {
            this.notification.add(err?.data?.message || err?.message || _t("That could not be saved."), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    discard() {
        this.state.draft = JSON.parse(this.state.base);
        this.state.errs = {};
        this.state.banner = "";
    }

    async runSetup() {
        this.state.busy = true;
        try {
            const out = await this.orm.call("stock.warehouse", "mart369_setup_run", []);
            this.state.done = out.done || [];
            await this.load();
        } finally {
            this.state.busy = false;
        }
    }

    open(xmlid) {
        this.action.doAction(xmlid).catch(() =>
            this.notification.add(_t("That screen is not installed here."), { type: "warning" }));
    }

    async fix(c) {
        const where = {
            branch: "mart369_cart.action_mart369_delivery_desk",
            address: "mart369_cart.action_mart369_delivery_desk",
            fees: null, slots: null, routes: null,
            riders: "sales_automation_delivery.action_sa_delivery_partner",
            shop: "sales_automation_delivery.action_sa_delivery_shop",
        }[c.fix];
        if (c.fix === "address" && c.branch) {
            this.action.doAction(await this.orm.call("stock.warehouse", "action_mart369_fix", [[c.branch.id]]));
            return;
        }
        if (where) {
            this.open(where);
            return;
        }
        document.getElementById(`dz-${c.fix}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}

registry.category("actions").add("mart369_cart.delivery_settings", DeliverySettings);
