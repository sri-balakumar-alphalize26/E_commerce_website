/* ==========================================================================
   369 Mart — order lifecycle helpers (status, rider, OTP, return window).
   Where an order is, and when each step happened, is the shop's answer: it
   comes from sale.order's own state and its stamps. This file used to run a
   clock instead - an order placed in the app walked itself to "delivered" in
   about a hundred seconds so every screen could be seen without a warehouse.
   That was worth having and is worth losing: an order now sits at "placed"
   for exactly as long as it really is.
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

export const RETURN_STEPS = [
  { key: "requested", label: "Return requested" },
  { key: "pickup", label: "Pickup scheduled" },
  { key: "picked", label: "Picked up" },
  { key: "done", label: "Refund issued" },
];
export const RETURN_DAYS = 7;

const hash = (s) => [...String(s)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

const STATUS_INDEX = { placed: 0, packed: 1, shipped: 1, out: 2, delivered: 3 };

/* Where an order is, and when it got there.

   `times` is one timestamp per step, from the order's own stamps, with a hole
   where a step has not happened. `progress` is how far along the current step
   to draw the map: the shop stamps steps, it does not report fractions, so
   this is the step itself rather than a guess at how far into it we are. */
export function liveStatus(o) {
  const mode = o.mode === "all" ? "all" : "quick";
  const steps = STEPS[mode];
  if (o.status === "cancelled") {
    return { mode, steps, idx: -1, key: "cancelled", progress: 0, times: [o.at || null] };
  }
  const idx = STATUS_INDEX[o.status] ?? 0;
  const stamped = {};
  for (const stamp of o.timeline || []) {
    const at = STATUS_INDEX[stamp.state];
    if (at !== undefined && stamp.at) stamped[at] = stamp.at;
  }
  if (stamped[0] === undefined && o.at) stamped[0] = o.at;
  const times = steps.map((__, i) => stamped[i] ?? null);
  return { mode, steps, idx, key: steps[idx].key, progress: idx >= 3 ? 1 : idx === 2 ? 0.55 : 0, times };
}

/* A return is the shop's record too: its state is the step it is on. */
export function returnStatus(ret) {
  if (!ret) return null;
  if (ret.state === "refused") return { idx: 0, key: "refused", refused: true };
  const idx = Math.max(0, RETURN_STEPS.findIndex((x) => x.key === (ret.state || "requested")));
  return { idx, key: RETURN_STEPS[idx].key };
}

const RIDERS = [
  { name: "Arjun K.", vehicle: "KL 07 CX 4821", rating: 4.9, trips: "2.1k" },
  { name: "Faizal M.", vehicle: "KL 43 B 1190", rating: 4.8, trips: "1.4k" },
  { name: "Vishnu R.", vehicle: "KL 01 AZ 7302", rating: 4.9, trips: "3.0k" },
  { name: "Suresh P.", vehicle: "KL 02 H 5518", rating: 4.7, trips: "980" },
];
export const riderFor = (o) => RIDERS[hash(o.id) % RIDERS.length];

/* The delivery code used to be worked out here, from a hash of the order id.
   Anyone holding an order number could work out the code for that doorstep
   without ever seeing the order, which is the whole thing the code exists to
   stop. It comes from the shop now, on the order itself, and only the
   customer who owns that order is ever sent it. Empty once it is spent. */

/* Both are the shop's call. `canCancel` comes straight off the order; the
   return window is the one rule the page still applies itself, because it is
   about what to offer rather than what to allow - the route refuses anything
   it should not accept. */
export const cancellable = (o, s) => (o.canCancel ?? (s.key === "placed")) && o.status !== "cancelled";
export const returnable = (o, s, now = Date.now()) =>
  s.key === "delivered" && !(o.returns || []).length &&
  (!s.times[3] || now - s.times[3] < RETURN_DAYS * 864e5);

/* "Today, 4:05 pm". The order carries the shop's own rendering of this too,
   but in the shop's timezone - printed beside a stamp the browser formats,
   the same moment shows up as two different times. One clock wins, and it is
   the reader's. */
export const fmtPlaced = (ts) => {
  if (!ts) return "";
  const d = new Date(ts);
  const time = d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }).toLowerCase();
  const day = new Date(d); day.setHours(0, 0, 0, 0);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const off = Math.round((today - day) / 864e5);
  if (off === 0) return `Today, ${time}`;
  if (off === 1) return `Yesterday, ${time}`;
  return `${d.getDate()} ${d.toLocaleDateString("en-IN", { month: "short" })}, ${time}`;
};

export const fmtTime = (ts) => (ts ? new Date(ts).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }) : "");
export const fmtDay = (ts, add = 0) => { const d = new Date(ts || Date.now()); d.setDate(d.getDate() + add); return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" }); };
