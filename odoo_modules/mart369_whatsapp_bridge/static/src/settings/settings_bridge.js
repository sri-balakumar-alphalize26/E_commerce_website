/** Settings > WhatsApp - the tab the journey map promised.
 *
 * Which session speaks, one switch and one wording per step, the invoice
 * switch, and a Check now that asks the gateway instead of the cache. The
 * tab plugs into the existing screen's own load/dirty/save machinery: the
 * server ships a `whatsapp` group, the screen shows a tab for it.
 */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { SettingsDesk } from "@mart369_payment/desk/settings_desk";

export const WA_STEPS = [
    ["placed", _t("Order placed")],
    ["packed", _t("Packed")],
    ["shipped", _t("Shipped")],
    ["out", _t("Out for delivery")],
    ["delivered", _t("Delivered")],
    ["cancelled", _t("Cancelled")],
];

patch(SettingsDesk.prototype, {
    setup() {
        super.setup();
        this.WA_STEPS = WA_STEPS;
    },

    get tabItems() {
        const tabs = super.tabItems;
        if (this.state.saved?.whatsapp) {
            // Before Alerts, which the base keeps last.
            tabs.splice(tabs.length - 1, 0, ["whatsapp", _t("WhatsApp"), null]);
        }
        return tabs;
    },

    get waSessionOptions() {
        const sessions = this.state.draft?.whatsapp?.sessions || [];
        return [
            [false, _t("Whichever is connected")],
            ...sessions.map((s) => [s.id, `${s.name} (${s.status})`]),
        ];
    },

    waSession() {
        const wa = this.state.draft?.whatsapp;
        return (wa?.sessions || []).find((s) => s.id === wa?.sessionId) || null;
    },

    setWaOn(step, value) {
        this.state.draft.whatsapp.on[step] = value;
    },

    setWaText(step, value) {
        this.state.draft.whatsapp.texts[step] = value;
    },

    /** Ask the gateway now. Refreshes the saved copy's session list only, so
     *  unsaved wording edits survive the button. */
    async waCheckNow() {
        this.state.busy = true;
        try {
            const wa = await this.orm.call("mart369.config", "mart369_admin_wa_check", []);
            this.state.saved.whatsapp.sessions = wa.sessions || [];
            this.state.draft.whatsapp.sessions = JSON.parse(
                JSON.stringify(wa.sessions || [])
            );
            this.state.error = "";
        } catch (err) {
            this.state.error = err.data?.message || String(err);
        } finally {
            this.state.busy = false;
        }
    },
});
