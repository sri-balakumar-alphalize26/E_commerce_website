import { motion } from '@/lib/mart-motion'

/**
 * The product picture flies into the cart.
 *
 * Modelled on the nova-store reference rather than on the motion layer's
 * own version, which sends an abstract coloured dot. Flying the actual
 * pack-shot is what makes the gesture read as "this item went there"
 * instead of "something happened" -- the same reason the grocery apps this
 * storefront is modelled on all clone the image.
 *
 * The arc is two motions at once: the clone travels the full horizontal
 * distance while the vertical leg overshoots upward first, so the path
 * bows over the page instead of cutting straight across it. Scale and
 * opacity fall away at the end so the clone reads as being absorbed rather
 * than as stopping dead on the icon.
 *
 * Fired BEFORE the cart is written, deliberately. The flight is the
 * feedback, and making it wait on state would put a hesitation exactly
 * where the interface should feel immediate.
 */

const DURATION = 780
const EASE = 'cubic-bezier(.45,.05,.35,1)'
/** How far above the straight line the arc rises, in px. */
const LIFT = 70

export function flyToCart(from: Element | null | undefined) {
  if (typeof window === 'undefined' || !from) return

  const mm = motion()

  // Reduced motion still gets the badge bump: the customer must be told
  // the cart changed, they just do not get a thing moving across the page.
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (reduced) {
    mm?.bumpCart()
    return
  }

  const cart = document.querySelector('[data-mm="cart"]')
  // The card is the article in a grid and the list item in a rail, and an
  // above-the-fold rail leaves it untagged entirely -- so fall back to the
  // nearest article before giving up.
  const card = from.closest('[data-mm="card"]') ?? from.closest('article')
  const source = card?.querySelector('img')

  if (!cart || !source) {
    mm?.bumpCart()
    return
  }

  const a = source.getBoundingClientRect()
  const b = cart.getBoundingClientRect()
  if (!a.width || !a.height) {
    mm?.bumpCart()
    return
  }

  const clone = document.createElement('img')
  clone.src = source.currentSrc || source.src
  clone.alt = ''
  clone.setAttribute('aria-hidden', 'true')
  Object.assign(clone.style, {
    position: 'fixed',
    left: `${a.left}px`,
    top: `${a.top}px`,
    width: `${a.width}px`,
    height: `${a.height}px`,
    objectFit: 'contain',
    background: 'var(--color-surface, #fff)',
    borderRadius: '12px',
    boxShadow: 'var(--shadow-float)',
    pointerEvents: 'none',
    zIndex: '2147483000',
    willChange: 'transform, opacity',
  } satisfies Partial<CSSStyleDeclaration>)
  document.body.appendChild(clone)

  const dx = b.left + b.width / 2 - (a.left + a.width / 2)
  const dy = b.top + b.height / 2 - (a.top + a.height / 2)

  let settled = false
  function land() {
    if (settled) return
    settled = true
    clone.remove()
    mm?.bumpCart()
  }

  const run = clone.animate(
    [
      { transform: 'translate(0, 0) scale(1)', opacity: 1, offset: 0 },
      {
        transform: `translate(${dx * 0.3}px, ${dy * 0.12 - LIFT}px) scale(0.62)`,
        opacity: 1,
        offset: 0.35,
      },
      { transform: `translate(${dx}px, ${dy}px) scale(0.14)`, opacity: 0.25, offset: 1 },
    ],
    { duration: DURATION, easing: EASE, fill: 'forwards' },
  )

  run.onfinish = land
  // A clone stranded by a cancelled or never-finishing animation would sit
  // over the page for good, so the timeout is a hard floor, not a retry.
  window.setTimeout(land, DURATION + 320)
}
