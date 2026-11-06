/** @odoo-module **/

/** Five glyphs, so a 4.2 reads as four full stars and one empty. */
export function starGlyphs(value) {
    const full = Math.round(value || 0);
    return { on: "★".repeat(Math.max(0, Math.min(5, full))),
             off: "☆".repeat(Math.max(0, 5 - Math.min(5, full))) };
}

export function money(value, currency) {
    const n = Number(value || 0);
    return (currency || "") + n.toLocaleString(undefined, {
        minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function when(iso) {
    if (!iso) {
        return "";
    }
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
        day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function clock(iso) {
    if (!iso) {
        return "";
    }
    return new Date(iso).toLocaleTimeString(undefined, {
        hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** Read a --sai-* custom property off the console root, for the charts. */
export function cssVar(el, name, fallback) {
    const root = el && el.closest ? el.closest(".sa_insights") : null;
    const v = root ? getComputedStyle(root).getPropertyValue(name).trim() : "";
    return v || fallback;
}
