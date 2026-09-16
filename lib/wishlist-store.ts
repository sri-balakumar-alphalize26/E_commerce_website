import { readStoredWishlist, writeStoredWishlist } from '@/lib/wishlist'

/**
 * My List, behind the same external-store pattern as the cart.
 *
 * A Set backs the membership test so a card asking "am I listed?" is O(1)
 * rather than a scan -- thirty cards each scanning the list on every toggle
 * is the shape that starts to bite at catalogue scale.
 */

let ids: number[] | null = null
let index = new Set<number>()
const listeners = new Set<() => void>()

/** One shared reference, so the server snapshot is never a new array. */
const SERVER_IDS: number[] = []

function emit() {
  for (const l of listeners) l()
}

function setIds(next: number[]) {
  ids = next
  index = new Set(next)
}

function commit(next: number[]) {
  setIds(next)
  writeStoredWishlist(next)
  emit()
}

export function subscribe(onStoreChange: () => void) {
  listeners.add(onStoreChange)

  function onStorage(e: StorageEvent) {
    if (e.key !== null && !e.key.startsWith('store.wishlist')) return
    setIds(readStoredWishlist())
    emit()
  }
  window.addEventListener('storage', onStorage)

  return () => {
    listeners.delete(onStoreChange)
    window.removeEventListener('storage', onStorage)
  }
}

export function getSnapshot(): number[] {
  if (ids === null) setIds(readStoredWishlist())
  return ids as number[]
}

export function getServerSnapshot(): number[] {
  return SERVER_IDS
}

export function has(productId: number) {
  getSnapshot()
  return index.has(productId)
}

export async function toggle(productId: number) {
  const current = getSnapshot()
  commit(
    index.has(productId) ? current.filter((n) => n !== productId) : [...current, productId],
  )
}

export async function remove(productId: number) {
  commit(getSnapshot().filter((n) => n !== productId))
}
