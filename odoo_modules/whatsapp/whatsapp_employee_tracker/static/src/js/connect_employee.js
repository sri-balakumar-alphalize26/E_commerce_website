/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ConnectNumber } from "@whatsapp_gateway/connect/connect";

patch(ConnectNumber.prototype, {
    onLoaded(data) {
        super.onLoaded(data);
        Object.assign(this.state.values, { employee_id: 0, employee_name: "" });
        Object.assign(this.state, { empSearch: "", empOpen: false, empActive: 0 });
    },
    // ---- the employee, searched (27 Nov 2026)
    get shownEmployees() {
        const word = (this.state.empSearch || "").trim().toLowerCase();
        return (this.state.data.employees || []).filter((e) => !word || (e.name || "").toLowerCase().includes(word)).slice(0, 50);
    },
    get employeeText() {
        if (this.state.empOpen) {
            return this.state.empSearch;
        }
        const v = this.state.values;
        if (String(v.employee_id) === "new") {
            return _t("+ New employee");
        }
        const one = (this.state.data.employees || []).find((e) => e.id === Number(v.employee_id));
        return one ? one.name : "";
    },
    onEmployeeFocus(ev) {
        this.state.empSearch = "";
        this.state.empActive = 0;
        this.state.empOpen = true;
        ev.target.value = "";               // a new search, never after the chosen name
    },
    onEmployeeInput(ev) {
        this.state.empSearch = ev.target.value;
        this.state.empActive = 0;
        this.state.empOpen = true;
    },
    onEmployeeKey(ev) {
        const list = this.shownEmployees;
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this.state.empActive = Math.min(this.state.empActive + 1, list.length);
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            this.state.empActive = Math.max(this.state.empActive - 1, 0);
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            const e = list[this.state.empActive];
            if (e && !e.taken) {
                this.pickEmployee(e);
            } else if (this.state.empActive === list.length) {
                this.newEmployee();
            }
            ev.target.blur();
        } else if (ev.key === "Escape") {
            this.state.empOpen = false;
            ev.target.blur();
        }
    },
    onEmployeeBlur() {
        setTimeout(() => (this.state.empOpen = false), 150);
    },
    pickEmployee(e) {
        if (e.taken) {
            return;
        }
        this.state.values.employee_id = e.id;
        this.state.values.employee_name = "";
        this.state.empOpen = false;
    },
    newEmployee() {
        this.state.values.employee_id = "new";
        this.state.values.employee_name = (this.state.empSearch || "").trim();
        this.state.empOpen = false;
    },
    get employeeOptions() {
        return (this.state.data.employees || []).map((e) => ({
            ...e, text: e.taken ? e.name + " - " + _t("has %s", e.taken) : e.name,
        }));
    },
    get ready1() {
        const v = this.state.values;
        const named = Number(v.employee_id) > 0 || (String(v.employee_id) === "new" && (v.employee_name || "").trim());
        const look = this.state.look;
        const picked = this.state.picked;
        return super.ready1 && (!!named || !!(picked && picked.off_session_id && picked.owner)
            || !!(!picked && look && look.where === "off" && look.owner));
    },
    get forWhom() {
        const v = this.state.values;
        if (String(v.employee_id) === "new") {
            return (v.employee_name || "").trim();
        }
        const one = (this.state.data.employees || []).find((e) => e.id === Number(v.employee_id));
        return one ? one.name : super.forWhom;
    },
    extraValues() {
        const v = this.state.values;
        return { ...super.extraValues(), employee_id: Number(v.employee_id) || 0,
                 employee_name: String(v.employee_id) === "new" ? v.employee_name : "" };
    },
});
