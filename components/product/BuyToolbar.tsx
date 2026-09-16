'use client'

import AddToCartControl from '@/components/cart/AddToCartControl'
import type { Product } from '@/lib/catalog'
import { formatMoney } from '@/lib/money'

/**
 * The mobile buy bar, pinned to the bottom of the viewport below 1100px.
 *
 * It exists because the desktop buy panel sits beside the gallery, and on a
 * phone that panel scrolls away -- leaving a customer who has read the specs
 * with no way to add the item without scrolling back up.
 *
 * It stacks ABOVE MobileTabBar rather than over it, so the cart and home
 * links stay reachable while buying. The offset is derived from --tabbar-h
 * rather than hardcoded, because the two were already out of step once.
 *
 * The bottom inset uses max() rather than addition. Adding the safe-area
 * inset to a fixed padding double-counts it on devices that report zero,
 * which is how these bars end up floating above a dead grey band.
 */
export default function BuyToolbar({ product }: { product: Product }) {
  return (
    <div
      className="border-surface-line bg-surface shadow-bar fixed inset-x-0 z-30 border-t lg:hidden"
      style={{
        bottom: 'calc(var(--tabbar-h) + max(0.375rem, env(safe-area-inset-bottom)))',
        paddingBottom: '0.75rem',
      }}
    >
      <div className="mx-auto flex max-w-[1360px] items-center justify-between gap-4 px-4 pt-3">
        <div className="min-w-0">
          <p className="tnum text-ink text-lg leading-none font-bold">
            {formatMoney(product.price, product.currency)}
          </p>
          {product.originalPrice > product.price ? (
            <p className="tnum text-slate-faint mt-1 text-xs line-through">
              {formatMoney(product.originalPrice, product.currency)}
            </p>
          ) : null}
        </div>
        <AddToCartControl product={product} />
      </div>
    </div>
  )
}
