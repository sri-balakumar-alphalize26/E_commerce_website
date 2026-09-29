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
import { Alarm } from "@sales_automation_store/store_screen";

const POLL_MS = 10000;
const MAX_FAILURES = 5;

export const counterAlarmService = {
    dependencies: ["orm", "bus_service"],

    start(env, { orm, bus_service }) {
        const state = reactive({ enabled: false, armed: false, ringing: 0 });
        const alarm = new Alarm();
        let ringFor = 30;
        let pause = 10;
        let timer = null;
        let failures = 0;

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
                sync();
            } catch {
                failures += 1;
            }
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
            await poll();
            const id = setInterval(() => {
                if (failures >= MAX_FAILURES) {
                    clearInterval(id);
                    return;
                }
                poll();
            }, POLL_MS);
        }
        begin();

        return { state, arm, refresh: poll };
    },
};

registry.category("services").add("mart369_counter_alarm", counterAlarmService);
