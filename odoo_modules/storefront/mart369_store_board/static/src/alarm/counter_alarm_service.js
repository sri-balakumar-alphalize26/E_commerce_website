/** @odoo-module **/

/**
 * The new-order alarm, from any menu.
 *
 * A service, not part of the Counter screen: it starts with the web client and
 * never unmounts, so somebody who moved from the Counter to All orders - or to
 * Contacts, or anywhere - still hears that an order is waiting. It rings while
 * any order waits for Accept, at the counter's own cadence (Delivery Settings:
 * ring seconds, then a pause), and stops when the last one is accepted.
 *
 * There is no off switch, on purpose - the counter's own alarm has none
 * either. A browser will not play sound before the person has clicked, so it
 * arms on the first click or key press anywhere; after that it cannot be
 * silenced from the screen, only by accepting the orders.
 *
 * The same pattern as the Store's enquiry alarm (sales_automation_store's
 * enquiry_alarm_service.js), and the Store's own `Alarm` sound, so the two
 * alarms a counter hears are built the same way.
 */

import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";
import { Alarm } from "@sales_automation_store/store_screen";

const POLL_MS = 10000;
/* The package's rule (enquiry_alarm_service.js): after this many failed asks
   in a row, go silent - the server is restarting or the user has lost access,
   and a sound about a count nobody can check is a sound about nothing. It
   used to keep ringing on the last count, for orders long since cancelled. */
const MAX_FAILURES = 3;
/* Unlike the package it does not stop asking: it slows down, and the moment
   the server answers again the count - and the sound - are true again. */
const BACKOFF_MS = [10000, 20000, 30000, 60000];

export const counterAlarmService = {
    dependencies: ["orm", "bus_service", "notification", "action"],

    start(env, { orm, bus_service, notification, action }) {
        const state = reactive({ enabled: false, armed: false, ringing: 0 });
        const alarm = new Alarm();
        let ringFor = 30;
        let pause = 10;
        let timer = null;
        let failures = 0;
        let closeNotification = null;

        function stop() {
            if (timer) {
                clearInterval(timer);
                timer = null;
            }
            alarm.stop();
        }

        /** The Store app's own counter screen rings for itself; stand down
         *  while it is open so the shop does not hear two alarms at once. */
        function storeScreenOpen() {
            return !!document.querySelector(".sa_store");
        }

        function sync() {
            if (state.armed && state.ringing > 0 && !storeScreenOpen()) {
                if (!timer) {
                    alarm.ring(ringFor);
                    timer = setInterval(() => alarm.ring(ringFor), (ringFor + pause) * 1000);
                }
            } else {
                stop();
            }
        }

        function counterOpen() {
            return !!document.querySelector(".mart_counter");
        }

        /** A sticky note, because a sound alone does not say what to do -
         *  the package's enquiry alarm does the same. Closed the moment
         *  nothing is waiting; not shown while the Counter itself is open. */
        function tellThem() {
            if (!state.ringing) {
                if (closeNotification) {
                    closeNotification();
                    closeNotification = null;
                }
                return;
            }
            if (closeNotification || counterOpen() || storeScreenOpen()) {
                return;
            }
            closeNotification = notification.add(
                state.ringing === 1
                    ? _t("1 order is waiting to be accepted")
                    : _t("%s orders are waiting to be accepted", state.ringing), {
                    title: _t("New orders"),
                    // The package's style (its enquiry notice): the button
                    // stays readable, where red washed it out.
                    type: "warning",
                    sticky: true,
                    buttons: [{
                        name: _t("Open the Counter"),
                        primary: true,
                        onClick: () => action.doAction(
                            "mart369_store_board.action_mart369_orders_board",
                            { clearBreadcrumbs: true }),
                    }],
                    onClose: () => {
                        closeNotification = null;
                    },
                });
        }

        async function poll() {
            try {
                const data = await orm.silent.call("stock.picking", "mart369_counter_ringing", []);
                failures = 0;
                const cadence = (data.ring || 30) !== ringFor || (data.repeat || 10) !== pause;
                ringFor = data.ring || 30;
                pause = data.repeat || 10;
                if (cadence) {
                    stop();
                }
                state.ringing = data.ringing || 0;
            } catch {
                failures += 1;
                if (failures < MAX_FAILURES) {
                    return;             // one blip: keep what we knew
                }
                state.ringing = 0;      // cannot check it: stop saying it
            }
            sync();
            tellThem();
        }

        async function arm() {
            if (!state.armed) {
                state.armed = await alarm.arm();
                sync();
            }
            return state.armed;
        }

        async function begin() {
            const staff = (await user.hasGroup("sales_team.group_sale_salesman"))
                || (await user.hasGroup("website.group_website_designer"));
            if (!staff) {
                return;
            }
            state.enabled = true;
            // Armed by the first gesture anywhere: nobody has to remember to
            // switch it on, and there is nothing to switch off.
            const onGesture = async () => {
                if (await arm()) {
                    document.removeEventListener("pointerdown", onGesture, true);
                    document.removeEventListener("keydown", onGesture, true);
                }
            };
            document.addEventListener("pointerdown", onGesture, true);
            document.addEventListener("keydown", onGesture, true);
            // The counter's own push: a new order is heard at once, not at
            // the next poll.
            bus_service.addChannel("sa_store_0");
            bus_service.subscribe("sa_store/refresh", () => poll());
            const loop = async () => {
                await poll();
                const wait = failures ? BACKOFF_MS[Math.min(failures, BACKOFF_MS.length - 1)] : POLL_MS;
                setTimeout(loop, wait);
            };
            loop();
        }
        begin();

        return { state, arm, refresh: poll };
    },
};

registry.category("services").add("mart369_counter_alarm", counterAlarmService);
