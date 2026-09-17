/* ==========================================================================
   369 Mart — catalogue for browsing: categories → subcategories → products,
   extra sample products for listings, and pack-size variants.
   In production build this from Odoo product.public.category + product.template.
   ========================================================================== */
import { SECTIONS, ALL_SECTIONS } from "./sampleData";

const pics = (id, n = 3) => Array.from({ length: n }, (_, k) => `/images/products/${id}-${k + 1}.svg`);
const E = (days = "2–3 days") => ({ delivery: days });

/* ---------------- extra sample products ---------------- */
export const EXTRA_ITEMS = [
  // fruits & vegetables
  { id: "x1", name: "Nagpur Orange 1 kg", unit: "1 kg", price: 129, mrp: 159, veg: true, art: "Orange", brand: "369 Fresh" },
  { id: "x3", name: "Kashmir Apple, 4 pcs", unit: "4 pieces", note: "Approx 600–750 g", price: 199, mrp: 239, veg: true, art: "Apple", color: "#c7202b", brand: "369 Fresh" },
  { id: "v1", name: "Hybrid Tomato 1 kg", unit: "1 kg", price: 39, mrp: 52, veg: true, art: "Tomato", brand: "369 Fresh" },
  { id: "v2", name: "Big Onion 1 kg", unit: "1 kg", price: 45, mrp: 60, veg: true, art: "Onion", color: "#b87a5a", brand: "369 Fresh" },
  { id: "v3", name: "Palak (Spinach) Bunch", unit: "250 g", price: 29, veg: true, art: "Leafy", brand: "369 Fresh" },
  { id: "v4", name: "Cherry Tomato 200 g", unit: "200 g", price: 79, mrp: 99, veg: true, art: "Tomato", color: "#e0453a", brand: "FarmFresh Co." },
  { id: "v5", name: "Sambar Onion 500 g", unit: "500 g", price: 59, mrp: 79, veg: true, art: "Onion", brand: "369 Fresh" },
  { id: "v6", name: "Coriander Leaves 100 g", unit: "100 g", price: 15, veg: true, art: "Leafy", color: "#3f8e2e", brand: "FarmFresh Co.", low: 3 },
  // staples
  { id: "s1", name: "Chakki Fresh Atta 10 kg", unit: "10 kg", price: 569, mrp: 699, veg: true, art: "Pack", color: "#a35c24", label: "ATTA", brand: "GoldenField" },
  { id: "s2", name: "Besan (Gram Flour) 1 kg", unit: "1 kg", price: 119, mrp: 140, veg: true, art: "Pack", color: "#d4a017", label: "BESAN", brand: "GoldenField" },
  { id: "s3", name: "Bombay Rava (Sooji) 1 kg", unit: "1 kg", price: 64, mrp: 78, veg: true, art: "Pack", color: "#b89468", label: "RAVA", brand: "369 Mart Select" },
  { id: "s4", name: "Refined Sunflower Oil 1 L", unit: "1 L", price: 159, mrp: 189, veg: true, art: "Bottle", color: "#e8b923", label: "OIL", brand: "Kerala Grove" },
  { id: "s5", name: "Pure Cow Ghee 500 ml", unit: "500 ml", price: 349, mrp: 399, veg: true, art: "Jar", color: "#f0c24b", label: "GHEE", brand: "369 Mart Select" },
  { id: "s6", name: "Virgin Coconut Oil 500 ml", unit: "500 ml", price: 289, mrp: 340, veg: true, art: "Bottle", color: "#7fae95", label: "VCO", brand: "Kerala Grove" },
  { id: "s7", name: "Kerala Matta Rice 5 kg", unit: "5 kg", price: 399, mrp: 475, veg: true, art: "Pack", color: "#8a4b2a", label: "RICE", brand: "GoldenField" },
  { id: "s8", name: "Toor Dal 1 kg", unit: "1 kg", price: 169, mrp: 199, veg: true, art: "Pack", color: "#d69a22", label: "DAL", brand: "369 Mart Select" },
  { id: "s9", name: "Basmati Rice 1 kg", unit: "1 kg", price: 139, mrp: 175, veg: true, art: "Pack", color: "#2d6a8a", label: "BASMATI", brand: "GoldenField", stock: 0 },
  { id: "s10", name: "Sugar 1 kg", unit: "1 kg", price: 52, mrp: 58, veg: true, art: "Jar", color: "#b8c7d2", label: "SUGAR", brand: "369 Mart Select" },
  { id: "s11", name: "Turmeric Powder 200 g", unit: "200 g", price: 69, mrp: 85, veg: true, art: "Jar", color: "#e8a317", label: "HALDI", brand: "Spice Coast" },
  { id: "s12", name: "Garam Masala 100 g", unit: "100 g", price: 89, mrp: 110, veg: true, art: "Jar", color: "#9b3d1f", label: "MASALA", brand: "Spice Coast" },
  { id: "s13", name: "California Almonds 500 g", unit: "500 g", price: 459, mrp: 599, veg: true, art: "Box", color: "#a8643a", brand: "Nutty Grove" },
  { id: "s14", name: "Cashews W320, 250 g", unit: "250 g", price: 299, mrp: 360, veg: true, art: "Pack", color: "#c9a36b", label: "CASHEW", brand: "Nutty Grove" },
  // snacks & beverages
  { id: "n1", name: "Milk Chocolate Bar 50 g", unit: "50 g", price: 49, mrp: 60, veg: true, art: "Bar", color: "#7a3e22", label: "MILK", brand: "Cocoa Lane" },
  { id: "n2", name: "Roasted Almond Chocolate 90 g", unit: "90 g", price: 129, mrp: 150, veg: true, art: "Bar", color: "#3b2a22", label: "NUTS", brand: "Cocoa Lane" },
  { id: "n3", name: "Filter Coffee Powder 500 g", unit: "500 g", price: 249, mrp: 300, veg: true, art: "Pack", color: "#5a2e1c", label: "FILTER", brand: "Nilgiri Estate" },
  { id: "n4", name: "Masala Chai 250 g", unit: "250 g", price: 149, mrp: 180, veg: true, art: "Pack", color: "#9b3d1f", label: "CHAI", brand: "Nilgiri Estate" },
  { id: "n5", name: "Butter Cookies 200 g", unit: "200 g", price: 89, mrp: 110, veg: true, art: "Box", color: "#d69a22", brand: "Oven Tales" },
  { id: "n6", name: "Digestive Biscuits 250 g", unit: "250 g", price: 65, mrp: 75, veg: true, art: "Pack", color: "#a35c24", label: "DIGEST", brand: "Oven Tales" },
  { id: "n7", name: "Cream Crackers 300 g", unit: "300 g", price: 55, veg: true, art: "Pack", color: "#2d6a8a", label: "CRACK", brand: "Oven Tales" },
  { id: "n8", name: "Mango Juice 1 L", unit: "1 L", price: 109, mrp: 125, veg: true, art: "Bottle", color: "#f28c1b", label: "MANGO", brand: "Orchard Pure" },
  { id: "n9", name: "Tender Coconut Water 200 ml", unit: "200 ml", price: 45, veg: true, art: "Bottle", color: "#7fae95", label: "COCO", brand: "Orchard Pure" },
  // personal care — bath soaps, body & hand wash, laundry bars
  { id: "p1", name: "Neem & Tulsi Herbal Soap 100 g", unit: "100 g", price: 38, mrp: 42, art: "Soap", color: "#2e7d4f", label: "NEEM", brand: "Leafline" },
  { id: "p2", name: "Neem & Tulsi Herbal Soap, Pack of 4", unit: "4 × 100 g", price: 145, mrp: 168, art: "Soap", color: "#256b43", label: "NEEM ×4", brand: "Leafline" },
  { id: "p3", name: "Neem Oil Soap 150 g", unit: "150 g", price: 62, mrp: 70, art: "Soap", color: "#3f8e2e", label: "NEEM OIL", brand: "Leafline" },
  { id: "p4", name: "Sandalwood Soap 75 g", unit: "75 g", price: 39, mrp: 45, art: "SoapBar", color: "#c98b4f", label: "SANDAL", brand: "Mysore Grove" },
  { id: "p5", name: "Turmeric & Saffron Glow Soap 125 g", unit: "125 g", price: 49, mrp: 55, art: "Soap", color: "#e39a1b", label: "HALDI", brand: "Kesari Naturals" },
  { id: "p6", name: "Ayurvedic 18-Herb Soap 125 g", unit: "125 g", price: 45, mrp: 52, art: "Soap", color: "#1f6b5a", label: "18 HERB", brand: "Vanaja Herbals" },
  { id: "p7", name: "Aloe Vera Moisture Soap 100 g", unit: "100 g", price: 35, art: "SoapBar", color: "#8fc79a", label: "ALOE", brand: "Kesari Naturals" },
  { id: "p8", name: "Rose Glycerine Soap 75 g", unit: "75 g", price: 42, mrp: 48, art: "SoapBar", color: "#e58aa0", label: "ROSE", brand: "Mysore Grove" },
  { id: "p9", name: "Charcoal Face & Body Soap 100 g", unit: "100 g", price: 55, mrp: 65, art: "Soap", color: "#2b3a42", label: "CHARCOAL", brand: "UrbanLeaf", stock: 0 },
  { id: "p10", name: "Neem Body Wash 250 ml", unit: "250 ml", price: 179, mrp: 210, art: "Bottle", color: "#2e7d4f", label: "NEEM", brand: "Leafline" },
  { id: "p11", name: "Handwash Refill Pouch 750 ml", unit: "750 ml", price: 99, mrp: 129, art: "Pack", color: "#0a78ab", label: "HAND", brand: "BrightWash" },
  { id: "p12", name: "Detergent Bar 250 g", unit: "250 g", price: 20, art: "Soap", color: "#1d5fb8", label: "WASH", brand: "BrightWash" },
  { id: "p13", name: "Detergent Powder 1 kg", unit: "1 kg", price: 95, mrp: 110, art: "Pack", color: "#1d5fb8", label: "WASH", brand: "BrightWash" },
  // personal care (Express)
  { id: "q1", name: "Neem & Aloe Herbal Soap Combo, Pack of 6", unit: "Pack of 6", price: 255, mrp: 330, art: "Soap", color: "#2e7d4f", label: "COMBO", brand: "Leafline", ...E() },
  { id: "q2", name: "Handmade Neem Soap with Scrub, Pack of 3", unit: "Pack of 3", price: 299, mrp: 399, art: "SoapBar", color: "#6f9a4a", label: "NEEM", brand: "Kesari Naturals", ...E("3–5 days") },
  { id: "q3", name: "Ayurvedic Bath Soap Gift Box, 5 Soaps", unit: "5 × 100 g", price: 449, mrp: 599, art: "Box", color: "#1f6b5a", brand: "Vanaja Herbals", ...E() },
  { id: "q4", name: "Neem & Turmeric Bathing Bar, Pack of 2", unit: "Pack of 2", price: 155, mrp: 199, art: "Soap", color: "#b7791f", label: "NEEM", brand: "UrbanLeaf", ...E() },
  { id: "q5", name: "Wooden Soap Dish, Set of 2", unit: "Set of 2", price: 199, mrp: 249, art: "Board", brand: "TerraLiving", ...E("3–5 days") },
  // electronics (Express)
  { id: "e1", name: "True Wireless Earbuds", unit: "AudioCore", price: 1999, mrp: 3499, art: "Headphones", color: "#2a86b8", ...E() },
  { id: "e2", name: "USB-C Flash Drive 128GB", unit: "DataVault", price: 899, mrp: 1299, art: "Ssd", color: "#0b4a6e", ...E() },
  { id: "e3", name: "20W USB-C Fast Charger", unit: "VoltEdge", price: 699, mrp: 999, art: "Charger", ...E() },
  { id: "e4", name: "Rechargeable Table Lamp", unit: "Lumen", price: 1499, mrp: 1999, art: "Lamp", color: "#2d6a8a", ...E("3–5 days") },
  // home & kitchen, stationery (Express)
  { id: "k1", name: "Steel Water Bottle 1 L", unit: "ThermaCore", price: 499, mrp: 699, art: "Flask", color: "#0a78ab", ...E() },
  { id: "k2", name: "Airtight Containers, Set of 6", unit: "TerraLiving", price: 799, mrp: 999, art: "Jar", color: "#9ec7de", label: "BOX", ...E("3–5 days") },
  { id: "o1", name: "Spiral Notebook A4, 200 pages", unit: "PaperNest", price: 149, mrp: 180, art: "Pack", color: "#1f8a3c", label: "A4", ...E() },
  { id: "o2", name: "Highlighters, Set of 5", unit: "PaperNest", price: 179, mrp: 220, art: "Pack", color: "#f7931e", label: "HIGH", ...E() },
].map((p) => ({ images: pics(p.id, p.stock === 0 ? 2 : 3), ...p }));

