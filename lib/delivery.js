"use client";
/* Who sells a product, and whether it comes Quick or Express - for this
   customer, at this address.

   Only the shop can answer: Quick depends on which branch is near the address
   and has the item on its shelf. Every card on a page asks, so the asks are
   gathered for a moment and sent as one GET /delivery/badges, rather than one
   request per card.

   Until the answer arrives a card draws a quiet placeholder rather than a
   guess (useBadgeState), so Quick never flips to Express in front of the
   customer. When the shop cannot be reached, a card draws exactly what it
   always did, from the product alone. */
import { createContext, useContext, useEffect, useReducer, useSyncExternalStore } from "react";
import { api } from "./api";

/* { addressId, pin }: where the customer is having things delivered. */
export const DeliveryContext = createContext(null);

const WAIT_MS = 40;      /* long enough for a page of cards to mount */
const CHUNK = 100;       /* ids per request; the shop takes up to 200 */

const FRESH_MS = 2 * 60 * 1000; /* stock moves; ask again after this */

const answers = new Map();    /* "where|id" -> { at, value }; value null = "no answer" */
const listeners = new Map();  /* "where|id" -> Set(callback) */
const queued = new Map();     /* where -> Set(id) */
let timer = null;

const whereKey = (ctx) => `${ctx?.addressId || ""}~${ctx?.pin || ""}`;

function tell(key) {
  listeners.get(key)?.forEach((cb) => cb());
}

function flush() {
  timer = null;
  const batches = [...queued.entries()];
  queued.clear();
  for (const [where, idSet] of batches) {
    const [addressId, pin] = where.split("~");
    const ids = [...idSet];
    for (let i = 0; i < ids.length; i += CHUNK) {
      const part = ids.slice(i, i + CHUNK);
      const q = new URLSearchParams({ ids: part.join(",") });
      if (addressId) q.set("address", addressId);
      if (pin) q.set("pin", pin);
      api(`/delivery/badges?${q.toString()}`)
        .then((r) => {
          const got = r?.badges || {};
          if (r && "sellers" in r) noteSellers(r.sellers);
          part.forEach((id) => { answers.set(`${where}|${id}`, { at: Date.now(), value: got[id] || null }); tell(`${where}|${id}`); });
        })
        .catch(() => {
          /* Offline or refused: the cards keep their own answer. */
          part.forEach((id) => { answers.set(`${where}|${id}`, { at: Date.now(), value: null }); tell(`${where}|${id}`); });
        });
    }
  }
}

function fresh(key) {
  const hit = answers.get(key);
  return !!hit && Date.now() - hit.at < FRESH_MS;
}

function want(where, id) {
  const key = `${where}|${id}`;
  if (fresh(key)) return;
  const set = queued.get(where) || new Set();
  if (set.has(id)) return;
  set.add(id);
  queued.set(where, set);
  if (!timer) timer = setTimeout(flush, WAIT_MS);
}

/* The shop's badge for one product and whether it has answered yet:
   { badge: { mode, eta?, seller?, ... } | null, ready }.

   `ready` false means "still asking", which is not the same as "nothing to
   say" (ready, badge null). While still asking, the screens draw a quiet
   placeholder instead of a guess, so a card never says Quick and then flips
   to Express, and "Sold by" never pops in late. An old answer is still drawn
   (ready) while a fresh one is on its way; a shop that cannot be reached
   answers null, and the cards fall back to what they always drew. */
export function useBadgeState(id) {
  const ctx = useContext(DeliveryContext);
  const where = whereKey(ctx);
  const key = `${where}|${id}`;
  const [, rerender] = useReducer((n) => n + 1, 0);
  useEffect(() => {
    if (!id) return undefined;
    const set = listeners.get(key) || new Set();
    set.add(rerender);
    listeners.set(key, set);
    want(where, String(id));
    return () => {
      set.delete(rerender);
      if (!set.size) listeners.delete(key);
    };
  }, [key]); // eslint-disable-line
  if (!id) return { badge: null, ready: true };
  const hit = answers.get(key);
  return { badge: hit?.value ?? null, ready: !!hit };
}

/* Just the badge - { mode, eta?, seller? } - or null until it has answered
   (and null for good when it has nothing to say). */
export function useBadge(id) {
  return useBadgeState(id).badge;
}

/* Did the last answer say the shop has several sellers? Remembered so a card
   still waiting can keep the "Sold by" line's room, instead of the line
   pushing the price down when it arrives. */
let sellersOn = false;
if (typeof window !== "undefined") {
  try { sellersOn = sessionStorage.getItem("mart.sellersOn") === "1"; } catch { /* no storage */ }
}
const sellerWatchers = new Set();
export function useSellersShown() {
  return useSyncExternalStore(
    (cb) => { sellerWatchers.add(cb); return () => sellerWatchers.delete(cb); },
    () => sellersOn,
    () => false, /* the server never knows; the browser's answer follows at once */
  );
}
function noteSellers(on) {
  if (sellersOn === !!on) return;
  sellersOn = !!on;
  try { sessionStorage.setItem("mart.sellersOn", on ? "1" : "0"); } catch { /* no storage */ }
  sellerWatchers.forEach((cb) => cb());
}

/* A new address, a new stock count after an order: ask again next time. */
export function forgetBadges() {
  answers.clear();
}

/* Quick or Express for a product: the shop's answer when it has one, else
   the product's own rule - a delivery promise makes it Express. */
export function modeOf(p, badge) {
  if (badge?.mode) return badge.mode;
  return p?.delivery ? "all" : "quick";
}

/* The one line the product page prints: "Quick · 30 mins" (the hub's own
   Quick promise, else the shop's usual words), "Express · Next day" (the
   product's own promise first, then the hub rules'), or just "Express". */
export function deliveryLine(p, badge) {
  if (modeOf(p, badge) === "quick") return `Quick · ${badge?.when || "10–20 mins"}`;
  const when = p?.delivery || badge?.when;
  return when ? `Express · ${when}` : "Express";
}
