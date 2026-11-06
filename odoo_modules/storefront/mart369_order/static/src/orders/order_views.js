import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { Mart369OrderBoard } from "./order_board";

export class Mart369OrderListRenderer extends ListRenderer {
    static template = "mart369_order.OrderListRenderer";
    static components = { ...ListRenderer.components, Mart369OrderBoard };
}

export class Mart369OrderKanbanRenderer extends KanbanRenderer {
    static template = "mart369_order.OrderKanbanRenderer";
    static components = { ...KanbanRenderer.components, Mart369OrderBoard };
}

registry.category("views").add("mart369_orders_list", {
    ...listView,
    Renderer: Mart369OrderListRenderer,
});

registry.category("views").add("mart369_orders_kanban", {
    ...kanbanView,
    Renderer: Mart369OrderKanbanRenderer,
});
