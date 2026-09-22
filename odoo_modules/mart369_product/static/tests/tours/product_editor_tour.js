/** Browser tour: the product page editor does what an employee expects.
 *
 *  This is the front door of 369 Mart > Product Page, so the tour walks the
 *  path a person actually takes: open the page, click the part of it they
 *  want to change, drill into one field, switch it off for the whole shop and
 *  watch it leave the page - then find it again behind "Show what is switched
 *  off", and finally let one product disagree with the shop.
 *
 *  The selectors are the shared chrome's own class names, from
 *  mart369/static/src/builder/builder.scss. That is deliberate: it makes this
 *  tour a contract on that stylesheet too, the way the home builder's is.
 */
import { registry } from "@web/core/registry";

const INFO_BAND = '.mart-canvas .pe-band:contains("Product information")';
const FIELD_ROW = '.pe-panel .pe-field-row:contains("Manufacturer address")';

registry.category("web_tour.tours").add("mart369_product_editor", {
    url: "/odoo/mart-product",
    steps: () => [
        {
            content: "the editor drew the real product page",
            trigger: ".mart-canvas .pd-page .pd-name",
        },
        {
            content: "nothing is selected, so the panel lists the whole page",
            trigger: '.pe-panel .pe-sec-row:contains("Product information")',
        },
        // The band, not its drawing: `.pe-band-in` is pointer-events:none on
        // purpose, so the page inside it cannot answer clicks. Aiming at the
        // drawing means the band intercepts and the click never lands.
        {
            content: "click that part of the page itself",
            trigger: INFO_BAND,
            run: "click",
        },
        {
            content: "the panel is now that section, and lists its fields",
            trigger: FIELD_ROW,
        },
        {
            content: "open the field",
            trigger: `${FIELD_ROW} .pe-field-open`,
            run: "click",
        },
        {
            content: "the field panel opened on the right field",
            trigger: '.pe-panel .mart-panel-head h2:contains("Manufacturer address")',
        },
        {
            content: "switch it off for the whole shop",
            trigger: '.pe-panel .mart-switch-row .mart-switch',
            run: "click",
        },
        {
            content: "it saved",
            trigger: ".pe-chip-saved",
        },
        // It has left the page: the canvas only draws what a shopper gets
        // until asked otherwise. So the proof it went off is that it comes
        // back *greyed* - `.mart-pdp-off` is only on a row the app would skip.
        {
            content: "ask to see what is switched off",
            trigger: '.pe-showhidden input[type="checkbox"]',
            run: "click",
        },
        {
            content: "it is on the page again, greyed out",
            trigger: `${INFO_BAND} .mart-pdp-off:contains("Manufacturer address")`,
        },
        {
            content: "switch to editing one product",
            trigger: '.mart-modes button:contains("One product")',
            run: "click",
        },
        // Choosing the scope opens the shop to browse, rather than an empty
        // search box you have to know a product's name to use.
        {
            content: "the shop is listed, by category",
            trigger: '.mart-pick-rail .mart-pick-row:contains("All products")',
        },
        {
            content: "and the products filed under nothing are reachable",
            trigger: '.mart-pick-rail .mart-pick-row:contains("Uncategorised")',
        },
        {
            content: "pick one",
            trigger: ".mart-pick-grid .mart-pick-tile",
            run: "click",
        },
        {
            content: "which opens that product's own page",
            trigger: ".mart-canvas .pd-page .pd-name",
        },
        {
            content: "and the toolbar says which product you are on",
            trigger: ".pe-prod-chip",
        },
        {
            content: "open the same band again, now for this one product",
            trigger: INFO_BAND,
            run: "click",
        },
        {
            content: "open the field",
            trigger: `${FIELD_ROW} .pe-field-open`,
            run: "click",
        },
        // Same field, other scope: the switch that was one question for the
        // whole shop is now three choices for this product alone.
        {
            content: "still the same field, now offering the three states",
            trigger: '.pe-panel .mart-radios:contains("Follow the default")',
        },
        {
            content: "and it is still the field we drilled into",
            trigger: '.pe-panel .mart-panel-head h2:contains("Manufacturer address")',
        },
        {
            content: "let this one product show it anyway",
            trigger: '.pe-panel .mart-radios label:contains("Always show") input',
            run: "click",
        },
        {
            content: "saved again",
            trigger: ".pe-chip-saved",
        },
        {
            content: "and this product may now be put back to following the shop",
            trigger: '.pe-panel .mart-actions button:contains("Put this one back")',
        },
    ],
});
