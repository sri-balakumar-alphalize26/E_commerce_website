import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";

import { Mart369PaymentDashboard } from "./payment_dashboard";

export class Mart369PaymentListRenderer extends ListRenderer {
    static template = "mart369_payment.PaymentListRenderer";
    static components = { ...ListRenderer.components, Mart369PaymentDashboard };
}

export class Mart369PaymentKanbanRenderer extends KanbanRenderer {
    static template = "mart369_payment.PaymentKanbanRenderer";
    static components = { ...KanbanRenderer.components, Mart369PaymentDashboard };
}

registry.category("views").add("mart369_payments_list", {
    ...listView,
    Renderer: Mart369PaymentListRenderer,
});

registry.category("views").add("mart369_payments_kanban", {
    ...kanbanView,
    Renderer: Mart369PaymentKanbanRenderer,
});
