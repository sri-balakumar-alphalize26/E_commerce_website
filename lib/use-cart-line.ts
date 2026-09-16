'use client'

import { useSyncExternalStore } from 'react'
import { getServerSnapshot, getSnapshot, lookup, subscribe } from '@/lib/cart-store'

/**
 * Subscribe to ONE cart line rather than to the whole cart.
 *
 * Every ADD control on a page used to read the cart through React context,
 * and context has no selector: when the provider's value changes, every
 * consumer re-renders. One `+` press therefore re-rendered up to 48 controls
 * on the home page, each running a scan to find its own line.
 *
 * useSyncExternalStore compares snapshots with Object.is, and `lookup`
 * returns the same CartLine object for a line that has not changed -- so a
 * control whose product was untouched bails out without rendering. That
 * property depends on the store replacing line objects only when they
 * actually change, which `commit` does.
 */
export function useCartLine(productId: number) {
  return useSyncExternalStore(
    subscribe,
    () => lookup(productId),
    () => undefined,
  )
}

/**
 * False during the server render and the first client paint, before the
 * stored cart is readable. Identity against the frozen server snapshot is
 * the signal.
 */
export function useCartReady() {
  return useSyncExternalStore(
    subscribe,
    () => getSnapshot() !== getServerSnapshot(),
    () => false,
  )
}
