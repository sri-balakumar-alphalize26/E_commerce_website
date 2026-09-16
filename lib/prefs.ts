/**
 * Delivery preference types and their persistence.
 *
 * Split from the store so a server component can import a type without
 * pulling the client-side store in behind it.
 */

export type DeliveryMode = 'quick' | 'all'

export type SavedAddress = {
  id: string
  /** Home / Work / Other -- the chip the header shows. */
  label: string
  line1: string
  line2: string
  city: string
  state: string
  pincode: string
  /**
   * Set when the address came from the browser's geolocation. We can capture
   * coordinates but cannot turn them into a street -- that needs a geocoding
   * service this build does not have -- so they are kept alongside whatever
   * the customer typed rather than pretending to be an address.
   */
  coords?: { lat: number; lon: number }
  selected: boolean
}

export const DEFAULT_MODE: DeliveryMode = 'all'

const ADDRESS_KEY = 'store.prefs.addresses.v1'
const MODE_KEY = 'store.prefs.mode.v1'

export function formatAddress(a: SavedAddress) {
  return [a.line1, a.line2, a.city, a.state, a.pincode].filter(Boolean).join(', ')
}

export function readStoredAddresses(): SavedAddress[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(ADDRESS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter(isAddress) : []
  } catch {
    // Private mode, blocked storage, or corrupt JSON. An empty book is the
    // only safe answer, and it must not take the header down.
    return []
  }
}

export function writeStoredAddresses(list: SavedAddress[]) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(ADDRESS_KEY, JSON.stringify(list))
  } catch {}
}

export function readStoredMode(): DeliveryMode {
  if (typeof window === 'undefined') return DEFAULT_MODE
  try {
    const raw = window.localStorage.getItem(MODE_KEY)
    return raw === 'quick' || raw === 'all' ? raw : DEFAULT_MODE
  } catch {
    return DEFAULT_MODE
  }
}

export function writeStoredMode(mode: DeliveryMode) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(MODE_KEY, mode)
  } catch {}
}

function isAddress(v: unknown): v is SavedAddress {
  if (!v || typeof v !== 'object') return false
  const a = v as Record<string, unknown>
  return typeof a.id === 'string' && typeof a.label === 'string' && typeof a.pincode === 'string'
}
