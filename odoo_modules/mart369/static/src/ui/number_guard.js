/** Numbers only, in every number box on a 369 Mart screen.
 *
 * The browser's number box accepts "e", "+" and "-" (1e5, -3), and a paste of
 * anything at all. None of those is a price, a count or a number of days, and
 * every one of them has reached a save as nonsense or as NaN.
 *
 * One listener for all of them, rather than a handler on each of the dozen
 * boxes across deals, coupons, referrals and the builders - so a box added
 * next month is covered without anybody remembering to.
 *
 * Only inside the 369 Mart screens (`.o_mart369_desk`, `.mart-builder`), so
 * Odoo's own number fields behave exactly as Odoo made them. A box with
 * step="1" is a count, so it refuses the decimal point too.
 */
import { registry } from "@web/core/registry";

const SCOPE = ".o_mart369_desk, .mart-builder";

function guarded(el) {
    return el instanceof HTMLInputElement && el.type === "number" && el.closest(SCOPE);
}

function whole(el) {
    return el.getAttribute("step") === "1";
}

export const numberGuardService = {
    start() {
        document.addEventListener("keydown", (ev) => {
            if (!guarded(ev.target) || ev.ctrlKey || ev.metaKey || ev.altKey) {
                return;
            }
            if (["e", "E", "+", "-"].includes(ev.key) || (ev.key === "." && whole(ev.target))) {
                ev.preventDefault();
            }
        }, true);

        document.addEventListener("paste", (ev) => {
            if (!guarded(ev.target)) {
                return;
            }
            const text = (ev.clipboardData?.getData("text") || "").trim();
            const ok = whole(ev.target) ? /^\d+$/ : /^\d*\.?\d+$|^\d+\.$/;
            if (!ok.test(text)) {
                ev.preventDefault();
            }
        }, true);
    },
};

registry.category("services").add("mart369_number_guard", numberGuardService);
