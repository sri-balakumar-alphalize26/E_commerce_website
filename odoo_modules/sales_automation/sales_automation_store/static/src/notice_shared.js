/** @odoo-module **/

// What the side panel and the enquiry alarm tell each other. Toggle off (or a
// user who may not see the panel): the alarm shows its own note, as always.
import { reactive } from "@odoo/owl";

export const shared = reactive({ known: false, on: false, pick: 0, stalled: 0, counter: 0 });

const listeners = [];
export function onShared(callback) {
    listeners.push(callback);
}
export function sharedChanged() {
    for (const callback of listeners) {
        callback();
    }
}
