/* What a product's delivery label says. No React and no network, so
   `npm run test:unit` can load it (tests/unit/deliveryLine.test.mjs).
   lib/delivery.js re-exports these for the screens. */

/* Nothing in stock (the shop sends stock: 0). A product Inventory does not
   track sends no stock at all and is never "out". */
export function isOut(p) {
  return p?.stock === 0;
}

/* Quick or Express for a product: the shop's answer when it has one, else
   the product's own rule - a delivery promise makes it Express.
   Out of stock is never Quick (13 Nov 2026): "all" when the product has its
   own Express promise, else "none" - no delivery line at all. */
export function modeOf(p, badge) {
  if (isOut(p)) return p?.delivery ? "all" : "none";
  if (badge?.mode) return badge.mode;
  return p?.delivery ? "all" : "quick";
}

/* The one line the product page prints: "Quick · 30 mins" (the hub's own
   Quick promise, else the shop's usual words), "Express · Next day" (the
   product's own promise first, then the hub rules'), or just "Express".
   Out of stock: only the product's own Express promise, else "". */
export function deliveryLine(p, badge) {
  const mode = modeOf(p, badge);
  if (mode === "none") return "";
  if (isOut(p)) return `Express · ${p.delivery}`;
  if (mode === "quick") return `Quick · ${badge?.when || "10–20 mins"}`;
  const when = p?.delivery || badge?.when;
  return when ? `Express · ${when}` : "Express";
}
