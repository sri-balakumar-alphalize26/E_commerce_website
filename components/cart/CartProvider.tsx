'use client'

import { createContext, useContext, useEffect, useMemo, useSyncExternalStore } from 'react'
import type { Product } from '@/lib/catalog'
import type { CartState } from '@/lib/cart'
import { summarise } from '@/lib/cart'
import {
  addProduct,
  clearCart,
  getServerSnapshot,
  getSnapshot,
  reconcile,
  removeProduct,
  setProductQty,
  subscribe,
} from '@/lib/cart-store'

type CartApi = {
  cart: CartState
  /**
   * False during the server render and the first client paint, when the
   * stored cart is not yet readable. Controls render their resting state
   * while it is false, so nothing flashes a wrong quantity.
   */
  ready: boolean
  add: (product: Product, qty?: number) => Promise<void>
  setQty: (productId: number, qty: number) => Promise<void>
  remove: (productId: number) => Promise<void>
  clear: () => Promise<void>
}

const CartContext = createContext<CartApi | null>(null)

/**
 * The cart lives in one client context at the root of the app.
 *
 * It has to: the header badge, every ADD control in every grid, the mobile
 * sticky bar and the cart page all need to answer "is this product in the
 * cart, and at what quantity?" against the same state. Lifting the provider
 * any lower than the root layout breaks one of them.
 *
 * State comes from useSyncExternalStore rather than useState-plus-effect --
 * see lib/cart-store.ts for why that distinction matters here.
 */
export default function CartProvider({ children }: { children: React.ReactNode }) {
  const lines = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)

  // Refresh stored lines against the catalogue once per load. This is an
  // effect that calls no setState of its own -- reconcile() writes to the
  // external store, and useSyncExternalStore picks the change up.
  useEffect(() => {
    void reconcile()
  }, [])

  // Referential identity is the readiness signal: getServerSnapshot returns
  // one frozen array, so anything else means the client store has been read.
  const ready = lines !== getServerSnapshot()

  const cart = useMemo(() => summarise(lines), [lines])

  const value = useMemo<CartApi>(
    () => ({
      cart,
      ready,
      add: addProduct,
      setQty: setProductQty,
      remove: removeProduct,
      clear: clearCart,
    }),
    [cart, ready],
  )

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

export function useCart() {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used within CartProvider')
  return ctx
}
