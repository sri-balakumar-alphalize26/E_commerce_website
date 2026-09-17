/** Browser tour: the home page builder does what an operator expects.
 *
 *  Opens the builder on the seeded Quick page, renames a row and watches the
 *  change save and come back into the phone mock from the server, hides a
 *  row, then adds a banner from the banners panel.
 */
import { registry } from "@web/core/registry";

const FRUITS = '.mart-band[data-band-id]:contains("Fresh fruits")';
const PICKS = '.mart-band[data-band-id]:contains("Fresh picks")';

registry.category("web_tour.tours").add("mart369_home_builder", {
    url: "/odoo/mart-home",
    steps: () => [
        {
            content: "the builder rendered the phone with the seeded page",
            trigger: ".mart-phone .hm-page .hm-rail h2",
        },
        {
            content: "the seeded Fresh fruits row is on the phone",
            trigger: `${FRUITS} h2:contains("Fresh fruits")`,
        },
        {
            content: "click the row to edit it",
            trigger: `${FRUITS} .mart-band-body`,
            run: "click",
        },
        {
            content: "the panel opened on that row",
            trigger: '.mart-panel h3:contains("Fresh fruits")',
        },
        {
            content: "rename it",
            trigger: '.mart-panel input[placeholder="e.g. Fresh fruits"]',
            run: "edit Fresh picks",
        },
        {
            content: "the edit is being saved",
            trigger: '.mart-status[data-state="saving"]',
        },
        {
            content: "the edit was saved",
            trigger: '.mart-status[data-state="saved"]',
        },
        {
            content: "the phone now shows the new title, reloaded from the server",
            trigger: `${PICKS} h2:contains("Fresh picks")`,
        },
        {
            content: "hide the row with the eye button",
            trigger: `${PICKS} .mart-band-tools .mart-tool:first-child`,
            run: "click",
        },
        {
            content: "the row is greyed out on the phone",
            trigger: `${PICKS}.mart-hidden`,
        },
        {
            content: "open the banners strip",
            trigger: "main.hm-main > .mart-band:first-child .mart-band-body",
            run: "click",
        },
        {
            content: "the banners panel opened",
            trigger: '.mart-panel h3:contains("Banners")',
        },
        {
            content: "add a banner",
            trigger: ".mart-panel .mart-btn-primary",
            run: "click",
        },
        {
            content: "the new banner is listed, opened for editing",
            trigger: '.mart-panel .mart-item.mart-selected:contains("New banner")',
        },
        {
            content: "and it is already on the phone",
            trigger: '.mart-phone .hm-banner strong:contains("New banner")',
        },
    ],
});
