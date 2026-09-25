/**
 * Settings - the app console's Settings screen, inside Odoo.
 *
 * The twin of /admin/settings. It reads `mart369.config.mart369_admin_settings`
 * and saves one tab at a time through `mart369_admin_save`, the same two
 * methods the console calls. Each tab lands on the record that really decides
 * it - the company, Odoo's payment providers, the shared settings record - so
 * neither screen keeps a copy the other could drift from. What lives where is
 * written down in mart369/models/settings_admin.py.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Icon } from "@mart369/ui/icon";
import { Tabs } from "@mart369/ui/tabs";
import { Switch } from "@mart369/ui/switch";
import { Pick } from "@mart369/ui/pick";
import { Dialog } from "@web/core/dialog/dialog";

const MODEL = "mart369.config";

const STORE_FIELDS = [
    { key: "name", label: _t("Store name"), wide: true },
    { key: "phone", label: _t("Phone") },
    { key: "email", label: _t("Email"), type: "email" },
    { key: "street", label: _t("Address"), wide: true, placeholder: _t("Door number and street") },
    { key: "street2", label: _t("Area") },
    { key: "city", label: _t("City") },
    { key: "zip", label: _t("PIN code") },
    { key: "gstin", label: _t("GSTIN") },
];

const ALERTS = [
    { key: "newOrder", label: _t("New orders"), help: _t("Badge and bell when orders are waiting to be moved on") },
    { key: "lowStock", label: _t("Low stock"), help: _t("Bell when products reach the level where the app says “Only N left”") },
];

const PAY_ICON = { cod: "money", wallet: "wallet", gateway: "lock" };
const PAY_STATE = {
    enabled: [_t("On"), "green"],
    test: [_t("Test mode"), "orange"],
    disabled: [_t("Off"), "grey"],
};

function message(err) {
    return (
        err?.data?.message ||
        err?.message?.data?.message ||
        err?.message ||
        _t("We could not reach the shop.")
    );
}

function money(amount, currency) {
    const value = Number(amount) || 0;
    const decimals = currency?.decimals ?? 2;
    const shown = value.toLocaleString(currency?.locale, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
    if (!currency?.symbol) {
        return shown;
    }
    return currency.position === "after"
        ? `${shown} ${currency.symbol}`
        : `${currency.symbol}${shown}`;
}

const copy = (v) => JSON.parse(JSON.stringify(v));

// The usual choices for "New for" and "Dormant after"; anything else is Custom.
const DAY_PRESETS = [15, 30, 45, 60, 90, 120, 150];

/** Custom number of days, asked for in a small dialog. */
export class DaysDialog extends Component {
    static template = "mart369_payment.DaysDialog";
    static components = { Dialog };
    static props = {
        close: { type: Function },
        title: { type: String },
        value: { type: Number },
        onSave: { type: Function },
    };

    setup() {
        this.state = useState({ value: String(this.props.value || "") });
    }

    get days() {
        return Number(this.state.value);
    }

    get canSave() {
        return Number.isInteger(this.days) && this.days >= 1 && this.days <= 3650;
    }

    edit(ev) {
        this.state.value = ev.target.value.replace(/\D/g, "");
    }

    save() {
        if (!this.canSave) {
            return;
        }
        this.props.onSave(this.days);
        this.props.close();
    }
}

export class SettingsDesk extends Component {
    static template = "mart369_payment.SettingsDesk";
    static components = { Layout, Icon, Tabs, Switch, Pick };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.STORE_FIELDS = STORE_FIELDS;
        this.ALERTS = ALERTS;
        this.PAY_ICON = PAY_ICON;

        this.state = useState({
            tab: "store",
            saved: null,
            draft: null,
            loading: true,
            busy: false,
            error: "",
        });

