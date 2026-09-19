/* ==========================================================================
   369 Mart — admin demo data.
   Deterministic (seeded) so server and client render the same HTML.
   Every export maps to an Odoo model — see README "Admin".
   ========================================================================== */
import { enrich } from "../home/catalog";

/* The drop was written against `buildIndex()` — the storefront's old sample
   catalogue, which this project deleted when the shop started reading real
   products from Odoo. It is not coming back, and reviving it would put a
   second, invented product list next to the real one.

   So the sample screens carry their own handful of products, here, where it
   is obvious what they are. This whole file goes when Phase B wires the last
   section; nothing outside components/admin/ may import it. */
const SAMPLE = [
  ["s1", "NVMe SSD 1TB", "1 TB · M.2", 5499, 6999, "SSD", "Storage"],
  ["s2", "DDR5 RAM 16GB", "16 GB · 5600MHz", 3899, 4799, "RAM", "Components"],
  ["s3", "Mechanical keyboard", "87 keys · brown", 2999, 3999, "Keyboard", "Peripherals"],
  ["s4", "Wireless mouse", "2.4GHz · silent", 899, 1299, "Mouse", "Peripherals"],
  ["s5", "27\" IPS monitor", "1440p · 165Hz", 18999, 22999, "Monitor", "Displays", true],
  ["s6", "Wi-Fi 6 router", "AX3000 · dual band", 4299, 5499, "Router", "Networking", true],
  ["s7", "USB-C cable 2m", "100W · braided", 499, 799, "Cable", "Accessories"],
  ["s8", "Laptop stand", "aluminium", 1499, 1999, "Stand", "Accessories", true],
  ["s9", "GPU RTX 4060", "8 GB GDDR6", 30999, 34999, "GPU", "Components", true],
  ["s10", "650W PSU", "80+ gold", 5999, 7499, "PSU", "Components", true],
  ["s11", "CPU cooler", "120mm tower", 2199, 2899, "Cooler", "Components"],
  ["s12", "Webcam 1080p", "auto focus", 2499, 3199, "Webcam", "Peripherals", true],
];
const buildIndex = () => Object.fromEntries(SAMPLE.map(
  ([id, name, unit, price, mrp, art, cat, delivery]) =>
    [id, { id, name, unit, price, mrp, art, cat, delivery: delivery ? "In 2 days" : "" }]));

/* Fixed "now" for the demo, in IST, so numbers never drift between the server
   (which may run in UTC) and the browser. All formatting is pinned to IST for
   the same reason — a hydration mismatch here shows up as React error #418. */
const HOUR = 3600000, DAY = 86400000, IST = 5.5 * HOUR;
export const TZ = "Asia/Kolkata";
export const TODAY = Date.UTC(2026, 8, 19, 10, 10); /* 19 Sep 2026, 3:40 pm IST */
const ist = (t) => new Date(t + IST);               /* read with getUTC* to stay in IST */
export const istMidnight = (t) => Math.floor((t + IST) / DAY) * DAY - IST;
export const istHour = (t) => ist(t).getUTCHours();

