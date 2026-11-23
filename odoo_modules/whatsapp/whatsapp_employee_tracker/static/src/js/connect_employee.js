/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ConnectNumber } from "@whatsapp_gateway/connect/connect";

patch(ConnectNumber.prototype, {
    onLoaded(data) {
        super.onLoaded(data);
        Object.assign(this.state.values, { employee_id: 0, employee_name: "" });
    },
    get employeeOptions() {
        return (this.state.data.employees || []).map((e) => ({
            ...e, text: e.taken ? e.name + " - " + _t("has %s", e.taken) : e.name,
        }));
    },
    get ready1() {
        const v = this.state.values;
        const named = Number(v.employee_id) > 0 || (String(v.employee_id) === "new" && (v.employee_name || "").trim());
        return super.ready1 && !!named;
    },
    extraValues() {
        const v = this.state.values;
        return { ...super.extraValues(), employee_id: Number(v.employee_id) || 0,
                 employee_name: String(v.employee_id) === "new" ? v.employee_name : "" };
    },
});
