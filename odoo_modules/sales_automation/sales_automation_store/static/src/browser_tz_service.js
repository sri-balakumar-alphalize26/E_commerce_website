/** @odoo-module **/

import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
const { Settings } = luxon;

/**
 * Times follow the browser's clock.
 *
 * 369ai shows every date in the user's timezone *preference*, which is often
 * left at whatever the first admin had. The counter staff read the screen
 * against the clock on the wall, so when the preference and the browser's
 * zone differ, the preference is moved to the browser's zone (one write, the
 * user's own record) and luxon is switched at once - no reload needed.
 */
export const saBrowserTzService = {
    dependencies: ["orm"],
    start(env, { orm }) {
        let zone;
        try {
            zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        } catch (e) {
            return;
        }
        if (!zone || !user.userId || user.tz === zone) {
            return;
        }
        orm.call("res.users", "sa_set_browser_tz", [zone]).then((ok) => {
            if (ok) {
                try {
                    Settings.defaultZone = zone;
                    user.updateContext({ tz: zone });
                } catch (e) {
                    /* display only */
                }
            }
        }).catch(() => {});
    },
};

registry.category("services").add("sa_browser_tz", saBrowserTzService);
