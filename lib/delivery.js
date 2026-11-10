"use client";
/* Who sells a product, and whether it comes Quick or Express - for this
   customer, at this address.

   Only the shop can answer: Quick depends on which branch is near the address
   and has the item on its shelf. Every card on a page asks, so the asks are
   gathered for a moment and sent as one GET /delivery/badges, rather than one
   request per card.

   Until the answer arrives - or when the shop cannot be reached - a card draws
   exactly what it always did, from the product alone. Nothing here can make a
   card worse than before. */
import { createContext, useContext, useEffect, useReducer } from "react";
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

/* The shop's badge for one product - { mode, eta?, seller? } - or null until
   it has answered (and null for good when it has nothing to say). */
export function useBadge(id) {
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
  /* An old answer is still drawn while the new one is on its way. */
  return id ? answers.get(key)?.value ?? null : null;
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
