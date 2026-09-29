/** @odoo-module **/

/**
 * "N new orders" in the top bar, on every screen, while the alarm rings -
 * so whoever hears it can see why and get to the Counter in one click.
 * Hidden when nothing is waiting.
 */

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class CounterAlarmSystray extends Component {
    static template = "mart369_store_board.CounterAlarmSystray";
    static props = {};

    setup() {
        this.alarm = useService("mart369_counter_alarm");
        this.state = useState(this.alarm.state);
        this.action = useService("action");
    }

    open() {
        this.alarm.arm();
        return this.action.doAction("mart369_store_board.action_mart369_orders_board", {
            clearBreadcrumbs: true,
        });
    }
}

registry.category("systray").add("mart369_store_board.counter_alarm", {
    Component: CounterAlarmSystray,
}, { sequence: 1 });