/* ---------------- pack-size variants ---------------- */
/* Each option is its own product (own id, price, stock) so the cart stays per size.
   Options that are not in SECTIONS/EXTRA_ITEMS are created here and hidden from listings. */
export const VARIANT_GROUPS = [
  { key: "atta", base: "d2", options: [
    { id: "d2v1", size: "1 kg", price: 89, mrp: 110, name: "Organic Whole Wheat Atta 1 kg" },
    { id: "d2", size: "5 kg" },
    { id: "d2v10", size: "10 kg", price: 689, mrp: 950, name: "Organic Whole Wheat Atta 10 kg" },
  ] },
  { key: "gnut", base: "d1", options: [
    { id: "d1", size: "1 L" },
    { id: "d1v5", size: "5 L", price: 1399, mrp: 1690, name: "Cold Pressed Groundnut Oil 5 L" },
  ] },
  { key: "coffee", base: "d3", options: [
    { id: "d3v250", size: "250 g", price: 349, mrp: 450, name: "Arabica Coffee Beans 250 g" },
    { id: "d3", size: "500 g" },
    { id: "d3v1k", size: "1 kg", price: 1199, mrp: 1650, name: "Arabica Coffee Beans 1 kg", low: 4 },
  ] },
  { key: "banana", base: "f2", options: [
    { id: "f2v500", size: "500 g", price: 39, name: "Robusta Banana 500 g" },
    { id: "f2", size: "1 kg" },
    { id: "f2v2", size: "2 kg", price: 129, mrp: 150, name: "Robusta Banana 2 kg" },
  ] },
  { key: "ssd", base: "t4", options: [
    { id: "t4v512", size: "512GB", price: 3999, mrp: 5499, name: "Portable SSD 512GB" },
    { id: "t4", size: "1TB" },
    { id: "t4v2", size: "2TB", price: 9999, mrp: 13499, name: "Portable SSD 2TB", stock: 0 },
  ] },
  { key: "towel", base: "h2", options: [
    { id: "h2v2", size: "Pack of 2", price: 499, mrp: 649, name: "Cotton Bath Towels, Pack of 2" },
    { id: "h2", size: "Pack of 4" },
    { id: "h2v8", size: "Pack of 8", price: 1599, mrp: 2099, name: "Cotton Bath Towels, Pack of 8" },
  ] },
];

