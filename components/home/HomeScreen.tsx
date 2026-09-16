'use client'

import { useCallback, useMemo } from 'react'
import VendorHome from '@/components/home/vendor/Home'
import { addProduct, setProductQty } from '@/lib/cart-store'
import type { Product } from '@/lib/catalog'
import type { HomeBanner, HomeCategory, HomeRail } from '@/lib/home-adapter'
import { toHomeItem } from '@/lib/home-adapter'
import { useCart } from '@/components/cart/CartProvider'
import { useDeliveryMode } from '@/lib/use-prefs'

/**
 * The bridge between the vendored home design and this app's state.
 *
 * Everything the design needs arrives as props; nothing inside
 * components/home/vendor knows about `Product`, the cart store, or the
 * delivery mode. That is what keeps the vendored files diffable against the
 * upstream zip.
 *
 * THE CART IS NOT DUPLICATED. The design renders an id -> qty map and reports
 * changes back; this component derives that map from the real store and
 * sends every change through addProduct / setProductQty, so clampQty stays
 * authoritative. Letting the design keep its own useState would mean a
 * quantity clamped by pack rules or the stock ceiling showing one number on
 * the page and another in the cart.
 *
 * The design's own header, category tabs, cart bar and free-delivery meter
 * were removed: the first three already exist in the root layout and would
 * have rendered twice, and nothing in this build can compute shipping.
 */
export default function HomeScreen({
  banners,
  categories,
  rails,
}: {
  banners: HomeBanner[]
  categories: HomeCategory[]
  rails: HomeRail[]
}) {
  const { cart } = useCart()
  const mode = useDeliveryMode()

  // Quick narrows to what the local store actually stocks. Reading the shared
  // hook rather than the design's own local toggle is what keeps this page
  // and the header's switch from disagreeing.
  const visible = useMemo(
    () =>
      rails
        .map((r) => ({
          ...r,
          products: mode === 'quick' ? r.products.filter((p) => p.quickDelivery) : r.products,
        }))
        .filter((r) => r.products.length > 0),
    [rails, mode],
  )

  // Kept so a tap on ADD can build a real CartLine without a round trip.
  const byId = useMemo(() => {
    const m = new Map<number, Product>()
    for (const r of rails) for (const p of r.products) m.set(p.id, p)
    return m
  }, [rails])

  const sections = useMemo(
    () =>
      visible.flatMap((r) => {
        const rail = {
          key: r.key,
          title: r.title,
          href: r.href,
          subtitle: r.subtitle,
          items: r.products.map(toHomeItem),
        }
        return r.bannerAfter?.length ? [rail, { banner: r.bannerAfter }] : [rail]
      }),
    [visible],
  )

  const qtyById = useMemo(() => {
    const m: Record<number, number> = {}
    for (const line of cart.lines) m[line.productId] = line.qty
    return m
  }, [cart.lines])

  const onQtyChange = useCallback(
    (id: number, qty: number) => {
      const product = byId.get(id)
      if (!product) return
      // A line that does not exist yet has to be created from the product, so
      // the cart carries its price, image and pack rules. After that the id
      // is enough.
      if (!(id in qtyById) && qty > 0) void addProduct(product, qty)
      else void setProductQty(id, qty)
    },
    [byId, qtyById],
  )

  return (
    <VendorHome
      banners={banners}
      categories={categories}
      sections={sections}
      cart={qtyById}
      onQtyChange={onQtyChange}
    />
  )
}
