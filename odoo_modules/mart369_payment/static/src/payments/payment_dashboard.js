import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Icon } from "@mart369/ui/icon";

/** The numbers strip above 369 Mart -> Payments (list and board). */
export class Mart369PaymentDashboard extends Component {
    static template = "mart369_payment.PaymentDashboard";
    static components = { Icon };
    static props = { list: { type: Object, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null });
        onWillStart(() => this.load());
        onWillUpdateProps(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("payment.transaction", "mart369_payment_dashboard", []);
    }

    get bars() {
        const rows = this.state.data?.bars || [];
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

    /** The wallet tile opens the wallets rather than filtering payments. */
    openWallets() {
        this.action.doAction("mart369_payment.action_mart369_wallets");
    }
}
