'use client'

import { useSyncExternalStore } from 'react'
import { getServerSnapshot, getSnapshot, has, subscribe } from '@/lib/wishlist-store'

/**
 * Subscribe to ONE product's membership rather than to the whole list.
 *
 * useSyncExternalStore compares snapshots with Object.is, and a boolean that
 * has not changed bails out without rendering -- so toggling one heart
 * re-renders one card, not the thirty around it. Reading this through
 * context instead would re-render every consumer, because context has no
 * selector. Same reasoning as lib/use-cart-line.ts.
 */
export function useWishlisted(productId: number) {
  return useSyncExternalStore(
    subscribe,
    () => has(productId),
    () => false,
  )
}

/** The whole list, for the My List page. */
export function useWishlist() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
