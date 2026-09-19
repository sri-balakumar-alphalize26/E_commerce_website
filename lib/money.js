"use client";

/* What money looks like, according to the shop.

   Every price in the app went through an `inr()`: a rupee sign glued to
   `toLocaleString("en-IN")`. It put ₹ in front of whatever number it was
   handed, so an Omani shop pricing in dollars printed all three currencies at
   once - the support bot said ر.ع. because it formats server-side, the cart
   said ₹, and the order was written in USD.

   Nothing here decides anything. The shop sends `{code, symbol, position,
   decimals}` with the amounts, and this formats what it is told to.

   It is a module-level store rather than a context because `money()` is a
   plain function called from eighty-odd places, most of them not components,
   and threading a hook through all of them would be a bigger change than the
   bug is worth. Same shape as the product store next door. */

import { useSyncExternalStore } from "react";

let current = null;
const subs = new Set();

export function setCurrency(next) {
  if (!next || !next.code) return;
  if (current && current.code === next.code && current.symbol === next.symbol) return;
  current = next;
  subs.forEach((fn) => fn());
}

const subscribe = (fn) => { subs.add(fn); return () => subs.delete(fn); };
const snapshot = () => current;
const serverSnapshot = () => null;

/* For the few places that should redraw the moment the shop answers. */
export function useCurrency() {
  return useSyncExternalStore(subscribe, snapshot, serverSnapshot);
}

/* `at` is for printing an old order in the money it was charged in, whatever
   the shop is quoting today. */
export function money(amount, at = null) {
  const c = at || current;
  const n = Number(amount) || 0;
  const decimals = c ? c.decimals : 2;
  /* The shop's locale, not the reader's: left to the browser, the same rupee
     price reads 189,000 to one customer and 1,89,000 to another, and only one
     of those is how the shop writes its own prices. */
  const shown = n.toLocaleString(c?.locale || undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  /* Before the first answer, a bare number. Guessing a symbol is how this
     went wrong in the first place. */
  if (!c || !c.symbol) return shown;
  return c.position === "after" ? `${shown} ${c.symbol}` : `${c.symbol}${shown}`;
}
