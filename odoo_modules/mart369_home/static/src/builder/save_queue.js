/**
 * The builders' save behaviour, in one place.
 *
 * Both the home-page builder and the product-page builder edit records the
 * same way: a field change shows at once, is written a moment after typing
 * stops, and the screen then reloads from the server so what is on screen is
 * always what the server would send the app. This hook is that behaviour, so
 * the two builders cannot drift apart.
 *
 *   const save = useSaveQueue({
 *       orm, notification,
 *       reload: () => this.load(),          // re-fetch and replace state
 *       onStatus: (s) => (this.state.status = s),   // "saving" | "saved" | "error"
 *       find: (model, id) => ...,           // locate a local record, for replay
 *   });
 *
 *   save.edit(model, rec, "name", value);   // debounced write
 *   save.run(() => orm.unlink(model, [id]));// anything that is not a field edit
 */
import { onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useDebounced } from "@web/core/utils/timing";

export function useSaveQueue({ orm, notification, reload, onStatus, find, delay = 600 }) {
    // Pending writes, batched per record so ten keystrokes are one write.
    const pending = new Map();
    const status = (s) => onStatus && onStatus(s);

    async function _flush() {
        if (!pending.size) {
            return;
        }
        const batch = [...pending.values()];
        pending.clear();
        try {
            for (const { model, id, vals } of batch) {
                await orm.write(model, [id], vals);
            }
            await reload();
            status(pending.size ? "saving" : "saved");
        } catch (err) {
            status("error");
            notification.add(_t("That change could not be saved."), { type: "danger" });
            throw err;
        }
    }

    const flush = useDebounced(_flush, delay, { execBeforeUnmount: true });

    /** Write whatever is pending right now, without waiting for the debounce. */
    function flushNow() {
        flush.cancel();
        return _flush();
    }

    /**
     * Re-apply edits that are still in flight on top of freshly loaded data,
     * so a reload landing mid-typing does not appear to undo the keystrokes.
     */
    function applyPending() {
        if (!find) {
            return;
        }
        for (const { model, id, vals } of pending.values()) {
            const rec = find(model, id);
            if (rec) {
                Object.assign(rec, vals);
            }
        }
    }

    /** Apply a field edit locally now, write it shortly. */
    function edit(model, rec, field, value) {
        rec[field] = value;
        const key = `${model}:${rec.id}`;
        const entry = pending.get(key) || { model, id: rec.id, vals: {} };
        entry.vals[field] = value;
        pending.set(key, entry);
        status("saving");
        flush();
    }

    /** Read a field off an input event, typed the way the model wants it. */
    function valueFrom(ev) {
        const el = ev.target;
        if (el.type === "checkbox") {
            return el.checked;
        }
        if (el.type === "number") {
            const n = parseFloat(el.value);
            return Number.isFinite(n) ? n : 0;
        }
        return el.value;
    }

    /** Run a server change, then reload. For everything that is not a field edit. */
    async function run(fn, { successMessage } = {}) {
        status("saving");
        try {
            await flushNow();
            const result = await fn();
            await reload();
            status("saved");
            if (successMessage) {
                notification.add(successMessage, { type: "success" });
            }
            return result;
        } catch (err) {
            status("error");
            notification.add(_t("That change could not be saved."), { type: "danger" });
            throw err;
        }
    }

    onWillUnmount(() => flush.cancel(true));

    return { edit, run, flush, flushNow, applyPending, valueFrom, pending };
}