/* ---------------- taxonomy ---------------- */
export const CATALOG = [
  { slug: "fruits-vegetables", name: "Fruits & Vegetables", mode: "quick", tone: "#e8f5e9", accent: "#1f7a4c",
    blurb: "Farm-fresh produce, picked daily", subs: [
      { slug: "fresh-fruits", name: "Fresh fruits", ids: ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "x1", "x3"] },
      { slug: "vegetables", name: "Vegetables", ids: ["v1", "v2", "v4", "v5"] },
      { slug: "leafy-herbs", name: "Leafy & herbs", ids: ["v3", "v6"] },
    ] },
  { slug: "staples", name: "Atta, Rice & Staples", mode: "quick", tone: "#fbf0e4", accent: "#a35c24",
    blurb: "Everything for your kitchen shelf", subs: [
      { slug: "atta-flours", name: "Atta, flours & sooji", ids: ["d2", "s1", "s2", "s3"] },
      { slug: "oils-ghee", name: "Oils & ghee", ids: ["d1", "s4", "s5", "s6"] },
      { slug: "rice-dals", name: "Rice & dals", ids: ["s7", "s8", "s9"] },
      { slug: "salt-sugar-spices", name: "Salt, sugar & spices", ids: ["d5", "s10", "s11", "s12"] },
      { slug: "dry-fruits", name: "Dry fruits & nuts", ids: ["d4", "s13", "s14"] },
    ] },
  { slug: "snacks-beverages", name: "Snacks & Beverages", mode: "quick", tone: "#f5ece6", accent: "#7a3e22",
    blurb: "Tea-time, treats and drinks", subs: [
      { slug: "chocolates", name: "Chocolates", ids: ["d6", "n1", "n2"] },
      { slug: "tea-coffee", name: "Tea & coffee", ids: ["d3", "d7", "n3", "n4"] },
      { slug: "biscuits", name: "Biscuits & cookies", ids: ["n5", "n6", "n7"] },
      { slug: "juices", name: "Juices & drinks", ids: ["n8", "n9"] },
    ] },
  { slug: "personal-care", name: "Personal Care", mode: "quick", tone: "#e9f5ee", accent: "#23704a",
    blurb: "Bath, body and laundry essentials", subs: [
      { slug: "bath-soaps", name: "Bath soaps", ids: ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9"] },
      { slug: "body-hand-wash", name: "Body & hand wash", ids: ["p10", "p11"] },
      { slug: "laundry", name: "Laundry", ids: ["p12", "p13"] },
      { slug: "soap-combos", name: "Soap combos & gift packs", ids: ["q1", "q2", "q3", "q4", "q5"] },
    ] },
  { slug: "electronics", name: "Electronics", mode: "all", tone: "#e6f2f9", accent: "#0b4a6e",
    blurb: "Audio, storage, chargers and more", subs: [
      { slug: "audio", name: "Audio", ids: ["t1", "t2", "a2", "a4", "e1"] },
      { slug: "storage", name: "Storage", ids: ["t4", "a1", "e2"] },
      { slug: "chargers", name: "Chargers", ids: ["t3", "a5", "e3"] },
      { slug: "webcams", name: "Webcams", ids: ["t5", "a3"] },
      { slug: "lighting", name: "Lighting", ids: ["t6", "a6", "e4"] },
    ] },
  { slug: "home-kitchen", name: "Home & Kitchen", mode: "all", tone: "#fbefe6", accent: "#b85a1c",
    blurb: "Dinnerware, linen, storage and more", subs: [
      { slug: "dinnerware", name: "Dinnerware", ids: ["h1", "b1"] },
      { slug: "bath-linen", name: "Bath linen", ids: ["h2", "b2"] },
      { slug: "bottles-flasks", name: "Bottles & flasks", ids: ["h3", "b4", "k1"] },
      { slug: "storage", name: "Storage & baskets", ids: ["h5", "b3", "k2"] },
      { slug: "serveware", name: "Boards & serveware", ids: ["h4", "b5"] },
    ] },
  { slug: "stationery", name: "Stationery", mode: "all", tone: "#fff1e2", accent: "#c2520c",
    blurb: "For school, office and home desks", subs: [
      { slug: "notebooks", name: "Notebooks", ids: ["c1", "o1"] },
      { slug: "pens", name: "Pens & markers", ids: ["c2", "c4", "o2"] },
      { slug: "desk", name: "Desk organisers", ids: ["c3"] },
    ] },
  { slug: "fashion", name: "Fashion", mode: "all", tone: "#f3eefb", accent: "#6a3fb5", blurb: "Launching soon on 369 Mart", subs: [] },
  { slug: "books", name: "Books", mode: "all", tone: "#eef4ee", accent: "#2f6b3f", blurb: "Launching soon on 369 Mart", subs: [] },
];

