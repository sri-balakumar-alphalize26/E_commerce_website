/* ==========================================================================
   369 Mart — account extras data (wallet log, saved payments, rewards,
   reviews, notifications, referrals). Demo data lives in localStorage; in
   production each key maps to an Odoo endpoint (see README "Account extras").
   ========================================================================== */
import { useCallback, useEffect, useState } from "react";

export const KEYS = {
  walletLog: "369mart.walletLog",
  payments: "369mart.payments",
  rewards: "369mart.rewards",
  reviews: "369mart.reviews",
  notifs: "369mart.notifs",
  notifPrefs: "369mart.notifPrefs",
  referrals: "369mart.referrals",
};

export const WALLET_LIMIT = 10000;

export function load(key, fallback) {
  try { const v = JSON.parse(localStorage.getItem(key) || "null"); return v ?? fallback; } catch (e) { return fallback; }
}
export function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("369mart:store", { detail: key }));
}

/* state that starts from the seed on the server and loads the saved copy after
   mount (no hydration mismatch); every tab/component using the key stays in sync */
export function useStored(key, seed) {
  const [value, setValue] = useState(seed);
  useEffect(() => {
    setValue(load(key, seed));
    const on = (e) => { if (e.detail === key) setValue(load(key, seed)); };
    window.addEventListener("369mart:store", on);
    return () => window.removeEventListener("369mart:store", on);
  }, [key]); // eslint-disable-line
  const set = useCallback((next) => {
    setValue((cur) => {
      const v = typeof next === "function" ? next(cur) : next;
      try { localStorage.setItem(key, JSON.stringify(v)); } catch (e) {}
      queueMicrotask(() => window.dispatchEvent(new CustomEvent("369mart:store", { detail: key })));
      return v;
    });
  }, [key]);
  return [value, set];
}

const day = (d, h = 10, m = 0) => new Date(2026, 8, d, h, m).getTime();

/* ---------- wallet ----------
   kind: add | spend | refund | reward   (seed entries add up to WALLET_BALANCE) */
export const SEED_WALLET_LOG = [
  { id: "w3", kind: "reward", amount: 50, title: "Scratch card reward", sub: "From order #369M-24090931", at: day(10, 9, 12) },
  { id: "w2", kind: "reward", amount: 100, title: "Referral reward", sub: "Anu R. placed her first order", at: day(6, 18, 40) },
  { id: "w1", kind: "add", amount: 100, title: "Welcome bonus", sub: "Added when you joined 369 Mart", at: day(1, 11, 5) },
];
export function logWallet(entry) {
  const list = load(KEYS.walletLog, SEED_WALLET_LOG);
  save(KEYS.walletLog, [{ id: "w" + Date.now(), at: Date.now(), ...entry }, ...list].slice(0, 200));
}

/* ---------- saved payments ---------- */
export const SEED_PAYMENTS = {
  cards: [
    { id: "c4821", brand: "visa", last4: "4821", name: "Demo User", exp: "08/29", bank: "HDFC Bank", default: true },
    { id: "c7390", brand: "rupay", last4: "7390", name: "Demo User", exp: "03/28", bank: "State Bank of India" },
  ],
  upis: [
    { id: "u1", vpa: "demo@okaxis", name: "Demo User", app: "gpay", default: true },
  ],
};

/* ---------- rewards ---------- */
export const SEED_REWARDS = {
  scratch: [
    { id: "s1", from: "Order #369M-24091612", reward: { type: "cash", amount: 25 }, scratched: false, at: day(16, 11, 50) },
    { id: "s2", from: "Order #369E-24091408", reward: { type: "coupon", code: "FREEDEL", title: "Free delivery" }, scratched: false, at: day(14, 16, 5) },
    { id: "s3", from: "Order #369M-24090931", reward: { type: "cash", amount: 50 }, scratched: true, at: day(9, 19, 30) },
    { id: "s4", from: "Referral · Rahul M.", reward: { type: "none" }, scratched: true, at: day(8, 12, 0) },
  ],
  won: [],
};

