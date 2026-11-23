/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillStart, onWillUpdateProps, useExternalListener, useRef, useState } from "@odoo/owl";
import { cleanPhone, findCountries, loadCountries, splitPhone } from "@whatsapp_gateway/phone/phone_data";

/**
 * Country + number. What is saved stays as it is until somebody types: a value
 * that is not surely one whole number is an ordinary box.
 */
export class WaPhoneField extends Component {
    static template = "whatsapp_gateway.PhoneField";
    static props = {
        ...standardFieldProps,
        placeholder: { type: String, optional: true },
        plus: { type: Boolean, optional: true },
        landline: { type: Boolean, optional: true },
    };

    setup() {
        this.orm = this.env.services.orm;
        this.root = useRef("root");
        this.state = useState({ plain: false, countries: [], country: null, number: "", pretty: "", error: "",
                                open: false, search: "", style: "" });
        this.asked = 0;
        this.last = undefined;
        onWillStart(() => this.load(this.props));
        onWillUpdateProps((next) => this.load(next));
        useExternalListener(window, "click", (ev) => {
            if (this.state.open && this.root.el && !this.root.el.contains(ev.target)) {
                this.state.open = false;
            }
        });
        useExternalListener(window, "scroll", (ev) => {
            if (this.state.open && !(this.root.el && this.root.el.contains(ev.target))) {
                this.state.open = false;
            }
        }, { capture: true });
    }

    valueOf(props) {
        return props.record.data[props.name] || "";
    }
    async load(props) {
        const value = this.valueOf(props);
        const fresh = value !== this.last || props.record.id !== this.recordId;
        this.recordId = props.record.id;
        this.last = value;
        try {
            if (!props.readonly && !this.state.countries.length) {
                const data = await loadCountries(this.orm);
                this.state.countries = data.countries;
                this.home = data.countries.find((c) => c.id === data.country) || null;
                if (value) {
                    await this.split(value);
                } else {
                    this.state.country = this.state.country || this.home;
                }
                return;
            }
            if (!fresh) {
                return;
            }
            if (!value) {
                Object.assign(this.state, { plain: false, number: "", pretty: "", error: "" });
                this.state.country = this.state.country || this.home || null;
                return;
            }
            await this.split(value);
        } catch {
            this.state.plain = true;            // the box still works
        }
    }
    async split(value) {
        const parts = await splitPhone(this.orm, value);
        if (value !== this.last) {
            return;
        }
        this.state.pretty = parts.pretty || value;
        this.state.error = "";
        const country = this.state.countries.find((c) => c.id === parts.country);
        if (country && cleanPhone(parts.national, country, this.props.landline) === parts.national) {
            Object.assign(this.state, { plain: false, country, number: parts.national });
        } else {
            this.state.plain = true;
        }
    }

    // ------------------------------------------------------------ the box
    get min() {
        const c = this.state.country;
        return c ? (this.props.landline ? c.amin || c.min : c.min) : 0;
    }
    get max() {
        const c = this.state.country;
        return c ? (this.props.landline ? c.amax || c.max : c.max) : 15;
    }
    get wanted() {
        return this.min === this.max ? _t("%s digits", this.max) : _t("%(a)s to %(b)s digits", { a: this.min, b: this.max });
    }
    get shownCountries() {
        return findCountries(this.state.countries, this.state.search);
    }
    get href() {
        return "tel:" + this.valueOf(this.props).replace(/\s+/g, "");
    }
    openCountries(ev) {
        const box = ev.currentTarget.getBoundingClientRect();
        const below = window.innerHeight - box.bottom > 320 || box.top < 320;
        const left = Math.max(8, Math.min(box.left, window.innerWidth - 308));
        this.state.style = `left:${left}px;` + (below ? `top:${box.bottom + 4}px` : `bottom:${window.innerHeight - box.top + 4}px`);
        this.state.search = "";
        this.state.open = !this.state.open;
    }
    onMenuKey(ev) {
        if (ev.key === "Escape") {
            ev.stopPropagation();
            this.state.open = false;
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            ev.stopPropagation();
            if (this.shownCountries.length) {
                this.pickCountry(this.shownCountries[0]);
            }
        }
    }
    async pickCountry(country) {
        this.state.country = country;
        this.state.open = false;
        this.state.number = cleanPhone(this.state.number, country, this.props.landline);
        if (this.state.number) {
            await this.save();
        }
    }
    onKey(ev) {
        if (ev.key.length === 1 && !/[0-9]/.test(ev.key) && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
            ev.preventDefault();
        }
    }
    async onNumber(ev) {
        const digits = cleanPhone(ev.target.value, this.state.country, this.props.landline);
        this.state.number = digits;
        ev.target.value = digits;
        await this.save();
    }
    async save() {
        const { record, name } = this.props;
        const country = this.state.country;
        const asked = ++this.asked;
        this.state.error = "";
        if (!this.state.number) {
            this.last = "";
            this.state.pretty = "";
            record.resetFieldValidity(name);
            return record.update({ [name]: false });
        }
        if (!country || this.state.number.length < this.min) {
            this.state.error = country ? this.wanted : _t("Choose the country");
            return record.setInvalidField(name);
        }
        const value = (this.props.plus ? "+" : "") + country.dial + this.state.number;
        this.last = value;
        this.state.pretty = "+" + country.dial + " " + this.state.number;
        record.resetFieldValidity(name);
        await record.update({ [name]: value });
        let answer = { ok: true };
        try {
            answer = await this.orm.silent.call("whatsapp.connect", "phone_check", [country.id, this.state.number, !!this.props.landline]);
        } catch {
            return;                              // not reached: the length was right
        }
        if (asked === this.asked) {
            if (answer.ok) {
                this.state.pretty = answer.pretty;
            } else {
                this.state.error = answer.error;
                record.setInvalidField(name);
            }
        }
    }

    // ------------------------------------------------------------ a plain value
    async onPlain(ev) {
        const value = ev.target.value.trim();
        this.last = value;
        await this.props.record.update({ [this.props.name]: value || false });
        if (value) {
            await this.split(value);
        } else {
            this.useCountry();
        }
    }
    useCountry() {
        Object.assign(this.state, { plain: false, number: "", error: "", country: this.state.country || this.home || null });
    }
}

export const waPhoneField = {
    component: WaPhoneField,
    displayName: _t("Phone with country"),
    supportedTypes: ["char"],
    extractProps: ({ placeholder, options }) => ({
        placeholder, plus: !!options.plus, landline: !!options.landline,
    }),
};

registry.category("fields").add("wa_phone", waPhoneField);
