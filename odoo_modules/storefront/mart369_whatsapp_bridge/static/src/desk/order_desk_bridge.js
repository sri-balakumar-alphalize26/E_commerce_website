/** The desk learns which door an order came in through.
 *
 * A Channel filter next to the others, a chip on the row, and the delivery
 * job's facts in the dialog. The list call itself is the same one - only the
 * `channel` keyword is added, and only when a channel is picked, so the
 * server method's behaviour is unchanged for everybody else.
 */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { OrderDesk } from "@mart369_order/desk/order_desk";

patch(OrderDesk.prototype, {
    setup() {
        super.setup();
        this.state.channel = "";
        // The list call builds its keywords inline; rather than carrying a
        // copy of load(), the one call that matters is dressed on its way
        // out. `Object.create` keeps the real service and its `this`.
        const orm = this.orm;
        const origCall = orm.call;
        this.orm = Object.assign(Object.create(orm), {
            call: (model, method, args = [], kwargs = {}) => {
                if (model === "sale.order" && method === "mart369_admin_list") {
                    kwargs = { ...kwargs, channel: this.state.channel || null };
                }
                return origCall.call(orm, model, method, args, kwargs);
            },
        });
    },

    get channelOptions() {
        return [
            ["", _t("Both channels")],
            ["website", _t("Website")],
            ["whatsapp", _t("WhatsApp")],
        ];
    },
});
