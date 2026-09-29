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

    /** Back to the Counter, replacing this screen (no breadcrumb pile-up). */
    showCounter() {
        return this.action.doAction("mart369_store_board.action_mart369_orders_board", {
            clearBreadcrumbs: true,
        });
    },
});
