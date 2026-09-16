/**
 * The terms a customer has searched before, kept on the device.
 *
 * Local storage is the right home for this in a way it is not for a cart:
 * a past search is a convenience belonging to this browser, and nothing is
 * lost if it is cleared. That also means it can ship in this phase without
 * waiting for a backend, unlike anything the server has to agree with.
 *
 * Every read is defensive. Storage throws in private mode in some browsers,
 * can be disabled outright, and the stored value is user-editable -- so a
 * malformed payload has to read as "no history" rather than take a screen
 * down with it.
 */

const KEY = 'store.searches.v1'
const MAX = 8

export function readSearches(): string[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((t): t is string => typeof t === 'string' && t.length > 0).slice(0, MAX)
  } catch {
    return []
  }
}

function write(terms: string[]) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(KEY, JSON.stringify(terms.slice(0, MAX)))
  } catch {
    // A full or disabled store costs the customer their history, nothing more.
  }
}

/** Most recent first, case-insensitively de-duplicated. */
export function rememberSearch(term: string): string[] {
  const clean = term.trim()
  if (!clean) return readSearches()
  const lower = clean.toLowerCase()
  const next = [clean, ...readSearches().filter((t) => t.toLowerCase() !== lower)].slice(0, MAX)
  write(next)
  return next
}

export function clearSearches(): string[] {
  write([])
  return []
}
