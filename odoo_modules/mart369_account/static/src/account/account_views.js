import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import {
    Mart369ReviewBoard,
    Mart369ReferralBoard,
    Mart369RewardBoard,
} from "./account_board";

class Mart369ReviewListRenderer extends ListRenderer {
    static template = "mart369_account.ReviewListRenderer";
    static components = { ...ListRenderer.components, Mart369ReviewBoard };
}

class Mart369ReferralKanbanRenderer extends KanbanRenderer {
    static template = "mart369_account.ReferralKanbanRenderer";
    static components = { ...KanbanRenderer.components, Mart369ReferralBoard };
}

class Mart369RewardListRenderer extends ListRenderer {
    static template = "mart369_account.RewardListRenderer";
    static components = { ...ListRenderer.components, Mart369RewardBoard };
}

registry.category("views").add("mart369_reviews_list", {
    ...listView,
    Renderer: Mart369ReviewListRenderer,
});

registry.category("views").add("mart369_referrals_kanban", {
    ...kanbanView,
    Renderer: Mart369ReferralKanbanRenderer,
});

registry.category("views").add("mart369_rewards_list", {
    ...listView,
    Renderer: Mart369RewardListRenderer,
});
