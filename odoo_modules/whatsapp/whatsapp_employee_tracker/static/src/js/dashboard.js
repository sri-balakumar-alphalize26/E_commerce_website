/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { onWillStart, useState } from "@odoo/owl";

class WaDashboardController extends KanbanController {
    static template = "whatsapp_employee_tracker.Dashboard";

    setup() {
        super.setup();
        this.waOrm = useService("orm");
        this.waAction = useService("action");
        this.wa = useState({ free: [] });
        onWillStart(async () => {
            try {
                this.wa.free = await this.waOrm.call("wa.employee.session", "numbers_without_employee", []);
            } catch {
                this.wa.free = [];
            }
        });
    }

    async giveNumber(id) {
        this.waAction.doAction(await this.waOrm.call("whatsapp.session", "action_give_number", [[id]]));
    }
}

registry.category("views").add("wa_dashboard_kanban", { ...kanbanView, Controller: WaDashboardController });