/* header tab / home tile / rail → category */
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

/* ---------------- build the product index ---------------- */
export function buildIndex() {
  const byId = {};
  [...SECTIONS, ...ALL_SECTIONS].forEach((s) => (s.items || []).forEach((p) => { byId[p.id] = { ...p }; }));
  EXTRA_ITEMS.forEach((p) => { byId[p.id] = { ...p }; });

  /* category / subcategory on every product */
  CATALOG.forEach((c) => c.subs.forEach((sub) => sub.ids.forEach((id) => {
    if (byId[id]) Object.assign(byId[id], { cat: c.slug, catName: c.name, sub: sub.slug, subName: sub.name });
  })));

  /* brand before variants, so a "512GB" size never becomes the brand */
  Object.values(byId).forEach((p) => { p.brand = p.brand || (p.veg ? "369 Mart Select" : p.unit); });

  /* variants */
  VARIANT_GROUPS.forEach((g) => {
    const base = byId[g.base];
    if (!base) return;
    g.options.forEach((o) => {
      const cur = byId[o.id] || { ...base, id: o.id, hidden: true, images: base.images };
      Object.assign(cur, { name: o.name || cur.name, unit: o.id === g.base ? cur.unit : o.size, price: o.price ?? cur.price, mrp: o.mrp ?? cur.mrp,
        stock: o.stock ?? (o.id === g.base ? cur.stock : undefined), low: o.low ?? (o.id === g.base ? cur.low : undefined),
        variantGroup: g.key, size: o.size });
      byId[o.id] = cur;
    });
  });

  Object.values(byId).forEach(enrich);
  return byId;
}

/* fields the listing filters and sorts on; safe to call on products from your API */
export function enrich(p) {
  p.brand = p.brand || (p.veg ? "369 Mart Select" : p.unit || "369 Mart");
  p.off = p.mrp ? Math.round(((p.mrp - p.price) / p.mrp) * 100) : 0;
  const h = [...String(p.id)].reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) >>> 0, 7);
  p.rating = p.rating ?? Math.round((3.8 + (h % 12) / 10) * 10) / 10;
  p.popularity = p.popularity ?? h % 1000;
  return p;
}

export const variantsOf = (p, byId) => {
  const g = VARIANT_GROUPS.find((x) => x.key === p.variantGroup);
  return g ? g.options.map((o) => byId[o.id]).filter(Boolean) : [];
};

export const categoryBySlug = (slug) => CATALOG.find((c) => c.slug === slug);
export const listable = (byId) => Object.values(byId).filter((p) => !p.hidden);
