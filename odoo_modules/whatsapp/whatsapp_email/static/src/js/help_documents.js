/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

class HelpDocumentsPage extends Component {
    static template = "whatsapp_gateway.HelpDocumentsPage";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ docs: [] });

        onWillStart(async () => {
            this.state.docs = await this.orm.call(
                "whatsapp.help.document",
                "get_help_documents",
                []
            );
        });
    }

}

registry.category("actions").add("whatsapp_gateway.help_documents", HelpDocumentsPage);
