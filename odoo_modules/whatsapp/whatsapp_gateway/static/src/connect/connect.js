/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { cleanPhone, findCountries } from "@whatsapp_gateway/phone/phone_data";

/** Connect a number: employee and number, scan, groups, done. */
export class ConnectNumber extends Component {
    static template = "whatsapp_gateway.ConnectNumber";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.state = useState({
            switching: false, switchCode: "", switchError: "", switchBusy: false,
            scanned: false, scannedSince: 0, showQrAgain: false,
            ready: false, step: "number", busy: false, error: "", data: {},
            countrySearch: "", countryOpen: false, country: null, number: "", check: "", checkError: "", look: null, confirm: false, turnOn: null, showKey: false, saved: false,
            company: 0, label: "", key: "", values: {}, picked: null,
            session: null, groups: [], groupSearch: "", groupsError: "", done: [],
        });
        this.timer = null;
        this.asked = 0;
        onWillStart(() => this.load());
        onWillUnmount(() => {
            this.stopTimer();
            clearTimeout(this.lookTimer);
        });
    }

    get steps() {
        const steps = [
            { key: "number", n: 1, name: _t("Number") },
            { key: "scan", n: 2, name: _t("Scan") },
        ];
        // groups only with Sales Automation
        return this.state.data.has_groups ? [...steps, { key: "groups", n: 3, name: _t("Groups") }] : steps;
    }
    stepState(key) {
        const order = ["number", "scan", "groups", "done"];
        const here = order.indexOf(this.state.step), it = order.indexOf(key);
        return it < here ? "past" : it === here ? "now" : "next";
    }

    message(err) {
        return (err && err.data && err.data.message) || (err && err.message) || _t("Something went wrong. Please try again.");
    }
    async call(method, args) {
        return this.orm.silent.call("whatsapp.connect", method, args || []);
    }

    async load() {
        const params = (this.props.action && this.props.action.params) || {};
        const context = (this.props.action && this.props.action.context) || {};
        try {
            const data = await this.call("start", [params.session_id || context.session_id || false]);
            this.state.data = data;
            this.state.country = data.countries.find((c) => c.id === data.country) || null;
            this.state.company = data.company;
            // opened from a company's WhatsApp and Email settings: that company,
            // and the number is the company's own (no employee asked for)
            this.companyMode = !!(params.company_mode || context.company_mode);
            const wanted = Number(params.company_id || context.company_id || 0);
            if (wanted && (data.companies || []).some((c) => c.id === wanted)) {
                this.state.company = wanted;
            }
            const given = params.give_session_id || context.give_session_id;
            this.state.picked = (data.scanned || []).find((r) => given && r.session_id === given) || null;
            if (data.off) {
                this.state.picked = data.off;
                this.state.turnOn = data.off.ask_on;
            }
            this.onLoaded(data);
            // Switch back (27 Nov 2026): the number is typed, the red line offers Switch
            const back = String(params.switch_number || "");
            if (back) {
                const whole = this.countryOfWhole("+" + back);
                if (whole) {
                    this.state.country = whole.country;
                    this.state.number = whole.number;
                    this.checkNumber();
                }
            }
            if (data.session) {
                this.useSession(data.session);
            }
        } catch (err) {
            this.state.error = this.message(err);
        }
        this.state.ready = true;
    }
    onLoaded() {}

    // ------------------------------------------------------------ 1. number
    get countries() {
        return findCountries(this.state.data.countries || [], this.state.countrySearch);
    }
    // ---- the country, typed: "india", "91", "+91" (27 Nov 2026)
    get countryText() {
        const c = this.state.country;
        return this.state.countryOpen ? this.state.countrySearch : (c ? `${c.name}  +${c.dial}` : "");
    }
    /** The one country the text can only mean, or null. */
    exactCountry(typed) {
        const all = this.state.data.countries || [];
        const word = (typed || "").trim().toLowerCase().replace(/^\+/, "");
        if (!word) {
            return null;
        }
        if (/^[0-9]+$/.test(word)) {
            const same = all.filter((c) => c.dial === word);
            const longer = all.some((c) => c.dial !== word && c.dial.startsWith(word));
            return same.length === 1 && !longer ? same[0] : null;
        }
        const named = all.find((c) => c.name.toLowerCase() === word);
        if (named) {
            return named;
        }
        const found = findCountries(all, word);
        return found.length === 1 ? found[0] : null;
    }
    onCountryFocus(ev) {
        this.state.countrySearch = "";
        this.state.countryOpen = true;
        ev.target.value = "";               // typing starts fresh, never after "Oman +968"
    }
    onCountryInput(ev) {
        this.state.countrySearch = ev.target.value;
        this.state.countryOpen = true;
        const exact = this.exactCountry(ev.target.value);
        if (exact) {
            this.pickCountry(exact);
            ev.target.blur();
        }
    }
    onCountryKey(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            const first = this.countries[0];
            if (first) {
                this.pickCountry(first);
                ev.target.blur();
            }
        } else if (ev.key === "Escape") {
            this.state.countryOpen = false;
            ev.target.blur();
        }
    }
    onCountryBlur() {
        // a click on the list is a mousedown first: it is picked before this
        setTimeout(() => (this.state.countryOpen = false), 150);
    }
    /** "+91 70106 16092" pasted in the number box: India, then the digits. */
    countryOfWhole(raw) {
        const all = this.state.data.countries || [];
        const digits = (raw || "").replace(/[^0-9]/g, "");
        const plus = (raw || "").trim().startsWith("+") || (raw || "").trim().startsWith("00");
        const whole = (raw || "").trim().startsWith("00") ? digits.slice(2) : digits;
        const c = this.state.country;
        if (!plus && (!c || whole.length <= c.max)) {
            return null;
        }
        const fits = all.filter((x) => whole.startsWith(x.dial)
            && whole.length - x.dial.length >= x.min && whole.length - x.dial.length <= x.max);
        fits.sort((a, b) => b.dial.length - a.dial.length);
        return fits[0] ? { country: fits[0], number: whole.slice(fits[0].dial.length) } : null;
    }
    openCountries() {
        this.state.countryOpen = !this.state.countryOpen;
        this.state.countrySearch = "";
    }
    pickCountry(country) {
        this.state.country = country;
        this.state.countryOpen = false;
        this.state.number = this.clean(this.state.number);
        this.checkNumber();
    }
    get wanted() {
        const c = this.state.country;
        if (!c) {
            return "";
        }
        return c.min === c.max ? _t("%s digits", c.max) : _t("%(a)s to %(b)s digits", { a: c.min, b: c.max });
    }
    clean(text) {
        return cleanPhone(text, this.state.country);
    }
    onNumber(ev) {
        const whole = this.countryOfWhole(ev.target.value);
        if (whole) {
            this.state.country = whole.country;
            this.state.number = whole.number;
            ev.target.value = whole.number;
            this.checkNumber();
            return;
        }
        const digits = this.clean(ev.target.value);
        this.state.number = digits;
        ev.target.value = digits;           // nothing else stays in the box
        this.checkNumber();
    }
    onNumberKey(ev) {
        if (ev.key.length === 1 && !/[0-9+]/.test(ev.key) && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
            ev.preventDefault();
        }
    }
    get complete() {
        const c = this.state.country;
        return !!c && this.state.number.length >= c.min && this.state.number.length <= c.max;
    }
    async checkNumber() {
        this.state.switching = false;
        this.state.switchCode = "";
        this.state.switchError = "";
        this.state.check = "";
        this.state.checkError = "";
        this.state.look = null;
        this.state.confirm = false;
        this.state.turnOn = null;
        clearTimeout(this.lookTimer);
        const asked = ++this.asked;
        if (!this.complete) {
            return;
        }
        try {
            const answer = await this.call("check_number", [this.state.country.id, this.state.number]);
            if (asked === this.asked) {
                this.state.check = answer.ok ? answer.pretty : "";
                this.state.checkError = answer.ok ? "" : answer.error;
                if (answer.ok) {
                    this.lookTimer = setTimeout(() => this.lookNow(), 400);
                }
            }
        } catch (err) {
            this.state.checkError = this.message(err);
        }
    }
    /** Is the number here, or in the panel, already? An older answer is dropped. */
    async lookNow() {
        clearTimeout(this.lookTimer);
        const asked = this.asked;
        let look;
        try {
            look = await this.call("look", [this.state.country.id, this.state.number]);
        } catch (err) {
            look = { where: "", ok: true, text: _t("Could not check in the panel now; checked again on Next") };
        }
        if (asked === this.asked) {
            this.state.look = look;
        }
        return asked === this.asked;
    }
    // ------------------------------------------------------------ switch here (27 Nov 2026)
    /** From another database of the same vendor: a pop-up, then a code the number sends to itself. */
    switchHere() {
        const look = this.state.look;
        const from = (look.used_in || []).join(", ");
        const here = this.state.data.db || _t("this database");
        const body = from
            ? _t("Switch %(number)s from %(from)s to %(here)s? In %(from)s this number stops at once: its WhatsApp groups, Sales Automation and WA Tracker get no more messages from it. Old messages and orders stay there. A code will be sent to the \"Message yourself\" chat on that phone. No QR scan.",
                  { number: look.pretty, from, here })
            : _t("Use %(number)s in %(here)s? A code will be sent to the \"Message yourself\" chat on that phone. No QR scan.",
                  { number: look.pretty, here });
        this.dialog.add(ConfirmationDialog, {
            title: _t("Switch WhatsApp number"),
            body,
            confirmLabel: _t("Switch"),
            cancelLabel: _t("Cancel"),
            confirm: () => this.sendSwitchCode(),
            cancel: () => {},
        });
    }
    async sendSwitchCode() {
        this.state.switchBusy = true;
        this.state.switchError = "";
        try {
            await this.call("switch_code", [this.state.country.id, this.state.number]);
            this.state.switching = true;
            this.state.switchCode = "";
        } catch (err) {
            this.state.switchError = this.message(err);
        }
        this.state.switchBusy = false;
    }
    onSwitchCode(ev) {
        this.state.switchCode = ev.target.value.replace(/\D/g, "").slice(0, 6);
        ev.target.value = this.state.switchCode;
        if (this.state.switchCode.length === 6) {
            this.confirmSwitch();
        }
    }
    async confirmSwitch() {
        if (this.state.switchBusy || this.state.switchCode.length !== 6) {
            return;
        }
        this.state.switchBusy = true;
        this.state.switchError = "";
        try {
            const look = await this.call("switch", [this.state.country.id, this.state.number, this.state.switchCode]);
            this.state.look = look;
            if (look.ok) {
                this.state.switching = false;
                this.state.switchBusy = false;
                // straight on: the phone is linked already, so no QR is needed
                return this.next1();
            }
            this.state.switchError = look.text || _t("The number could not be switched.");
        } catch (err) {
            this.state.switchError = this.message(err);
        }
        this.state.switchBusy = false;
    }

    /** Whom it is for, in the question. */
    get forWhom() {
        return (this.state.label || "").trim();
    }
    changeNumber() {
        this.state.confirm = false;
        this.state.turnOn = null;
        this.state.picked = null;
    }
    get scanned() {
        return this.state.picked ? [] : this.state.data.scanned || [];
    }
    pick(row) {
        this.state.picked = row;
        this.state.turnOn = null;
        this.state.error = "";
    }
    get needsKey() {
        const look = this.state.look;
        // refused already: no key would help
        if (this.state.picked || (look && (!look.ok || look.where === "off" || (look.where === "here" && !look.key)))) {
            return false;
        }
        return !this.state.data.can_add || !!(look && look.key);
    }
    get ready1() {
        if (this.state.picked) {
            return !this.state.busy;
        }
        return this.complete && !!this.state.check && !(this.state.look && !this.state.look.ok)
            && (!this.needsKey || !!this.state.key.trim()) && !this.state.busy;
    }
    async openLink() {
        // the link form; back here it reads again, now with the link
        // Settings > WhatsApp: the panel address and the link token
        await this.action.doAction({
            type: "ir.actions.act_window", res_model: "res.config.settings", name: _t("Settings"),
            views: [[false, "form"]], target: "inline", context: { module: "whatsapp_gateway" },
        });
    }
    extraValues() {
        return this.companyMode ? { ...this.state.values, for_company: true } : this.state.values;
    }
    async next1() {
        if (!this.ready1) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        if (!this.state.picked && !this.state.look && !(await this.lookNow())) {
            this.state.busy = false;
            return;
        }
        if (!this.state.picked && (!this.state.look.ok || (this.needsKey && !this.state.key.trim()))) {
            this.state.busy = false;
            return;
        }
        // a new number is asked about first
        if (!this.state.picked && this.state.look.where === "new" && !this.state.confirm) {
            this.state.confirm = true;
            this.state.busy = false;
            return;
        }
        try {
            const p = this.state.picked;
            const which = p ? (p.off_session_id ? { off_session_id: p.off_session_id }
                : p.session_id ? { session_id: p.session_id } : { free_number: p.number })
                            : { country_id: this.state.country.id, number: this.state.number };
            const session = await this.call("add", [{
                ...which, company_id: Number(this.state.company), turn_on: !!this.state.turnOn, quick: true,
                label: this.state.label, key: this.needsKey ? this.state.key.trim() : "", ...this.extraValues(),
            }]);
            if (session.ask_on) {
                this.state.turnOn = session.ask_on;     // it is off: one question
                this.state.busy = false;
                return;
            }
            this.state.saved = !this.state.picked && !this.needsKey && !this.state.turnOn;
            this.useSession(session);
        } catch (err) {
            this.state.error = this.message(err);
        }
        this.state.busy = false;
    }

    // ------------------------------------------------------------ 2. scan
    useSession(session) {
        this.state.session = session;
        if (session.connected) {
            this.state.scanned = false;
            this.stopTimer();
            this.toGroups();
            return;
        }
        if (session.scanned && !this.state.scanned) {
            // the phone has scanned: the QR goes, a spinner until Odoo has it
            this.state.scanned = true;
            this.state.scannedSince = Date.now();
            this.state.showQrAgain = false;
        }
        if (this.state.scanned && Date.now() - this.state.scannedSince > 90000) {
            this.state.showQrAgain = true;
        }
        this.state.step = "scan";
        this.stopTimer();
        this.timer = setTimeout(() => this.poll(), this.state.scanned ? 1000
            : session.qr ? 2500 : session.first ? 50 : session.error ? 3000 : 1000);
    }
    qrAgain() {
        this.state.scanned = false;
        this.state.showQrAgain = false;
        this.poll();
    }
    async poll() {
        if (this.state.step !== "scan" || !this.state.session) {
            return;
        }
        if (document.hidden) {
            this.timer = setTimeout(() => this.poll(), 3000);
            return;
        }
        try {
            const before = this.state.session.qr;
            const session = await this.call("state", [this.state.session.id]);
            if (!session.connected && !session.qr && !session.wrong && !session.error) {
                session.qr = before;         // the panel renews it in a moment
            }
            this.useSession(session);
        } catch (err) {
            this.state.session.error = this.message(err);
            this.timer = setTimeout(() => this.poll(), 6000);
        }
    }
    stopTimer() {
        if (this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
    }

    // ------------------------------------------------------------ 3. groups
    async toGroups() {
        this.state.step = "groups";
        this.state.busy = true;
        this.state.groupsError = "";
        try {
            const answer = await this.call("groups", [this.state.session.id]);
            if (!answer.available) {
                this.state.busy = false;
                return this.finish();
            }
            this.state.groups = answer.groups.map((g) => ({ ...g, chosen: g.enabled }));
            this.state.groupsError = answer.error || "";
        } catch (err) {
            this.state.groupsError = this.message(err);
        }
        this.state.busy = false;
    }
    get shownGroups() {
        const word = this.state.groupSearch.trim().toLowerCase();
        return this.state.groups.filter((g) => !word || g.name.toLowerCase().includes(word));
    }
    get chosenCount() {
        return this.state.groups.filter((g) => g.chosen && !g.taken).length;
    }
    toggleGroup(group) {
        if (!group.taken && !group.enabled) {
            group.chosen = !group.chosen;
        }
    }
    async finish() {
        this.state.busy = true;
        this.state.error = "";
        try {
            const ids = this.state.groups.filter((g) => g.chosen && !g.taken).map((g) => g.id);
            const answer = await this.call("finish", [this.state.session.id, ids]);
            this.state.done = answer.lines;
            this.state.step = "done";
        } catch (err) {
            this.state.error = this.message(err);
        }
        this.state.busy = false;
    }

    // ------------------------------------------------------------ away
    another() {
        this.action.doAction("whatsapp_gateway.action_whatsapp_connect", { clearBreadcrumbs: true });
    }
    close() {
        this.stopTimer();
        this.action.doAction("whatsapp_gateway.action_whatsapp_session", { clearBreadcrumbs: true });
    }
}

registry.category("actions").add("whatsapp_gateway.connect", ConnectNumber);
