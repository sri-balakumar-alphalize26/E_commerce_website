/* ==========================================================================
   369 Mart — order lifecycle helpers (status, rider, OTP, return window).
   Demo: orders placed in this app move on their own on a fast clock so every
   screen can be seen; "Skip ahead (demo)" jumps to the next step. In
   production read status, rider and events from Odoo (sale.order +
   stock.picking + your delivery app) and drop the timers.
   ========================================================================== */

export const STEPS = {
  quick: [
    { key: "placed", label: "Order placed", sub: "We've received your order" },
    { key: "packed", label: "Packed", sub: "Your items are packed at the store" },
    { key: "out", label: "Out for delivery", sub: "Your rider is on the way" },
    { key: "delivered", label: "Delivered", sub: "Enjoy your order" },
  ],
  all: [
    { key: "placed", label: "Order placed", sub: "Seller is preparing your order" },
    { key: "shipped", label: "Shipped", sub: "Handed to our delivery partner" },
    { key: "out", label: "Out for delivery", sub: "Arriving today" },
    { key: "delivered", label: "Delivered", sub: "Enjoy your order" },
  ],
};

/* demo step lengths in ms (placed → next, next → next, …) */
export const DEMO_MS = { quick: [18000, 22000, 60000], all: [25000, 40000, 45000] };
export const RETURN_STEPS = [
  { key: "requested", label: "Return requested" },
  { key: "pickup", label: "Pickup scheduled" },
  { key: "picked", label: "Picked up" },
  { key: "done", label: "Refund issued" },
];
const RETURN_MS = [12000, 20000, 25000];
export const QUICK_ETA_MIN = 12;
export const RETURN_DAYS = 7;

const hash = (s) => [...String(s)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

const STATUS_INDEX = { placed: 0, packed: 1, shipped: 1, out: 2, delivered: 3 };

/* where an order is right now */
export function liveStatus(o, now = Date.now(), base = o.at) {
  const mode = o.mode === "all" ? "all" : "quick";
  const steps = STEPS[mode];
  if (o.status === "cancelled") return { mode, steps, idx: -1, key: "cancelled", progress: 0, times: [o.at || null], etaMin: 0 };
  if (!base) {
    const idx = STATUS_INDEX[o.status] ?? 0;
    return { mode, steps, idx, key: steps[idx].key, progress: idx === 2 ? 0.55 : idx > 2 ? 1 : 0, times: [], etaMin: idx === 2 ? 6 : 0, static: true };
  }
  const t = now - base + (o.skip || 0);
  const ms = DEMO_MS[mode];
  let acc = 0, idx = 0;
  const times = [base];
  for (let i = 0; i < ms.length; i++) {
    if (t >= acc + ms[i]) { acc += ms[i]; idx = i + 1; times.push(base + acc - (o.skip || 0)); } else break;
  }
  const progress = idx >= 3 ? 1 : Math.min(1, (t - acc) / ms[idx]);
  const etaMin = mode !== "quick" || idx >= 3 ? 0 : idx < 2 ? Math.ceil(QUICK_ETA_MIN - (idx + progress) * 2) : Math.max(1, Math.ceil(8 * (1 - progress)));
  return { mode, steps, idx, key: steps[idx].key, progress, times, etaMin, nextIn: idx < 3 ? acc + ms[idx] - t : 0 };
}

/* ms to add to o.skip to reach the next step */
export function skipAmount(o, now = Date.now(), base = o.at) {
  const s = liveStatus(o, now, base);
  return s.nextIn ? s.nextIn + 50 : 0;
}

export function returnStatus(ret, now = Date.now()) {
  if (!ret) return null;
  const t = now - ret.at + (ret.skip || 0);
  let acc = 0, idx = 0;
  for (let i = 0; i < RETURN_MS.length; i++) { if (t >= acc + RETURN_MS[i]) { acc += RETURN_MS[i]; idx = i + 1; } else break; }
  return { idx, key: RETURN_STEPS[idx].key, nextIn: idx < 3 ? acc + RETURN_MS[idx] - t : 0 };
}

const RIDERS = [
  { name: "Arjun K.", vehicle: "KL 07 CX 4821", rating: 4.9, trips: "2.1k" },
  { name: "Faizal M.", vehicle: "KL 43 B 1190", rating: 4.8, trips: "1.4k" },
  { name: "Vishnu R.", vehicle: "KL 01 AZ 7302", rating: 4.9, trips: "3.0k" },
  { name: "Suresh P.", vehicle: "KL 02 H 5518", rating: 4.7, trips: "980" },
];
export const riderFor = (o) => RIDERS[hash(o.id) % RIDERS.length];
export const deliveryOtp = (o) => String(1000 + (hash(o.id + "otp") % 9000));

export const cancellable = (o, s) => s.key === "placed" && o.status !== "cancelled";
export const returnable = (o, s, now = Date.now()) =>
  s.key === "delivered" && !o.ret && (!s.times[3] || now - s.times[3] < RETURN_DAYS * 864e5);

export const fmtTime = (ts) => (ts ? new Date(ts).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }) : "");
export const fmtDay = (ts, add = 0) => { const d = new Date(ts || Date.now()); d.setDate(d.getDate() + add); return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" }); };
