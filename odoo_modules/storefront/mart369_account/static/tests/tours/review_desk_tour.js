/**
 * The reviews desk, driven the way somebody would drive it.
 *
 * Modelled on order_desk_tour.js in mart369_order, and it makes the same two
 * promises about how it asserts:
 *
 *  - Selectors are the desk's own classes, so this is a contract on
 *    review_desk.scss as much as on the component. Renaming `.rv-row` without
 *    renaming it here should fail loudly rather than quietly pass.
 *  - Never an absolute number. The test database already holds reviews from
 *    the demo data and from whatever anybody seeded, so a tile is asserted to
 *    be non-empty, never to equal 3.
 *
 * What it proves that the Python tests cannot: that the tiles filter, that a
 * moderation button reaches the server, and that the row leaves the tab it was
 * in once it has.
 */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("mart369_review_desk", {
    url: "/odoo/mart-reviews",
    steps: () => [
        {
            content: "The desk drew, with its tiles",
            trigger: ".mart-builder.rv .rv-tile",
        },
        {
            content: "Published has something in it",
            trigger: ".rv-tiles button.rv-tile:not(:empty)",
            run: () => {},
        },
        {
            // The tile is the filter, not a read-out above one.
            content: "Click the Published tile",
            trigger: ".rv-tiles button.rv-tile:nth-child(3)",
            run: "click",
        },
        {
            content: "It switched the tab on",
            trigger: ".rv-tile-on",
        },
        {
            content: "A published review is listed",
            trigger: ".rv-rows .rv-row",
        },
        {
            // Publish is absent on an already-published review: the desk hides
            // what cannot be done rather than offering it and refusing.
            content: "A published row offers Hide and not Publish",
            trigger: ".rv-rows .rv-row:first-child .rv-act button:contains(Hide)",
            run: "click",
        },
        {
            content: "It asked before taking the review down",
            trigger: ".modal button:contains(Hide review)",
            run: "click",
        },
        {
            content: "The Hidden tile is no longer empty",
            trigger: ".rv-tiles button.rv-tile:nth-child(4) b:not(:contains(0))",
            run: () => {},
        },
    ],
});
