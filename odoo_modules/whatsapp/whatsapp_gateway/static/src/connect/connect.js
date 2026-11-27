/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { cleanPhone, findCountries } from "@whatsapp_gateway/phone/phone_data";

/** Connect a number: employee and number, scan, groups, done. */
export class ConnectNumber extends Component {
    static template = "whatsapp_gateway.ConnectNumber";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
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
        const digits = this.clean(ev.target.value);
        this.state.number = digits;
        ev.target.value = digits;           // nothing else stays in the box
        this.checkNumber();
    }
    onNumberKey(ev) {
        if (ev.key.length === 1 && !/[0-9]/.test(ev.key) && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
            ev.preventDefault();
        }
    }
    get complete() {
        const c = this.state.country;
        return !!c && this.state.number.length >= c.min && this.state.number.length <= c.max;
    }
    async checkNumber() {
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
            this.stopTimer();
            this.toGroups();
            return;
        }
        this.state.step = "scan";
        this.stopTimer();
        this.timer = setTimeout(() => this.poll(), session.qr ? 5000 : session.first ? 50 : session.error ? 3000 : 1000);
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
