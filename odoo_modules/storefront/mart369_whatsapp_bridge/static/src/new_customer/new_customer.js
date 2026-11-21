/** ➕ New customer - the shop's own popup, over whatever screen is open.
 *
 * The same customer the admin console's "New customer" adds (one rule,
 * wizard/new_customer.py `_mart369_create_customer`): a login on the mobile
 * number with the number trusted, so they sign in on the website with a code
 * and the WhatsApp bot already knows them.
 *
 * Like the storefront: the country code first, then a number that may only
 * be what a mobile there can be (India: ten digits starting 6, 7, 8 or 9 -
 * the rule comes from the shop, read off libphonenumber), and an Indian
 * postcode fills in the city and state.
 *
 * A function client action: nothing replaces the current screen, the popup
 * is laid over it (overlay service) and is gone again on close.
 */

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const MODEL = "mart369.new.customer";
const LABELS = ["Home", "Work", "Other"];

/* lib/phoneRule.js, the storefront's: what may stay in a mobile box. */
function cleanMobile(value, rule) {
    let v = String(value ?? "").replace(/\D/g, "");
    const len = rule?.length || 0;
    const cc = String(rule?.dial || "").replace(/\D/g, "");
    if (len && cc && v.length > len && v.startsWith(cc)) v = v.slice(cc.length);
    if (len && v.length > len && v.startsWith("0")) v = v.replace(/^0+/, "");
    const starts = rule?.starts || "";
    if (starts) while (v && !starts.includes(v[0])) v = v.slice(1);
    return len ? v.slice(0, len) : v.slice(0, 15);
}
function startsText(starts) {
    const d = String(starts || "").split("");
    return d.length <= 1 ? d.join("") : `${d.slice(0, -1).join(", ")} or ${d[d.length - 1]}`;
}
function mobileError(value, rule, required = true) {
    const v = String(value || "");
    if (!v) return required ? _t("Enter the mobile number") : "";
    const len = rule?.length || 0;
    if (rule?.starts && !rule.starts.includes(v[0])) {
        return rule.country
            ? _t("%s mobile numbers start with %s", rule.country, startsText(rule.starts))
            : _t("Mobile numbers start with %s", startsText(rule.starts));
    }
    if (len ? v.length !== len : !/^\d{6,15}$/.test(v)) {
        return len ? _t("Enter a %s-digit mobile number", len) : _t("Enter a valid mobile number");
    }
    return "";
}

/* The storefront's country picker (components/signin/CountryPicker.jsx):
   🇮🇳 from "IN", and how well a country answers what was typed. */
const flag = (code) =>
    (code || "").length === 2
        ? String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65))
        : "";
