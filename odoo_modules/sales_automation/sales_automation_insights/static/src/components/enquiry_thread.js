/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { clock } from "./util";

/**
 * One enquiry's whole conversation, fetched on expand and never before.
 *
 * `sa_enquiry_detail` runs up to five searches per enquiry; a profile with
 * thirty enquiries must not pay that thirty times on open.
 */
export class EnquiryThread extends Component {
    static template = "sales_automation_insights.EnquiryThread";
    static props = { entityId: Number, requestId: Number };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ detail: null, error: "" });
        onWillStart(async () => {
            try {
                this.state.detail = await this.orm.call(
                    "sa.insight.entity", "sa_insights_enquiry",
                    [this.props.entityId, this.props.requestId]);
            } catch (err) {
                this.state.error = (err && err.data && err.data.message) || String(err);
            }
        });
    }

    clock(iso) {
        return clock(iso);
    }
}
