import type { DeliveryMode, SavedAddress } from '@/lib/prefs'
import {
  DEFAULT_MODE,
  readStoredAddresses,
  readStoredMode,
  writeStoredAddresses,
  writeStoredMode,
} from '@/lib/prefs'

/**
 * Delivery preferences: the address book and the Quick / Express mode,
 * behind the same external-store pattern the cart uses.
 *
 * Both are genuinely read, which is the bar this had to clear before it
 * could ship. The header label follows the selected address and the mode
 * really filters the catalogue -- an address picker that only changes a
 * label promises serviceability checking that nothing here can answer.
 *
 * Snapshots are cached so useSyncExternalStore sees a stable reference.
 * Returning a freshly parsed array on every call makes React believe the
 * store changed on every render, and it loops.
 */

let addresses: SavedAddress[] | null = null
let mode: DeliveryMode | null = null
const listeners = new Set<() => void>()

/** One shared reference, so the server snapshot is never a new array. */
const SERVER_ADDRESSES: SavedAddress[] = []

function emit() {
  for (const l of listeners) l()
}

export function subscribe(onStoreChange: () => void) {
  listeners.add(onStoreChange)

  function onStorage(e: StorageEvent) {
    if (e.key !== null && !e.key.startsWith('store.prefs')) return
    addresses = readStoredAddresses()
    mode = readStoredMode()
    emit()
  }
  window.addEventListener('storage', onStorage)

  return () => {
    listeners.delete(onStoreChange)
    window.removeEventListener('storage', onStorage)
  }
}

export function getAddresses(): SavedAddress[] {
  // Populated lazily rather than at module scope: this module is imported
  // during SSR, where localStorage does not exist.
  if (addresses === null) addresses = readStoredAddresses()
  return addresses
}

export function getServerAddresses(): SavedAddress[] {
  return SERVER_ADDRESSES
}

export function getMode(): DeliveryMode {
  if (mode === null) mode = readStoredMode()
  return mode
}

export function getServerMode(): DeliveryMode {
  return DEFAULT_MODE
}

export function getSelectedAddress(): SavedAddress | undefined {
  const all = getAddresses()
  return all.find((a) => a.selected) ?? all[0]
}

export async function setMode(next: DeliveryMode) {
  mode = next
  writeStoredMode(next)
  emit()
}

export async function saveAddress(input: Omit<SavedAddress, 'id' | 'selected'>) {
  const all = getAddresses()
  // Derived from the list rather than from Date.now() or Math.random():
  // both differ between tabs reading the same list, and a key that changes
  // per render is a React reconciliation bug waiting to happen.
  const id = `addr-${all.length + 1}-${input.pincode || 'na'}`
  const next = [...all.map((a) => ({ ...a, selected: false })), { ...input, id, selected: true }]
  addresses = next
  writeStoredAddresses(next)
  emit()
}

export async function selectAddress(id: string) {
  const next = getAddresses().map((a) => ({ ...a, selected: a.id === id }))
  addresses = next
  writeStoredAddresses(next)
  emit()
}

export async function removeAddress(id: string) {
  const remaining = getAddresses().filter((a) => a.id !== id)
  // Removing the selected address promotes the next one, so the header is
  // never left with nothing to show.
  if (remaining.length && !remaining.some((a) => a.selected)) remaining[0].selected = true
  addresses = remaining
  writeStoredAddresses(remaining)
  emit()
}