function rank(c, q) {
    const digits = q.replace(/\D/g, "");
    const dial = (c.dial || "").replace(/\D/g, "");
    const name = (c.name || "").toLowerCase();
    const code = (c.code || "").toLowerCase();
    const word = q.toLowerCase().replace(/^\+/, "").trim();
    if (digits && dial === digits) return 0;
    if (word && code === word) return 1;
    if (word && name.startsWith(word)) return 2;
    if (digits && dial.startsWith(digits)) return 3;
    if (word && name.split(/[\s(-]+/).some((w) => w.startsWith(word))) return 4;
    if (word && name.includes(word)) return 5;
    return -1;
}

export class NewCustomerPopup extends Component {
    static template = "mart369_whatsapp_bridge.NewCustomerPopup";
    static props = { close: Function };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.labels = LABELS;
        this.state = useState({
            meta: null, country: "", rule: null, loading: true, busy: false,
            name: "", mobile: "", email: "",
            // Ticked by default: staff save the address with the customer
            // (every line then required); untick to add them without one.
            withAddress: true,
            addr: { label: "Home", line: "", area: "", landmark: "", pin: "", town: "", state_id: "", alt: "" },
            pinBusy: false, place: "", areas: [], errors: {}, formError: "",
            cpOpen: false, cpQ: "", cpHi: 0, home: "",
        });
        this.flag = flag;
        this.cpBox = useRef("cpBox");
        this.cpSearch = useRef("cpSearch");
        this.loadForm(null);
        const onKey = (ev) => {
            if (ev.key !== "Escape" || this.state.busy) return;
            if (this.state.cpOpen) { this.state.cpOpen = false; return; }
            this.props.close();
        };
        const away = (ev) => {
            if (this.state.cpOpen && this.cpBox.el && !this.cpBox.el.contains(ev.target)) this.state.cpOpen = false;
        };
        onMounted(() => {
            window.addEventListener("keydown", onKey);
            document.addEventListener("pointerdown", away);
        });
        onWillUnmount(() => {
            window.removeEventListener("keydown", onKey);
            document.removeEventListener("pointerdown", away);
        });
    }

    /* ---- the country code: a chip, and a searchable list under it ---- */
    get currentCountry() {
        const list = this.state.meta?.countries || [];
        return list.find((c) => c.code === this.state.country) || { code: this.state.country, dial: this.dial, name: "" };
    }
    get shownCountries() {
        const list = this.state.meta?.countries || [];
        const term = this.state.cpQ.trim();
        if (!term) {
            const home = this.state.home;
            return [...list.filter((c) => c.code === home), ...list.filter((c) => c.code !== home)];
        }
        return list.map((c) => [rank(c, term), c]).filter(([r]) => r >= 0)
            .sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name)).map(([, c]) => c);
    }
    toggleCountries() {
        this.state.cpOpen = !this.state.cpOpen;
        this.state.cpQ = "";
        this.state.cpHi = 0;
        if (this.state.cpOpen) setTimeout(() => this.cpSearch.el?.focus(), 0);
    }
    onCpSearch(ev) { this.state.cpQ = ev.target.value; this.state.cpHi = 0; }
    onCpKeys(ev) {
        const n = this.shownCountries.length;
        if (ev.key === "ArrowDown") { ev.preventDefault(); this.state.cpHi = Math.min(this.state.cpHi + 1, n - 1); this.scrollHi(); }
        else if (ev.key === "ArrowUp") { ev.preventDefault(); this.state.cpHi = Math.max(this.state.cpHi - 1, 0); this.scrollHi(); }
        else if (ev.key === "Enter") { ev.preventDefault(); this.pickCountry(this.shownCountries[this.state.cpHi]); }
    }
    scrollHi() {
        setTimeout(() => this.cpBox.el?.querySelector(`[data-i="${this.state.cpHi}"]`)?.scrollIntoView({ block: "nearest" }), 0);
    }
    pickCountry(c) {
        if (!c) return;
        this.state.cpOpen = false;
        this.state.cpQ = "";
        if (c.code !== this.state.country) {
            this.clearError("mobile");
            this.state.place = "";
            this.loadForm(c.code);
        }
    }

    async loadForm(country) {
        this.state.loading = true;
        try {
            const meta = await this.orm.call(MODEL, "mart369_popup_form", [country || null]);
            this.state.meta = meta;
            this.state.country = meta.country?.code || "";
            if (!this.state.home) this.state.home = this.state.country;
            this.state.rule = meta.phone || null;
            this.state.mobile = cleanMobile(this.state.mobile, this.state.rule);
            this.state.addr.alt = this.state.addr.alt ? cleanMobile(this.state.addr.alt, this.state.rule) : "";
            const ids = (meta.states || []).map((s) => String(s.id));
            if (!ids.includes(String(this.state.addr.state_id))) this.state.addr.state_id = "";
        } finally {
            this.state.loading = false;
        }
    }

    get dial() {
        return this.state.rule?.dial || "";
    }
    get mobileHint() {
        const r = this.state.rule;
        if (!r?.length) return "";
        return r.starts ? _t("%s digits, starts with %s", r.length, startsText(r.starts)) : _t("%s digits", r.length);
    }
    get pinLength() {
        return this.state.meta?.pin_length || 0;
    }

    clearError(k) {
        if (this.state.errors[k]) this.state.errors = { ...this.state.errors, [k]: undefined };
        this.state.formError = "";
    }
    onCountry(ev) {
        this.clearError("mobile");
        this.state.place = "";
        this.loadForm(ev.target.value);
    }
    onName(ev) { this.state.name = ev.target.value; this.clearError("name"); }
    onEmail(ev) { this.state.email = ev.target.value; this.clearError("email"); }
    onMobile(ev) {
        const v = cleanMobile(ev.target.value, this.state.rule);
        this.state.mobile = v;
        ev.target.value = v;
        this.clearError("mobile");
    }
    onAddr(key, ev) {
        let v = ev.target.value;
        if (key === "alt") { v = cleanMobile(v, this.state.rule); ev.target.value = v; }
        if (key === "pin") {
            v = v.replace(/\D/g, "").slice(0, this.pinLength || 10);
            ev.target.value = v;
        }
        this.state.addr[key] = v;
        this.clearError(key === "state_id" ? "state" : key);
        if (key === "pin") this.lookPin(v);
    }
    setLabel(l) { this.state.addr.label = l; }
    /* Templates have no `String`: the comparison lives here. */
    isState(st) { return String(st.id) === String(this.state.addr.state_id); }
    onWithAddress(ev) {
        this.state.withAddress = ev.target.checked;
        if (!this.state.withAddress) {
            const e = { ...this.state.errors };
            for (const k of ["line", "area", "landmark", "town", "pin", "state", "alt"]) delete e[k];
            this.state.errors = e;
        }
    }

    /* India: a full postcode fills in the city and state (India Post, kept). */
    async lookPin(pin) {
        this.state.place = "";
        if (!this.state.meta?.pin_lookup || !this.pinLength || pin.length !== this.pinLength) return;
        this.state.pinBusy = true;
        try {
            const r = await this.orm.call(MODEL, "mart369_popup_pincode", [pin]);
            if (r?.ok && this.state.addr.pin === pin) {
                if (r.town) this.state.addr.town = r.town;
                if (r.state_id) this.state.addr.state_id = String(r.state_id);
                this.state.place = [r.town, r.state].filter(Boolean).join(", ");
                if (!this.state.addr.area && r.areas?.length) this.state.areas = r.areas;
                this.clearError("town");
                this.clearError("state");
            }
        } finally {
            this.state.pinBusy = false;
        }
    }
    pickArea(a) { this.state.addr.area = a; this.state.areas = []; this.clearError("area"); }

    check() {
        const e = {};
        const s = this.state;
        if (s.name.trim().length < 2) e.name = _t("Enter the customer's name");
        const m = mobileError(s.mobile, s.rule);
        if (m) e.mobile = m;
        if (s.withAddress) {
            const a = s.addr;
            if (!a.line.trim()) e.line = _t("Enter the house no., building or apartment");
            if (!a.area.trim()) e.area = _t("Enter the street or area");
            if (!a.landmark.trim()) e.landmark = _t("Enter a landmark the rider can see");
            if (!a.town.trim()) e.town = _t("Enter the city, district or town");
            if (this.pinLength ? a.pin.length !== this.pinLength : !/^\d{3,10}$/.test(a.pin)) {
                e.pin = this.pinLength ? _t("Enter a %s-digit postcode", this.pinLength) : _t("Enter a valid postcode");
            }
            if ((s.meta?.states || []).length && !a.state_id) e.state = _t("Pick a state");
            const altErr = a.alt ? mobileError(a.alt, s.rule, false) : "";
            if (altErr) e.alt = altErr;
            if (a.alt && a.alt === s.mobile) e.alt = _t("Use a different number, or leave it empty");
        }
        s.errors = e;
        return !Object.keys(e).length;
    }

    async save() {
        if (this.state.busy || !this.check()) return;
        const s = this.state;
        const body = { name: s.name.trim(), mobile: s.mobile, country: s.country, email: s.email.trim() };
        if (s.withAddress) {
            const a = s.addr;
            body.address = {
                label: a.label, name: s.name.trim(), line: a.line.trim(), area: a.area.trim(),
                landmark: a.landmark.trim(), town: a.town.trim(), pin: a.pin,
                state_id: a.state_id ? Number(a.state_id) : false, alt: a.alt, country_id: s.country,
            };
        }
        s.busy = true;
        let r;
        try {
            r = await this.orm.call(MODEL, "mart369_popup_create", [body]);
        } catch (err) {
            r = { ok: false, error: err?.data?.message || err?.message || _t("Could not add the customer. Try again.") };
        } finally {
            s.busy = false;
        }
        if (!r?.ok) {
            const field = { phone: "mobile", state_id: "state" }[r?.field] || r?.field;
            if (field && field !== "form") s.errors = { ...s.errors, [field]: r.error };
            else s.formError = r?.error || _t("Could not add the customer. Try again.");
            if (field && ["line", "area", "town", "pin", "state", "alt", "landmark"].includes(field)) s.withAddress = true;
            return;
        }
        this.notification.add(_t("%s is added. They can sign in with %s.", r.name, r.phone), { type: "success" });
        this.props.close();
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "res.users", res_id: r.id,
            views: [[r.view_id || false, "form"]], target: "current",
        });
    }
}

registry.category("actions").add("mart369_new_customer", (env) => {
    const remove = env.services.overlay.add(NewCustomerPopup, { close: () => remove() });
});
