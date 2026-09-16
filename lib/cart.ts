import type { Product, StockStatus } from '@/lib/catalog'
import { clampQty } from '@/lib/catalog'

/**
 * Cart domain types and the storage-backed implementation.
 *
 * Everything here is deliberately async even though localStorage is
 * synchronous. The eventual backend keeps the cart server-side, where every
 * mutation is a round trip that returns the whole cart. Writing the
 * interface that way now means swapping the implementation later touches
 * this file only -- no call site changes, no component changes, no
 * sprinkling of `await` through the tree at the point it hurts most.
 */

export type CartLine = {
  /** Product id. Doubles as the line key: one line per product. */
  productId: number
  vertical: string
  slug: string
  name: string
  subtitle: string
  /**
   * Carried through from the product so the badge and the low-stock
   * warning survive into the cart and into order history. Dropping them
   * here is why carts so often look plainer than the grid that fed them:
   * the micro-labels a customer used to choose the item vanish at the
   * moment they are reviewing that choice.
   */
  badge: string | null
  stockStatus: StockStatus
  image: string
  currency: string
  /** Refreshed against the catalogue on load -- see reconcile() in cart-store. */
  price: number
  originalPrice: number
  qty: number
  minQty: number
  qtyStep: number
  /** Snapshot of availability so the cart can flag items that lapsed. */
  inStock: boolean
  /**
   * Whether the local store stocks this, which is what splits the cart into
   * its two delivery groups.
   *
   * Optional because carts written before it existed do not carry it, and
   * the reader validates only three fields on purpose -- dropping an
   * otherwise good cart over a missing flag would be a worse trade than
   * showing one line in the wrong group until reconcile() refreshes it on
   * the next load.
   */
  quickDelivery?: boolean
  stock: number
}

export type CartState = {
  lines: CartLine[]
  currency: string
  /** Sum of price * qty. */
  subtotal: number
  /** Sum of (originalPrice - price) * qty. */
  savings: number
  /** Sum of quantities. */
  itemCount: number
}

export const EMPTY_CART: CartState = {
  lines: [],
  currency: 'INR',
  subtotal: 0,
  savings: 0,
  itemCount: 0,
}

export function lineFromProduct(p: Product, qty: number): CartLine {
  return {
    productId: p.id,
    vertical: p.vertical,
    slug: p.slug,
    name: p.name,
    subtitle: p.subtitle,
    badge: p.badge,
    stockStatus: p.stockStatus,
    image: p.image,
    currency: p.currency,
    price: p.price,
    originalPrice: p.originalPrice,
    qty,
    minQty: p.minQty,
    qtyStep: p.qtyStep,
    inStock: p.inStock,
    stock: p.stock,
    quickDelivery: p.quickDelivery,
  }
}

export function summarise(lines: CartLine[]): CartState {
  let subtotal = 0
  let savings = 0
  let itemCount = 0
  for (const l of lines) {
    subtotal += l.price * l.qty
    savings += Math.max(0, l.originalPrice - l.price) * l.qty
    itemCount += l.qty
  }
  return {
    lines,
    currency: lines[0]?.currency ?? EMPTY_CART.currency,
    subtotal,
    savings,
    itemCount,
  }
}

// ---------------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------------

const KEY = 'store.cart.v1'

/**
 * The version suffix is load-bearing. When CartLine gains or loses a field,
 * bumping it drops the old cart instead of rendering a half-populated one --
 * a cleared cart is a recoverable annoyance, a cart that throws mid-render
 * is not.
 */
export function readStoredCart(): CartLine[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isCartLine)
  } catch {
    // Private mode, blocked site data, or corrupt JSON. An empty cart is
    // the only safe answer, and it must not take the page down.
    return []
  }
}

export function writeStoredCart(lines: CartLine[]) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(KEY, JSON.stringify(lines))
  } catch {
    // Quota or blocked storage. The in-memory cart still works for this
    // session, which is better than refusing the interaction.
  }
}

function isCartLine(v: unknown): v is CartLine {
  if (!v || typeof v !== 'object') return false
  const l = v as Record<string, unknown>
  return typeof l.productId === 'number' && typeof l.qty === 'number' && typeof l.name === 'string'
}

// ---------------------------------------------------------------------------
// Mutations -- pure functions over a line list
// ---------------------------------------------------------------------------

export function addLine(lines: CartLine[], product: Product, qty: number): CartLine[] {
  const wanted = clampQty(product, qty)
  const existing = lines.find((l) => l.productId === product.id)
  if (!existing) return [...lines, lineFromProduct(product, wanted)]
  return lines.map((l) =>
    l.productId === product.id ? { ...l, qty: clampQty(product, l.qty + wanted) } : l,
  )
}

export function setLineQty(lines: CartLine[], productId: number, qty: number): CartLine[] {
  const line = lines.find((l) => l.productId === productId)
  if (!line) return lines
  const next = clampQty(line, qty)
  // Dropping below the minimum is how the stepper removes an item: the
  // customer pressing minus at qty 1 means "take it out", not "clamp to 1".
  if (qty < line.minQty) return lines.filter((l) => l.productId !== productId)
  return lines.map((l) => (l.productId === productId ? { ...l, qty: next } : l))
}

export function removeLine(lines: CartLine[], productId: number): CartLine[] {
  return lines.filter((l) => l.productId !== productId)
}
