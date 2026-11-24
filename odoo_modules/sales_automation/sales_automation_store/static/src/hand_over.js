/** @odoo-module **/

// Hand over without a rider: store pickup (the code) or home delivery (a link
// to one person). 24 Nov 2026.
import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { SaSelect } from "./fields";

export class HandOverDialog extends Component {
    static template = "sales_automation_store.HandOverDialog";
    static components = { Dialog, SaSelect };
    static props = { row: Object, act: Function, onCode: Function, change: { type: Boolean, optional: true }, close: Function };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            step: this.props.change ? "link" : "", how: "list", word: "", carrier: "", country: "", number: "", name: "", told: "", busy: false,
            carriers: [], countries: [],
        });
        onWillStart(async () => {
            const [carriers, phones] = await Promise.all([
                this.orm.call("stock.picking", "sa_store_carriers", []),
                this.orm.call("whatsapp.connect", "phone_countries", []),
            ]);
            this.state.carriers = carriers;
            this.state.countries = phones.countries.map((c) => ({ value: `${c.id}`, label: `${c.name} +${c.dial}` }));
            this.state.country = phones.country ? `${phones.country}` : "";
            if (!carriers.length) {
                this.state.how = "number";
            }
        });
    }

    get title() {
        const ref = this.props.row.ref;
        if (this.props.change) {
            return `Another person - #${ref}`;
        }
        return { "": `Hand over #${ref}`, collect: `Store pickup - #${ref}`, link: `Home delivery - #${ref}` }[this.state.step];
    }

    get unpaid() {
        return this.props.row.self_due > 0.005;
    }

    get shown() {
        const w = this.state.word.trim().toLowerCase().replace(/^\+/, "");
        const list = w ? this.state.carriers.filter((c) => c.name.toLowerCase().includes(w) || c.phone.includes(w.replace(/\D/g, "") || "x")) : this.state.carriers;
        return list.slice(0, 50);
    }

    get ready() {
        if (this.state.busy) {
            return false;
        }
        return this.state.how === "list" ? !!this.state.carrier : !!this.state.country && this.state.number.replace(/\D/g, "").length >= 5;
    }

    go(step) {
        this.state.step = step;
        this.state.told = "";
    }

    async run(action, extra) {
        this.state.busy = true;
        this.state.told = "";
        try {
            return await this.props.act(action, extra);
        } catch (err) {
            this.state.told = (err && err.data && err.data.message) || (err && err.message) || "It did not work. Try again.";
            return null;
        } finally {
            this.state.busy = false;
        }
    }

    async collect() {
        if (await this.run("self_collect")) {
            this.props.close();
            this.props.onCode();
        }
    }

    async send() {
        const s = this.state;
        const data = await this.run("self_link", s.how === "list" ? { carrier: s.carrier }
            : { country_id: parseInt(s.country), number: s.number, name: s.name });
        if (data) {
            this.notification.add(data.self_told, { type: "success" });
            this.props.close();
        }
    }
}
