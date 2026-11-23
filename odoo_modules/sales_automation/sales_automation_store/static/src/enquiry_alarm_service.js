/** @odoo-module **/

/**
 * The enquiry alarm, from any menu.
 *
 * A service, not a component: it starts with the web client and never
 * unmounts, so a counter working in Contacts or the POS still hears that an
 * enquiry is waiting. The Enquiries screen keeps its own alarm for when it is
 * open; this one stands down then (see `presence`).
 *
 * Two deliberate choices:
 *
 *   * **It rings until the deadline, not for a fixed few minutes.** The
 *     vendor-pick alarm stops when the enquiry's own timeout passes - which
 *     is also the moment the auto-send cron takes the decision away, so the
 *     sound stops exactly when there is nothing left to decide.
 *   * **Every tab that has been clicked in will ring.** Restricting it to one
 *     "main" tab is tidier but silent in the case that matters: if the main
 *     tab happens to be one nobody has clicked, its AudioContext was never
 *     allowed to start and the alarm never sounds at all.
 */

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { Alarm } from "./store_screen";
import { ENQUIRY_TONE, STALLED_TONE, presence } from "./enquiry_alarm_shared";
import { onShared, shared, sharedChanged } from "./notice_shared";

const POLL_MS = 20000;
/** Give up after this many consecutive RPC failures rather than hammer. */
const MAX_FAILURES = 3;

export const enquiryAlarmService = {
    dependencies: ["orm", "bus_service", "notification", "action"],

    start(env, { orm, bus_service, notification, action }) {
        const pickAlarm = new Alarm();
        const stalledAlarm = new Alarm();
        let armed = false;
        let failures = 0;
        let closeNotification = null;
        let state = null;
        let pickTimer = null;
        let stalledTimer = null;
        let stalledUntil = 0;

        /**
         * A browser will not start an AudioContext outside a user gesture, so
         * the alarm is armed on the first click or key press anywhere in the
         * app. Nobody has to remember to switch it on, and by the time an
         * enquiry arrives the person has certainly clicked something.
         */
        function armOnFirstGesture() {
            const arm = async () => {
                if (armed) {
                    return;
                }
                armed = (await pickAlarm.arm()) && (await stalledAlarm.arm());
                if (armed) {
                    document.removeEventListener("pointerdown", arm, true);
                    document.removeEventListener("keydown", arm, true);
                    sync();
                }
            };
            document.addEventListener("pointerdown", arm, true);
            document.addEventListener("keydown", arm, true);
        }

        function stopPick() {
            if (pickTimer) {
                clearInterval(pickTimer);
                pickTimer = null;
            }
            pickAlarm.stop();
        }

        function stopStalled() {
            if (stalledTimer) {
                clearInterval(stalledTimer);
                stalledTimer = null;
            }
            stalledAlarm.stop();
        }

        function stopAll() {
            stopPick();
            stopStalled();
        }

        function sync() {
            if (!state || !armed || presence.screens > 0) {
                // The screen is open and already ringing, or we have nothing
                // to ring about yet.
                stopAll();
                return;
            }

            // Vendor pick: ring for as long as the enquiry still has time on
            // its own clock. When that runs out the cron asks every vendor
            // anyway, so there is nothing left for the alarm to ask for.
            if (state.pick > 0 && state.pick_seconds_left > 0) {
                if (!pickTimer) {
                    pickAlarm.ring(state.ring, ENQUIRY_TONE);
                    pickTimer = setInterval(
                        () => pickAlarm.ring(state.ring, ENQUIRY_TONE),
                        (state.ring + state.repeat) * 1000);
                }
            } else {
                stopPick();
            }

            // No vendor replied: there is no deadline to stop at - it waits
            // for a person - so this one keeps its minute cap.
            if (state.stalled > 0) {
                if (!stalledTimer) {
                    const minutes = state.stalled_max_minutes;
                    stalledUntil = minutes
                        ? Date.now() + minutes * 60000
                        : Infinity;
                    stalledAlarm.ring(state.stalled_ring, STALLED_TONE);
                    stalledTimer = setInterval(() => {
                        if (Date.now() >= stalledUntil) {
                            stopStalled();
                            return;
                        }
                        stalledAlarm.ring(state.stalled_ring, STALLED_TONE);
                    }, state.stalled_repeat * 1000);
                }
            } else {
                stopStalled();
            }
        }

        /** A sticky note, because a sound alone does not say what to do. */
        function tellThem() {
            const waiting = state.pick + state.stalled;
            if (shared.pick !== state.pick || shared.stalled !== state.stalled) {
                shared.pick = state.pick;
                shared.stalled = state.stalled;
                sharedChanged();
            }
            if (!shared.known) {
                return;                 // told when the side panel answered
            }
            if (!waiting || shared.on) {
                if (closeNotification) {
                    closeNotification();
                    closeNotification = null;
                }
                return;
            }
            if (closeNotification || presence.screens > 0) {
                return;                 // already told, or already looking
            }
            const parts = [];
            if (state.pick) {
                parts.push(_t("%s waiting for vendors to be chosen",
                              state.pick));
            }
            if (state.stalled) {
                parts.push(_t("%s where no vendor replied", state.stalled));
            }
            closeNotification = notification.add(parts.join(" - "), {
                title: _t("Enquiries need you"),
                type: "warning",
                sticky: true,
                buttons: [{
                    name: _t("Open Enquiries"),
                    primary: true,
                    onClick: () => {
                        action.doAction(
                            "sales_automation_store.action_sa_enquiry_screen");
                    },
                }],
                onClose: () => {
                    closeNotification = null;
                },
            });
        }

        async function poll() {
            try {
                state = await orm.call("sa.group.request", "sa_alarm_state",
                                       []);
                failures = 0;
            } catch (_err) {
                // A user without access, or a server restart. Neither is
                // worth a dialog on somebody else's screen.
                failures += 1;
                if (failures >= MAX_FAILURES) {
                    stopAll();
                    clearInterval(poller);
                }
                return;
            }
            sync();
            tellThem();
        }

        armOnFirstGesture();
        let was = null;
        onShared(() => {
            const now = `${shared.known}${shared.on}`;
            if (now !== was) {
                was = now;
                if (state) {
                    tellThem();
                }
            }
        });
        bus_service.addChannel("sa_store_0");
        bus_service.subscribe("sa_enquiry/refresh", () => poll());
        const poller = setInterval(poll, POLL_MS);
        poll();

        return { poll };
    },
};

registry.category("services").add("sa_enquiry_alarm", enquiryAlarmService);
