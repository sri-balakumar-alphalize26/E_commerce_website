import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Base for the three strips on this module's screens.
 *
 * Same contract as mart369_auth's customer dashboard, mart369_payment's
 * payments one and mart369_order's board: one ORM call, tiles that switch the
 * view's own filters on by name. Subclasses only choose a model, a method and
 * a template.
 */
class Mart369Strip extends Component {
    static props = { list: { type: Object, optional: true } };
    static model = null;
    static method = null;

    setup() {
        this.orm = useService("orm");
        this.state = useState({ data: null });
        onWillStart(() => this.load());
        onWillUpdateProps(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call(
            this.constructor.model, this.constructor.method, []
        );
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

export class Mart369ReviewBoard extends Mart369Strip {
    static template = "mart369_account.ReviewBoard";
    static model = "rating.rating";
    static method = "mart369_review_dashboard";

    get bars() {
        const rows = this.state.data?.written || [];
        const max = Math.max(1, ...rows.map((r) => r.count));
        return rows.map((r, i) => ({
            ...r,
            h: Math.max(6, Math.round((r.count / max) * 100)),
            last: i === rows.length - 1,
        }));
    }

    /** Five slots, filled to the rounded average. */
    get stars() {
        const filled = this.state.data?.stars || 0;
        return [1, 2, 3, 4, 5].map((n) => ({ n, on: n <= filled }));
    }
}

export class Mart369ReferralBoard extends Mart369Strip {
    static template = "mart369_account.ReferralBoard";
    static model = "mart369.referral";
    static method = "mart369_referral_dashboard";
}

export class Mart369RewardBoard extends Mart369Strip {
    static template = "mart369_account.RewardBoard";
    static model = "mart369.scratch";
    static method = "mart369_scratch_dashboard";
}