        onWillStart(() => this.load());
    }

    // -------------------------------------------------------------- reading

    async load() {
        this.state.loading = true;
        try {
            const settings = await this.orm.call(MODEL, "mart369_admin_settings", []);
            this.take(settings);
            this.state.error = "";
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.loading = false;
        }
    }

    /** What the shop answered becomes both the saved copy and the draft, so a
     *  save shows what was stored, not what was typed. */
    take(settings) {
        this.state.saved = settings;
        this.state.draft = copy(settings);
    }

    // ---------------------------------------------------------------- state

    get group() {
        return this.state.tab === "payments" ? "pay" : this.state.tab;
    }

    get tabItems() {
        const tabs = [["store", _t("Store"), null]];
        if (this.state.saved?.pay) {
            tabs.push(["payments", _t("Payments"), null]);
        }
        // Added by mart369_auth: how long New lasts, when Dormant starts.
        if (this.state.saved?.customers) {
            tabs.push(["customers", _t("Customers"), null]);
        }
        tabs.push(["alerts", _t("Alerts"), null]);
        return tabs;
    }

    get dirty() {
        const { saved, draft } = this.state;
        if (!saved || !draft) {
            return false;
        }
        return JSON.stringify(saved[this.group]) !== JSON.stringify(draft[this.group]);
    }

    pickTab(tab) {
        this.state.tab = tab;
        this.state.error = "";
    }

    setField(group, key, value) {
        this.state.draft[group][key] = value;
    }

    /** The day choices as Pick takes them. A saved number that is not one of
     *  the usual ones is listed too, marked custom, so it shows as chosen. */
    dayOptions(key) {
        const current = this.state.draft.customers[key];
        const days = DAY_PRESETS.includes(current) || !current
            ? DAY_PRESETS
            : [...DAY_PRESETS, current].sort((a, b) => a - b);
        return [
            ...days.map((d) => [String(d), DAY_PRESETS.includes(d) ? _t("%s days", d) : _t("%s days (custom)", d)]),
            ["custom", _t("Custom…")],
        ];
    }

    /** The Pick takes strings; the setting is a number. */
    dayValue(key) {
        return String(this.state.draft.customers[key]);
    }

    pickDays(key, value, title) {
        if (value !== "custom") {
            this.state.draft.customers[key] = Number(value);
            return;
        }
        this.dialog.add(DaysDialog, {
            title,
            value: this.state.draft.customers[key],
            onSave: (days) => {
                this.state.draft.customers[key] = days;
            },
        });
    }

    setCod(value) {
        this.state.draft.pay.codLimit = Number(String(value).replace(/[^\d.]/g, "")) || 0;
    }

    toggleProvider(provider, on) {
        provider.state = on ? "enabled" : "disabled";
    }

    reset() {
        this.state.draft[this.group] = copy(this.state.saved[this.group]);
        this.state.error = "";
    }

    // --------------------------------------------------------------- saving

    async save() {
        if (this.state.busy) {
            return;
        }
        const group = this.group;
        let values = this.state.draft[group];
        if (group === "pay") {
            // Only what this screen can change: the switches and the limit.
            values = {
                providers: Object.fromEntries(
                    values.providers.map((p) => [p.id, p.state !== "disabled"])
                ),
                codLimit: values.codLimit,
            };
        }
        this.state.busy = true;
        this.state.error = "";
        try {
            const settings = await this.orm.call(MODEL, "mart369_admin_save", [group, values]);
            this.take(settings);
            this.notification.add(_t("Settings saved"), { type: "success" });
        } catch (err) {
            this.state.error = message(err);
        } finally {
            this.state.busy = false;
        }
    }

    // --------------------------------------------------------------- moving

    /** Odoo's own providers list, where a gateway's keys are entered. */
    openProviders() {
        this.action.doAction("payment.action_payment_provider");
    }

    // --------------------------------------------------------------- drawing

    payState(p) {
        return PAY_STATE[p.state] || PAY_STATE.disabled;
    }

    payHelp(p) {
        const pay = this.state.draft.pay;
        if (p.kind === "cod") {
            return _t("Allowed up to %s", money(pay.codLimit, pay.currency));
        }
        if (p.state === "disabled" && !p.canEnable) {
            return _t("Set up its keys in Odoo to switch it on");
        }
        if (p.kind === "wallet") {
            return _t("Balance, refunds and rewards");
        }
        return _t("Card and UPI payments through this gateway");
    }
}

registry.category("actions").add("mart369_payment.settings", SettingsDesk);
