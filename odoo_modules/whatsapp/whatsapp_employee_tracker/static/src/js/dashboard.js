/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";

class WaDashboardController extends KanbanController {
    static template = "whatsapp_employee_tracker.Dashboard";

    setup() {
        super.setup();
        this.waOrm = useService("orm");
        this.waAction = useService("action");
        this.waBus = useService("bus_service");
        this.wa = useState({ free: [] });
        this._waNew = () => {
            // many messages at once: one refresh
            clearTimeout(this._waSoon);
            this._waSoon = setTimeout(() => this._waRefresh(), 2000);
        };
        this._waSeen = () => this._waRefresh();
        onWillStart(() => this._waLoadFree());
        onMounted(() => {
            this.waBus.subscribe("wa_tracker_new", this._waNew);
            this.waBus.start();
            document.addEventListener("visibilitychange", this._waSeen);
            this._waTimer = setInterval(() => this._waRefresh(), 20000);
        });
        onWillUnmount(() => {
            this._waGone = true;
            clearInterval(this._waTimer);
            clearTimeout(this._waSoon);
            this.waBus.unsubscribe("wa_tracker_new", this._waNew);
            document.removeEventListener("visibilitychange", this._waSeen);
        });
    }

    async _waLoadFree() {
        try {
            this.wa.free = await this.waOrm.call("wa.employee.session", "numbers_without_employee", []);
        } catch {
            // what is shown stays
        }
    }

    /** The cards as they are now; filters and the place scrolled to stay. */
    async _waRefresh() {
        if (document.hidden || this._waGone || this._waBusy || this.model.root?.selection?.length) {
            return;
        }
        this._waBusy = true;
        try {
            await this.model.load();
            if (!this._waGone) {
                await this._waLoadFree();
            }
        } catch {
            // the next refresh tries again
        } finally {
            this._waBusy = false;
        }
    }

    async giveNumber(id) {
        this.waAction.doAction(await this.waOrm.call("whatsapp.session", "action_give_number", [[id]]));
    }
}

registry.category("views").add("wa_dashboard_kanban", { ...kanbanView, Controller: WaDashboardController });