/* small deterministic PRNG */
function rng(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

export const byId = (() => { const m = buildIndex(); Object.keys(m).forEach((k) => (m[k] = enrich(m[k]))); return m; })();
export const PRODUCTS = Object.values(byId).filter((p) => p && p.name && p.price && !p.hidden);

export const AREAS = ["Kadavanthra", "Palarivattom", "Edappally", "Vyttila", "Panampilly Nagar", "Kakkanad", "Fort Kochi", "Thevara"];
export const CUSTOMER_NAMES = [
  "Anu Rajan", "Rahul Menon", "Fathima Sherin", "Vinod Nair", "Meera Krishnan", "Joseph Thomas", "Sneha Pillai", "Arun Kumar",
  "Divya Suresh", "Nikhil Varma", "Asha George", "Praveen Das", "Lakshmi Iyer", "Sameer Ali", "Reshma Babu", "Tony Mathew",
];
export const RIDERS = [
  { id: "r1", name: "Ajith P", vehicle: "KL 07 BX 4412", phone: "+91 98470 11223", rating: 4.9, trips: 1284, shift: "9 am – 6 pm" },
  { id: "r2", name: "Sujith M", vehicle: "KL 07 CH 9087", phone: "+91 98470 33445", rating: 4.8, trips: 962, shift: "9 am – 6 pm" },
  { id: "r3", name: "Ramesh K", vehicle: "KL 43 AA 2210", phone: "+91 98470 55667", rating: 4.7, trips: 730, shift: "12 pm – 9 pm" },
  { id: "r4", name: "Nisha V", vehicle: "KL 07 DK 1198", phone: "+91 98470 77889", rating: 4.9, trips: 1503, shift: "12 pm – 9 pm" },
  { id: "r5", name: "Bilal S", vehicle: "KL 07 EF 3321", phone: "+91 98470 99001", rating: 4.6, trips: 415, shift: "6 pm – 11 pm" },
];

export const STATUS = {
  new: { label: "New", tone: "blue" },
  packing: { label: "Packing", tone: "amber" },
  ready: { label: "Ready", tone: "violet" },
  out: { label: "Out for delivery", tone: "orange" },
  delivered: { label: "Delivered", tone: "green" },
  cancelled: { label: "Cancelled", tone: "red" },
};
export const FLOW = ["new", "packing", "ready", "out", "delivered"];
export const NEXT_LABEL = { new: "Start packing", packing: "Mark ready", ready: "Send out", out: "Mark delivered" };

const PAYS = ["UPI · Google Pay", "UPI · PhonePe", "Card •••• 4821", "Cash on delivery", "369 Wallet"];

function makeOrder(r, i, at, status) {
  const mode = r() > 0.32 ? "quick" : "all";
  const pool = PRODUCTS.filter((p) => (mode === "all" ? p.delivery : !p.delivery));
  /* The sample list is short; never index into an empty pool. */
  if (!pool.length) pool.push(...PRODUCTS);
  const n = 1 + Math.floor(r() * (mode === "quick" ? 5 : 2));
  const items = [];
  for (let k = 0; k < n; k++) {
    const p = pool[Math.floor(r() * pool.length)];
    if (!p || items.some((x) => x.id === p.id)) continue;
    items.push({ id: p.id, name: p.name, unit: p.unit, price: p.price, qty: 1 + Math.floor(r() * 2) });
  }
  const sub = items.reduce((s, l) => s + l.price * l.qty, 0);
  const fee = mode === "quick" ? (sub < 499 ? 30 : 0) : sub < 999 ? 49 : 0;
  const name = CUSTOMER_NAMES[Math.floor(r() * CUSTOMER_NAMES.length)];
  const rider = status === "out" || status === "delivered" ? RIDERS[Math.floor(r() * RIDERS.length)] : null;
  return {
    id: `${mode === "quick" ? "369M" : "369E"}-${String(100000 + Math.floor(r() * 899999))}`,
    at, mode, status, items, sub, fee, total: sub + fee,
    pay: PAYS[Math.floor(r() * PAYS.length)],
    customer: { name, phone: "+91 9" + String(400000000 + Math.floor(r() * 99999999)), area: AREAS[Math.floor(r() * AREAS.length)], orders: 1 + Math.floor(r() * 24) },
    rider: rider && { id: rider.id, name: rider.name },
    eta: mode === "quick" ? 8 + Math.floor(r() * 14) : null,
    slot: mode === "quick" ? "Next 20 min" : "Tomorrow, 9 am – 1 pm",
    note: r() > 0.86 ? "Leave at the door, don't ring the bell" : "",
  };
}

/* ~350 orders across the last 14 days, 28 of them today (7 live) */
export const ORDERS = (() => {
  const r = rng(36919);
  const list = [];
  for (let d = 13; d >= 1; d--) {
    const count = 22 + Math.floor(r() * 10);
    for (let i = 0; i < count; i++) {
      const at = istMidnight(TODAY - d * DAY) + (9 + Math.floor(r() * 12)) * HOUR + Math.floor(r() * 59) * 60000;
      list.push(makeOrder(r, i, at, r() > 0.06 ? "delivered" : "cancelled"));
    }
  }
  const live = ["new", "new", "packing", "ready", "out", "out", "packing"];
  for (let i = 0; i < 28; i++) {
    const done = i >= live.length;
    const at = done ? TODAY - (2 + Math.floor(r() * 7)) * HOUR : TODAY - Math.floor(r() * 46) * 60000;
    list.push(makeOrder(r, i, at, done ? (r() > 0.05 ? "delivered" : "cancelled") : live[i]));
  }
  return list.sort((a, b) => b.at - a.at);
})();

export const isToday = (t) => istMidnight(t) === istMidnight(TODAY);
export const LIVE = ORDERS.filter((o) => ["new", "packing", "ready", "out"].includes(o.status));

/* ---------- series for the charts ---------- */
export const revenueSeries = () => {
  const days = [];
  for (let d = 13; d >= 0; d--) {
    const from = istMidnight(TODAY - d * DAY);
    const to = from + DAY;
    const rows = ORDERS.filter((o) => o.at >= from && o.at < to && o.status !== "cancelled");
    days.push({
      label: dateShort(from),
      short: String(ist(from).getUTCDate()),
      quick: rows.filter((o) => o.mode === "quick").reduce((s, o) => s + o.total, 0),
      express: rows.filter((o) => o.mode === "all").reduce((s, o) => s + o.total, 0),
      orders: rows.length,
    });
  }
  return days;
};

export const hourlyOrders = () => {
  const out = [];
  for (let h = 7; h <= 22; h++) {
    const rows = ORDERS.filter((o) => isToday(o.at) && istHour(o.at) === h);
    out.push({ label: `${h % 12 || 12}${h < 12 ? "a" : "p"}`, full: `${h % 12 || 12} ${h < 12 ? "am" : "pm"}`, value: rows.length });
  }
  return out;
};

export const categorySales = () => {
  const map = {};
  ORDERS.filter((o) => o.status !== "cancelled" && o.at > TODAY - 7 * DAY).forEach((o) =>
    o.items.forEach((l) => {
      const p = byId[l.id];
      const cat = (p && (p.catName || p.subName)) || (p && p.delivery ? "Express" : "Grocery");
      map[cat] = (map[cat] || 0) + l.price * l.qty;
    })
  );
  return Object.entries(map).map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value).slice(0, 6);
};

