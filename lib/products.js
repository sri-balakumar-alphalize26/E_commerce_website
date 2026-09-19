"use client";

/* Every product the session has seen, in one place.

   This replaces buildIndex() in components/home/catalog.js. The meaning of
   `byId` does not change -- it is still "every product we know about", keyed by
   id -- only where those products come from. Eleven components read it through
   the `common` prop, so keeping the shape identical is the whole point.

   Products arrive from several feeds (home rails, a category listing, a search,
   a product page) and are merged as they land. Anything the cart or the
   wishlist asks for that has not arrived yet is fetched by id. */

import { useSyncExternalStore } from "react";
import { api } from "@/lib/api";
import { enrich } from "@/components/home/catalog";

const store = new Map();
const subs = new Set();
let snapshot = {};

function publish() {
  snapshot = Object.fromEntries(store); /* a new object, so React sees the change */
  subs.forEach((fn) => fn());
}

/* Merge, don't replace: a search card is thinner than a product page's card,
   and the thin one must not wipe fields the fat one already gave us. */
export function absorb(...products) {
  let changed = false;
  for (const p of products.flat()) {
    if (!p || p.id == null) continue;
    const id = String(p.id);
    const merged = enrich({ ...(store.get(id) || {}), ...p, id });
    store.set(id, merged);
    changed = true;
  }
  if (changed) publish();
  return products;
}

/* Server cards, ready to render.

   The listing filters on `off`, `rating` and `popularity`, which the shop does
   not always send - a product with no discount has no `off` at all. enrich()
   fills those in, and without it every filter comparison is against undefined,
   which is false, so a full page of products quietly renders as none. absorb()
   enriches its own copies for the store; anything handed straight to a
   component has to come through here. */
export const cards = (list) => (list || []).map((p) => enrich({ ...p }));

export const get = (id) => store.get(String(id));
export const has = (id) => store.has(String(id));

/* Ask for ids we don't have. Calls are collected across a tick so that a cart
   of twenty lines is one request, not twenty. */
let pending = new Set();
let inflight = null;
let batchWorks = true; /* set false the first time /products?ids= is not there */

/* Ask for one id on its own. The product page route answers with far more than
   a card needs, but it exists on every install, which the batch route does not
   yet. `missing` is capped by the caller, so this stays a handful of requests. */
async function one(id) {
  try {
    const res = await api(`/product/${encodeURIComponent(id)}`);
    if (res?.p) absorb(res.p);
  } catch (e) {
    /* Gone, unpublished, or never ours. A card that cannot be drawn is simply
       not drawn - far better than drawing the wrong thing. */
  }
}

export function ensure(ids) {
  const missing = [...new Set((ids || []).map(String))].filter((id) => id && !store.has(id));
  if (!missing.length) return Promise.resolve();
  missing.forEach((id) => pending.add(id));
  inflight = inflight || Promise.resolve().then(async () => {
    const batch = [...pending];
    pending = new Set();
    inflight = null;
    if (!batch.length) return;
    if (batchWorks) {
      try {
        const res = await api(`/products?ids=${batch.map(encodeURIComponent).join(",")}`);
        absorb(res?.items || []);
        return;
      } catch (e) {
        if (e?.status !== 404) return; /* a real outage: leave them unresolved */
        batchWorks = false; /* the route is not installed; stop asking */
      }
    }
    await Promise.all(batch.slice(0, 24).map(one));
  });
  return inflight;
}

const subscribe = (fn) => { subs.add(fn); return () => subs.delete(fn); };
const getSnapshot = () => snapshot;
const getServerSnapshot = () => snapshot;

/* The `byId` every screen already reads. */
export function useProducts() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/* Test/debug only. */
export function _reset() { store.clear(); publish(); }
