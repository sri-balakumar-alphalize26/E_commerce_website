/** @odoo-module **/
// A number for the company itself (opened from WhatsApp and Email settings):
// WA Tracker's employee choice is hidden and not required.
import { patch } from "@web/core/utils/patch";
import { ConnectNumber } from "@whatsapp_gateway/connect/connect";

patch(ConnectNumber.prototype, {
    onLoaded(data) {
        super.onLoaded(data);
        if (this.companyMode) {
            const company = (data.companies || []).find((c) => c.id === Number(this.state.company));
            // satisfies WA Tracker's "named" check; the server ignores it for a company number
            Object.assign(this.state.values, { employee_id: "new", employee_name: company ? company.name : "Company" });
        }
    },
});
