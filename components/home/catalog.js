/* What survived the sample catalogue.

   This file used to hold the shop: seventy products, a taxonomy, pack sizes,
   and buildIndex() to assemble them. All of that now comes from Odoo, and the
   storefront no longer carries a second, invented shop around with it.

   What is left is the small amount that is not product data:

   - three maps from a home-page key to a route, kept only for keys that are
     not category addresses (home, offers) and for feeds written before tiles
     and rows carried their own `route`;
   - enrich(), which fills in the fields the listing filters on. It is
     load-bearing: a card arrives without `off` when the product has no
     discount, and an undefined value fails every comparison silently.
*/

export const TAB_TO_ROUTE = {
  home: ["home"], foryou: ["home"],
  grocery: ["category", "staples"], fruits: ["category", "fruits-vegetables"],
  electronics: ["category", "electronics"], kitchen: ["category", "home-kitchen"],
  stationery: ["category", "stationery"], fashion: ["category", "fashion"], books: ["category", "books"],
  coupons: ["offers"], offers: ["offers"],
};
export const TILE_TO_ROUTE = {
  fruits: "fruits-vegetables/fresh-fruits", veg: "fruits-vegetables/vegetables", staples: "staples/atta-flours",
  oil: "staples/oils-ghee", snacks: "snacks-beverages/chocolates", audio: "electronics/audio", kitchen: "home-kitchen/dinnerware",
  stationery: "stationery", storage: "electronics/storage", chargers: "electronics/chargers", cameras: "electronics/webcams",
  dinner: "home-kitchen/dinnerware", linen: "home-kitchen/bath-linen", lighting: "electronics/lighting", baskets: "home-kitchen/storage",
};
export const SECTION_TO_ROUTE = {
  fruits: "fruits-vegetables/fresh-fruits", daily: "staples", tech: "electronics", home: "home-kitchen",
  "all-tech": "electronics", "all-home": "home-kitchen", "all-office": "stationery",
};
export function enrich(p) {
  p.brand = p.brand || (p.veg ? "369 Mart Select" : p.unit || "369 Mart");
  p.off = p.mrp ? Math.round(((p.mrp - p.price) / p.mrp) * 100) : 0;
  const h = [...String(p.id)].reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) >>> 0, 7);
  p.rating = p.rating ?? Math.round((3.8 + (h % 12) / 10) * 10) / 10;
  p.popularity = p.popularity ?? h % 1000;
  return p;
}
export const listable = (byId) => Object.values(byId).filter((p) => !p.hidden);
