import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { Mart369SupportBoard } from "./support_board";

class Mart369SupportKanbanRenderer extends KanbanRenderer {
    static template = "mart369_support.SupportKanbanRenderer";
    static components = { ...KanbanRenderer.components, Mart369SupportBoard };
}

registry.category("views").add("mart369_support_kanban", {
    ...kanbanView,
    Renderer: Mart369SupportKanbanRenderer,
});
