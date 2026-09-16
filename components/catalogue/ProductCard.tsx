'use client'

import Link from 'next/link'
import AddToCartControl from '@/components/cart/AddToCartControl'
import ProductCardMedia from '@/components/catalogue/ProductCardMedia'
import WishlistButton from '@/components/catalogue/WishlistButton'
import type { Product } from '@/lib/catalog'
import { cn } from '@/lib/cn'
import { formatMoneyCompact } from '@/lib/money'
import { productHref } from '@/lib/slug'

/**
 * The product tile. This is the component the whole storefront is judged on,
 * because it is the one a customer sees a hundred times.
 *
 * Layout follows the real site rather than the RN reference: a square image
 * carrying the wishlist heart top-left, the ADD control top-right and the
 * discount badge bottom-left, a centred pack-size strip beneath it, then the
 * name, then price over struck MRP. The control being an overlay rather than a bar at the foot is what
 * keeps the text block uninterrupted and lets the ADD-to-stepper swap happen
 * without moving any layout at all.
 *
 * The control is a SIBLING of the link, not a child. Nesting a button inside
 * an anchor is invalid HTML and makes every tap a coin-flip between adding
 * the item and navigating away from it.
 *
 * DENSITY: at most one badge. A card carrying a discount chip, a popularity
 * chip, a stock warning and a rating is not dense, it is noisy -- and the
 * discount is the one a shopper acts on.
 *
 * The heart is real: My List is a set of ids in localStorage, persisted and
 * re-resolved against the catalogue on read, exactly as the cart is.
 */

type Props = {
  product: Product
  priority?: boolean
  /** Passed through to the media carousel; see ProductCardMedia. */
  railSafe?: boolean
  className?: string
}

/** The pack-size strip under the image, e.g. "144 g" or "Box of 10". */
function packLabel(product: Product) {
  const attr = product.attributes.find((a) => a.key === 'weight' || a.key === 'pack')
  return attr?.value ?? null
}

export default function ProductCard({ product, priority, railSafe, className }: Props) {
  const discounted = product.originalPrice > product.price
  const lowStock = product.stockStatus === 'low' && product.inStock
  const pack = packLabel(product)

  return (
    <article
      /* In a rail the surrounding li carries this role instead -- see
         ProductRail. Tagging both would nest the role, and the inner one
         would never receive data-mm-in. */
      data-mm={railSafe ? undefined : 'card'}
      className={cn(
        'group border-surface-line bg-surface shadow-card relative flex h-full flex-col overflow-hidden rounded-[14px] border',
        className,
      )}
    >
      <div className="relative">
        {/* Dimming the art, not just captioning it, is what makes an
            unavailable tile read as unavailable at a glance down a grid --
            a ribbon alone is easy to scan straight past. */}
        <ProductCardMedia
          product={product}
          priority={priority}
          railSafe={railSafe}
          className={!product.inStock ? 'opacity-55' : undefined}
        />

        {/* Over the media, outside every link it contains. */}
        <div className="pointer-events-none absolute inset-0">
          {discounted ? (
            <span
              data-mm="badge"
              className="bg-save rounded-tag absolute bottom-2 left-2 px-[7px] py-[3px] text-[10px] font-extrabold tracking-[0.3px] text-white tabular-nums shadow-[0_2px_6px_rgb(0_0_0/0.15)]"
            >
              {product.discountPercent}% OFF
            </span>
          ) : product.badge ? (
            <span
              data-mm="badge"
              className="bg-brand-600 rounded-tag absolute bottom-2 left-2 px-[7px] py-[3px] text-[10px] font-extrabold tracking-[0.3px] text-white uppercase shadow-[0_2px_6px_rgb(0_0_0/0.15)]"
            >
              {product.badge}
            </span>
          ) : null}

          {!product.inStock ? (
            <span
              data-mm="oos"
              className="bg-danger/92 absolute inset-x-0 bottom-0 px-1 py-1.5 text-center text-[10.5px] font-extrabold tracking-[0.4px] text-white uppercase"
            >
              Out of stock
            </span>
          ) : null}
        </div>

        {/* Both controls are siblings of the link, not children: a button
            inside an anchor is invalid HTML and makes every tap a coin-flip
            between acting on the product and navigating away from it. */}
        <div className="absolute top-2 left-2">
          <WishlistButton productId={product.id} name={product.name} />
        </div>
        <div className="absolute top-2 right-2">
          <AddToCartControl product={product} overlay />
        </div>
      </div>

      {/*
        Always rendered, never conditional. A band that appears only for
        products carrying a pack attribute made cards in the same row differ
        by ~25px, and a grid of tiles that do not line up is the fastest way
        to make a storefront look unfinished. Products without a pack fall
        back to the brand line, which every product has.
      */}
      <p className="bg-surface-alt text-slate-muted border-surface-line truncate border-y px-2 py-1 text-center text-[11px] font-semibold">
        {pack ?? product.subtitle}
      </p>

      <div className="flex flex-1 flex-col px-3 pt-2.5 pb-3">
        <h3 className="text-ink line-clamp-2 min-h-[34px] text-[13px] leading-[1.25] font-extrabold">
          <Link href={productHref(product)} className="hover:text-brand-600 transition-colors">
            {product.name}
          </Link>
        </h3>

        {/* mt-auto pins the price row to the foot, so cards in a row align on
            price no matter how many lines the title takes. */}
        <div className="mt-auto flex items-baseline gap-1.5 pt-2">
          <span className="tnum text-ink text-[15px] font-extrabold">
            {formatMoneyCompact(product.price, product.currency)}
          </span>
          {discounted ? (
            <span data-mm="old-price" className="tnum text-slate-faint text-xs line-through">
              {formatMoneyCompact(product.originalPrice, product.currency)}
            </span>
          ) : null}
        </div>

        {/* Neutral ink, emphasised by weight. Red is rationed for failures
            the customer must fix and low stock is not one; orange is worse,
            because the grid is the one surface that must stay free of it or
            the cart's single orange button stops being unmissable. */}
        {/* The slot is always present so its absence cannot change the
            card's height; only the text inside it is conditional. */}
        {/* Tagged only when it actually says something: the engine draws a
            pulsing dot before [data-mm="low"], and this slot is always
            rendered to hold the card's height, so tagging it unconditionally
            would leave a bare dot pulsing on every in-stock card. */}
        <p
          data-mm={lowStock ? 'low' : undefined}
          className="text-ink mt-1 min-h-[15px] text-[11px] leading-[15px] font-bold"
        >
          {lowStock ? `Only ${product.stock} left` : ''}
        </p>
      </div>
    </article>
  )
}
