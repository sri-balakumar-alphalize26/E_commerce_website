/**
 * My List persistence.
 *
 * A wishlist is viable in this phase for exactly the reason the cart is:
 * it is a set of product ids in localStorage. An earlier pass ruled it out
 * on the grounds that the backend could not support it, which conflated two
 * different things -- the SERVER cannot hold a wishlist yet, but the device
 * can, and that is enough for a list that is explicitly device-local.
 *
 * Only ids are stored. Names and prices are re-resolved from the catalogue
 * on read, so a list opened weeks later cannot show a stale price.
 */

const KEY = 'store.wishlist.v1'

export function readStoredWishlist(): number[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((n) => Number.isInteger(n)) : []
  } catch {
    return []
  }
}

export function writeStoredWishlist(ids: number[]) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(KEY, JSON.stringify(ids))
  } catch {}
}