/* ---------- stock, customers, coupons, reviews ---------- */
export const STOCK = (() => {
  const r = rng(771);
  return PRODUCTS.slice(0, 64).map((p) => {
    const sold = Math.floor(r() * 40);
    const qty = r() > 0.93 ? 0 : Math.max(2, Math.round(r() * 70) - (r() > 0.78 ? 58 : 0));
    return { id: p.id, name: p.name, unit: p.unit, price: p.price, mrp: p.mrp || p.price, image: p.image, images: p.images, art: p.art, color: p.color, label: p.label, delivery: !!p.delivery, cat: p.catName || p.subName || "Grocery", qty, sold7: sold, active: r() > 0.05, reorder: 12 };
  });
})();

export const CUSTOMERS = (() => {
  const r = rng(4242);
  return CUSTOMER_NAMES.map((name, i) => {
    const orders = ORDERS.filter((o) => o.customer.name === name);
    const spent = orders.reduce((s, o) => s + (o.status === "cancelled" ? 0 : o.total), 0);
    const last = orders[0]?.at || TODAY - (10 + Math.floor(r() * 80)) * DAY;
    const joined = TODAY - (3 + Math.floor(r() * 400)) * DAY;
    const status = TODAY - joined < 7 * DAY ? "New" : TODAY - last > 45 * DAY ? "Dormant" : "Active";
    return {
      id: "c" + (i + 1), name, email: name.toLowerCase().replace(/\s+/g, ".") + "@example.com",
      phone: "+91 9" + String(400000000 + Math.floor(r() * 99999999)), area: AREAS[i % AREAS.length],
      orders: orders.length, spent, last, joined, status, wallet: Math.floor(r() * 6) * 50,
    };
  }).sort((a, b) => b.spent - a.spent);
})();

