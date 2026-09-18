import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * The numbers strip above 369 Mart -> Support.
 *
 * Same contract as the customers, payments, orders, reviews, referrals and
 * rewards strips: one ORM call, tiles that switch the view's own filters on by
 * name. Kept identical so all seven stay interchangeable.
 */
export class Mart369SupportBoard extends Component {
    static template = "mart369_support.SupportBoard";
    static props = { list: { type: Object, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ data: null });
        onWillStart(() => this.load());
        onWillUpdateProps(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("mart369.ticket", "mart369_support_dashboard", []);
    }

    get bars() {
        const rows = this.state.data?.asked || [];
        const max = Math.max(1, ...rows.map((r) => r.count));
        return rows.map((r, i) => ({
            ...r,
            h: Math.max(6, Math.round((r.count / max) * 100)),
            last: i === rows.length - 1,
        }));
    }

    applyFilter(names) {
        const wanted = names.split(",");
        const searchModel = this.env.searchModel;
        if (!searchModel) {
            return;
        }
        const items = searchModel.getSearchItems((item) => wanted.includes(item.name));
        // clearQuery(), not `query = []`: the setter alone skips _notify(), so a
        // tile whose filters are missing would leave the view showing old facets.
        searchModel.clearQuery();
        for (const item of items) {
            searchModel.toggleSearchItem(item.id);
        }
    }
}
