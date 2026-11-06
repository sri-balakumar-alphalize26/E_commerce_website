import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { Mart369CustomerDashboard } from "./customer_dashboard";

export class Mart369CustomerListRenderer extends ListRenderer {
    static template = "mart369_auth.CustomerListRenderer";
    static components = { ...ListRenderer.components, Mart369CustomerDashboard };
}

export class Mart369CustomerKanbanRenderer extends KanbanRenderer {
    static template = "mart369_auth.CustomerKanbanRenderer";
    static components = { ...KanbanRenderer.components, Mart369CustomerDashboard };
}

registry.category("views").add("mart369_customers_list", {
    ...listView,
    Renderer: Mart369CustomerListRenderer,
});

registry.category("views").add("mart369_customers_kanban", {
    ...kanbanView,
    Renderer: Mart369CustomerKanbanRenderer,
});