export const COUPONS = [
  { code: "QUICK20", title: "20% off on Quick orders", note: "Up to ₹60 · Quick items above ₹199", used: 342, cap: 500, active: true, ends: "30 Sep 2026" },
  { code: "WELCOME50", title: "Flat ₹50 off", note: "First order above ₹499", used: 189, cap: 1000, active: true, ends: "31 Dec 2026" },
  { code: "FREEDEL", title: "Free delivery", note: "Orders above ₹299", used: 764, cap: 800, active: true, ends: "22 Sep 2026" },
  { code: "ONAM25", title: "25% off staples", note: "Atta, rice and oils · max ₹150", used: 1200, cap: 1200, active: false, ends: "Ended 14 Sep 2026" },
];

export const REVIEWS = (() => {
  const r = rng(99);
  const texts = [
    ["Fresh and neatly packed", "Arrived cold within 15 minutes. Will order again."],
    ["Good quality", "Bananas were slightly ripe but fine for the price."],
    ["Delivery was late", "Took 45 minutes instead of 20. Products were fine."],
    ["Packaging damaged", "Oil bottle had leaked into the bag."],
    ["Great value", "Cheaper than the shop near my house and faster too."],
    ["Wrong item sent", "Ordered 1 kg atta, received 500 g."],
  ];
  return texts.map((t, i) => {
    const p = PRODUCTS[Math.floor(r() * PRODUCTS.length)];
    return { id: "rv" + i, product: p.name, productId: p.id, stars: [5, 4, 2, 2, 5, 1][i], title: t[0], text: t[1], by: CUSTOMER_NAMES[i], at: TODAY - (i + 1) * 9 * HOUR, state: i < 4 ? "pending" : "published" };
  });
})();

export const SETTINGS = {
  store: { name: "369 Mart · Kochi hub", phone: "+91 484 400 3690", email: "hub.kochi@369mart.in", address: "Door 14/220, Kadavanthra, Kochi 682020", gstin: "32AAZCA2582P1ZW", open: "07:00", close: "23:00" },
  quick: { min: 99, fee: 30, freeAbove: 499, radius: 4, slots: 6, eta: "10–20 min" },
  express: { min: 0, fee: 49, freeAbove: 999, radius: 0, slots: 3, eta: "2–5 days" },
  pay: { upi: true, card: true, netbanking: true, cod: true, wallet: true, codLimit: 5000 },
  alerts: { lowStock: true, newOrder: true, cancelled: true, dailySummary: true },
};

/* ---------- helpers ----------
   Formatted by hand, not with toLocaleString: Node and the browser disagree on
   some en-IN output ("Sept" vs "Sep"), which React reports as a hydration
   mismatch (error #418). */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
export const groupIN = (n) => {
  const s = String(Math.abs(Math.round(n)));
  if (s.length <= 3) return (n < 0 ? "-" : "") + s;
  const last3 = s.slice(-3);
  const rest = s.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return (n < 0 ? "-" : "") + rest + "," + last3;
};
export const inr = (n) => "₹" + groupIN(n);
export const inrShort = (n) => (n >= 100000 ? "₹" + (n / 100000).toFixed(1) + "L" : n >= 1000 ? "₹" + (n / 1000).toFixed(1) + "k" : "₹" + Math.round(n));
export const clock = (t) => {
  const d = new Date(t + IST), h = d.getUTCHours(), m = d.getUTCMinutes();
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`;
};
export const dateShort = (t) => { const d = new Date(t + IST); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`; };
export const dateLong = (t) => { const d = new Date(t + IST); return `${WEEKDAYS[d.getUTCDay()]}, ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
export const dateTime = (t) => `${dateShort(t)}, ${clock(t)}`;
export const since = (t, now = TODAY) => {
  const m = Math.max(0, Math.round((now - t) / 60000));
  return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.floor(m / 60)} h ago` : `${Math.floor(m / 1440)} d ago`;
};
export const initials = (n) => n.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
