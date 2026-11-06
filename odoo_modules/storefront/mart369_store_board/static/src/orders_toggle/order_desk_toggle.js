/** @odoo-module **/

/**
 * All orders (mart369_order's desk) gets the same Counter | All orders toggle
 * as the Counter, and opens an order the Counter hands over (a row click
 * there). Added from here, so mart369_order knows nothing about the Counter
 * and still works without the Store installed.
 */

import { onMounted } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { OrderDesk } from "@mart369_order/desk/order_desk";

patch(OrderDesk.prototype, {
    setup() {
        super.setup(...arguments);
        const ref = this.props.action?.context?.mart369_open_ref;
        if (ref) {
            onMounted(() => this.select(ref));
        }
    },

    /** The desk reloads after every action - a cancel among them - so the
     *  app-wide alarm asks again at once rather than ringing on for an order
     *  that was just cancelled here until its next poll. */
    async load(...args) {
        const result = await super.load(...args);
        this.env.services.mart369_counter_alarm?.refresh();
        return result;
    },

    /** Back to the Counter, replacing this screen (no breadcrumb pile-up). */
    showCounter() {
        return this.action.doAction("mart369_store_board.action_mart369_orders_board", {
            clearBreadcrumbs: true,
        });
    },
});
