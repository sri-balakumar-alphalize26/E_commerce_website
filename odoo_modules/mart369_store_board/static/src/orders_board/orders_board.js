/** @odoo-module **/

/**
 * 369 Mart › Sales › Orders › Counter.
 *
 * The Store's counter screen (sales_automation_store) inside the 369 Mart
 * app, drawn like All orders (mart369_order's desk) - the same header, tabs,
 * rows and buttons - with New / Quick / Express tabs. The admin console's
 * Counter (components/admin/AdminCounter.jsx) draws the same rows.
 *
 * What is inherited, not copied: the alarm that rings until somebody presses
 * Accept, the live refresh over the bus, Accept (with its company and supply
 * dialogs) -> Packed -> rider, Put back, Cancel. Only the read changes: it asks
 * `mart369_counter`, which is the Store's `sa_store_queue` plus each order as
 * All orders draws it (models/stock_picking.py). The number, money and time
 * words are All orders' own helpers, borrowed from OrderDesk.
 *
 * The alarm is left alone on purpose: it counts every waiting order, so a new
 * Express order still rings while somebody is looking at the Quick tab.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";
import { Layout } from "@web/search/layout";
import { StoreScreen } from "@sales_automation_store/store_screen";
import { OrderDesk } from "@mart369_order/desk/order_desk";
import { Icon } from "@mart369/ui/icon";
import { Tabs } from "@mart369/ui/tabs";

export const BOARD_TABS = [
    { key: "new", label: "New", match: (row) => row.state === "awaiting_shop" },
    { key: "quick", label: "Quick", match: (row) => row.kind === "quick" },
    { key: "express", label: "Express", match: (row) => row.kind === "express" },
];

const STAGE_TONE = {
    awaiting_shop: "red",
    preparing: "amber",
    ready: "blue",
    offered: "blue",
    accepted: "violet",
};

const desk = OrderDesk.prototype;

export class Mart369OrdersBoard extends StoreScreen {
    static template = "mart369_store_board.OrdersBoard";
    static components = { ...StoreScreen.components, Layout, Icon, Tabs };

    setup() {
        super.setup();
        this.actionService = useService("action");
        this.counterAlarm = useService("mart369_counter_alarm");
        this.alarmState = useState(this.counterAlarm.state);
        this.BOARD_TABS = BOARD_TABS;
        this.board = useState({ tab: "new" });
    }

    // ------------------------------------------------------------ the alarm

    /** The ringing belongs to the app-wide alarm (alarm/counter_alarm_service),
     *  which keeps going on every other screen too; this screen only says
     *  whether it is on. Two alarms here would ring over each other. */
    _syncAlarm() {
        this._stopAlarm();
        this.counterAlarm.refresh();
    }

    async onEnableSound() {
        await this.counterAlarm.arm();
    }

    // ------------------------------------------------------------ reading

    /** The Store's refresh, reading the enriched queue instead. A server
     *  process started before this module was upgraded does not have
     *  `mart369_counter` yet: then the Store's own read is used, and the rows
     *  draw without the order's total and tags until it is restarted. */
    async refresh() {
        let data;
        try {
            data = await this.orm.call(
                "stock.picking", "mart369_counter", [this.state.shopId || null]);
        } catch {
            return super.refresh();
        }
        this.state.rows = data.rows;
        this.state.ringing = data.ringing;
        this.state.packing = data.packing;
        this.state.waitingSupply = data.waiting_supply || 0;
        this.state.supplyRinging = data.supply_ringing || 0;
        this.state.loading = false;
        if ((data.repeat && data.repeat !== this.state.repeat)
            || (data.ring && data.ring !== this.state.ring)) {
            this.state.repeat = data.repeat || this.state.repeat;
            this.state.ring = data.ring || this.state.ring;
            this._stopAlarm();
        }
        this._syncAlarm();
        this._syncSupplyAlarm();
    }

    /** The Store's buttons answer with its plain queue; read ours again so
     *  the rows keep their All orders shape. */
    async act(row, action, extra = {}) {
        await super.act(row, action, extra);
        await this.refresh();
    }

    // --------------------------------------------------------------- tabs

    get activeTab() {
        return BOARD_TABS.find((tab) => tab.key === this.board.tab) || BOARD_TABS[0];
    }

    get tabRows() {
        return this.state.rows.filter(this.activeTab.match);
    }

    /** [key, label, count] triples, the way the kit's Tabs take them. */
    get tabItems() {
        return BOARD_TABS.map((tab) => [tab.key, tab.label, this.state.rows.filter(tab.match).length]);
    }

    pickTab(key) {
        this.board.tab = key;
    }

    // ------------------------------------------------------------ the toggle

    /** All orders, replacing this screen - optionally with one order open. */
    showAllOrders(ref = null) {
        return this.actionService.doAction("mart369_order.action_mart369_order_desk", {
            clearBreadcrumbs: true,
            additionalContext: ref ? { mart369_open_ref: ref } : {},
        });
    }

    openOrder(row) {
        if (row.order?.ref) {
            this.showAllOrders(row.order.ref);
        }
    }

    // --------------------------------------------------- All orders' words

    money(amount, currency) { return desk.money.call(this, amount, currency); }
    ago(ms) { return desk.ago.call(this, ms); }
    payText(order) { return desk.payText.call(this, order); }
    tagTone(tag) { return desk.tagTone.call(this, tag); }

    stageTone(row) {
        return STAGE_TONE[row.state] || "grey";
    }

    channelLabel(row) {
        return row.channel === "whatsapp" ? "WhatsApp" : "Website";
    }
}

registry.category("actions").add("mart369_store_board.orders_board", Mart369OrdersBoard);