/* ---------- reviews (by product id) ---------- */
export const SEED_REVIEWS = {
  d2: { stars: 5, title: "Fresh and well packed", text: "Arrived cold within 15 minutes. Will order again.", tags: ["Fresh", "Well packed"], at: day(10, 8, 30), helpful: 4 },
};
export const STAR_WORDS = ["", "Terrible", "Bad", "Okay", "Good", "Excellent"];

/* ---------- notifications ---------- */
export const SEED_NOTIFS = [
  { id: "n-offer-1", type: "offer", title: "Weekend grocery sale is live", text: "Up to 40% off on fruits, vegetables and staples. Ends Sunday midnight.", at: day(16, 8, 0), go: ["offers"] },
  { id: "n-reward-1", type: "wallet", title: "You won a scratch card", text: "Scratch it to reveal cashback or a coupon.", at: day(16, 12, 5), go: ["account", "rewards"] },
  { id: "n-ref-1", type: "wallet", title: "₹100 referral reward added", text: "Anu R. placed her first order. The reward is in your 369 Wallet.", at: day(6, 18, 41), go: ["account", "wallet"] },
  { id: "n-offer-2", type: "offer", title: "Price drop on an item in your list", text: "Items saved in My List are cheaper today. Take a look before stock runs out.", at: day(12, 9, 30), go: ["account", "list"] },
];
export const SEED_NOTIF_STATE = { read: ["n-ref-1", "n-offer-2"], dismissed: [] };
export const SEED_PREFS = { orders: true, offers: true, wallet: true, whatsapp: true, email: false, sms: true };

/* order updates are generated from the orders list, so they follow live status */
export function orderNotifs(orders) {
  const out = [];
  orders.forEach((o) => {
    const when = o.at || (/^today/i.test(o.placed || "") ? Date.now() - 25 * 60000 : Date.parse(o.placed)) || day(9);
    if (o.status === "out") out.push({ id: `n-${o.id}-out`, type: "order", title: "Your order is on the way", text: `Order #${o.id} is out for delivery${o.eta ? ` · arriving in ${o.eta}` : ""}.`, at: when + 60000 * 6, go: ["track", o.id] });
    else if (o.status === "shipped") out.push({ id: `n-${o.id}-shipped`, type: "order", title: "Order shipped", text: `Order #${o.id} has left the warehouse. ${o.eta || ""}`.trim(), at: when + 3600000 * 20, go: ["track", o.id] });
    else if (o.status === "delivered") out.push({ id: `n-${o.id}-delivered`, type: "order", title: "Delivered · rate your order", text: `Order #${o.id} was delivered. Tell us how it went.`, at: when + 60000 * 18, go: ["account", "reviews"] });
    else if (o.status === "cancelled") out.push({ id: `n-${o.id}-cancelled`, type: "order", title: "Order cancelled", text: `Order #${o.id} was cancelled. ${o.eta || ""}`.trim(), at: when + 60000 * 30, go: ["track", o.id] });
    else if (o.status === "placed" || o.status === "packed") out.push({ id: `n-${o.id}-placed`, type: "order", title: "Order confirmed", text: `We've received order #${o.id} and the store is packing it.`, at: when, go: ["track", o.id] });
  });
  return out;
}

/* ---------- referrals ---------- */
export const REFER_REWARD = 100;
export const REFER_GOAL = 5;
export const REFER_BONUS = 500;
export const SEED_REFERRALS = [
  { id: "r1", name: "Anu R.", status: "ordered", at: day(6) },
  { id: "r2", name: "Rahul M.", status: "joined", at: day(8) },
  { id: "r3", name: "Fathima S.", status: "invited", at: day(13) },
];

/* ---------- time labels ---------- */
export function ago(t, now = Date.now()) {
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return "Just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`;
  return new Date(t).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
export const fmtDate = (t) => new Date(t).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
export const fmtDateTime = (t) => new Date(t).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
