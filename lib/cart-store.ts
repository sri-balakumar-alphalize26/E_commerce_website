import type { Product } from '@/lib/catalog'
import type { CartLine } from '@/lib/cart'
import { clampQty } from '@/lib/catalog'
import { addLine, readStoredCart, removeLine, setLineQty, writeStoredCart } from '@/lib/cart'

/**
 * A module-level external store for the cart, read through
 * useSyncExternalStore.
 *
 * The obvious implementation -- useState plus an effect that reads
 * localStorage on mount -- is what most carts do and it is wrong in three
 * ways at once. It sets state synchronously inside an effect, which React 19
 * flags because it causes a second render pass on every mount. It tears
 * under concurrent rendering, because two components can read different
 * values in the same pass. And it needs a separate `storage` listener bolted
 * on for cross-tab sync.
 *
 * useSyncExternalStore solves all three, but only if getSnapshot returns a
 * REFERENTIALLY STABLE value: returning a freshly parsed array each call
 * makes React believe the store changed on every render and loop forever.
 * So the parsed lines are cached here and the reference changes only when
 * the data actually does.
 */

let lines: CartLine[] | null = null
/** Rebuilt with , so a lookup is O(1) rather than a scan per card. */
let index: Map<number, CartLine> = new Map()
const listeners = new Set<() => void>()

/** One shared reference, so the server snapshot is never a new array. */
const SERVER_SNAPSHOT: CartLine[] = []

function emit() {
  for (const l of listeners) l()
}

function setLines(next: CartLine[]) {
  lines = next
  index = new Map(next.map((l) => [l.productId, l]))
}

function commit(next: CartLine[]) {
  setLines(next)
  writeStoredCart(next)
  emit()
}

export function lookup(productId: number) {
  getSnapshot()
  return index.get(productId)
}

export function subscribe(onStoreChange: () => void) {
  listeners.add(onStoreChange)

  // Another tab writing the cart must land here too, or a customer checks
  // out with a total they can see is wrong in their other window.
  function onStorage(e: StorageEvent) {
    if (e.key !== null && !e.key.startsWith('store.cart')) return
    setLines(readStoredCart())
    emit()
  }
  window.addEventListener('storage', onStorage)

  return () => {
    listeners.delete(onStoreChange)
    window.removeEventListener('storage', onStorage)
  }
}

export function getSnapshot(): CartLine[] {
  // Populated lazily on first read rather than at module scope: this module
  // is imported during SSR, where localStorage does not exist.
  if (lines === null) setLines(readStoredCart())
  return lines as CartLine[]
}

export function getServerSnapshot(): CartLine[] {
  return SERVER_SNAPSHOT
}

// ---------------------------------------------------------------------------
// Mutations. Async on purpose -- see the note in lib/cart.ts.
// ---------------------------------------------------------------------------

export async function addProduct(product: Product, qty?: number) {
  commit(addLine(getSnapshot(), product, qty ?? product.minQty ?? 1))
}

export async function setProductQty(productId: number, qty: number) {
  commit(setLineQty(getSnapshot(), productId, qty))
}

export async function removeProduct(productId: number) {
  commit(removeLine(getSnapshot(), productId))
}

export async function clearCart() {
  commit([])
}

// ---------------------------------------------------------------------------
// Reconciliation
// ---------------------------------------------------------------------------

type RepricedLine =
  | {
      id: number
      gone?: false
      name: string
      subtitle: string
      image: string
      currency: string
      price: number
      originalPrice: number
      stock: number
      stockStatus: CartLine['stockStatus']
      inStock: boolean
      minQty: number
      qtyStep: number
      badge: string | null
    }
  | { id: number; gone: true }

let reconciled = false

/**
 * Refresh stored lines against the live catalogue.
 *
 * Every field on a persisted line is a snapshot from whenever the item was
 * added. `lib/cart.ts` described price as "refreshed from the catalogue" and
 * nothing ever did it, so a cart reopened later showed a stale total, a
 * stale availability label, and a stepper whose cap was computed from stock
 * that may have changed. That is the class of bug that reaches a checkout.
 *
 * Runs once per page load. Failures are swallowed on purpose: a cart that
 * cannot be revalidated is still better than an empty one, and the customer
 * has done nothing wrong.
 */
export async function reconcile() {
  if (reconciled) return
  reconciled = true

  const current = getSnapshot()
  if (!current.length) return

  try {
    const res = await fetch('/api/reprice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: current.map((l) => l.productId) }),
    })
    if (!res.ok) return

    const { lines: fresh } = (await res.json()) as { lines: RepricedLine[] }
    const byId = new Map(fresh.map((f) => [f.id, f]))

    const next: CartLine[] = []
    for (const line of current) {
      const f = byId.get(line.productId)
      // A product that no longer resolves is dropped rather than kept at a
      // price nothing can honour.
      if (!f || f.gone) continue
      next.push({
        ...line,
        name: f.name,
        subtitle: f.subtitle,
        image: f.image,
        currency: f.currency,
        price: f.price,
        originalPrice: f.originalPrice,
        stock: f.stock,
        stockStatus: f.stockStatus,
        inStock: f.inStock,
        minQty: f.minQty,
        qtyStep: f.qtyStep,
        badge: f.badge,
        // Re-clamp: stock may have fallen below the quantity held.
        qty: clampQty(f, line.qty),
      })
    }

    const changed =
      next.length !== current.length ||
      next.some((l, i) => l.qty !== current[i].qty || l.price !== current[i].price)

    if (changed) commit(next)
  } catch {
    // Offline or aborted. The stored cart stands.
  }
}
