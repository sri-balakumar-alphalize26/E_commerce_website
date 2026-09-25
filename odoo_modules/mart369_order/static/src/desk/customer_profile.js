/**
 * One customer's full profile, in Odoo - the twin of the console's profile
 * page (components/admin/AdminCatalog.jsx, CustomerProfile).
 *
 * Opened from the Customers desk's "Open full profile". It reads the same
 * `res.users.mart369_admin_profile` the console's route reads, so the two show
 * the same customer: who they are, the risk strip and the cash-on-delivery
 * switch, the figures and goodwill credit, tags, staff notes, addresses, every
 * order, their support tickets and returns, and the wallet's history.
 *
 * Draws inside the desk's own classes (`.mart-builder.cu`) so the tags, notes
 * and address cards look exactly like the Customers panel's. The account
 * itself - login, groups, archive - is still changed on the customer form:
 * "Edit account" opens it.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "@mart369/ui/icon";
import { Switch } from "@mart369/ui/switch";

const MODEL = "res.users";
const TAG_TONES = ["grey", "red", "orange", "amber", "blue", "violet", "green", "blue", "red", "violet", "green", "orange"];
const ORDER_STATE = {
    placed: [_t("Placed"), "blue"], packed: [_t("Packed"), "violet"], shipped: [_t("Shipped"), "violet"],
    out: [_t("Out for delivery"), "amber"], delivered: [_t("Delivered"), "green"], cancelled: [_t("Cancelled"), "grey"],
};
const PAID_BY = { cod: _t("Cash on delivery"), upi: "UPI", card: _t("Card"), netbanking: _t("Net banking"), wallet: _t("Wallet") };
const TICKET_TONE = { new: "red", open: "amber", waiting: "blue", done: "green", cancelled: "grey" };
const RETURN_TONE = { requested: "amber", pickup: "blue", picked: "violet", done: "green", refused: "grey" };
const CREDIT = ["add", "refund", "reward"];

function message(err) {
    return err?.data?.message || err?.message?.data?.message || err?.message || _t("We could not reach the shop.");
}

function money(amount, currency) {
    const value = Number(amount) || 0;
    const decimals = currency?.decimals ?? 2;
    const shown = value.toLocaleString(currency?.locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    if (!currency?.symbol) {
        return shown;
    }
    return currency.position === "after" ? `${shown} ${currency.symbol}` : `${currency.symbol}${shown}`;
}

function ago(ms) {
    if (!ms) {
        return _t("Never");
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

function day(ms) {
    return ms ? new Date(ms).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
}

export class CustomerProfile extends Component {
    static template = "mart369_order.CustomerProfile";
    static components = { Layout, Icon, Switch };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.userId = this.props.action?.params?.userId;
        this.ORDER_STATE = ORDER_STATE;
        this.PAID_BY = PAID_BY;
        this.TICKET_TONE = TICKET_TONE;
        this.RETURN_TONE = RETURN_TONE;
        this.state = useState({
            c: null, error: "", busy: false, allTags: [],
            tagging: false, tagText: "",
            note: "", editing: null, editText: "",
            giving: false, giveAmount: "", giveReason: "",
        });
        onWillStart(() => this.load());
    }

    async load() {
        if (!this.userId) {
            this.state.error = _t("Open a customer from the Customers screen.");
            return;
        }
        try {
            this.state.c = await this.orm.call(MODEL, "mart369_admin_profile", [this.userId]);
            this.state.allTags = await this.orm.call(MODEL, "mart369_admin_tags", []);
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        }
    }

    /** Run a write, then read the profile again. */
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
            this.notification.add(message(err), { type: "danger" });
            return false;
        } finally {
            this.state.busy = false;
        }
    }

    // --------------------------------------------------------------- drawing

    money(v) { return money(v, this.state.c?.currency); }
    ago(ms) { return ago(ms); }
    day(ms) { return day(ms); }
    tone(tag) { return TAG_TONES[(tag.color || 0) % TAG_TONES.length]; }
    credit(m) { return CREDIT.includes(m.kind); }

    badges(c) {
        const ordered = c?.lastPlaced ? _t("ordered %s", ago(c.lastPlaced)) : "";
        if (c?.status === "new") {
            const left = c.newDaysLeft;
            return [
                [!left ? _t("New") : left === 1 ? _t("New · last day") : _t("New · %s days left", left), "blue"],
                ordered ? [_t("Active · %s", ordered), "green"] : [_t("Not ordered yet"), "amber"],
            ];
        }
        if (c?.status === "dormant") {
            return [[_t("Dormant · %s", ordered || _t("no orders")), "grey"]];
        }
        return [[_t("Active · %s", ordered || _t("no orders yet")), "green"]];
    }

    riskTone(n, loud) {
        return !n ? "" : loud && n >= 3 ? "cu-risk-bad" : "cu-risk-warn";
    }

    addressLines(a) {
        const near = a.landmark && !/^(near|opp|opposite|behind|beside|next to)\b/i.test(a.landmark)
            ? "near " + a.landmark : a.landmark;
        const place = a.town
            ? `${a.town}${a.state ? ", " + a.state : ""}${a.pin ? " " + a.pin : ""}`
            : [a.city, a.state].filter(Boolean).join(", ");
        return [a.line, [a.area, near].filter(Boolean).join(", "), place].filter(Boolean);
    }

    get callHref() {
        const phone = this.state.c?.phone;
        return phone ? "tel:" + phone.replace(/[^\d+]/g, "") : "";
    }

    get waHref() {
        return this.state.c?.waPhone ? "https://wa.me/" + this.state.c.waPhone : "";
    }

    // ------------------------------------------------------------ navigating

    back() {
        this.action.doAction("mart369_auth.action_mart369_customer_desk");
    }

    editAccount() {
        this.action.doAction("mart369_auth.action_mart369_customers", {
            viewType: "form", props: { resId: this.userId },
        });
    }

    openTicket(t) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "mart369.ticket", res_id: t.id,
            views: [[false, "form"]], target: "current",
        });
    }

    // ------------------------------------------------------------- writing

    setCod(off) {
        return this.run(() => this.orm.call(MODEL, "mart369_admin_set_cod", [this.userId, off]),
            off ? _t("Cash on delivery is off for this customer.") : _t("Cash on delivery is back on."));
    }

    get canGive() {
        return Number(this.state.giveAmount) > 0 && !!this.state.giveReason.trim() && !this.state.busy;
    }

    setGiveAmount(v) {
        this.state.giveAmount = (v || "").replace(/[^0-9.]/g, "");
    }

    async giveGoodwill() {
        const done = await this.run(() => this.orm.call(MODEL, "mart369_admin_goodwill",
            [this.userId, Number(this.state.giveAmount), this.state.giveReason.trim()]),
            _t("Goodwill credit added to the wallet."));
        if (done) {
            Object.assign(this.state, { giving: false, giveAmount: "", giveReason: "" });
        }
    }

    get tagChoices() {
        const on = new Set((this.state.c?.tags || []).map((t) => t.id));
        const text = this.state.tagText.trim().toLowerCase();
        return this.state.allTags.filter((t) => !on.has(t.id) && t.name.toLowerCase().includes(text));
    }

    get tagIsNew() {
        const text = this.state.tagText.trim().toLowerCase();
        return !!text && !this.state.allTags.some((t) => t.name.toLowerCase() === text);
    }

    async saveTags(names) {
        const done = await this.run(() => this.orm.call(MODEL, "mart369_admin_set_tags", [this.userId, names]));
        if (done) {
            this.state.tagging = false;
            this.state.tagText = "";
        }
    }

    addTag(name) {
        const clean = (name || "").trim();
        if (clean) {
            this.saveTags([...(this.state.c.tags || []).map((t) => t.name), clean]);
        }
    }

    removeTag(tag) {
        this.saveTags((this.state.c.tags || []).filter((t) => t.id !== tag.id).map((t) => t.name));
    }

    onTagKey(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            const first = this.tagChoices[0];
            this.addTag(this.tagIsNew || !first ? this.state.tagText : first.name);
        } else if (ev.key === "Escape") {
            this.state.tagging = false;
        }
    }

    async addNote() {
        const text = this.state.note.trim();
        if (text && await this.run(() => this.orm.call(MODEL, "mart369_admin_add_note", [this.userId, text]))) {
            this.state.note = "";
        }
    }

    startEdit(n) {
        this.state.editing = n.id;
        this.state.editText = n.text;
    }

    async saveEdit(n) {
        const text = this.state.editText.trim();
        if (text && await this.run(() => this.orm.call(MODEL, "mart369_admin_edit_note", [this.userId, n.id, text]))) {
            this.state.editing = null;
        }
    }

    deleteNote(n) {
        return this.run(() => this.orm.call(MODEL, "mart369_admin_delete_note", [this.userId, n.id]));
    }

    async addAddress() {
        try {
            const action = await this.orm.call(MODEL, "action_mart369_add_address", [[this.userId]]);
            await this.action.doAction(action, { onClose: () => this.load() });
        } catch (err) {
            this.notification.add(message(err), { type: "danger" });
        }
    }
}

registry.category("actions").add("mart369_order.customer_profile", CustomerProfile);
