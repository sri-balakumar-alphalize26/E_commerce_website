/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { EnquiryScreen, PriceDialog } from "@sales_automation_store/enquiry_screen";

/**
 * The counter screen learns one more section: WeChat price checks that the
 * bridge PC could not send (it is down, or the contact is missing). A person
 * copies the text into WeChat by hand, marks it sent, and types the vendor's
 * price back in.
 */
patch(EnquiryScreen.prototype, {
    setup() {
        super.setup();
        this.state.wechat = { enabled: false, alive: false, manual_on: false, rows: [] };
    },

    async refresh() {
        await super.refresh();
        // `sa_enquiry_queue` carries the block; a second call is avoided.
        // The base refresh stored nothing of it, so fetch it here cheaply.
        try {
            const w = await this.orm.call("sa.wechat.message", "sa_wechat_relay_rows", []);
            this.state.wechat = w || this.state.wechat;
        } catch (e) {
            // the desk must never break over WeChat
        }
    },

    async wechatCopy(row) {
        try {
            await navigator.clipboard.writeText(row.text || "");
            this.notification.add(`Copied - paste it to ${row.remark} in WeChat.`, { type: "success" });
        } catch (e) {
            this.notification.add("Copy failed - select the text and copy it by hand.", { type: "warning" });
        }
    },

    async wechatAct(row, action, extra) {
        const data = await this.orm.call("sa.wechat.message", "sa_wechat_act",
            [row.id, action, extra ? extra.cost : null, extra ? extra.days : 0]);
        this.state.wechat = data || this.state.wechat;
        await this.refresh();
    },

    wechatSentByHand(row) {
        return this.wechatAct(row, "sent_by_hand");
    },

    wechatPrice(row) {
        this.dialog.add(PriceDialog, {
            row: {
                ref: row.ref, product: row.product, customer: "", margin: 0, currency: "",
                vendors: row.partner_id ? [{ id: row.partner_id, name: row.vendor }] : [],
                hint_cost: 0,
            },
            onApply: ({ cost, days }) => this.wechatAct(row, "price", { cost, days }),
        });
    },
});
