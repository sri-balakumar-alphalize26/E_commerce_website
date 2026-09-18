import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * The numbers strip above 369 Mart -> Orders (board and list).
 *
 * Same contract as mart369_auth's customer dashboard and mart369_payment's
 * payments one: one ORM call, tiles that switch the view's own filters on by
 * name. Kept deliberately identical so the three strips stay interchangeable.
 */
export class Mart369OrderBoard extends Component {
    static template = "mart369_order.OrderBoard";
    static props = { list: { type: Object, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ data: null });
        onWillStart(() => this.load());
        onWillUpdateProps(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("sale.order", "mart369_order_dashboard", []);
    }

    get bars() {
        const rows = this.state.data?.placed || [];
        const max = Math.max(1, ...rows.map((r) => r.count));
        return rows.map((r, i) => ({
            ...r,
            h: Math.max(6, Math.round((r.count / max) * 100)),
            last: i === rows.length - 1,
        }));
    }

    /** Clear the search and apply the filters named on the tile. */
    applyFilter(names) {
        const wanted = names.split(",");
        const searchModel = this.env.searchModel;
        if (!searchModel) {
            return;
        }
        const items = searchModel.getSearchItems((item) => wanted.includes(item.name));
        // clearQuery(), not `query = []`: the setter alone skips _notify(), so a
        // tile whose filters are missing would leave the view showing the old facets.
        searchModel.clearQuery();
        for (const item of items) {
            searchModel.toggleSearchItem(item.id);
        }
    }
}
