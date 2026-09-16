'use client'

import { useRouter } from 'next/navigation'
import { useMemo } from 'react'
import { useCart } from '@/components/cart/CartProvider'
import VendorCart from '@/components/cart/vendor/Cart'
import type { HomeItem } from '@/lib/home-adapter'
import { setProductQty } from '@/lib/cart-store'
import { productHref } from '@/lib/slug'

/**
 * The bridge between the vendored cart design and this app's cart.
 *
 * Same arrangement as HomeScreen: everything the design needs arrives as
 * props, and nothing inside components/cart/vendor knows about CartLine or
 * the store.
 *
 * THE STORE STAYS AUTHORITATIVE. The design asks for an id -> quantity map
 * and reports changes back through setQty; every one of those goes through
 * setProductQty so clampQty still applies. Letting the design hold its own
 * quantities would mean a number clamped by pack rules or by the stock
 * ceiling reading one way on the page and another in the cart -- and the
 * cart is the screen where a customer checks exactly that.
 *
 * Arithmetic is NOT recomputed here. summarise() in lib/cart.ts is the only
 * place subtotal and savings are worked out, and the design's own totals are
 * derived from the same per-line prices it is handed.
 */

/** The design groups on `delivery`; our lines carry `quick` instead. */
type CartItem = HomeItem & { delivery?: boolean }

export default function CartScreen({
  recommended,
  alsoLike,
}: {
  recommended: HomeItem[]
  alsoLike: HomeItem[]
}) {
  const router = useRouter()
  const { cart, ready } = useCart()

  const { qtyById, byId } = useMemo(() => {
    const qty: Record<number, number> = {}
    const map: Record<number, CartItem> = {}

    for (const line of cart.lines) {
      qty[line.productId] = line.qty
      map[line.productId] = {
        id: line.productId,
        // A cart line carries everything the product URL needs, so the
        // suggestion rails and the line thumbnails can link without
        // fetching the product back.
        href: productHref({ vertical: line.vertical, slug: line.slug, id: line.productId }),
        name: line.name,
        // The design prints `unit` under the name, where the brand line is
        // what this catalogue has to say about a product at that size.
        unit: line.subtitle,
        price: line.price,
        mrp: line.originalPrice > line.price ? line.originalPrice : undefined,
        image: line.image,
        stock: line.stock,
        low: line.stockStatus === 'low' ? line.stock : undefined,
        quick: line.quickDelivery,
        // Truthy puts the line in the Express group, falsy in Quick. A line
        // saved before the flag existed reads undefined and sits in Quick
        // until reconcile() refreshes it on the next load.
        delivery: line.quickDelivery ? undefined : true,
      }
    }

    return { qtyById: qty, byId: map }
  }, [cart.lines])

  /*
   * The design renders nothing until it has lines, and its own empty state
   * is good, so the only thing guarded here is the moment before storage has
   * been read -- without it every visit would flash "your cart is empty"
   * before the real contents arrived.
   */
  if (!ready) {
    return (
      <div className="ct-page">
        <div className="ct-empty">
          <p>Loading your cart…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="hm-page">
      <VendorCart
        cart={qtyById}
        byId={byId}
        setQty={(id: number, qty: number) => void setProductQty(Number(id), qty)}
        recommended={recommended}
        alsoLike={alsoLike}
        onBack={() => router.push('/')}
      />
    </div>
  )
}
