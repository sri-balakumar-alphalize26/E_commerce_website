/**
 * The order desk, driven the way an operator drives it.
 *
 * Three things are worth a tour here, and they are the three that a unit test
 * on the model cannot see.
 *
 *  - The queue drew something. The desk reads `mart369_admin_list` over
 *    `orm.call`; a rename on either side leaves a screen that loads, shows
 *    "Nothing waiting" and is wrong.
 *  - The button says what the server told it to. The whole point of shipping
 *    `row.next.label` is that the browser never works out whether packed or
 *    shipped comes next, so the label is asserted, not just the click.
 *  - The write went through and the screen caught up. Nothing here is
 *    optimistic, so a state that changes on screen means the reload really
 *    happened.
 *
 * Selectors are the desk's own `.od-*` classes, which makes this a contract on
 * order_desk.scss too - the same bargain the product tours strike with the
 * shared stylesheet.
 */
import { registry } from "@web/core/registry";

const ROW = ".od-row";
const NEXT = `${ROW} .od-next`;

registry.category("web_tour.tours").add("mart369_order_desk", {
    url: "/odoo/mart-orders",
    steps: () => [
        {
            content: "the queue drew the order that is waiting",
            trigger: `${ROW} .od-ref:contains(369M-TOUR)`,
        },
        {
            /* That the tile counted *something*, not that it counted one. An
               absolute number here only passes on an empty database, which is
               not what a shop that has been running looks like. */
            content: "the tiles counted it",
            trigger: ".od-tile:contains(To pack) b",
            run: () => {
                const n = document.querySelector(".od-tile b").textContent.trim();
                if (!Number(n)) {
                    throw new Error(`To pack counted ${n} with an order waiting`);
                }
            },
        },
        {
            content: "a quick order is packed next, and the server said so",
            trigger: `${NEXT}:contains(Start packing)`,
        },
        {
            content: "open it",
            trigger: `${ROW} .od-ref:contains(369M-TOUR)`,
            run: "click",
        },
        {
            content: "the panel drew this order's own ladder",
            trigger: ".od-panel .od-steps li:contains(Packed)",
        },
        {
            content: "and the delivery code it has, never the code itself",
            trigger: ".od-panel .mart-hint:contains(not used yet)",
        },
        {
            content: "move it on from the row",
            trigger: `${NEXT}:contains(Start packing)`,
            run: "click",
        },
        {
            content: "it really moved - the state is the server's answer",
            trigger: `${ROW} .mart-pill:contains(Packed)`,
        },
        {
            content: "and the button relabelled itself for the next step",
            trigger: `${NEXT}:contains(Send out)`,
        },
        {
            content: "once it is packed, cancelling is no longer offered",
            trigger: ".od-panel .od-foot",
            run: () => {
                if (document.querySelector(".od-panel .mart-btn-danger")) {
                    throw new Error("Cancel is offered on an order the model would refuse");
                }
            },
        },
        {
            content: "the tiles are the filter",
            trigger: ".od-tile:contains(Packed & shipped)",
            run: "click",
        },
        {
            content: "and it filtered",
            trigger: `.od-tile-on:contains(Packed & shipped)`,
        },
    ],
});
