/**
 * Typed access to the vendored motion engine in public/mart-motion.js.
 *
 * The engine is a plain script rather than a module, so it announces
 * itself on `window` once it has loaded. Every call here is therefore
 * optional BY CONSTRUCTION: the script is loaded `afterInteractive` and
 * can legitimately be absent -- still downloading, blocked, or dropped by
 * its own 2.5s failsafe -- and nothing in the storefront may depend on it
 * having arrived. Motion is decoration; the page works without it.
 */

export type MartMotion = {
  /** Re-tag markup that appeared after boot. Idempotent. */
  refresh: (ctx?: ParentNode) => void
  flyToCart: (from: Element, done?: () => void) => void
  bumpCart: () => void
  replay: () => void
  openSearch: () => void
  closeSearch: () => void
  /** Re-cascade a list that has just been re-rendered. */
  staggerIn: (el: Element) => void
  staggerOut: (el: Element, cb?: () => void) => void
}

declare global {
  interface Window {
    MartMotion?: MartMotion
  }
}

export function motion(): MartMotion | null {
  if (typeof window === 'undefined') return null
  return window.MartMotion ?? null
}
