/* ==========================================================================
   Loyalty points — the words, in one place for Checkout and Account.

   The numbers are the shop's (the counter's loyalty card and its rule, via
   /cart/bill and /loyalty). This file only says them.
   ========================================================================== */

/* 1234.5 -> "1,234.5" */
export const pointsText = (n) =>
  (Math.round((Number(n) || 0) * 100) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 });

/* When an online order earns - the shop's setting (Settings → Loyalty). */
export const EARN_WHEN = {
  placed: "once your order is placed",
  packed: "once your order is packed",
  out: "when your order is out for delivery",
  delivered: "when your order is delivered",
  settled: "a few days after delivery",
};

/* Why points cannot go on this bill - `reason` from the shop's bill. */
export function pointsWhy(p) {
  switch (p?.reason) {
    case "inactive": return "Your loyalty card is paused. Ask at the store.";
    case "min": return `Points can be used from ${pointsText(p.min)}. You have ${pointsText(p.balance)}.`;
    case "small": return "This order is too small to use your points.";
    case "today": return "Points can be used once a day. Try again tomorrow.";
    default: return "";
  }
}
