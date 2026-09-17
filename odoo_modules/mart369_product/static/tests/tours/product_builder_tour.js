/** Browser tour: the product-page builder does what an employee expects.
 *
 *  Opens the builder, switches a field off for the whole shop and watches the
 *  phone grey it out, then switches to one product and sets that same field
 *  back to "Always show" - the case the whole three-state design exists for.
 */
import { registry } from "@web/core/registry";

const INFO_BAND = '.mart-phone .mart-band:contains("Product information")';

registry.category("web_tour.tours").add("mart369_product_builder", {
    url: "/odoo/mart-product",
    steps: () => [
        {
            content: "the builder drew the product page",
            trigger: ".mart-phone .pd-page .pd-name",
        },
        {
            content: "the Product information band is there",
            trigger: INFO_BAND,
        },
        {
            content: "open it",
            trigger: `${INFO_BAND} .mart-band-body`,
            run: "click",
        },
        {
            content: "its fields are listed in the panel",
            trigger: '.mart-panel .mart-fieldrow:contains("Manufacturer address")',
        },
        {
            content: "switch Manufacturer address off for the whole shop",
            trigger: '.mart-panel .mart-fieldrow:contains("Manufacturer address") input[type="checkbox"]',
            run: "click",
        },
        {
            content: "it saved",
            trigger: '.mart-status[data-state="saved"]',
        },
        {
            content: "and the phone now greys that row out",
            trigger: `${INFO_BAND} .mart-pdp-off:contains("Manufacturer address")`,
        },
        {
            content: "switch to editing one product",
            trigger: '.mart-modes button:contains("One product")',
            run: "click",
        },
        {
            content: "the panel offers the three states",
            trigger: '.mart-panel .mart-radios:contains("Follow the default")',
        },
        {
            content: "set this one product to always show it",
            trigger: '.mart-panel .mart-fieldrow:contains("Manufacturer address") .mart-radios label:contains("Always show") input',
            run: "click",
        },
        {
            content: "saved again",
            trigger: '.mart-status[data-state="saved"]',
        },
        {
            content: "the row is back for this product, and marked as differing",
            trigger: '.mart-panel .mart-fieldrow:contains("Manufacturer address") .mart-differs',
        },
        {
            content: "put it back to following the shop",
            trigger: '.mart-panel .mart-fieldrow:contains("Manufacturer address") .mart-radios label:contains("Follow the default") input',
            run: "click",
        },
        {
            content: "no longer differing",
            trigger: '.mart-panel .mart-fieldrow:contains("Manufacturer address"):not(:has(.mart-differs))',
        },
    ],
});
